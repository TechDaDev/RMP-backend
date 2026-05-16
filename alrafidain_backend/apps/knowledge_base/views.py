from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.views import APIView

from apps.audit.services import create_audit_log, record_security_event
from apps.common.job_utils import create_background_job
from apps.common.permissions import CanAccessKnowledgeBase
from apps.common.responses import error_response, success_response

from .models import KnowledgeChunk, KnowledgeDocument
from .serializers import (
    KnowledgeChunkSearchSerializer,
    KnowledgeChunkSerializer,
    KnowledgeDocumentApproveSerializer,
    KnowledgeDocumentArchiveSerializer,
    KnowledgeDocumentDetailSerializer,
    KnowledgeDocumentRejectSerializer,
    KnowledgeDocumentSerializer,
    KnowledgeDocumentUploadSerializer,
    SemanticSearchResultSerializer,
    SemanticSearchSerializer,
)
from .services import (
    approve_knowledge_document,
    archive_knowledge_document,
    embed_document_chunks,
    reject_knowledge_document,
    search_approved_chunks,
    semantic_search_approved_chunks,
    process_knowledge_document,
)
from .tasks import process_knowledge_document_task


@extend_schema(tags=["Knowledge Base"])
class KnowledgeDocumentUploadView(APIView):
    """
    POST /api/knowledge-base/documents/ — Upload a new document.
    GET  /api/knowledge-base/documents/ — List all documents (staff only).
    """

    permission_classes = [CanAccessKnowledgeBase]

    FILE_FIELD_ALIASES = ("reference", "document", "document_file", "upload")

    def get(self, request):
        qs = KnowledgeDocument.objects.select_related("uploaded_by", "approved_by").annotate(
            chunk_count=Count("chunks", filter=Q(chunks__is_active=True), distinct=True)
        )
        params = request.query_params

        for field in (
            "approval_status",
            "processing_status",
            "document_type",
            "language",
            "audience",
            "specialty",
        ):
            val = params.get(field)
            if val:
                qs = qs.filter(**{field: val})

        is_active = params.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ("1", "true", "yes"))

        return success_response(data=KnowledgeDocumentSerializer(qs, many=True).data)

    def post(self, request):
        payload = request.data.copy()
        if "file" not in payload:
            for alias in self.FILE_FIELD_ALIASES:
                if alias in request.FILES:
                    payload["file"] = request.FILES[alias]
                    break
                if alias in payload:
                    payload["file"] = payload[alias]
                    break

        serializer = KnowledgeDocumentUploadSerializer(data=payload, context={"request": request})
        if not serializer.is_valid():
            record_security_event(
                actor=request.user,
                action="knowledge_document_upload_rejected",
                request=request,
                metadata={
                    "reason_code": "validation_failed",
                    "error_fields": sorted(serializer.errors.keys()),
                    "file_aliases_present": sorted(
                        [alias for alias in self.FILE_FIELD_ALIASES if alias in request.FILES]
                    ),
                },
            )
            return error_response(errors=serializer.errors)

        document = serializer.save()
        create_audit_log(
            actor=request.user,
            action="knowledge_document_uploaded",
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
            request=request,
        )
        return success_response(
            data=KnowledgeDocumentDetailSerializer(document).data,
            status_code=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Knowledge Base"])
class KnowledgeDocumentDetailView(RetrieveAPIView):
    """GET /api/knowledge-base/documents/<uuid:document_id>/ — Get document detail."""

    permission_classes = [CanAccessKnowledgeBase]
    serializer_class = KnowledgeDocumentDetailSerializer
    lookup_url_kwarg = "document_id"

    def get_queryset(self):
        return (
            KnowledgeDocument.objects.prefetch_related("processing_logs")
            .select_related("uploaded_by", "approved_by")
            .annotate(chunk_count=Count("chunks", filter=Q(chunks__is_active=True), distinct=True))
        )

    def retrieve(self, request, *args, **kwargs):
        document = get_object_or_404(self.get_queryset(), pk=kwargs["document_id"])
        return success_response(data=self.get_serializer(document).data)


@extend_schema(tags=["Knowledge Base"])
class KnowledgeDocumentProcessView(APIView):
    """POST /api/knowledge-base/documents/<uuid:document_id>/process/ — Extract and chunk.
    
    Query params:
    - sync=true|1 : Run processing synchronously (for dev/testing; slow response).
                    Default: queued (returns 202 immediately).
    """

    permission_classes = [CanAccessKnowledgeBase]

    def post(self, request, document_id):
        document = get_object_or_404(KnowledgeDocument, pk=document_id)
        is_sync = request.query_params.get("sync", "").lower() in ("true", "1")

        if is_sync:
            # Synchronous processing for dev/testing (no worker needed)
            from apps.knowledge_base.services import process_knowledge_document

            process_knowledge_document(document)
            return success_response(
                message="Knowledge document processed synchronously.",
                data=KnowledgeDocumentDetailSerializer(document).data,
                status_code=status.HTTP_200_OK,
            )

        # Async (queued) processing
        job = create_background_job(
            task_name="knowledge_base.process_document",
            created_by=request.user,
            metadata={"document_id": str(document.pk)},
        )

        transaction.on_commit(
            lambda: process_knowledge_document_task.delay(
                document_id=str(document.pk),
                job_id=str(job.pk),
                actor_id=str(request.user.pk),
            )
        )

        return success_response(
            message="Knowledge document processing queued. Poll document status to detect completion.",
            data={
                "document_id": str(document.pk),
                "job_id": str(job.pk),
                "job_status": job.status,
                "polling_hint": "GET /api/knowledge-base/documents/{document_id}/ until processing_status changes from 'uploaded'",
            },
            status_code=status.HTTP_202_ACCEPTED,
        )


@extend_schema(tags=["Knowledge Base"])
class KnowledgeDocumentApproveView(APIView):
    """POST /api/knowledge-base/documents/<uuid:document_id>/approve/"""

    permission_classes = [CanAccessKnowledgeBase]

    def post(self, request, document_id):
        serializer = KnowledgeDocumentApproveSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(errors=serializer.errors)

        document = get_object_or_404(KnowledgeDocument, pk=document_id)
        try:
            approve_knowledge_document(document, approved_by=request.user)
        except (ValueError, PermissionError) as exc:
            # Check if the issue is incomplete processing
            if document.chunks.filter(is_active=True).count() == 0:
                return error_response(
                    message=f"Cannot approve: Document must be processed into chunks first. "
                    f"Current status: {document.processing_status}. "
                    f"POST /api/knowledge-base/documents/{document_id}/process/ then wait for processing_status='chunked'.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            return error_response(message=str(exc))

        return success_response(data=KnowledgeDocumentDetailSerializer(document).data)


@extend_schema(tags=["Knowledge Base"])
class KnowledgeDocumentRejectView(APIView):
    """POST /api/knowledge-base/documents/<uuid:document_id>/reject/"""

    permission_classes = [CanAccessKnowledgeBase]

    def post(self, request, document_id):
        serializer = KnowledgeDocumentRejectSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(errors=serializer.errors)

        document = get_object_or_404(KnowledgeDocument, pk=document_id)
        try:
            reject_knowledge_document(
                document,
                rejected_by=request.user,
                reason=serializer.validated_data["reason"],
            )
        except (ValueError, PermissionError) as exc:
            return error_response(message=str(exc))

        return success_response(data=KnowledgeDocumentDetailSerializer(document).data)


@extend_schema(tags=["Knowledge Base"])
class KnowledgeDocumentArchiveView(APIView):
    """POST /api/knowledge-base/documents/<uuid:document_id>/archive/"""

    permission_classes = [CanAccessKnowledgeBase]

    def post(self, request, document_id):
        serializer = KnowledgeDocumentArchiveSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(errors=serializer.errors)

        document = get_object_or_404(KnowledgeDocument, pk=document_id)
        try:
            archive_knowledge_document(document, archived_by=request.user)
        except (ValueError, PermissionError) as exc:
            return error_response(message=str(exc))

        return success_response(data=KnowledgeDocumentDetailSerializer(document).data)


@extend_schema(tags=["Knowledge Base"])
class KnowledgeChunkListView(ListAPIView):
    """GET /api/knowledge-base/documents/<uuid:document_id>/chunks/"""

    permission_classes = [CanAccessKnowledgeBase]
    serializer_class = KnowledgeChunkSerializer

    def get_queryset(self):
        document = get_object_or_404(KnowledgeDocument, pk=self.kwargs["document_id"])
        return KnowledgeChunk.objects.filter(document=document).order_by("chunk_index")

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        return success_response(data=self.get_serializer(qs, many=True).data)


@extend_schema(
    tags=["Knowledge Base"],
    parameters=[
        OpenApiParameter("q", str, description="Search query"),
        OpenApiParameter("document_type", str, required=False),
        OpenApiParameter("specialty", str, required=False),
        OpenApiParameter("language", str, required=False),
        OpenApiParameter("limit", int, required=False),
    ],
)
class KnowledgeChunkSearchView(APIView):
    """GET /api/knowledge-base/chunks/search/?q=crp"""

    permission_classes = [CanAccessKnowledgeBase]

    def get(self, request):
        serializer = KnowledgeChunkSearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return error_response(errors=serializer.errors)

        data = serializer.validated_data
        chunks = search_approved_chunks(
            query=data["q"],
            document_type=data.get("document_type") or None,
            specialty=data.get("specialty") or None,
            language=data.get("language") or None,
            limit=data.get("limit", 10),
            actor=request.user,
            request=request,
        )
        return success_response(data=KnowledgeChunkSerializer(chunks, many=True).data)


@extend_schema(tags=["Knowledge Base"])
class KnowledgeDocumentEmbedView(APIView):
    """POST /api/knowledge-base/documents/<uuid:document_id>/embed/"""

    permission_classes = [CanAccessKnowledgeBase]

    def post(self, request, document_id):
        document = get_object_or_404(KnowledgeDocument, pk=document_id)
        force = str(request.data.get("force", "false")).lower() in ("1", "true", "yes")
        try:
            result = embed_document_chunks(document, force=force)
        except ValueError as exc:
            return error_response(message=str(exc))

        create_audit_log(
            actor=request.user,
            action="knowledge_document_embedded",
            target=document,
            metadata={
                "document_id": str(document.pk),
                "force": force,
                **result,
            },
            request=request,
        )
        return success_response(data=result)


@extend_schema(
    tags=["Knowledge Base"],
    parameters=[
        OpenApiParameter("q", str, description="Semantic search query"),
        OpenApiParameter("document_type", str, required=False),
        OpenApiParameter("specialty", str, required=False),
        OpenApiParameter("language", str, required=False),
        OpenApiParameter("audience", str, required=False),
        OpenApiParameter("limit", int, required=False),
    ],
)
class KnowledgeChunkSemanticSearchView(APIView):
    """GET /api/knowledge-base/chunks/semantic-search/?q=..."""

    permission_classes = [CanAccessKnowledgeBase]

    def get(self, request):
        serializer = SemanticSearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return error_response(errors=serializer.errors)

        data = serializer.validated_data
        hits = semantic_search_approved_chunks(
            query=data["q"],
            document_type=data.get("document_type") or None,
            specialty=data.get("specialty") or None,
            language=data.get("language") or None,
            audience=data.get("audience") or None,
            limit=data.get("limit", 10),
            actor=request.user,
            request=request,
        )

        output = [
            {
                "chunk_id": str(hit["chunk"].pk),
                "document_id": str(hit["chunk"].document_id),
                "document_title": hit["chunk"].document.title,
                "document_type": hit["chunk"].document.document_type,
                "language": hit["chunk"].document.language,
                "text": hit["chunk"].text,
                "chunk_index": hit["chunk"].chunk_index,
                "score": hit["score"],
                "distance": hit["distance"],
                "rank": hit["rank"],
                "embedding_model": hit["chunk"].embedding_model,
            }
            for hit in hits
        ]
        return success_response(data=SemanticSearchResultSerializer(output, many=True).data)
