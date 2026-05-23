from django.urls import path

from .views import (
    AdminRAGAnalyticsSummaryView,
    AdminRAGDatasetExportView,
    AdminRAGFeedbackListView,
    AdminRAGFeedbackReviewView,
    ConsultationDoctorAIAssistantMessageListView,
    ConsultationRAGSupportView,
    DoctorAIAssistantMessageDetailView,
    DoctorAIAssistantMessageMarkReadView,
    DoctorGeneralRAGQueryView,
    LabResultRAGSupportView,
    MedicalReportCaseUpdateRAGView,
    MedicalReportDoctorAIAssistantGenerateView,
    MyRAGFeedbackListView,
    RAGResponseFeedbackCreateView,
    RAGResponseSaveToPatientRecordView,
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
    path(
        "medical-reports/<uuid:report_id>/case-update/",
        MedicalReportCaseUpdateRAGView.as_view(),
        name="rag-medical-report-case-update",
    ),
    path(
        "consultations/<uuid:consultation_id>/doctor-ai-messages/",
        ConsultationDoctorAIAssistantMessageListView.as_view(),
        name="rag-consultation-doctor-ai-messages",
    ),
    path(
        "medical-reports/<uuid:report_id>/doctor-ai-message/",
        MedicalReportDoctorAIAssistantGenerateView.as_view(),
        name="rag-medical-report-doctor-ai-message-generate",
    ),
    path(
        "doctor-ai-messages/<uuid:message_id>/",
        DoctorAIAssistantMessageDetailView.as_view(),
        name="rag-doctor-ai-message-detail",
    ),
    path(
        "doctor-ai-messages/<uuid:message_id>/mark-read/",
        DoctorAIAssistantMessageMarkReadView.as_view(),
        name="rag-doctor-ai-message-mark-read",
    ),
    # Phase 12D — Feedback
    path(
        "responses/<uuid:rag_response_id>/feedback/",
        RAGResponseFeedbackCreateView.as_view(),
        name="rag-response-feedback-create",
    ),
    path(
        "responses/<uuid:rag_response_id>/save-to-record/",
        RAGResponseSaveToPatientRecordView.as_view(),
        name="rag-response-save-to-record",
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
