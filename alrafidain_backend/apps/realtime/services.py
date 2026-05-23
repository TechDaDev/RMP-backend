"""
Broadcast services for realtime WebSocket events.

Provides sync-safe helpers for sending events to WebSocket groups.
All functions use async_to_sync() to be callable from sync contexts like views.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def get_channel_layer_safe():
    """Get channel layer, return None if unavailable."""
    try:
        return get_channel_layer()
    except Exception as e:
        logger.error(f"Failed to get channel layer: {e}")
        return None


def send_to_group_safe(group_name, event_data):
    """
    Send an event to a channel group synchronously.

    Args:
        group_name: Channel group name
        event_data: Dict containing event type and payload
    """
    channel_layer = get_channel_layer_safe()
    if not channel_layer:
        logger.warning(
            "Channel layer unavailable, skipping realtime broadcast",
            extra={"group_name": group_name, "event_type": event_data.get("type")},
        )
        return

    try:
        logger.info(
            "Sending realtime event to group",
            extra={"group_name": group_name, "event_type": event_data.get("type")},
        )
        async_to_sync(channel_layer.group_send)(group_name, event_data)
    except Exception:
        logger.exception(
            "Failed to send realtime event to group",
            extra={"group_name": group_name, "event_type": event_data.get("type")},
        )


# ── Group Name Helpers ─────────────────────────────────────────────────────


def user_group_name(user_id):
    """Get channel group name for user notifications."""
    return f"user_{user_id}"


def consultation_group_name(consultation_id):
    """Get channel group name for consultation messages."""
    return f"consultation_{consultation_id}"


# ── Broadcast Helpers ──────────────────────────────────────────────────────


def broadcast_notification_created(notification):
    """
    Broadcast notification.created event to user socket.

    Payload includes safe notification data without sensitive details.

    Args:
        notification: Notification instance
    """
    from apps.notifications.serializers import NotificationSerializer

    try:
        serializer = NotificationSerializer(notification)
        payload = serializer.data

        event_data = {
            "type": "notification.created",
            "notification": payload,
        }

        send_to_group_safe(
            user_group_name(notification.recipient_id),
            event_data,
        )
    except Exception as e:
        logger.error(f"Failed to broadcast notification.created: {e}")


def broadcast_unread_notification_count(user):
    """
    Broadcast notification.unread_count event to user socket.

    Args:
        user: User instance
    """
    from apps.notifications.models import Notification

    try:
        unread_count = Notification.objects.filter(
            recipient=user,
            is_read=False,
        ).count()

        event_data = {
            "type": "notification.unread_count",
            "unread_count": unread_count,
        }

        send_to_group_safe(user_group_name(user.id), event_data)
    except Exception as e:
        logger.error(f"Failed to broadcast notification.unread_count: {e}")


def broadcast_message_created(message):
    """
    Broadcast chat.message.created event to consultation socket.

    Payload includes safe message data without sensitive details.

    Args:
        message: Message instance
    """
    from apps.messaging.serializers import ConsultationRealtimeMessageSerializer

    try:
        serializer = ConsultationRealtimeMessageSerializer(message)
        payload = serializer.data

        event_data = {
            "type": "chat.message.created",
            "consultation_id": str(message.consultation_id),
            "message": payload,
        }

        logger.info(
            "Broadcasting chat.message.created",
            extra={
                "consultation_id": str(message.consultation_id),
                "message_id": str(message.id),
            },
        )

        send_to_group_safe(
            consultation_group_name(message.consultation_id),
            event_data,
        )
    except Exception:
        logger.exception(
            "Failed to broadcast chat.message.created",
            extra={
                "consultation_id": str(message.consultation_id),
                "message_id": str(message.id),
            },
        )


def broadcast_doctor_ai_message_created(message):
    """
    Broadcast doctor_ai.message.created event to the owning doctor's user socket.

    Args:
        message: DoctorAIAssistantMessage instance
    """
    try:
        event_data = {
            "type": "doctor_ai.message.created",
            "consultation_id": str(message.consultation_id),
            "message_id": str(message.id),
            "doctor_id": str(message.doctor_id),
            "trigger_type": message.trigger_type,
            "status": message.status,
            "safety_level": message.safety_level,
            "title": message.title,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

        send_to_group_safe(user_group_name(message.doctor_id), event_data)
    except Exception:
        logger.exception(
            "Failed to broadcast doctor_ai.message.created",
            extra={
                "consultation_id": str(message.consultation_id),
                "message_id": str(message.id),
                "doctor_id": str(message.doctor_id),
            },
        )


def broadcast_messages_marked_read(consultation, reader, count):
    """
    Broadcast chat.messages.read event to consultation socket.

    Args:
        consultation: Consultation instance
        reader: User who marked messages as read
        count: Number of messages marked as read
    """
    try:
        event_data = {
            "type": "chat.messages.read",
            "consultation_id": str(consultation.id),
            "reader_id": str(reader.id),
            "count": count,
        }

        logger.info(
            "Broadcasting chat.messages.read",
            extra={
                "consultation_id": str(consultation.id),
                "reader_id": str(reader.id),
                "count": count,
            },
        )

        send_to_group_safe(
            consultation_group_name(consultation.id),
            event_data,
        )
    except Exception:
        logger.exception(
            "Failed to broadcast chat.messages.read",
            extra={
                "consultation_id": str(consultation.id),
                "reader_id": str(reader.id),
                "count": count,
            },
        )


def broadcast_consultation_updated(consultation):
    """
    Broadcast consultation.updated event to user and consultation sockets.

    Args:
        consultation: Consultation instance
    """
    try:
        from apps.consultations.serializers import ConsultationDetailSerializer

        serializer = ConsultationDetailSerializer(consultation)
        payload = serializer.data

        # Safe subset for event - only key status fields
        safe_payload = {
            "id": payload["id"],
            "status": payload["status"],
            "created_at": payload["created_at"],
            "accepted_at": payload.get("accepted_at"),
            "closed_at": payload.get("closed_at"),
        }

        event_data = {
            "type": "consultation.updated",
            "consultation": safe_payload,
        }

        # Send to consultation group
        send_to_group_safe(consultation_group_name(consultation.id), event_data)

        # Send to patient
        send_to_group_safe(user_group_name(consultation.patient_id), event_data)

        # Send to assigned doctor if any
        if consultation.assigned_doctor_id:
            send_to_group_safe(
                user_group_name(consultation.assigned_doctor_id),
                event_data,
            )
    except Exception as e:
        logger.error(f"Failed to broadcast consultation.updated: {e}")


def broadcast_prescription_updated(prescription):
    """
    Broadcast prescription.updated event to patient socket.

    Only includes patient-safe data (no medication details).

    Args:
        prescription: Prescription instance
    """
    try:
        # Safe payload - patient-safe only
        safe_payload = {
            "id": str(prescription.id),
            "status": prescription.status,
            "expires_at": prescription.expires_at.isoformat() if prescription.expires_at else None,
            "fully_dispensed_at": prescription.fully_dispensed_at.isoformat()
            if prescription.fully_dispensed_at
            else None,
        }

        event_data = {
            "type": "prescription.updated",
            "prescription": safe_payload,
        }

        send_to_group_safe(
            user_group_name(prescription.patient_id),
            event_data,
        )
    except Exception as e:
        logger.error(f"Failed to broadcast prescription.updated: {e}")


def broadcast_lab_order_updated(lab_order):
    """
    Broadcast lab_order.updated event to patient socket.

    Only includes patient-safe data (no test details).

    Args:
        lab_order: LabOrder instance
    """
    try:
        # Safe payload - patient-safe only
        safe_payload = {
            "id": str(lab_order.id),
            "status": lab_order.status,
            "test_count": lab_order.items.count(),
            "expires_at": lab_order.expires_at.isoformat() if lab_order.expires_at else None,
            "fully_completed_at": lab_order.fully_completed_at.isoformat()
            if lab_order.fully_completed_at
            else None,
        }

        event_data = {
            "type": "lab_order.updated",
            "lab_order": safe_payload,
        }

        send_to_group_safe(
            user_group_name(lab_order.patient_id),
            event_data,
        )
    except Exception as e:
        logger.error(f"Failed to broadcast lab_order.updated: {e}")


def broadcast_lab_result_released(lab_result):
    """
    Broadcast lab_result.released event to patient socket.

    Only includes patient-safe data (no doctor/lab notes).

    Args:
        lab_result: LabResult instance
    """
    try:
        # Safe payload - patient-safe only, no notes
        safe_payload = {
            "id": str(lab_result.id),
            "lab_order": str(lab_result.lab_order_id),
            "status": lab_result.status,
            "released_at": lab_result.released_at.isoformat() if lab_result.released_at else None,
        }

        event_data = {
            "type": "lab_result.released",
            "lab_result": safe_payload,
        }

        send_to_group_safe(
            user_group_name(lab_result.lab_order.patient_id),
            event_data,
        )
    except Exception as e:
        logger.error(f"Failed to broadcast lab_result.released: {e}")
