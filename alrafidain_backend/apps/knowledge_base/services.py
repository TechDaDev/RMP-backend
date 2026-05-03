from __future__ import annotations

import os
from typing import TYPE_CHECKING

from django.utils import timezone

from apps.audit.services import create_audit_log
from apps.common.choices import KnowledgeApprovalStatus, KnowledgeProcessingStatus

if TYPE_CHECKING:
    from .models import KnowledgeDocument


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _log(document, action: str, status: str, message: str = "", metadata: dict | None = None):
    from .models import KnowledgeProcessingLog

    KnowledgeProcessingLog.objects.create(
        document=document,
        action=action,
        status=status,
        message=message,
        metadata=metadata or {},
    )


def _require_staff(user, label: str = "action"):
    if not (user and (user.is_staff or user.is_superuser)):
        raise PermissionError(f"Only staff or superuser may perform: {label}")


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_document(document: "KnowledgeDocument"):
    """
    Extract text from the uploaded file (PDF / DOCX / TXT).
    Creates a KnowledgeDocumentText row and updates processing_status.
    """
    from .models import KnowledgeDocumentText

    try:
        file_path = document.file.path
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            text, page_count = _extract_pdf(file_path)
            mime = "application/pdf"
        elif ext == ".docx":
            text, page_count = _extract_docx(file_path)
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif ext == ".txt":
            text, page_count = _extract_txt(file_path)
            mime = "text/plain"
        else:
            raise ValueError(f"Unsupported file extension: {ext}")

        doc_text, _ = KnowledgeDocumentText.objects.update_or_create(
            document=document,
            defaults={
                "text": text,
                "page_count": page_count,
                "extraction_metadata": {"extension": ext, "mime_type": mime},
            },
        )

        document.processing_status = KnowledgeProcessingStatus.EXTRACTED
        document.save(update_fields=["processing_status", "updated_at"])
        _log(document, "extract_text", "success", f"Extracted {len(text)} characters.")
        return doc_text

    except Exception as exc:
        document.processing_status = KnowledgeProcessingStatus.FAILED
        document.save(update_fields=["processing_status", "updated_at"])
        _log(document, "extract_text", "failed", str(exc))
        raise


def _extract_pdf(path: str) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages), len(pages)


def _extract_docx(path: str) -> tuple[str, int]:
    from docx import Document

    doc = Document(path)
    paragraphs = [p.text for p in doc.paragraphs]
    return "\n\n".join(paragraphs), None  # page count not directly available


def _extract_txt(path: str) -> tuple[str, None]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read(), None


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_knowledge_document(
    document: "KnowledgeDocument",
    chunk_size: int = 1200,
    overlap: int = 200,
):
    """
    Split extracted text into overlapping character-based chunks.
    Deactivates old chunks before creating new ones.
    """
    from .models import KnowledgeChunk

    try:
        doc_text = document.extracted_text
    except Exception:
        raise ValueError("Document has no extracted text. Run extraction first.")

    text = doc_text.text
    if not text.strip():
        raise ValueError("Extracted text is empty; cannot chunk.")

    # Delete existing chunks to avoid unique_together (document, chunk_index) conflicts on re-chunk
    document.chunks.all().delete()

    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]
        token_est = len(chunk_text) // 4  # rough estimate: 4 chars ≈ 1 token

        chunks.append(
            KnowledgeChunk(
                document=document,
                chunk_index=idx,
                text=chunk_text,
                token_estimate=token_est,
                is_active=True,
                metadata={"char_start": start, "char_end": end},
            )
        )
        start += chunk_size - overlap
        idx += 1

    KnowledgeChunk.objects.bulk_create(chunks)

    document.processing_status = KnowledgeProcessingStatus.CHUNKED
    document.save(update_fields=["processing_status", "updated_at"])
    _log(
        document,
        "chunk_text",
        "success",
        f"Created {len(chunks)} chunks (size={chunk_size}, overlap={overlap}).",
        {"chunk_count": len(chunks)},
    )
    return chunks


# ---------------------------------------------------------------------------
# Process (extract + chunk)
# ---------------------------------------------------------------------------

def process_knowledge_document(document: "KnowledgeDocument"):
    """Extract text and chunk in one call."""
    extract_text_from_document(document)
    chunk_knowledge_document(document)
    _log(document, "process", "success", "Processing complete.")
    return document


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------

def approve_knowledge_document(document: "KnowledgeDocument", approved_by):
    _require_staff(approved_by, "approve")

    if not document.chunks.filter(is_active=True).exists():
        raise ValueError("Document must have active chunks before approval.")

    document.approval_status = KnowledgeApprovalStatus.APPROVED
    document.approved_by = approved_by
    document.approved_at = timezone.now()
    document.save(update_fields=["approval_status", "approved_by", "approved_at", "updated_at"])

    _log(document, "approve", "success", f"Approved by {approved_by.email}.")
    create_audit_log(
        actor=approved_by,
        action="knowledge_document_approved",
        target=document,
        metadata={
            "document_id": str(document.pk),
            "document_type": document.document_type,
            "language": document.language,
            "specialty": document.specialty,
            "approval_status": document.approval_status,
            "processing_status": document.processing_status,
            "chunk_count": document.chunks.filter(is_active=True).count(),
        },
    )
    return document


def reject_knowledge_document(document: "KnowledgeDocument", rejected_by, reason: str):
    _require_staff(rejected_by, "reject")

    document.approval_status = KnowledgeApprovalStatus.REJECTED
    document.rejected_reason = reason
    document.save(update_fields=["approval_status", "rejected_reason", "updated_at"])

    _log(document, "reject", "success", f"Rejected by {rejected_by.email}. Reason: {reason}")
    create_audit_log(
        actor=rejected_by,
        action="knowledge_document_rejected",
        target=document,
        metadata={
            "document_id": str(document.pk),
            "document_type": document.document_type,
            "language": document.language,
            "specialty": document.specialty,
            "approval_status": document.approval_status,
            "processing_status": document.processing_status,
            "chunk_count": document.chunks.filter(is_active=True).count(),
        },
    )
    return document


def archive_knowledge_document(document: "KnowledgeDocument", archived_by):
    _require_staff(archived_by, "archive")

    document.approval_status = KnowledgeApprovalStatus.ARCHIVED
    document.is_active = False
    document.save(update_fields=["approval_status", "is_active", "updated_at"])

    document.chunks.filter(is_active=True).update(is_active=False)

    _log(document, "archive", "success", f"Archived by {archived_by.email}.")
    create_audit_log(
        actor=archived_by,
        action="knowledge_document_archived",
        target=document,
        metadata={
            "document_id": str(document.pk),
            "document_type": document.document_type,
            "language": document.language,
            "specialty": document.specialty,
            "approval_status": document.approval_status,
            "processing_status": document.processing_status,
            "chunk_count": 0,
        },
    )
    return document


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_approved_chunks(
    query: str,
    document_type: str | None = None,
    specialty: str | None = None,
    language: str | None = None,
    limit: int = 10,
    actor=None,
    request=None,
):
    """
    Basic icontains search over active chunks from approved documents.
    No embeddings — Phase 12A only.
    """
    from .models import KnowledgeChunk

    qs = KnowledgeChunk.objects.filter(
        is_active=True,
        document__approval_status=KnowledgeApprovalStatus.APPROVED,
        document__is_active=True,
    ).select_related("document")

    if query:
        qs = qs.filter(text__icontains=query)
    if document_type:
        qs = qs.filter(document__document_type=document_type)
    if specialty:
        qs = qs.filter(document__specialty=specialty)
    if language:
        qs = qs.filter(document__language=language)

    results = list(qs[:limit])

    create_audit_log(
        actor=actor,
        action="knowledge_chunk_search_performed",
        metadata={
            "query": query,
            "document_type": document_type,
            "specialty": specialty,
            "language": language,
            "result_count": len(results),
        },
        request=request,
    )
    return results
