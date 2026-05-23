from django.urls import path

from .views import PatientMedicalReportDetailView, PatientMedicalReportListView

urlpatterns = [
    path(
        "medical-reports/", PatientMedicalReportListView.as_view(), name="patient-medical-reports"
    ),
    path(
        "medical-reports/<uuid:report_id>/",
        PatientMedicalReportDetailView.as_view(),
        name="patient-medical-report-detail",
    ),
]
