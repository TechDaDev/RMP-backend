from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.choices import MedicalRecordVerificationStatus, UserType
from apps.common.responses import error_response, success_response

from .models import MedicalRecordEntry, PatientMedicalRecord
from .serializers import (
    BloodGroupRecordSerializer,
    MedicalRecordEntryConfirmSerializer,
    MedicalRecordEntryCreateSerializer,
    MedicalRecordEntryDeactivateSerializer,
    MedicalRecordEntrySerializer,
    PatientMedicalRecordSerializer,
    SetBloodGroupSerializer,
)
from .services import (
    confirm_medical_record_entry,
    create_medical_record_entry,
    doctor_can_access_patient_record,
    get_or_create_patient_medical_record,
    set_blood_group,
)

User = get_user_model()


@extend_schema(tags=["Patient Records"])
class MyMedicalRecordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get current patient medical record")
    def get(self, request):
        if request.user.user_type != UserType.PATIENT:
            return error_response(
                "Only patients can access this endpoint.", status_code=status.HTTP_403_FORBIDDEN
            )

        record = get_or_create_patient_medical_record(request.user)
        return success_response(
            "Medical record retrieved.", data=PatientMedicalRecordSerializer(record).data
        )


@extend_schema(tags=["Patient Records"])
class DoctorPatientMedicalRecordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get patient medical record for doctor")
    def get(self, request, patient_id):
        if request.user.user_type != UserType.DOCTOR:
            return error_response(
                "Only doctors can access this endpoint.", status_code=status.HTTP_403_FORBIDDEN
            )

        patient = get_object_or_404(User, id=patient_id, user_type=UserType.PATIENT)
        if not doctor_can_access_patient_record(request.user, patient):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)

        record = get_or_create_patient_medical_record(patient)
        return success_response(
            "Medical record retrieved.", data=PatientMedicalRecordSerializer(record).data
        )


@extend_schema(tags=["Patient Records"])
class MedicalRecordEntryCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Create medical record entry", request=MedicalRecordEntryCreateSerializer
    )
    def post(self, request, record_id):
        record = get_object_or_404(PatientMedicalRecord, id=record_id)
        forbidden_fields = {
            "verification_status",
            "source_user",
            "source_role",
            "verified_by",
            "verified_at",
            "is_active",
        }
        provided_forbidden = sorted(forbidden_fields.intersection(set(request.data.keys())))
        if provided_forbidden:
            return error_response(
                "These fields are not allowed in this request.",
                errors={"forbidden_fields": provided_forbidden},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = MedicalRecordEntryCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        if request.user.user_type == UserType.PATIENT and record.patient_id != request.user.id:
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)
        if request.user.user_type == UserType.DOCTOR and not doctor_can_access_patient_record(
            request.user, record.patient
        ):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)
        if request.user.user_type in [UserType.PHARMACIST, UserType.LABORATORIAN]:
            return error_response(
                "This role cannot create generic medical record entries.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        try:
            entry = create_medical_record_entry(
                record=record,
                source_user=request.user,
                category=serializer.validated_data["category"],
                title=serializer.validated_data["title"],
                value=serializer.validated_data["value"],
                notes=serializer.validated_data.get("notes"),
                request=request,
            )
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        return success_response(
            "Medical record entry created.",
            data=MedicalRecordEntrySerializer(entry).data,
            status_code=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Patient Records"])
class MedicalRecordEntryConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Confirm or reject medical record entry",
        request=MedicalRecordEntryConfirmSerializer,
    )
    def post(self, request, entry_id):
        if request.user.user_type != UserType.DOCTOR:
            return error_response(
                "Only doctors can confirm entries.", status_code=status.HTTP_403_FORBIDDEN
            )

        entry = get_object_or_404(MedicalRecordEntry, id=entry_id, is_active=True)
        serializer = MedicalRecordEntryConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        if not doctor_can_access_patient_record(request.user, entry.medical_record.patient):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)

        try:
            entry = confirm_medical_record_entry(
                entry=entry,
                doctor=request.user,
                status=serializer.validated_data["verification_status"],
                notes=serializer.validated_data.get("notes"),
                request=request,
            )
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        return success_response(
            "Entry status updated.", data=MedicalRecordEntrySerializer(entry).data
        )


@extend_schema(tags=["Patient Records"])
class MedicalRecordEntryDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Deactivate medical record entry", request=MedicalRecordEntryDeactivateSerializer
    )
    def post(self, request, entry_id):
        entry = get_object_or_404(MedicalRecordEntry, id=entry_id, is_active=True)
        serializer = MedicalRecordEntryDeactivateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        if request.user.user_type == UserType.PATIENT:
            if entry.medical_record.patient_id != request.user.id:
                return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)
            if entry.verification_status != MedicalRecordVerificationStatus.SELF_REPORTED:
                return error_response(
                    "You can only deactivate self-reported entries.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        elif request.user.user_type == UserType.DOCTOR:
            if not doctor_can_access_patient_record(request.user, entry.medical_record.patient):
                return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)
        else:
            return error_response(
                "This role cannot deactivate entries.", status_code=status.HTTP_403_FORBIDDEN
            )

        entry.is_active = False
        notes = serializer.validated_data.get("notes")
        if notes:
            entry.notes = notes
        entry.save(update_fields=["is_active", "notes", "updated_at"])

        from apps.audit.services import create_audit_log

        create_audit_log(
            actor=request.user,
            action="medical_record_entry_deactivated",
            target=entry,
            metadata={
                "record_id": str(entry.medical_record_id),
                "entry_id": str(entry.id),
                "patient_id": str(entry.medical_record.patient_id),
                "actor_id": str(request.user.id),
                "category": entry.category,
                "verification_status": entry.verification_status,
            },
            request=request,
        )

        return success_response("Entry deactivated.", data=MedicalRecordEntrySerializer(entry).data)


@extend_schema(tags=["Patient Records"])
class SetBloodGroupView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Set blood group", request=SetBloodGroupSerializer)
    def post(self, request, record_id):
        record = get_object_or_404(PatientMedicalRecord, id=record_id)
        serializer = SetBloodGroupSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        if request.user.user_type == UserType.PATIENT and record.patient_id != request.user.id:
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)
        if request.user.user_type == UserType.DOCTOR and not doctor_can_access_patient_record(
            request.user, record.patient
        ):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)
        if request.user.user_type == UserType.LABORATORIAN:
            return error_response(
                "Laboratorians must use the verify endpoint.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if request.user.user_type == UserType.PHARMACIST:
            return error_response(
                "Pharmacists cannot set blood group.", status_code=status.HTTP_403_FORBIDDEN
            )

        try:
            blood_group_record = set_blood_group(
                record=record,
                user=request.user,
                blood_group=serializer.validated_data["blood_group"],
                notes=serializer.validated_data.get("notes"),
                request=request,
            )
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        return success_response(
            "Blood group updated.", data=BloodGroupRecordSerializer(blood_group_record).data
        )


@extend_schema(tags=["Patient Records"])
class LaboratorianVerifyBloodGroupView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Laboratory verify blood group", request=SetBloodGroupSerializer)
    def post(self, request, patient_id):
        if request.user.user_type != UserType.LABORATORIAN:
            return error_response(
                "Only laboratorians can use this endpoint.", status_code=status.HTTP_403_FORBIDDEN
            )

        patient = get_object_or_404(User, id=patient_id, user_type=UserType.PATIENT)
        serializer = SetBloodGroupSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        record = get_or_create_patient_medical_record(patient)
        try:
            blood_group_record = set_blood_group(
                record=record,
                user=request.user,
                blood_group=serializer.validated_data["blood_group"],
                notes=serializer.validated_data.get("notes"),
                request=request,
            )
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_403_FORBIDDEN)

        return success_response(
            "Blood group verified.", data=BloodGroupRecordSerializer(blood_group_record).data
        )
