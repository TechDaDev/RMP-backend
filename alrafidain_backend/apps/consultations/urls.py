from django.urls import include, path

from apps.lab_orders.views import LabOrderCreateView
from apps.prescriptions.views import PrescriptionCreateView

from .views import (
    ConsultationAcceptView,
    ConsultationCloseView,
    ConsultationCreateView,
    ConsultationDetailView,
    ConsultationResponseCreateView,
    DoctorAssignedConsultationListView,
    DoctorPendingConsultationListView,
    MyConsultationListView,
    SymptomCategoryListView,
    SymptomListView,
)

urlpatterns = [
    path("symptom-categories/", SymptomCategoryListView.as_view(), name="symptom-categories-list"),
    path("symptoms/", SymptomListView.as_view(), name="symptoms-list"),
    path("", ConsultationCreateView.as_view(), name="consultation-create"),
    path("my/", MyConsultationListView.as_view(), name="my-consultations"),
    path("doctor/pending/", DoctorPendingConsultationListView.as_view(), name="doctor-pending-consultations"),
    path("doctor/assigned/", DoctorAssignedConsultationListView.as_view(), name="doctor-assigned-consultations"),
    path("<uuid:consultation_id>/", ConsultationDetailView.as_view(), name="consultation-detail"),
    path("<uuid:consultation_id>/accept/", ConsultationAcceptView.as_view(), name="consultation-accept"),
    path("<uuid:consultation_id>/responses/", ConsultationResponseCreateView.as_view(), name="consultation-response-create"),
    path("<uuid:consultation_id>/close/", ConsultationCloseView.as_view(), name="consultation-close"),
    path("<uuid:consultation_id>/prescriptions/", PrescriptionCreateView.as_view(), name="prescription-create"),
    path("<uuid:consultation_id>/lab-orders/", LabOrderCreateView.as_view(), name="lab-order-create"),
    path("", include("apps.messaging.urls")),
]
