from django.urls import path

from .views import (
    DoctorCancelLabOrderView,
    DoctorLabResultDetailView,
    DoctorLinkLabResultToMedicalRecordView,
    DoctorReleaseLabResultView,
    DoctorReviewLabResultView,
    DoctorLabOrderDetailView,
    LabResultCorrectionView,
    LabResultCreateView,
    LabResultDetailView,
    LaboratorianCompleteLabOrderItemsView,
    LaboratorianLabOrderScanView,
    LabTestCatalogListView,
    PatientLabResultDetailView,
    PatientLabResultListView,
    PatientLabOrderDetailView,
    PatientLabOrderListView,
)

urlpatterns = [
    path("tests/", LabTestCatalogListView.as_view(), name="lab-test-catalog-list"),
    path("my/", PatientLabOrderListView.as_view(), name="patient-lab-order-list"),
    path("my/<uuid:lab_order_id>/", PatientLabOrderDetailView.as_view(), name="patient-lab-order-detail"),
    path("doctor/<uuid:lab_order_id>/", DoctorLabOrderDetailView.as_view(), name="doctor-lab-order-detail"),
    path("doctor/<uuid:lab_order_id>/cancel/", DoctorCancelLabOrderView.as_view(), name="doctor-lab-order-cancel"),
    path("scan/", LaboratorianLabOrderScanView.as_view(), name="laboratorian-lab-order-scan"),
    path("<uuid:lab_order_id>/complete/", LaboratorianCompleteLabOrderItemsView.as_view(), name="laboratorian-complete-lab-order-items"),
    path("items/<uuid:lab_order_item_id>/results/", LabResultCreateView.as_view(), name="lab-result-create"),
    path("results/<uuid:lab_result_id>/", LabResultDetailView.as_view(), name="lab-result-detail"),
    path("results/<uuid:lab_result_id>/correct/", LabResultCorrectionView.as_view(), name="lab-result-correct"),
    path("doctor/results/<uuid:lab_result_id>/", DoctorLabResultDetailView.as_view(), name="doctor-lab-result-detail"),
    path("doctor/results/<uuid:lab_result_id>/review/", DoctorReviewLabResultView.as_view(), name="doctor-lab-result-review"),
    path("doctor/results/<uuid:lab_result_id>/release/", DoctorReleaseLabResultView.as_view(), name="doctor-lab-result-release"),
    path(
        "doctor/results/<uuid:lab_result_id>/link-medical-record/",
        DoctorLinkLabResultToMedicalRecordView.as_view(),
        name="doctor-lab-result-link-medical-record",
    ),
    path("my-results/", PatientLabResultListView.as_view(), name="patient-lab-result-list"),
    path("my-results/<uuid:lab_result_id>/", PatientLabResultDetailView.as_view(), name="patient-lab-result-detail"),
]
