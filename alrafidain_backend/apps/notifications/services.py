from django.db import transaction

from apps.common.choices import NotificationPriority

from .models import Notification


def create_notification(
    recipient,
    notification_type,
    title,
    message,
    priority=NotificationPriority.NORMAL,
    data=None,
):
    if recipient is None:
        raise ValueError("Notification recipient is required.")

    notification = Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        priority=priority,
        data=data or {},
    )

    # Broadcast realtime events (Phase 14)
    # Use transaction.on_commit to ensure DB commit before broadcast
    def broadcast_events():
        from apps.realtime.services import (
            broadcast_notification_created,
            broadcast_unread_notification_count,
        )

        try:
            broadcast_notification_created(notification)
            broadcast_unread_notification_count(recipient)
        except Exception as e:
            # Log but don't break notification creation
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to broadcast notification event: {e}")

    transaction.on_commit(broadcast_events)

    return notification


def notify_many(
    recipients, notification_type, title, message, priority=NotificationPriority.NORMAL, data=None
):
    notifications = []
    for recipient in recipients:
        if recipient is not None:
            notifications.append(
                create_notification(
                    recipient=recipient,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    priority=priority,
                    data=data or {},
                )
            )
    return notifications
