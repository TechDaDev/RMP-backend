from celery import shared_task

from apps.common.job_utils import mark_job_completed, mark_job_failed, mark_job_running


@shared_task(bind=True, max_retries=2)
def generate_rag_export_task(
    self,
    *,
    export_format="json",
    include_text=False,
    anonymize=True,
    job_id=None,
):
    from apps.rag.exporters import export_rag_evaluation_dataset

    mark_job_running(job_id, celery_task_id=self.request.id)
    try:
        content = export_rag_evaluation_dataset(
            format=export_format,
            include_text=include_text,
            anonymize=anonymize,
        )
        mark_job_completed(job_id)
        record_count = len(content) if export_format == "json" else max(0, content.count("\n") - 1)
        return {
            "format": export_format,
            "record_count": record_count,
            "data": content,
        }
    except Exception as exc:
        mark_job_failed(job_id, exc)
        raise self.retry(exc=exc) from exc
