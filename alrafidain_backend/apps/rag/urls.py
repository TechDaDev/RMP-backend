from django.urls import path

from .views import (
    AdminRAGAnalyticsSummaryView,
    AdminRAGDatasetExportView,
    AdminRAGFeedbackListView,
    AdminRAGFeedbackReviewView,
    ConsultationRAGSupportView,
    DoctorGeneralRAGQueryView,
    LabResultRAGSupportView,
    MyRAGFeedbackListView,
    RAGResponseFeedbackCreateView,
)

urlpatterns = [
    # Phase 12C — RAG queries
    path("doctor/query/", DoctorGeneralRAGQueryView.as_view(), name="rag-doctor-query"),
    path(
        "consultations/<uuid:consultation_id>/support/",
        ConsultationRAGSupportView.as_view(),
        name="rag-consultation-support",
    ),
    path(
        "lab-results/<uuid:lab_result_id>/support/",
        LabResultRAGSupportView.as_view(),
        name="rag-lab-result-support",
    ),
    # Phase 12D — Feedback
    path(
        "responses/<uuid:rag_response_id>/feedback/",
        RAGResponseFeedbackCreateView.as_view(),
        name="rag-response-feedback-create",
    ),
    path(
        "feedback/my/",
        MyRAGFeedbackListView.as_view(),
        name="rag-feedback-my-list",
    ),
    path(
        "admin/feedback/",
        AdminRAGFeedbackListView.as_view(),
        name="rag-admin-feedback-list",
    ),
    path(
        "admin/feedback/<uuid:feedback_id>/review/",
        AdminRAGFeedbackReviewView.as_view(),
        name="rag-admin-feedback-review",
    ),
    # Phase 12E — Analytics and export
    path(
        "admin/analytics/summary/",
        AdminRAGAnalyticsSummaryView.as_view(),
        name="rag-admin-analytics-summary",
    ),
    path(
        "admin/exports/dataset/",
        AdminRAGDatasetExportView.as_view(),
        name="rag-admin-dataset-export",
    ),
]
