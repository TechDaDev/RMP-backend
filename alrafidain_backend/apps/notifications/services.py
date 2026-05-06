from django.db import transaction

from apps.common.choices import NotificationPriority
from apps.common.job_utils import create_background_job

from .models import Notification
from .tasks import publish_notification_event_task


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

    job = create_background_job(
        task_name="notifications.publish_notification_event",
        created_by=recipient,
        metadata={"notification_id": str(notification.id)},
    )

    # Queue side-effect fanout only after commit.
    transaction.on_commit(
        lambda: publish_notification_event_task.delay(
            notification_id=str(notification.id),
            job_id=str(job.id),
        )
    )

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
