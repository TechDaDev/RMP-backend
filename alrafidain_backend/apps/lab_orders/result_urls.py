from django.urls import path

from .views import PatientLabResultDetailView, PatientLabResultListView

urlpatterns = [
    path("my/", PatientLabResultListView.as_view(), name="patient-lab-result-list-v2"),
    path(
        "my/<uuid:lab_result_id>/",
        PatientLabResultDetailView.as_view(),
        name="patient-lab-result-detail-v2",
    ),
]
