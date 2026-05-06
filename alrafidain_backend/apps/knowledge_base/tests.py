import io
import tempfile
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.common.choices import (
    KnowledgeApprovalStatus,
    KnowledgeAudience,
    KnowledgeDocumentType,
    KnowledgeLanguage,
    KnowledgeProcessingStatus,
)
from apps.common.models import BackgroundJob

from .models import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentText, KnowledgeProcessingLog
from .services import (
    approve_knowledge_document,
    archive_knowledge_document,
    chunk_knowledge_document,
    extract_text_from_document,
    search_approved_chunks,
)
from .tasks import process_knowledge_document_task

User = get_user_model()

UPLOAD_URL = "/api/knowledge-base/documents/"
MEDIA_ROOT_TMP = tempfile.mkdtemp()


def _make_txt_file(content: str = "Hello medical world. " * 200) -> SimpleUploadedFile:
    return SimpleUploadedFile("test_doc.txt", content.encode("utf-8"), content_type="text/plain")


def _make_docx_file() -> SimpleUploadedFile:
    from docx import Document as DocxDocument

    buf = io.BytesIO()
    doc = DocxDocument()
    doc.add_paragraph("This is a test DOCX medical document content. " * 100)
    doc.save(buf)
    buf.seek(0)
    return SimpleUploadedFile(
        "test_doc.docx",
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _make_staff_user(email="staff@example.com"):
    user = User.objects.create_user(email=email, password="StrongPass1!", user_type="doctor")
    user.is_staff = True
    user.is_active = True
    user.save()
    return user


def _make_regular_user(email="regular@example.com"):
    user = User.objects.create_user(email=email, password="StrongPass1!", user_type="patient")
    user.is_active = True
    user.save()
    return user


def _upload_document(client, file=None, extra=None):
    if file is None:
        file = _make_txt_file()
    payload = {
        "title": "Test Medical Book",
        "document_type": KnowledgeDocumentType.MEDICAL_BOOK,
        "language": KnowledgeLanguage.ENGLISH,
        "audience": KnowledgeAudience.DOCTOR,
        "file": file,
    }
    if extra:
        payload.update(extra)
    return client.post(UPLOAD_URL, payload, format="multipart")


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TMP)
class UploadTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = _make_staff_user()
        self.regular = _make_regular_user()

    def test_staff_can_upload_txt(self):
        self.client.force_authenticate(self.staff)
        response = _upload_document(self.client)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(KnowledgeDocument.objects.count(), 1)

    def test_staff_can_upload_docx(self):
        self.client.force_authenticate(self.staff)
        response = _upload_document(self.client, file=_make_docx_file())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_non_staff_cannot_upload(self):
        self.client.force_authenticate(self.regular)
        response = _upload_document(self.client)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_uploaded_document_starts_pending(self):
        self.client.force_authenticate(self.staff)
        _upload_document(self.client)
        doc = KnowledgeDocument.objects.first()
        self.assertEqual(doc.approval_status, KnowledgeApprovalStatus.PENDING)

    def test_uploaded_document_starts_status_uploaded(self):
        self.client.force_authenticate(self.staff)
        _upload_document(self.client)
        doc = KnowledgeDocument.objects.first()
        self.assertEqual(doc.processing_status, KnowledgeProcessingStatus.UPLOADED)

    def test_original_filename_stored(self):
        self.client.force_authenticate(self.staff)
        _upload_document(self.client, file=_make_txt_file())
        doc = KnowledgeDocument.objects.first()
        self.assertEqual(doc.original_filename, "test_doc.txt")

    def test_invalid_extension_rejected(self):
        self.client.force_authenticate(self.staff)
        bad_file = SimpleUploadedFile(
            "malware.exe", b"data", content_type="application/octet-stream"
        )
        response = _upload_document(self.client, file=bad_file)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TMP)
class ExtractionTests(TestCase):
    def setUp(self):
        self.staff = _make_staff_user()
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        _upload_document(self.client, file=_make_txt_file("CRP is a blood test marker. " * 200))
        self.doc = KnowledgeDocument.objects.first()

    def test_txt_extraction_works(self):
        extract_text_from_document(self.doc)
        self.assertTrue(KnowledgeDocumentText.objects.filter(document=self.doc).exists())

    def test_extraction_updates_processing_status(self):
        extract_text_from_document(self.doc)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.processing_status, KnowledgeProcessingStatus.EXTRACTED)

    def test_docx_extraction_works(self):
        _upload_document(self.client, file=_make_docx_file())
        doc = KnowledgeDocument.objects.order_by("-created_at").first()
        extract_text_from_document(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, KnowledgeProcessingStatus.EXTRACTED)

    def test_extraction_creates_processing_log(self):
        extract_text_from_document(self.doc)
        self.assertTrue(
            KnowledgeProcessingLog.objects.filter(document=self.doc, action="extract_text").exists()
        )

    def test_extraction_failure_sets_failed_status(self):
        # Point file to non-existent path to force failure
        self.doc.file.name = "knowledge-base/documents/nonexistent/no_file.txt"
        self.doc.save()
        with self.assertRaises(Exception):
            extract_text_from_document(self.doc)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.processing_status, KnowledgeProcessingStatus.FAILED)


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TMP)
class ChunkingTests(TestCase):
    def setUp(self):
        self.staff = _make_staff_user()
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        _upload_document(self.client, file=_make_txt_file("word " * 2000))
        self.doc = KnowledgeDocument.objects.first()
        extract_text_from_document(self.doc)
        self.doc.refresh_from_db()

    def test_chunking_creates_chunks(self):
        chunk_knowledge_document(self.doc)
        self.assertGreater(KnowledgeChunk.objects.filter(document=self.doc).count(), 0)

    def test_chunk_indexes_unique_per_document(self):
        chunk_knowledge_document(self.doc)
        chunks = KnowledgeChunk.objects.filter(document=self.doc, is_active=True)
        indexes = list(chunks.values_list("chunk_index", flat=True))
        self.assertEqual(len(indexes), len(set(indexes)))

    def test_rechunking_does_not_create_duplicate_active_chunks(self):
        chunk_knowledge_document(self.doc)
        first_count = KnowledgeChunk.objects.filter(document=self.doc, is_active=True).count()
        chunk_knowledge_document(self.doc)
        second_count = KnowledgeChunk.objects.filter(document=self.doc, is_active=True).count()
        self.assertEqual(first_count, second_count)

    def test_chunking_updates_processing_status(self):
        chunk_knowledge_document(self.doc)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.processing_status, KnowledgeProcessingStatus.CHUNKED)


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TMP)
class ApprovalTests(TestCase):
    def setUp(self):
        self.staff = _make_staff_user()
        self.regular = _make_regular_user()
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        _upload_document(self.client, file=_make_txt_file("medical text " * 300))
        self.doc = KnowledgeDocument.objects.first()
        extract_text_from_document(self.doc)
        self.doc.refresh_from_db()
        chunk_knowledge_document(self.doc)
        self.doc.refresh_from_db()

    def test_staff_can_approve_chunked_document(self):
        approve_url = f"/api/knowledge-base/documents/{self.doc.pk}/approve/"
        self.client.force_authenticate(self.staff)
        response = self.client.post(approve_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.approval_status, KnowledgeApprovalStatus.APPROVED)

    def test_cannot_approve_document_without_chunks(self):
        _upload_document(self.client, file=_make_txt_file(), extra={"title": "Empty doc"})
        empty_doc = KnowledgeDocument.objects.order_by("-created_at").first()
        with self.assertRaises(ValueError):
            approve_knowledge_document(empty_doc, approved_by=self.staff)

    def test_approval_sets_approved_by_and_approved_at(self):
        approve_knowledge_document(self.doc, approved_by=self.staff)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.approved_by, self.staff)
        self.assertIsNotNone(self.doc.approved_at)

    def test_non_staff_cannot_approve_via_service(self):
        with self.assertRaises(PermissionError):
            approve_knowledge_document(self.doc, approved_by=self.regular)

    def test_staff_can_reject_with_reason(self):
        reject_url = f"/api/knowledge-base/documents/{self.doc.pk}/reject/"
        response = self.client.post(reject_url, {"reason": "Outdated."}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.approval_status, KnowledgeApprovalStatus.REJECTED)
        self.assertEqual(self.doc.rejected_reason, "Outdated.")

    def test_staff_can_archive_document_and_deactivate_chunks(self):
        archive_url = f"/api/knowledge-base/documents/{self.doc.pk}/archive/"
        response = self.client.post(archive_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.approval_status, KnowledgeApprovalStatus.ARCHIVED)
        self.assertFalse(self.doc.is_active)


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TMP)
class KnowledgeQueryPerformanceTests(TestCase):
    def setUp(self):
        self.staff = _make_staff_user("staff-perf@example.com")
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

        for idx in range(4):
            _upload_document(
                self.client,
                file=_make_txt_file(f"knowledge {idx} " * 200),
                extra={"title": f"Doc {idx}"},
            )
            document = KnowledgeDocument.objects.order_by("-created_at").first()
            extract_text_from_document(document)
            chunk_knowledge_document(document)

    def test_document_list_uses_bounded_queries(self):
        with CaptureQueriesContext(connection) as context:
            response = self.client.get(UPLOAD_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(context), 5)


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TMP)
class SearchTests(TestCase):
    def setUp(self):
        self.staff = _make_staff_user()
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        # Create and approve a document
        _upload_document(
            self.client,
            file=_make_txt_file("CRP C-reactive protein inflammation marker blood test " * 200),
        )
        self.doc = KnowledgeDocument.objects.first()
        extract_text_from_document(self.doc)
        self.doc.refresh_from_db()
        chunk_knowledge_document(self.doc)
        self.doc.refresh_from_db()
        approve_knowledge_document(self.doc, approved_by=self.staff)
        self.doc.refresh_from_db()

        # Create pending document (should not appear in search)
        _upload_document(
            self.client,
            file=_make_txt_file("Hemoglobin pending test " * 200),
            extra={"title": "Pending Doc"},
        )
        self.pending_doc = KnowledgeDocument.objects.order_by("-created_at").first()

    def test_search_returns_approved_documents(self):
        results = search_approved_chunks("CRP", actor=self.staff)
        self.assertGreater(len(results), 0)

    def test_search_does_not_return_pending_documents(self):
        results = search_approved_chunks("Hemoglobin", actor=self.staff)
        for chunk in results:
            self.assertEqual(chunk.document.approval_status, KnowledgeApprovalStatus.APPROVED)

    def test_search_does_not_return_archived_chunks(self):
        archive_knowledge_document(self.doc, archived_by=self.staff)
        results = search_approved_chunks("CRP", actor=self.staff)
        self.assertEqual(len(results), 0)

    def test_search_filter_by_document_type(self):
        results = search_approved_chunks(
            "CRP",
            document_type=KnowledgeDocumentType.LABORATORY_BOOK,
            actor=self.staff,
        )
        for chunk in results:
            self.assertEqual(chunk.document.document_type, KnowledgeDocumentType.LABORATORY_BOOK)

    def test_search_creates_audit_log(self):
        initial_count = AuditLog.objects.filter(action="knowledge_chunk_search_performed").count()
        search_approved_chunks("CRP", actor=self.staff)
        self.assertEqual(
            AuditLog.objects.filter(action="knowledge_chunk_search_performed").count(),
            initial_count + 1,
        )


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TMP)
class KnowledgeProcessQueueTests(TestCase):
    def setUp(self):
        self.staff = _make_staff_user("staff-queue@example.com")
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        _upload_document(self.client, file=_make_txt_file("Queue process test content. " * 100))
        self.doc = KnowledgeDocument.objects.first()

    @patch("apps.knowledge_base.views.process_knowledge_document_task.delay")
    def test_process_endpoint_queues_background_task(self, delay_mock):
        url = f"/api/knowledge-base/documents/{self.doc.pk}/process/"
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn("job_id", response.data["data"])

        job = BackgroundJob.objects.get(pk=response.data["data"]["job_id"])
        self.assertEqual(job.task_name, "knowledge_base.process_document")
        delay_mock.assert_called_once_with(
            document_id=str(self.doc.pk),
            job_id=str(job.pk),
            actor_id=str(self.staff.pk),
        )

    @patch("apps.knowledge_base.services.process_knowledge_document")
    def test_process_task_uses_id_only_and_handles_missing_job(self, process_mock):
        process_mock.return_value = None
        result = process_knowledge_document_task.apply(
            kwargs={
                "document_id": str(self.doc.pk),
                "job_id": str(uuid.uuid4()),
                "actor_id": str(self.staff.pk),
            }
        ).get()
        self.assertEqual(result["status"], "ok")
        process_mock.assert_called_once()

    def test_process_task_handles_missing_document(self):
        result = process_knowledge_document_task.apply(
            kwargs={"document_id": str(uuid.uuid4()), "job_id": str(uuid.uuid4())}
        ).get()
        self.assertEqual(result["status"], "skipped")


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TMP)
class SecurityTests(TestCase):
    def setUp(self):
        self.staff = _make_staff_user()
        self.regular = _make_regular_user()
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        _upload_document(self.client, file=_make_txt_file())
        self.doc = KnowledgeDocument.objects.first()

    def test_non_staff_cannot_list_documents(self):
        self.client.force_authenticate(self.regular)
        response = self.client.get(UPLOAD_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_staff_cannot_view_document_detail(self):
        self.client.force_authenticate(self.regular)
        response = self.client.get(f"/api/knowledge-base/documents/{self.doc.pk}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_staff_cannot_list_chunks(self):
        self.client.force_authenticate(self.regular)
        response = self.client.get(f"/api/knowledge-base/documents/{self.doc.pk}/chunks/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_staff_cannot_search_chunks(self):
        self.client.force_authenticate(self.regular)
        response = self.client.get("/api/knowledge-base/chunks/search/?q=crp")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_upload(self):
        self.client.force_authenticate(None)
        response = _upload_document(self.client)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
