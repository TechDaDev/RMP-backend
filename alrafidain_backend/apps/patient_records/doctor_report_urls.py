from django.urls import path

from .views import (
    DoctorConsultationMedicalReportListView,
    DoctorMedicalReportClassifyLLMView,
    DoctorMedicalReportDetailView,
    DoctorMedicalReportProcessOCRView,
    DoctorMedicalReportReviewView,
)

urlpatterns = [
    path(
        "consultations/<uuid:consultation_id>/medical-reports/",
        DoctorConsultationMedicalReportListView.as_view(),
        name="doctor-consultation-medical-reports",
    ),
    path(
        "medical-reports/<uuid:report_id>/",
        DoctorMedicalReportDetailView.as_view(),
        name="doctor-medical-report-detail",
    ),
    path(
        "medical-reports/<uuid:report_id>/review/",
        DoctorMedicalReportReviewView.as_view(),
        name="doctor-medical-report-review",
    ),
    path(
        "medical-reports/<uuid:report_id>/process-ocr/",
        DoctorMedicalReportProcessOCRView.as_view(),
        name="doctor-medical-report-process-ocr",
    ),
    path(
        "medical-reports/<uuid:report_id>/classify-llm/",
        DoctorMedicalReportClassifyLLMView.as_view(),
        name="doctor-medical-report-classify-llm",
    ),
]
