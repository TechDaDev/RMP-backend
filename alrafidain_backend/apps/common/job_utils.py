from __future__ import annotations

from django.utils import timezone

from .models import BackgroundJob, BackgroundJobStatus


def create_background_job(*, task_name: str, created_by=None, metadata: dict | None = None):
    return BackgroundJob.objects.create(
        task_name=task_name,
        created_by=created_by,
        metadata=metadata or {},
    )


def _resolve_job(job_id):
    if not job_id:
        return None
    return BackgroundJob.objects.filter(pk=job_id).first()


def mark_job_running(job_id, celery_task_id: str | None = None):
    job = _resolve_job(job_id)
    if not job:
        return None

    update_fields = ["status", "started_at", "updated_at"]
    job.status = BackgroundJobStatus.RUNNING
    if job.started_at is None:
        job.started_at = timezone.now()
    if celery_task_id:
        job.celery_task_id = celery_task_id
        update_fields.append("celery_task_id")
    job.save(update_fields=update_fields)
    return job


def mark_job_completed(job_id):
    job = _resolve_job(job_id)
    if not job:
        return None

    now = timezone.now()
    if job.started_at is None:
        job.started_at = now
    job.status = BackgroundJobStatus.COMPLETED
    job.finished_at = now
    job.save(update_fields=["status", "started_at", "finished_at", "updated_at"])
    return job


def mark_job_failed(job_id, error):
    job = _resolve_job(job_id)
    if not job:
        return None

    now = timezone.now()
    if job.started_at is None:
        job.started_at = now
    job.status = BackgroundJobStatus.FAILED
    job.finished_at = now
    job.error_message = str(error)[:2000]
    job.save(update_fields=["status", "started_at", "finished_at", "error_message", "updated_at"])
    return job
