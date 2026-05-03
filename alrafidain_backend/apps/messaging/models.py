from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.choices import ConsultationStatus, MessageSenderRole, MessageType, UserType
from apps.common.models import BaseModel
from apps.common.upload_paths import message_attachment_upload_path
from apps.consultations.models import Consultation


class ConsultationMessage(BaseModel):
	consultation = models.ForeignKey(
		Consultation,
		on_delete=models.CASCADE,
		related_name="messages",
	)
	sender = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="sent_consultation_messages",
	)
	sender_role = models.CharField(max_length=20, choices=MessageSenderRole.choices)
	message_type = models.CharField(
		max_length=20,
		choices=MessageType.choices,
		default=MessageType.TEXT,
	)
	body = models.TextField(blank=True)
	is_read = models.BooleanField(default=False)
	read_at = models.DateTimeField(blank=True, null=True)

	class Meta:
		ordering = ["created_at"]

	def clean(self):
		allowed_send_statuses = [ConsultationStatus.ACCEPTED, ConsultationStatus.DOCTOR_RESPONDED]
		if self.consultation.status not in allowed_send_statuses:
			raise ValidationError({"consultation": "Messages are only allowed for accepted or doctor_responded consultations."})

		if self.sender_id not in [self.consultation.patient_id, self.consultation.assigned_doctor_id]:
			raise ValidationError({"sender": "Sender must be consultation patient or assigned doctor."})

		if self.sender.user_type == UserType.PATIENT and self.sender_role != MessageSenderRole.PATIENT:
			raise ValidationError({"sender_role": "sender_role must match sender user type."})

		if self.sender.user_type == UserType.DOCTOR and self.sender_role != MessageSenderRole.DOCTOR:
			raise ValidationError({"sender_role": "sender_role must match sender user type."})

		if self.sender.user_type not in [UserType.PATIENT, UserType.DOCTOR]:
			raise ValidationError({"sender": "Only patient and doctor can send messages in this phase."})

	def __str__(self):
		return f"Message {self.id} in consultation {self.consultation_id}"


class MessageAttachment(BaseModel):
	message = models.ForeignKey(
		ConsultationMessage,
		on_delete=models.CASCADE,
		related_name="attachments",
	)
	file = models.FileField(upload_to=message_attachment_upload_path)
	original_name = models.CharField(max_length=255)
	uploaded_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="message_attachments",
	)

	def clean(self):
		if self.uploaded_by_id and self.message_id and self.uploaded_by_id != self.message.sender_id:
			raise ValidationError({"uploaded_by": "uploaded_by must match message sender."})

	def __str__(self):
		return f"Attachment {self.id} for message {self.message_id}"
