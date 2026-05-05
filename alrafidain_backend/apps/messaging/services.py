from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import create_audit_log
from apps.common.choices import MessageSenderRole, MessageType, NotificationType, UserType
from apps.notifications.services import create_notification

from .models import ConsultationMessage, MessageAttachment
from .permissions import can_send_messages


def _sender_role_from_user(user: object) -> str:
    if user.user_type == UserType.PATIENT:
        return MessageSenderRole.PATIENT
    if user.user_type == UserType.DOCTOR:
        return MessageSenderRole.DOCTOR
    raise ValidationError("Only patient and doctor can send messages.")


@transaction.atomic
def create_consultation_message(
    consultation,
    sender,
    body=None,
    attachments=None,
    request=None,
):
    attachments = attachments or []
    body = (body or "").strip()

    if not can_send_messages(sender, consultation):
        raise ValidationError("You are not allowed to send messages for this consultation.")

    if not body and len(attachments) == 0:
        raise ValidationError("At least body or one attachment is required.")

    sender_role = _sender_role_from_user(sender)
    message_type = MessageType.TEXT if body else MessageType.ATTACHMENT

    message = ConsultationMessage(
        consultation=consultation,
        sender=sender,
        sender_role=sender_role,
        message_type=message_type,
        body=body,
    )
    message.full_clean()
    message.save()

    for file_obj in attachments:
        attachment = MessageAttachment(
            message=message,
            file=file_obj,
            original_name=getattr(file_obj, "name", "attachment"),
            uploaded_by=sender,
        )
        attachment.full_clean()
        attachment.save()
        create_audit_log(
            actor=sender,
            action="message_attachment_uploaded",
            target=attachment,
            metadata={
                "consultation_id": str(consultation.id),
                "message_id": str(message.id),
                "sender_id": str(sender.id),
                "sender_role": sender_role,
            },
            request=request,
        )

    create_audit_log(
        actor=sender,
        action="consultation_message_created",
        target=message,
        metadata={
            "consultation_id": str(consultation.id),
            "message_id": str(message.id),
            "sender_id": str(sender.id),
            "sender_role": sender_role,
            "attachment_count": len(attachments),
        },
        request=request,
    )
    if sender_role == MessageSenderRole.PATIENT:
        if consultation.assigned_doctor:
            create_notification(
                recipient=consultation.assigned_doctor,
                notification_type=NotificationType.MESSAGE,
                title="New patient message",
                message="A patient has sent a message in their consultation.",
                data={"consultation_id": str(consultation.id), "message_id": str(message.id)},
            )
    elif sender_role == MessageSenderRole.DOCTOR:
        create_notification(
            recipient=consultation.patient,
            notification_type=NotificationType.MESSAGE,
            title="New doctor message",
            message="Your doctor has sent a message in your consultation.",
            data={"consultation_id": str(consultation.id), "message_id": str(message.id)},
        )

    # Broadcast realtime message event (Phase 14)
    def broadcast_message_event():
        from apps.realtime.services import broadcast_message_created

        try:
            broadcast_message_created(message)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to broadcast message.created event: {e}")

    transaction.on_commit(broadcast_message_event)

    return message


def mark_messages_as_read(consultation, reader):
    if reader.id == consultation.patient_id:
        qs = ConsultationMessage.objects.filter(
            consultation=consultation,
            sender_id=consultation.assigned_doctor_id,
            is_read=False,
        )
    elif reader.id == consultation.assigned_doctor_id:
        qs = ConsultationMessage.objects.filter(
            consultation=consultation,
            sender_id=consultation.patient_id,
            is_read=False,
        )
    else:
        raise ValidationError("You are not allowed to mark messages for this consultation.")

    count = qs.update(is_read=True, read_at=timezone.now())

    # Broadcast read event (Phase 14)
    if count > 0:

        def broadcast_read_event():
            from apps.realtime.services import broadcast_messages_marked_read

            try:
                broadcast_messages_marked_read(consultation, reader, count)
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.error(f"Failed to broadcast messages.read event: {e}")

        transaction.on_commit(broadcast_read_event)

    return count
