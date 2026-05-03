from apps.common.choices import NotificationPriority, NotificationType

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
    return Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        priority=priority,
        data=data or {},
    )


def notify_many(recipients, notification_type, title, message, priority=NotificationPriority.NORMAL, data=None):
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
