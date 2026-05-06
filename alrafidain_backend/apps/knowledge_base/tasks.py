import logging

from celery import shared_task

from apps.common.job_utils import mark_job_completed, mark_job_failed, mark_job_running

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def process_knowledge_document_task(self, document_id, job_id=None, actor_id=None):
    from apps.accounts.models import User
    from apps.audit.services import create_audit_log
    from apps.common.choices import KnowledgeProcessingStatus, KnowledgeSecurityStatus
    from apps.common.file_scanner import scan_uploaded_file
    from apps.knowledge_base.models import KnowledgeDocument
    from apps.knowledge_base.services import process_knowledge_document

    mark_job_running(job_id, celery_task_id=self.request.id)

    document = KnowledgeDocument.objects.filter(pk=document_id).first()
    if document is None:
        mark_job_completed(job_id)
        return {"status": "skipped", "reason": "document_not_found"}

    # --- Malware scan boundary ---
    try:
        scan_result = scan_uploaded_file(document.file.path)
    except Exception:
        scan_result = None

    if scan_result is not None and scan_result.status == "scan_failed":
        document.security_status = KnowledgeSecurityStatus.SCAN_FAILED
        document.processing_status = KnowledgeProcessingStatus.FAILED
        document.save(update_fields=["security_status", "processing_status"])
        mark_job_failed(job_id, RuntimeError("Malware scan failed — document blocked"))
        return {"status": "blocked", "reason": "scan_failed", "document_id": str(document.pk)}

    if scan_result is not None:
        status_map = {
            "scan_clean": KnowledgeSecurityStatus.SCAN_CLEAN,
            "scan_skipped": KnowledgeSecurityStatus.SCAN_SKIPPED,
        }
        document.security_status = status_map.get(
            scan_result.status, KnowledgeSecurityStatus.SCAN_SKIPPED
        )
        document.save(update_fields=["security_status"])

    try:
        process_knowledge_document(document)
        actor = User.objects.filter(pk=actor_id).first() if actor_id else None
        create_audit_log(
            actor=actor,
            action="knowledge_document_processed",
            target=document,
            metadata={
                "document_id": str(document.pk),
                "document_type": document.document_type,
                "language": document.language,
                "specialty": document.specialty,
                "approval_status": document.approval_status,
                "processing_status": document.processing_status,
                "security_status": document.security_status,
                "chunk_count": document.chunks.filter(is_active=True).count(),
            },
        )
        mark_job_completed(job_id)
        return {"status": "ok", "document_id": str(document.pk)}
    except Exception as exc:
        logger.exception(
            "Knowledge document processing task failed",
            extra={"document_id": document_id},
        )
        mark_job_failed(job_id, exc)
        raise self.retry(exc=exc) from exc


@shared_task(bind=True, max_retries=2)
def embed_knowledge_document_task(self, document_id, force=False, job_id=None):
    from apps.knowledge_base.models import KnowledgeDocument
    from apps.knowledge_base.services import embed_document_chunks

    mark_job_running(job_id, celery_task_id=self.request.id)

    document = KnowledgeDocument.objects.filter(pk=document_id).first()
    if document is None:
        mark_job_completed(job_id)
        return {"status": "skipped", "reason": "document_not_found"}

    try:
        result = embed_document_chunks(document, force=force)
        mark_job_completed(job_id)
        return {"status": "ok", "document_id": str(document.pk), **result}
    except Exception as exc:
        mark_job_failed(job_id, exc)
        raise self.retry(exc=exc) from exc
