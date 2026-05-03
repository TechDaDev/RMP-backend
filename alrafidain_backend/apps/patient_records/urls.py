from django.urls import path

from .views import (
    DoctorPatientMedicalRecordView,
    LaboratorianVerifyBloodGroupView,
    MedicalRecordEntryConfirmView,
    MedicalRecordEntryCreateView,
    MedicalRecordEntryDeactivateView,
    MyMedicalRecordView,
    SetBloodGroupView,
)

urlpatterns = [
    path("my/", MyMedicalRecordView.as_view(), name="patient-record-my"),
    path("patients/<uuid:patient_id>/", DoctorPatientMedicalRecordView.as_view(), name="patient-record-doctor-view"),
    path("<uuid:record_id>/entries/", MedicalRecordEntryCreateView.as_view(), name="patient-record-entry-create"),
    path("entries/<uuid:entry_id>/confirm/", MedicalRecordEntryConfirmView.as_view(), name="patient-record-entry-confirm"),
    path("entries/<uuid:entry_id>/deactivate/", MedicalRecordEntryDeactivateView.as_view(), name="patient-record-entry-deactivate"),
    path("<uuid:record_id>/blood-group/", SetBloodGroupView.as_view(), name="patient-record-blood-group-set"),
    path(
        "patients/<uuid:patient_id>/blood-group/verify/",
        LaboratorianVerifyBloodGroupView.as_view(),
        name="patient-record-blood-group-verify",
    ),
]
