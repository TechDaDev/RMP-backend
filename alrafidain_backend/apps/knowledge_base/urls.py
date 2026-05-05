from django.urls import path

from .views import (
    KnowledgeChunkListView,
    KnowledgeChunkSearchView,
    KnowledgeChunkSemanticSearchView,
    KnowledgeDocumentApproveView,
    KnowledgeDocumentArchiveView,
    KnowledgeDocumentDetailView,
    KnowledgeDocumentEmbedView,
    KnowledgeDocumentProcessView,
    KnowledgeDocumentRejectView,
    KnowledgeDocumentUploadView,
)

urlpatterns = [
    # POST (upload) + GET (list) on same endpoint
    path(
        "documents/", KnowledgeDocumentUploadView.as_view(), name="knowledge-document-list-upload"
    ),
    path(
        "documents/<uuid:document_id>/",
        KnowledgeDocumentDetailView.as_view(),
        name="knowledge-document-detail",
    ),
    # Document workflow actions
    path(
        "documents/<uuid:document_id>/process/",
        KnowledgeDocumentProcessView.as_view(),
        name="knowledge-document-process",
    ),
    path(
        "documents/<uuid:document_id>/approve/",
        KnowledgeDocumentApproveView.as_view(),
        name="knowledge-document-approve",
    ),
    path(
        "documents/<uuid:document_id>/reject/",
        KnowledgeDocumentRejectView.as_view(),
        name="knowledge-document-reject",
    ),
    path(
        "documents/<uuid:document_id>/archive/",
        KnowledgeDocumentArchiveView.as_view(),
        name="knowledge-document-archive",
    ),
    path(
        "documents/<uuid:document_id>/embed/",
        KnowledgeDocumentEmbedView.as_view(),
        name="knowledge-document-embed",
    ),
    # Chunks
    path(
        "documents/<uuid:document_id>/chunks/",
        KnowledgeChunkListView.as_view(),
        name="knowledge-chunk-list",
    ),
    path("chunks/search/", KnowledgeChunkSearchView.as_view(), name="knowledge-chunk-search"),
    path(
        "chunks/semantic-search/",
        KnowledgeChunkSemanticSearchView.as_view(),
        name="knowledge-chunk-semantic-search",
    ),
]
