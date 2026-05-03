from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.common.choices import (
	ConsultationDuration,
	ConsultationStatus,
	DoctorRecommendationType,
	MedicalSpecialty,
	SeverityLevel,
	UserType,
	VerificationStatus,
)
from apps.common.models import BaseModel
from apps.common.upload_paths import consultation_attachment_upload_path


class SymptomCategory(BaseModel):
	name = models.CharField(max_length=120, unique=True)
	description = models.TextField(blank=True)
	display_order = models.PositiveIntegerField(default=0)
	is_active = models.BooleanField(default=True)

	class Meta:
		ordering = ["display_order", "name"]
		verbose_name = "Symptom Category"
		verbose_name_plural = "Symptom Categories"

	def __str__(self):
		return self.name


class Symptom(BaseModel):
	category = models.ForeignKey(
		SymptomCategory,
		on_delete=models.CASCADE,
		related_name="symptoms",
	)
	name = models.CharField(max_length=120)
	description = models.TextField(blank=True)
	is_red_flag = models.BooleanField(default=False)
	is_active = models.BooleanField(default=True)
	display_order = models.PositiveIntegerField(default=0)

	class Meta:
		ordering = ["category__display_order", "display_order", "name"]
		constraints = [
			models.UniqueConstraint(fields=["category", "name"], name="uniq_symptom_category_name"),
		]

	def __str__(self):
		return f"{self.category.name} - {self.name}"


class SymptomSpecialtyRule(BaseModel):
	symptom = models.ForeignKey(
		Symptom,
		on_delete=models.CASCADE,
		related_name="specialty_rules",
	)
	specialty = models.CharField(max_length=50, choices=MedicalSpecialty.choices)
	weight = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
	is_active = models.BooleanField(default=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["symptom", "specialty"], name="uniq_symptom_specialty_rule"),
		]

	def __str__(self):
		return f"{self.symptom.name} -> {self.specialty} ({self.weight})"


class Consultation(BaseModel):
	patient = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="consultations",
	)
	assigned_doctor = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="assigned_consultations",
	)
	status = models.CharField(
		max_length=30,
		choices=ConsultationStatus.choices,
		default=ConsultationStatus.SUBMITTED,
	)

	recommended_specialty = models.CharField(max_length=50, choices=MedicalSpecialty.choices, blank=True, null=True)
	selected_specialty = models.CharField(max_length=50, choices=MedicalSpecialty.choices, blank=True, null=True)
	selected_specialty_other = models.CharField(max_length=150, blank=True)

	ai_predicted_specialty = models.CharField(max_length=50, choices=MedicalSpecialty.choices, blank=True, null=True)
	ai_predicted_specialty_confidence = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
	ai_predicted_disease = models.CharField(max_length=255, blank=True)
	ai_predicted_disease_confidence = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
	ai_prediction_notes = models.TextField(blank=True)

	duration = models.CharField(max_length=40, choices=ConsultationDuration.choices)
	severity = models.CharField(max_length=20, choices=SeverityLevel.choices)

	has_fever = models.BooleanField(default=False)
	has_pain = models.BooleanField(default=False)
	has_breathing_difficulty = models.BooleanField(default=False)
	has_emergency_warning = models.BooleanField(default=False)
	previous_visit_for_same_issue = models.BooleanField(default=False)

	current_medications_related = models.TextField(blank=True)
	additional_notes = models.TextField(blank=True)

	accepted_at = models.DateTimeField(blank=True, null=True)
	closed_at = models.DateTimeField(blank=True, null=True)

	class Meta:
		ordering = ["-created_at"]

	def clean(self):
		if self.patient and self.patient.user_type != UserType.PATIENT:
			raise ValidationError({"patient": "Consultation patient must have patient user type."})

		if self.selected_specialty == MedicalSpecialty.OTHER and not self.selected_specialty_other:
			raise ValidationError({"selected_specialty_other": "This field is required when selected specialty is Other."})

		if self.selected_specialty != MedicalSpecialty.OTHER:
			self.selected_specialty_other = ""

		if self.assigned_doctor:
			if self.assigned_doctor.user_type != UserType.DOCTOR:
				raise ValidationError({"assigned_doctor": "Assigned user must be a doctor."})

			try:
				doctor_profile = self.assigned_doctor.doctor_profile
			except Exception:
				raise ValidationError({"assigned_doctor": "Assigned doctor profile not found."})

			if doctor_profile.verification_status != VerificationStatus.APPROVED:
				raise ValidationError({"assigned_doctor": "Assigned doctor must be approved."})

			target_specialty = self.selected_specialty or self.recommended_specialty
			if doctor_profile.specialty == MedicalSpecialty.OTHER:
				if target_specialty != MedicalSpecialty.OTHER:
					raise ValidationError({"assigned_doctor": "Doctor with Other specialty can only handle Other consultations."})
			elif target_specialty and doctor_profile.specialty != target_specialty:
				raise ValidationError({"assigned_doctor": "Doctor specialty does not match consultation specialty."})

	def __str__(self):
		return f"Consultation {self.id} ({self.status})"


class ConsultationSymptom(BaseModel):
	consultation = models.ForeignKey(
		Consultation,
		on_delete=models.CASCADE,
		related_name="consultation_symptoms",
	)
	symptom = models.ForeignKey(
		Symptom,
		on_delete=models.CASCADE,
		related_name="consultation_links",
	)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["consultation", "symptom"], name="uniq_consultation_symptom"),
		]

	def __str__(self):
		return f"{self.consultation_id} - {self.symptom.name}"


class ConsultationAttachment(BaseModel):
	consultation = models.ForeignKey(
		Consultation,
		on_delete=models.CASCADE,
		related_name="attachments",
	)
	file = models.FileField(upload_to=consultation_attachment_upload_path)
	original_name = models.CharField(max_length=255)
	uploaded_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="consultation_attachments",
	)

	def clean(self):
		if self.uploaded_by_id and self.consultation_id and self.uploaded_by_id != self.consultation.patient_id:
			raise ValidationError({"uploaded_by": "Only consultation patient can upload attachments in this phase."})

	def __str__(self):
		return f"Attachment {self.id} for consultation {self.consultation_id}"


class ConsultationResponse(BaseModel):
	consultation = models.ForeignKey(
		Consultation,
		on_delete=models.CASCADE,
		related_name="responses",
	)
	doctor = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="consultation_responses",
	)
	response_text = models.TextField()
	recommendation_type = models.CharField(max_length=40, choices=DoctorRecommendationType.choices)

	def clean(self):
		if self.consultation_id and self.doctor_id and self.consultation.assigned_doctor_id != self.doctor_id:
			raise ValidationError({"doctor": "Only assigned doctor can respond."})

		if self.consultation.status not in [ConsultationStatus.ACCEPTED, ConsultationStatus.DOCTOR_RESPONDED]:
			raise ValidationError({"consultation": "Consultation must be accepted before adding a response."})

	def __str__(self):
		return f"Response {self.id} for consultation {self.consultation_id}"
