from collections import defaultdict

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


SPECIALTY_CLINICAL_HINTS = {
    MedicalSpecialty.CARDIOLOGY: (
        "consider cardiac ischemia, rhythm disturbance, or hemodynamic stress indicators"
    ),
    MedicalSpecialty.GASTROENTEROLOGY: (
        "consider acute GI inflammation, infectious gastroenteritis, or upper/lower tract irritation"
    ),
    MedicalSpecialty.PULMONOLOGY: (
        "consider airway inflammation, infection, bronchospasm, or gas-exchange compromise"
    ),
    MedicalSpecialty.NEUROLOGY: (
        "consider primary neurologic causes, intracranial pathology, or secondary neurologic effects"
    ),
    MedicalSpecialty.ENT: (
        "consider upper airway/ear-throat inflammatory or infectious processes"
    ),
    MedicalSpecialty.INTERNAL_MEDICINE: (
        "consider systemic or multi-organ etiologies that need broad internal medicine workup"
    ),
    MedicalSpecialty.GENERAL_MEDICINE: (
        "consider common outpatient etiologies while ruling out evolving serious disease"
    ),
    MedicalSpecialty.EMERGENCY_MEDICINE: (
        "consider time-sensitive causes requiring immediate stabilization and urgent escalation"
    ),
}


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
            models.UniqueConstraint(
                fields=["symptom", "specialty"], name="uniq_symptom_specialty_rule"
            ),
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

    recommended_specialty = models.CharField(
        max_length=50, choices=MedicalSpecialty.choices, blank=True, null=True
    )
    recommended_specialties = models.JSONField(default=list, blank=True)
    selected_specialty = models.CharField(
        max_length=50, choices=MedicalSpecialty.choices, blank=True, null=True
    )
    selected_specialty_other = models.CharField(max_length=150, blank=True)

    ai_predicted_specialty = models.CharField(
        max_length=50, choices=MedicalSpecialty.choices, blank=True, null=True
    )
    ai_predicted_specialty_confidence = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True
    )
    ai_predicted_disease = models.CharField(max_length=255, blank=True)
    ai_predicted_disease_confidence = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True
    )
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
        indexes = [
            models.Index(fields=["patient", "-created_at"]),
            models.Index(fields=["assigned_doctor", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["selected_specialty", "status", "-created_at"]),
        ]

    def get_recommended_specialties(self):
        allowed_specialties = {value for value, _label in MedicalSpecialty.choices}
        ranked_specialties = []

        for specialty in self.recommended_specialties or []:
            if specialty in allowed_specialties and specialty not in ranked_specialties:
                ranked_specialties.append(specialty)

        primary_specialty = self.selected_specialty or self.recommended_specialty
        if primary_specialty in allowed_specialties:
            if primary_specialty in ranked_specialties:
                ranked_specialties.remove(primary_specialty)
            ranked_specialties.insert(0, primary_specialty)

        return ranked_specialties[:3]

    def matches_specialty(self, specialty):
        return specialty in self.get_recommended_specialties()

    def get_ai_case_summary(self):
        consultation_symptoms = [
            consultation_symptom
            for consultation_symptom in self.consultation_symptoms.all()
            if consultation_symptom.symptom_id and consultation_symptom.symptom.is_active
        ]
        symptom_names = [consultation_symptom.symptom.name for consultation_symptom in consultation_symptoms]
        symptom_ids = [consultation_symptom.symptom_id for consultation_symptom in consultation_symptoms]
        category_names = list(
            dict.fromkeys(
                consultation_symptom.symptom.category.name
                for consultation_symptom in consultation_symptoms
                if consultation_symptom.symptom.category_id
            )
        )
        recommended_specialties = self.get_recommended_specialties()

        specialty_scores = defaultdict(int)
        for rule in SymptomSpecialtyRule.objects.filter(symptom_id__in=symptom_ids, is_active=True):
            specialty_scores[rule.specialty] += rule.weight

        ranked_score_items = sorted(
            specialty_scores.items(), key=lambda item: (-item[1], item[0])
        )[:3]
        specialty_labels = {value: label for value, label in MedicalSpecialty.choices}

        parts = []
        if symptom_names:
            parts.append("Reported symptoms: " + ", ".join(symptom_names[:5]) + ".")

        if category_names:
            parts.append(
                "Clinical interpretation: the symptom cluster spans "
                + ", ".join(category_names[:3])
                + " systems, which increases the likelihood of a multi-system differential."
            )

        if self.severity:
            parts.append(f"Severity reported as {self.severity}.")

        if self.duration:
            parts.append(f"Duration reported as {self.duration}.")

        if self.has_emergency_warning:
            parts.append("Emergency warning is present, so the case should be reviewed urgently.")

        if ranked_score_items:
            weighted_ranking_text = ", ".join(
                f"{specialty_labels.get(specialty, specialty)} (signal {score})"
                for specialty, score in ranked_score_items
            )
            parts.append(
                "Weighted symptom-to-specialty signal: " + weighted_ranking_text + "."
            )

        if recommended_specialties:
            parts.append(
                "AI routing focus: "
                + ", ".join(
                    specialty_labels.get(specialty, specialty)
                    for specialty in recommended_specialties[:3]
                )
                + "."
            )

        clinical_hints = [
            SPECIALTY_CLINICAL_HINTS[specialty]
            for specialty in recommended_specialties
            if specialty in SPECIALTY_CLINICAL_HINTS
        ]
        if clinical_hints:
            parts.append(
                "Focused diagnostic directions: " + "; ".join(clinical_hints[:2]) + "."
            )

        if not parts:
            return "No AI summary is available for this consultation yet."

        parts.append(
            "This summary is generated from the consultation symptoms and routing data, "
            "and does not replace the doctor's clinical judgment."
        )
        return " ".join(parts)

    def clean(self):
        if self.patient and self.patient.user_type != UserType.PATIENT:
            raise ValidationError({"patient": "Consultation patient must have patient user type."})

        if self.selected_specialty == MedicalSpecialty.OTHER and not self.selected_specialty_other:
            raise ValidationError(
                {
                    "selected_specialty_other": (
                        "This field is required when selected specialty is Other."
                    )
                }
            )

        if self.selected_specialty != MedicalSpecialty.OTHER:
            self.selected_specialty_other = ""

        if self.assigned_doctor:
            if self.assigned_doctor.user_type != UserType.DOCTOR:
                raise ValidationError({"assigned_doctor": "Assigned user must be a doctor."})

            try:
                doctor_profile = self.assigned_doctor.doctor_profile
            except Exception:
                raise ValidationError(
                    {"assigned_doctor": "Assigned doctor profile not found."}
                ) from None

            if doctor_profile.verification_status != VerificationStatus.APPROVED:
                raise ValidationError({"assigned_doctor": "Assigned doctor must be approved."})

            target_specialties = self.get_recommended_specialties()
            if doctor_profile.specialty == MedicalSpecialty.OTHER:
                if MedicalSpecialty.OTHER not in target_specialties:
                    raise ValidationError(
                        {
                            "assigned_doctor": (
                                "Doctor with Other specialty can only handle Other consultations."
                            )
                        }
                    )
            elif target_specialties and doctor_profile.specialty not in target_specialties:
                raise ValidationError(
                    {"assigned_doctor": "Doctor specialty does not match consultation specialty."}
                )

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
            models.UniqueConstraint(
                fields=["consultation", "symptom"], name="uniq_consultation_symptom"
            ),
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
        if (
            self.uploaded_by_id
            and self.consultation_id
            and self.uploaded_by_id != self.consultation.patient_id
        ):
            raise ValidationError(
                {"uploaded_by": "Only consultation patient can upload attachments in this phase."}
            )

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

    class Meta:
        indexes = [
            models.Index(fields=["consultation", "-created_at"]),
            models.Index(fields=["doctor", "-created_at"]),
        ]

    def clean(self):
        if (
            self.consultation_id
            and self.doctor_id
            and self.consultation.assigned_doctor_id != self.doctor_id
        ):
            raise ValidationError({"doctor": "Only assigned doctor can respond."})

        if self.consultation.status not in [
            ConsultationStatus.ACCEPTED,
            ConsultationStatus.DOCTOR_RESPONDED,
        ]:
            raise ValidationError(
                {"consultation": "Consultation must be accepted before adding a response."}
            )

    def __str__(self):
        return f"Response {self.id} for consultation {self.consultation_id}"
