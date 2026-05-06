from celery import shared_task

from .job_utils import (
    mark_job_completed as _mark_job_completed,
)
from .job_utils import (
    mark_job_failed as _mark_job_failed,
)
from .job_utils import (
    mark_job_running as _mark_job_running,
)


@shared_task(bind=True)
def debug_task(self, *args, **kwargs):
    return {
        "task_id": self.request.id,
        "args": args,
        "kwargs": kwargs,
    }


@shared_task
def mark_job_running(job_id, celery_task_id=None):
    _mark_job_running(job_id, celery_task_id=celery_task_id)


@shared_task
def mark_job_completed(job_id):
    _mark_job_completed(job_id)


@shared_task
def mark_job_failed(job_id, error_message):
    _mark_job_failed(job_id, error_message)
