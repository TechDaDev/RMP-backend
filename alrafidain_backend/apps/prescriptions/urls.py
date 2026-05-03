from django.urls import path

from .views import (
    DoctorCancelPrescriptionView,
    DoctorPrescriptionDetailView,
    PatientPrescriptionDetailView,
    PatientPrescriptionListView,
    PharmacistDispenseItemsView,
    PharmacistPrescriptionScanView,
)

urlpatterns = [
    path("my/", PatientPrescriptionListView.as_view(), name="patient-prescription-list"),
    path("my/<uuid:prescription_id>/", PatientPrescriptionDetailView.as_view(), name="patient-prescription-detail"),
    path("doctor/<uuid:prescription_id>/", DoctorPrescriptionDetailView.as_view(), name="doctor-prescription-detail"),
    path("doctor/<uuid:prescription_id>/cancel/", DoctorCancelPrescriptionView.as_view(), name="doctor-prescription-cancel"),
    path("scan/", PharmacistPrescriptionScanView.as_view(), name="pharmacist-prescription-scan"),
    path("<uuid:prescription_id>/dispense/", PharmacistDispenseItemsView.as_view(), name="pharmacist-dispense-items"),
]
