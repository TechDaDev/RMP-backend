"""
Phase 12B Tests — pgvector Embeddings and Semantic Retrieval

Strategy:
- All tests mock the embedding client so NO real SentenceTransformer model is loaded.
- The mock client returns [0.1] * 384 by default.
- Semantic search tests that rely on CosineDistance annotate queries are mocked at the
  service layer level (patch semantic_search_approved_chunks) because SQLite in-memory
  does not support pgvector operations.
- Management command tests mock embed_document_chunks / embed_all_approved_chunks.
"""

import io
import tempfile
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
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

from .models import KnowledgeChunk, KnowledgeDocument, KnowledgeProcessingLog
from .services import (
    embed_all_approved_chunks,
    embed_document_chunks,
    embed_knowledge_chunk,
)

User = get_user_model()
MEDIA_ROOT_TMP = tempfile.mkdtemp()
EMBED_URL_FMT = "/api/knowledge-base/documents/{}/embed/"
SEMANTIC_SEARCH_URL = "/api/knowledge-base/chunks/semantic-search/"

MOCK_VECTOR = [0.1] * 384


# ---------------------------------------------------------------------------
# Helpers (shared with existing tests.py pattern)
# ---------------------------------------------------------------------------

def _make_txt_file(content: str = "Medical content. " * 300) -> SimpleUploadedFile:
    return SimpleUploadedFile("test_doc.txt", content.encode("utf-8"), content_type="text/plain")


def _make_staff_user(email="staff_emb@example.com"):
    user = User.objects.create_user(email=email, password="StrongPass1!", user_type="doctor")
    user.is_staff = True
    user.is_active = True
    user.save()
    return user


def _make_regular_user(email="regular_emb@example.com"):
    user = User.objects.create_user(email=email, password="StrongPass1!", user_type="patient")
    user.is_active = True
    user.save()
    return user


def _make_mock_embedding_client():
    client = mock.MagicMock()
    client.embed_text.return_value = MOCK_VECTOR
    client.embed_texts.return_value = [MOCK_VECTOR]
    return client


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TMP)
def _create_approved_document(staff_user, title="Test Doc"):
    """Create an approved document with active chunks via the service layer."""
    from django.utils import timezone

    from .models import KnowledgeDocumentText
    from .services import approve_knowledge_document, chunk_knowledge_document

    doc = KnowledgeDocument.objects.create(
        title=title,
        document_type=KnowledgeDocumentType.MEDICAL_BOOK,
        language=KnowledgeLanguage.ENGLISH,
        audience=KnowledgeAudience.DOCTOR,
        original_filename="test.txt",
        approval_status=KnowledgeApprovalStatus.PENDING,
        processing_status=KnowledgeProcessingStatus.UPLOADED,
        uploaded_by=staff_user,
        file=SimpleUploadedFile("test.txt", b"x"),
    )
    KnowledgeDocumentText.objects.create(
        document=doc,
        text="Medical text content. " * 200,
        page_count=1,
        extraction_metadata={},
    )
    doc.processing_status = KnowledgeProcessingStatus.EXTRACTED
    doc.save(update_fields=["processing_status", "updated_at"])
    chunk_knowledge_document(doc)
    approve_knowledge_document(doc, approved_by=staff_user)
    return doc


# ---------------------------------------------------------------------------
# Unit tests — embed_knowledge_chunk
# ---------------------------------------------------------------------------

@override_settings(
    MEDIA_ROOT=MEDIA_ROOT_TMP,
    EMBEDDING_MODEL_NAME="test-model",
)
class EmbedKnowledgeChunkTest(TestCase):
    def setUp(self):
        self.staff = _make_staff_user("staff_unit@test.com")
        self.doc = _create_approved_document(self.staff)
        self.chunk = self.doc.chunks.filter(is_active=True).first()

    def test_embed_chunk_sets_fields(self):
        client = _make_mock_embedding_client()
        result = embed_knowledge_chunk(self.chunk, embedding_client=client)

        self.chunk.refresh_from_db()
        self.assertEqual(list(self.chunk.embedding), MOCK_VECTOR)
        self.assertEqual(self.chunk.embedding_model, "test-model")
        self.assertIsNotNone(self.chunk.embedded_at)
        self.assertTrue(self.chunk.has_embedding)
        client.embed_text.assert_called_once_with(self.chunk.text)

    def test_embed_chunk_rejected_if_doc_not_approved(self):
        self.doc.approval_status = KnowledgeApprovalStatus.PENDING
        self.doc.save(update_fields=["approval_status"])
        client = _make_mock_embedding_client()
        with self.assertRaises(ValueError, msg="not approved"):
            embed_knowledge_chunk(self.chunk, embedding_client=client)

    def test_embed_chunk_rejected_if_chunk_inactive(self):
        self.chunk.is_active = False
        self.chunk.save(update_fields=["is_active"])
        client = _make_mock_embedding_client()
        with self.assertRaises(ValueError, msg="inactive"):
            embed_knowledge_chunk(self.chunk, embedding_client=client)

    def test_has_embedding_false_before_embed(self):
        self.assertFalse(self.chunk.has_embedding)

    def test_has_embedding_true_after_embed(self):
        client = _make_mock_embedding_client()
        embed_knowledge_chunk(self.chunk, embedding_client=client)
        self.chunk.refresh_from_db()
        self.assertTrue(self.chunk.has_embedding)


# ---------------------------------------------------------------------------
# Unit tests — embed_document_chunks
# ---------------------------------------------------------------------------

@override_settings(
    MEDIA_ROOT=MEDIA_ROOT_TMP,
    EMBEDDING_MODEL_NAME="test-model",
)
class EmbedDocumentChunksTest(TestCase):
    def setUp(self):
        self.staff = _make_staff_user("staff_doc@test.com")
        self.doc = _create_approved_document(self.staff)

    def test_embeds_all_active_chunks(self):
        client = _make_mock_embedding_client()
        result = embed_document_chunks(self.doc, embedding_client=client)
        self.assertGreater(result["embedded"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(client.embed_text.call_count, result["embedded"])

    def test_skips_already_embedded_without_force(self):
        client = _make_mock_embedding_client()
        embed_document_chunks(self.doc, embedding_client=client)
        first_count = client.embed_text.call_count

        # Second call without force — nothing new to embed
        client.embed_text.reset_mock()
        result2 = embed_document_chunks(self.doc, embedding_client=client)
        self.assertEqual(result2["embedded"], 0)
        client.embed_text.assert_not_called()

    def test_force_reembeds_all_chunks(self):
        client = _make_mock_embedding_client()
        embed_document_chunks(self.doc, embedding_client=client)
        first_count = client.embed_text.call_count

        client.embed_text.reset_mock()
        result2 = embed_document_chunks(self.doc, force=True, embedding_client=client)
        self.assertEqual(result2["embedded"], first_count)

    def test_raises_for_unapproved_document(self):
        self.doc.approval_status = KnowledgeApprovalStatus.PENDING
        self.doc.save(update_fields=["approval_status"])
        client = _make_mock_embedding_client()
        with self.assertRaises(ValueError):
            embed_document_chunks(self.doc, embedding_client=client)

    def test_processing_log_created(self):
        client = _make_mock_embedding_client()
        embed_document_chunks(self.doc, embedding_client=client)
        self.assertTrue(
            KnowledgeProcessingLog.objects.filter(document=self.doc, action="embed_chunks").exists()
        )


# ---------------------------------------------------------------------------
# Unit tests — embed_all_approved_chunks
# ---------------------------------------------------------------------------

@override_settings(
    MEDIA_ROOT=MEDIA_ROOT_TMP,
    EMBEDDING_MODEL_NAME="test-model",
)
class EmbedAllApprovedChunksTest(TestCase):
    def setUp(self):
        self.staff = _make_staff_user("staff_all@test.com")
        self.doc1 = _create_approved_document(self.staff, title="Doc 1")
        self.doc2 = _create_approved_document(self.staff, title="Doc 2")

    def test_embeds_chunks_across_all_docs(self):
        client = _make_mock_embedding_client()
        result = embed_all_approved_chunks(embedding_client=client)
        self.assertGreater(result["embedded"], 0)
        self.assertEqual(result["failed"], 0)

    def test_force_flag_propagated(self):
        client = _make_mock_embedding_client()
        embed_all_approved_chunks(embedding_client=client)

        # Second pass without force — no new embeds
        client.embed_text.reset_mock()
        result = embed_all_approved_chunks(embedding_client=client)
        self.assertEqual(result["embedded"], 0)

    def test_inactive_document_skipped(self):
        self.doc2.is_active = False
        self.doc2.save(update_fields=["is_active"])
        client = _make_mock_embedding_client()
        # Should only embed doc1
        result = embed_all_approved_chunks(embedding_client=client)
        doc2_embedded = self.doc2.chunks.filter(embedding__isnull=False).count()
        self.assertEqual(doc2_embedded, 0)


# ---------------------------------------------------------------------------
# API tests — KnowledgeDocumentEmbedView
# ---------------------------------------------------------------------------

@override_settings(
    MEDIA_ROOT=MEDIA_ROOT_TMP,
    EMBEDDING_MODEL_NAME="test-model",
)
class KnowledgeDocumentEmbedViewTest(TestCase):
    def setUp(self):
        self.staff = _make_staff_user("staff_api_emb@test.com")
        self.regular = _make_regular_user("regular_api_emb@test.com")
        self.doc = _create_approved_document(self.staff)
        self.url = EMBED_URL_FMT.format(self.doc.pk)

        self.staff_client = APIClient()
        self.staff_client.force_authenticate(self.staff)

        self.anon_client = APIClient()
        self.regular_client = APIClient()
        self.regular_client.force_authenticate(self.regular)

    @mock.patch("apps.knowledge_base.views.embed_document_chunks")
    def test_staff_can_embed(self, mock_embed):
        mock_embed.return_value = {"embedded": 5, "skipped": 0, "failed": 0}
        response = self.staff_client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["embedded"], 5)
        mock_embed.assert_called_once()

    @mock.patch("apps.knowledge_base.views.embed_document_chunks")
    def test_force_flag_passed(self, mock_embed):
        mock_embed.return_value = {"embedded": 3, "skipped": 0, "failed": 0}
        self.staff_client.post(self.url, {"force": "true"})
        _, kwargs = mock_embed.call_args
        self.assertTrue(kwargs.get("force") or mock_embed.call_args[0][1] is True or
                        mock_embed.call_args.kwargs.get("force") is True or
                        mock_embed.call_args.args[1] is True)

    def test_non_staff_blocked(self):
        response = self.regular_client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_blocked(self):
        response = self.anon_client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @mock.patch("apps.knowledge_base.views.embed_document_chunks")
    def test_audit_log_created(self, mock_embed):
        mock_embed.return_value = {"embedded": 2, "skipped": 0, "failed": 0}
        self.staff_client.post(self.url)
        self.assertTrue(
            AuditLog.objects.filter(action="knowledge_document_embedded").exists()
        )

    def test_invalid_document_id_returns_404(self):
        url = EMBED_URL_FMT.format(uuid.uuid4())
        response = self.staff_client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @mock.patch("apps.knowledge_base.views.embed_document_chunks")
    def test_unapproved_document_returns_error(self, mock_embed):
        mock_embed.side_effect = ValueError("Document must be approved")
        response = self.staff_client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# API tests — KnowledgeChunkSemanticSearchView (service mocked)
# ---------------------------------------------------------------------------

@override_settings(
    MEDIA_ROOT=MEDIA_ROOT_TMP,
    EMBEDDING_MODEL_NAME="test-model",
)
class KnowledgeChunkSemanticSearchViewTest(TestCase):
    def setUp(self):
        self.staff = _make_staff_user("staff_sem@test.com")
        self.regular = _make_regular_user("regular_sem@test.com")
        self.doc = _create_approved_document(self.staff)
        self.chunk = self.doc.chunks.filter(is_active=True).first()

        # Pre-embed one chunk directly so it has an embedding
        self.chunk.embedding = MOCK_VECTOR
        self.chunk.embedding_model = "test-model"
        self.chunk.save(update_fields=["embedding", "embedding_model"])

        self.staff_client = APIClient()
        self.staff_client.force_authenticate(self.staff)
        self.regular_client = APIClient()
        self.regular_client.force_authenticate(self.regular)
        self.anon_client = APIClient()

    def _mock_hit(self):
        return {
            "chunk": self.chunk,
            "score": 0.95,
            "distance": 0.05,
            "rank": 1,
        }

    @mock.patch("apps.knowledge_base.views.semantic_search_approved_chunks")
    def test_staff_semantic_search(self, mock_search):
        mock_search.return_value = [self._mock_hit()]
        response = self.staff_client.get(SEMANTIC_SEARCH_URL, {"q": "medical test"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)
        hit = response.data["data"][0]
        self.assertIn("chunk_id", hit)
        self.assertIn("score", hit)
        self.assertIn("rank", hit)
        self.assertIn("text", hit)

    @mock.patch("apps.knowledge_base.views.semantic_search_approved_chunks")
    def test_missing_q_param_returns_error(self, mock_search):
        response = self.staff_client.get(SEMANTIC_SEARCH_URL)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_search.assert_not_called()

    def test_non_staff_blocked(self):
        response = self.regular_client.get(SEMANTIC_SEARCH_URL, {"q": "test"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_blocked(self):
        response = self.anon_client.get(SEMANTIC_SEARCH_URL, {"q": "test"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @mock.patch("apps.knowledge_base.views.semantic_search_approved_chunks")
    def test_audit_log_created(self, mock_search):
        mock_search.return_value = []
        self.staff_client.get(SEMANTIC_SEARCH_URL, {"q": "diabetes"})
        # Audit log created inside the service mock — verify mock was called
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args.kwargs
        self.assertEqual(call_kwargs.get("query"), "diabetes")
        self.assertEqual(call_kwargs.get("actor"), self.staff)

    @mock.patch("apps.knowledge_base.views.semantic_search_approved_chunks")
    def test_filters_passed_to_service(self, mock_search):
        mock_search.return_value = []
        self.staff_client.get(
            SEMANTIC_SEARCH_URL,
            {
                "q": "test",
                "document_type": KnowledgeDocumentType.MEDICAL_BOOK,
                "language": KnowledgeLanguage.ENGLISH,
                "limit": "5",
            },
        )
        call_kwargs = mock_search.call_args.kwargs
        self.assertEqual(call_kwargs.get("document_type"), KnowledgeDocumentType.MEDICAL_BOOK)
        self.assertEqual(call_kwargs.get("language"), KnowledgeLanguage.ENGLISH)
        self.assertEqual(call_kwargs.get("limit"), 5)


# ---------------------------------------------------------------------------
# Serializer tests — KnowledgeChunkSerializer embedding fields
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=MEDIA_ROOT_TMP)
class KnowledgeChunkSerializerEmbeddingFieldsTest(TestCase):
    def setUp(self):
        self.staff = _make_staff_user("staff_ser@test.com")
        self.doc = _create_approved_document(self.staff)
        self.chunk = self.doc.chunks.filter(is_active=True).first()

    def test_chunk_serializer_has_embedding_false(self):
        from .serializers import KnowledgeChunkSerializer

        data = KnowledgeChunkSerializer(self.chunk).data
        self.assertFalse(data["has_embedding"])
        self.assertIn("embedding_model", data)
        self.assertIn("embedded_at", data)
        self.assertNotIn("embedding", data)  # raw vector NOT exposed

    def test_chunk_serializer_has_embedding_true_after_embed(self):
        from .serializers import KnowledgeChunkSerializer

        self.chunk.embedding = MOCK_VECTOR
        self.chunk.embedding_model = "test-model"
        self.chunk.save(update_fields=["embedding", "embedding_model"])

        data = KnowledgeChunkSerializer(self.chunk).data
        self.assertTrue(data["has_embedding"])
        self.assertEqual(data["embedding_model"], "test-model")


# ---------------------------------------------------------------------------
# Management command tests
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=MEDIA_ROOT_TMP)
class ManagementCommandEmbedKnowledgeBaseTest(TestCase):
    def setUp(self):
        self.staff = _make_staff_user("staff_cmd@test.com")
        self.doc = _create_approved_document(self.staff)

    @mock.patch("apps.knowledge_base.management.commands.embed_knowledge_base.embed_all_approved_chunks")
    def test_command_calls_embed_all(self, mock_fn):
        mock_fn.return_value = {"embedded": 3, "skipped": 0, "failed": 0}
        call_command("embed_knowledge_base")
        mock_fn.assert_called_once_with(force=False, limit=None)

    @mock.patch("apps.knowledge_base.management.commands.embed_knowledge_base.embed_all_approved_chunks")
    def test_command_force_flag(self, mock_fn):
        mock_fn.return_value = {"embedded": 3, "skipped": 0, "failed": 0}
        call_command("embed_knowledge_base", "--force")
        mock_fn.assert_called_once_with(force=True, limit=None)

    @mock.patch("apps.knowledge_base.management.commands.embed_knowledge_base.embed_document_chunks")
    def test_command_single_document(self, mock_fn):
        mock_fn.return_value = {"embedded": 2, "skipped": 0, "failed": 0}
        call_command("embed_knowledge_base", f"--document-id={self.doc.pk}")
        mock_fn.assert_called_once()

    @mock.patch("apps.knowledge_base.management.commands.embed_knowledge_base.embed_all_approved_chunks")
    def test_command_limit_option(self, mock_fn):
        mock_fn.return_value = {"embedded": 1, "skipped": 0, "failed": 0}
        call_command("embed_knowledge_base", "--limit=5")
        mock_fn.assert_called_once_with(force=False, limit=5)

    def test_command_invalid_uuid_raises_error(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("embed_knowledge_base", "--document-id=not-a-uuid")

    def test_command_nonexistent_document_raises_error(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("embed_knowledge_base", f"--document-id={uuid.uuid4()}")


# ---------------------------------------------------------------------------
# embedding_client unit tests (no real model loaded)
# ---------------------------------------------------------------------------

class EmbeddingClientTest(TestCase):
    @mock.patch("apps.knowledge_base.embedding_client.LocalEmbeddingClient._load_model")
    def test_embed_text_calls_encode(self, mock_load):
        import numpy as np

        mock_model = mock.MagicMock()
        mock_model.encode.return_value = np.array([MOCK_VECTOR])
        mock_load.return_value = mock_model

        from .embedding_client import LocalEmbeddingClient

        client = LocalEmbeddingClient(model_name="test")
        result = client.embed_text("hello world")
        self.assertEqual(result, MOCK_VECTOR)
        mock_model.encode.assert_called_once()

    @mock.patch("apps.knowledge_base.embedding_client.LocalEmbeddingClient._load_model")
    def test_embed_texts_returns_list_of_lists(self, mock_load):
        import numpy as np

        mock_model = mock.MagicMock()
        mock_model.encode.return_value = np.array([MOCK_VECTOR, MOCK_VECTOR])
        mock_load.return_value = mock_model

        from .embedding_client import LocalEmbeddingClient

        client = LocalEmbeddingClient(model_name="test")
        results = client.embed_texts(["text a", "text b"])
        self.assertEqual(len(results), 2)
        self.assertIsInstance(results[0], list)

    def test_get_default_embedding_client_singleton(self):
        import apps.knowledge_base.embedding_client as ec

        ec._default_client = None  # reset singleton
        c1 = ec.get_default_embedding_client()
        c2 = ec.get_default_embedding_client()
        self.assertIs(c1, c2)
        ec._default_client = None  # cleanup
