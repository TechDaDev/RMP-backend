from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import CreateAPIView, ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.audit.services import create_audit_log
from apps.common.choices import UserType
from apps.common.responses import error_response, success_response
from apps.common.throttles import QRScanRateThrottle
from apps.consultations.models import Consultation
from apps.consultations.permissions import is_approved_doctor, is_assigned_doctor

from .models import DispensingRecord, Prescription
from .permissions import is_approved_pharmacist, is_prescription_doctor, is_prescription_patient
from .serializers import (
    DispenseItemsSerializer,
    PharmacistDispensingHistorySerializer,
    PrescriptionCreateSerializer,
    PrescriptionDoctorDetailSerializer,
    PrescriptionPatientDetailSerializer,
    PrescriptionPatientListSerializer,
    PrescriptionPharmacistScanSerializer,
)
from .services import (
    cancel_prescription,
    create_prescription,
    dispense_prescription_items,
    get_prescription_by_qr_token,
    get_remaining_items_for_pharmacist,
)


@extend_schema(tags=["Prescriptions"])
class PrescriptionCreateView(CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PrescriptionCreateSerializer

    def create(self, request, *args, **kwargs):
        consultation_id = kwargs.get("consultation_id")
        consultation = get_object_or_404(Consultation, id=consultation_id)

        if not is_approved_doctor(request.user):
            return error_response(
                "Only approved doctors can create prescriptions.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if not is_assigned_doctor(request.user, consultation):
            return error_response(
                "You are not the assigned doctor for this consultation.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            prescription = create_prescription(
                consultation=consultation,
                doctor=request.user,
                items_data=serializer.validated_data["items"],
                request=request,
            )
        except (ValueError, Exception) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        return success_response(
            "Prescription created.",
            data=PrescriptionDoctorDetailSerializer(prescription).data,
            status_code=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Prescriptions"])
class PatientPrescriptionListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PrescriptionPatientListSerializer

    def get_queryset(self):
        if self.request.user.user_type != UserType.PATIENT:
            return Prescription.objects.none()
        return Prescription.objects.filter(patient=self.request.user).select_related(
            "doctor", "consultation"
        )

    def list(self, request, *args, **kwargs):
        if request.user.user_type != UserType.PATIENT:
            return error_response(
                "Only patients can list their prescriptions.", status_code=status.HTTP_403_FORBIDDEN
            )
        qs = self.get_queryset()
        serializer = self.get_serializer(qs, many=True)
        return success_response("Prescriptions retrieved.", data=serializer.data)


@extend_schema(tags=["Prescriptions"])
class PatientPrescriptionDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PrescriptionPatientDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        prescription = get_object_or_404(
            Prescription.objects.select_related("doctor", "consultation"),
            id=kwargs["prescription_id"],
        )
        if not is_prescription_patient(request.user, prescription):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)
        return success_response(
            "Prescription retrieved.", data=self.get_serializer(prescription).data
        )


@extend_schema(tags=["Prescriptions"])
class DoctorPrescriptionDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PrescriptionDoctorDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        prescription = get_object_or_404(
            Prescription.objects.select_related(
                "doctor", "patient", "consultation"
            ).prefetch_related("items", "dispensing_records__pharmacist"),
            id=kwargs["prescription_id"],
        )
        if not is_prescription_doctor(request.user, prescription):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)
        return success_response(
            "Prescription retrieved.", data=self.get_serializer(prescription).data
        )


@extend_schema(tags=["Prescriptions"])
class DoctorCancelPrescriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, prescription_id):
        prescription = get_object_or_404(Prescription, id=prescription_id)
        if not is_prescription_doctor(request.user, prescription):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)

        try:
            prescription = cancel_prescription(
                prescription=prescription,
                doctor=request.user,
                request=request,
            )
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        return success_response(
            "Prescription cancelled.", data=PrescriptionDoctorDetailSerializer(prescription).data
        )


@extend_schema(tags=["Prescriptions"])
class PharmacistPrescriptionScanView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [QRScanRateThrottle]

    def post(self, request):
        if not is_approved_pharmacist(request.user):
            return error_response(
                "Only approved pharmacists can scan QR tokens.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        token = request.data.get("qr_token", "").strip()
        if not token:
            return error_response("qr_token is required.", status_code=status.HTTP_400_BAD_REQUEST)

        try:
            prescription = get_prescription_by_qr_token(token, request.user)
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        create_audit_log(
            actor=request.user,
            action="prescription_qr_scanned",
            target=prescription,
            metadata={
                "prescription_id": str(prescription.id),
                "consultation_id": str(prescription.consultation_id),
                "patient_id": str(prescription.patient_id),
                "doctor_id": str(prescription.doctor_id),
                "pharmacist_id": str(request.user.id),
                "status": prescription.status,
            },
            request=request,
        )

        locked = prescription.is_locked()
        remaining = [] if locked else list(get_remaining_items_for_pharmacist(prescription))

        data = {
            "prescription": prescription,
            "remaining_items": remaining,
            "locked": locked,
            "message": "This prescription is no longer available for dispensing."
            if locked
            else None,
        }
        serializer = PrescriptionPharmacistScanSerializer(data)
        return success_response("QR scanned.", data=serializer.data)


@extend_schema(tags=["Prescriptions"])
class PharmacistDispenseItemsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, prescription_id):
        if not is_approved_pharmacist(request.user):
            return error_response(
                "Only approved pharmacists can dispense items.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        prescription = get_object_or_404(Prescription, id=prescription_id)

        serializer = DispenseItemsSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            prescription = dispense_prescription_items(
                prescription=prescription,
                pharmacist=request.user,
                items_payload=serializer.validated_data["items"],
                request=request,
            )
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        locked = prescription.is_locked()
        remaining = [] if locked else list(get_remaining_items_for_pharmacist(prescription))

        data = {
            "prescription": prescription,
            "remaining_items": remaining,
            "locked": locked,
            "message": "This prescription is no longer available for dispensing."
            if locked
            else None,
        }
        response_serializer = PrescriptionPharmacistScanSerializer(data)
        return success_response("Items processed.", data=response_serializer.data)


@extend_schema(tags=["Prescriptions"])
class PharmacistDispensingHistoryView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PharmacistDispensingHistorySerializer

    def get_queryset(self):
        return (
            DispensingRecord.objects.filter(pharmacist=self.request.user)
            .select_related(
                "prescription",
                "prescription_item",
                "prescription__patient",
                "prescription__patient__user_profile",
                "prescription__doctor",
                "prescription__doctor__doctor_profile",
            )
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):
        if not is_approved_pharmacist(request.user):
            return error_response(
                "Only approved pharmacists can view dispensing history.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated = self.get_paginated_response(serializer.data).data
            return success_response("Dispensing history retrieved.", data=paginated)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            "Dispensing history retrieved.",
            data={
                "count": len(serializer.data),
                "next": None,
                "previous": None,
                "results": serializer.data,
            },
        )
