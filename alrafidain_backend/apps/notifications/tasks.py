import logging

from celery import shared_task

from apps.common.job_utils import mark_job_completed, mark_job_failed, mark_job_running

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def publish_notification_event_task(self, notification_id, job_id=None):
    from apps.notifications.models import Notification
    from apps.realtime.services import (
        broadcast_notification_created,
        broadcast_unread_notification_count,
    )

    mark_job_running(job_id, celery_task_id=self.request.id)

    notification = (
        Notification.objects.filter(pk=notification_id).select_related("recipient").first()
    )
    if notification is None:
        mark_job_completed(job_id)
        return {"status": "skipped", "reason": "notification_not_found"}

    try:
        broadcast_notification_created(notification)
        broadcast_unread_notification_count(notification.recipient)
        mark_job_completed(job_id)
        return {"status": "ok", "notification_id": str(notification.pk)}
    except Exception as exc:
        logger.exception(
            "Failed notification publish task",
            extra={"notification_id": notification_id},
        )
        mark_job_failed(job_id, exc)
        raise self.retry(exc=exc) from exc
