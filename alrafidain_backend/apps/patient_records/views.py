from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.audit.services import create_audit_log
from apps.common.choices import (
    MedicalRecordVerificationStatus,
    MedicalReportProcessingStatus,
    NotificationType,
    UserType,
)
from apps.common.responses import error_response, success_response
from apps.consultations.models import Consultation
from apps.notifications.services import create_notification

from .models import MedicalRecordEntry, PatientMedicalRecord, PatientMedicalReport
from .permissions import can_review_medical_report, can_view_medical_report
from .serializers import (
    BloodGroupRecordSerializer,
    MedicalRecordEntryConfirmSerializer,
    MedicalRecordEntryCreateSerializer,
    MedicalRecordEntryDeactivateSerializer,
    MedicalRecordEntrySerializer,
    PatientMedicalRecordSerializer,
    PatientMedicalReportDetailSerializer,
    PatientMedicalReportDoctorReviewSerializer,
    PatientMedicalReportListSerializer,
    PatientMedicalReportLLMClassifySerializer,
    PatientMedicalReportOCRProcessSerializer,
    SetBloodGroupSerializer,
)
from .services import (
    classify_medical_report_with_llm,
    confirm_medical_record_entry,
    create_medical_record_entry,
    deactivate_medical_record_entry,
    doctor_can_access_patient_record,
    get_or_create_patient_medical_record,
    process_medical_report_ocr,
    set_blood_group,
)

User = get_user_model()


def _optimized_record_queryset():
    return PatientMedicalRecord.objects.select_related(
        "patient",
        "blood_group_record__source_user",
        "blood_group_record__verified_by",
    ).prefetch_related(
        Prefetch(
            "entries",
            queryset=MedicalRecordEntry.objects.filter(is_active=True)
            .select_related("source_user", "verified_by")
            .order_by("-created_at"),
            to_attr="active_entries",
        )
    )


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
        record = _optimized_record_queryset().get(pk=record.pk)
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
        record = _optimized_record_queryset().get(pk=record.pk)
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

        entry = deactivate_medical_record_entry(
            entry=entry,
            actor=request.user,
            notes=serializer.validated_data.get("notes"),
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


def _apply_medical_report_filters(queryset, request):
    report_type = request.query_params.get("report_type")
    if report_type:
        queryset = queryset.filter(report_type=report_type)

    processing_status = request.query_params.get("processing_status")
    if processing_status:
        queryset = queryset.filter(processing_status=processing_status)

    is_medical_report = request.query_params.get("is_medical_report")
    if is_medical_report is not None:
        queryset = queryset.filter(is_medical_report=is_medical_report.lower() == "true")

    return queryset


@extend_schema(tags=["Patient Medical Reports"])
class PatientMedicalReportListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="List patient medical report candidates")
    def get(self, request):
        if request.user.user_type != UserType.PATIENT:
            return error_response(
                "Only patients can access this endpoint.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        queryset = PatientMedicalReport.objects.filter(patient=request.user).select_related(
            "consultation",
            "reviewed_by",
        )
        queryset = _apply_medical_report_filters(queryset, request)
        data = PatientMedicalReportListSerializer(
            queryset.order_by("-created_at"),
            many=True,
            context={"request": request},
        ).data
        return success_response(data=data)


@extend_schema(tags=["Patient Medical Reports"])
class PatientMedicalReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get patient medical report candidate detail")
    def get(self, request, report_id):
        report = get_object_or_404(
            PatientMedicalReport.objects.select_related(
                "patient",
                "consultation",
                "source_message",
                "source_attachment",
                "linked_medical_record_entry",
                "reviewed_by",
            ),
            id=report_id,
        )

        if not can_view_medical_report(request.user, report):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)

        data = PatientMedicalReportDetailSerializer(report, context={"request": request}).data
        return success_response(data=data)


@extend_schema(tags=["Patient Medical Reports"])
class DoctorConsultationMedicalReportListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="List medical report candidates for a doctor consultation")
    def get(self, request, consultation_id):
        if request.user.user_type != UserType.DOCTOR:
            return error_response(
                "Only doctors can access this endpoint.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        try:
            consultation = Consultation.objects.get(id=consultation_id)
        except Consultation.DoesNotExist:
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)

        if consultation.assigned_doctor_id != request.user.id:
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)

        queryset = PatientMedicalReport.objects.filter(consultation=consultation).select_related(
            "patient",
            "consultation",
            "reviewed_by",
        )
        queryset = _apply_medical_report_filters(queryset, request)
        data = PatientMedicalReportListSerializer(
            queryset.order_by("-created_at"),
            many=True,
            context={"request": request},
        ).data
        return success_response(data=data)


@extend_schema(tags=["Patient Medical Reports"])
class DoctorMedicalReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get doctor medical report candidate detail")
    def get(self, request, report_id):
        if not (request.user.user_type == UserType.DOCTOR or request.user.is_staff):
            return error_response(
                "Only doctors can access this endpoint.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        report = get_object_or_404(
            PatientMedicalReport.objects.select_related(
                "patient",
                "consultation",
                "source_message",
                "source_attachment",
                "linked_medical_record_entry",
                "reviewed_by",
            ),
            id=report_id,
        )

        if not can_view_medical_report(request.user, report):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)

        data = PatientMedicalReportDetailSerializer(report, context={"request": request}).data
        return success_response(data=data)


@extend_schema(tags=["Patient Medical Reports"])
class DoctorMedicalReportReviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Review medical report candidate",
        request=PatientMedicalReportDoctorReviewSerializer,
    )
    def post(self, request, report_id):
        if not (request.user.user_type == UserType.DOCTOR or request.user.is_staff):
            return error_response(
                "Only doctors can access this endpoint.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        report = get_object_or_404(
            PatientMedicalReport.objects.select_related("consultation"),
            id=report_id,
        )

        if not can_review_medical_report(request.user, report):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)

        serializer = PatientMedicalReportDoctorReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        if "doctor_notes" in data:
            report.doctor_notes = data["doctor_notes"]
        if "report_type" in data:
            report.report_type = data["report_type"]
        if "is_medical_report" in data:
            report.is_medical_report = data["is_medical_report"]
        if "processing_status" in data:
            report.processing_status = data["processing_status"]

        if data.get("mark_reviewed", True):
            report.reviewed_by = request.user
            report.reviewed_at = timezone.now()
            if "processing_status" not in data:
                report.processing_status = MedicalReportProcessingStatus.DOCTOR_REVIEWED

        try:
            report.full_clean()
        except ValidationError as exc:
            return error_response(
                "Invalid input.",
                errors=exc.message_dict,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        report.save()

        create_notification(
            recipient=report.patient,
            notification_type=NotificationType.MEDICAL_RECORD,
            title="Medical report reviewed",
            message="A doctor reviewed one of your uploaded medical reports.",
            data={
                "medical_report_id": str(report.id),
                "consultation_id": str(report.consultation_id) if report.consultation_id else None,
            },
        )

        return success_response(
            message="Medical report reviewed.",
            data=PatientMedicalReportDetailSerializer(report, context={"request": request}).data,
        )


@extend_schema(tags=["Patient Medical Reports"])
class DoctorMedicalReportProcessOCRView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Process OCR for medical report candidate",
        request=PatientMedicalReportOCRProcessSerializer,
    )
    def post(self, request, report_id):
        if not (request.user.user_type == UserType.DOCTOR or request.user.is_staff):
            return error_response(
                "Only doctors can access this endpoint.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        report = get_object_or_404(
            PatientMedicalReport.objects.select_related(
                "patient",
                "consultation",
                "source_message",
                "source_attachment",
                "linked_medical_record_entry",
                "reviewed_by",
            ),
            id=report_id,
        )

        if not can_review_medical_report(request.user, report):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)

        serializer = PatientMedicalReportOCRProcessSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        force = serializer.validated_data.get("force", False)
        create_audit_log(
            actor=request.user,
            action="medical_report_ocr_triggered_by_doctor",
            target=report,
            metadata={
                "report_id": str(report.id),
                "patient_id": str(report.patient_id),
                "consultation_id": str(report.consultation_id) if report.consultation_id else None,
                "source_attachment_id": (
                    str(report.source_attachment_id) if report.source_attachment_id else None
                ),
                "processing_status": report.processing_status,
                "force": bool(force),
            },
            request=request,
        )
        report = process_medical_report_ocr(report=report, request=request, force=force)
        data = PatientMedicalReportDetailSerializer(report, context={"request": request}).data
        return success_response(message="Medical report OCR processed.", data=data)


@extend_schema(tags=["Patient Medical Reports"])
class DoctorMedicalReportClassifyLLMView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Classify medical report candidate with LLM",
        request=PatientMedicalReportLLMClassifySerializer,
    )
    def post(self, request, report_id):
        if not (request.user.user_type == UserType.DOCTOR or request.user.is_staff):
            return error_response(
                "Only doctors can access this endpoint.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not bool(getattr(settings, "CLINICAL_REPORT_LLM_ENABLED", False)):
            return error_response(
                "LLM classification is disabled.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        report = get_object_or_404(
            PatientMedicalReport.objects.select_related(
                "patient",
                "consultation",
                "source_message",
                "source_attachment",
                "linked_medical_record_entry",
                "reviewed_by",
            ),
            id=report_id,
        )

        if not can_review_medical_report(request.user, report):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)

        serializer = PatientMedicalReportLLMClassifySerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        force = serializer.validated_data.get("force", False)
        create_audit_log(
            actor=request.user,
            action="medical_report_llm_triggered_by_doctor",
            target=report,
            metadata={
                "report_id": str(report.id),
                "patient_id": str(report.patient_id),
                "consultation_id": str(report.consultation_id) if report.consultation_id else None,
                "source_attachment_id": (
                    str(report.source_attachment_id) if report.source_attachment_id else None
                ),
                "processing_status": report.processing_status,
                "force": bool(force),
            },
            request=request,
        )

        report = classify_medical_report_with_llm(
            report=report,
            request=request,
            force=force,
        )
        data = PatientMedicalReportDetailSerializer(report, context={"request": request}).data
        return success_response(message="Medical report LLM classification processed.", data=data)
