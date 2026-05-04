from django.urls import path

from .views import (
    ConsultationRAGSupportView,
    DoctorGeneralRAGQueryView,
    LabResultRAGSupportView,
)

urlpatterns = [
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
]
