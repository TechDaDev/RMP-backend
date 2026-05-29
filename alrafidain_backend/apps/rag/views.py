from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import create_audit_log, record_security_event
from apps.common.choices import RAGServiceContext
from apps.common.permissions import CanExportRagDataset
from apps.common.staff_access import has_staff_capability
from apps.consultations.models import Consultation
from apps.patient_records.models import PatientMedicalReport

from .assistant_services import generate_doctor_ai_message_for_report, mark_doctor_ai_message_read
from .models import DoctorAIAssistantMessage, RAGResponse, RAGResponseFeedback
from .permissions import (
    can_access_consultation_rag,
    can_access_doctor_ai_assistant_message,
    can_access_lab_result_rag,
    can_list_doctor_ai_messages_for_consultation,
)
from .serializers import (
    ConsultationRAGSupportSerializer,
    DoctorAIAssistantGenerateFromReportSerializer,
    DoctorAIAssistantMarkReadSerializer,
    DoctorAIAssistantMessageSerializer,
    DoctorRAGQuerySerializer,
    LabResultRAGSupportSerializer,
    MedicalReportRAGSupportSerializer,
    RAGAnalyticsSummarySerializer,
    RAGDatasetExportSerializer,
    RAGFeedbackReviewSerializer,
    RAGResponseFeedbackCreateSerializer,
    RAGResponseFeedbackSerializer,
    RAGResponseSaveToRecordSerializer,
    RAGResponseSerializer,
)
from .services import (
    build_consultation_summary_for_rag,
    build_lab_result_summary_for_rag,
    doctor_can_use_rag,
    review_rag_feedback,
    run_doctor_rag_query,
    run_medical_report_case_update_rag,
    save_rag_response_to_patient_record,
    submit_rag_response_feedback,
)

_DEFAULT_CONSULTATION_QUESTION = (
    "Based on the consultation data, provide a doctor-facing summary, relevant red flags, "
    "and suggested follow-up questions using approved medical sources."
)

_DEFAULT_LAB_RESULT_QUESTION = (
    "Explain this lab result for doctor review, including possible clinical relevance "
    "and follow-up considerations using approved laboratory references."
)


class DoctorGeneralRAGQueryView(APIView):
    """POST /api/rag/doctor/query/ — general RAG query for approved doctors."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not doctor_can_use_rag(request.user):
            return Response(
                {"detail": "Only approved doctors may use the RAG endpoint."},
                status=403,
            )

        serializer = DoctorRAGQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        top_k = data.get("top_k") or getattr(settings, "RAG_DEFAULT_TOP_K", 6)
        filters = {
            k: v
            for k, v in {
                "document_type": data.get("document_type") or None,
                "specialty": data.get("specialty") or None,
                "language": data.get("language") or None,
                "audience": data.get("audience") or None,
            }.items()
            if v
        }

        _, rag_response = run_doctor_rag_query(
            doctor=request.user,
            query_text=data["question"],
            service_context=RAGServiceContext.GENERAL_DOCTOR_QUERY,
            filters=filters,
            top_k=top_k,
            request=request,
        )

        return Response(RAGResponseSerializer(rag_response).data, status=200)


class ConsultationRAGSupportView(APIView):
    """
    POST /api/rag/consultations/<uuid:consultation_id>/support/ —
    RAG support for a specific consultation.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, consultation_id):
        from apps.consultations.models import Consultation

        consultation = get_object_or_404(Consultation, pk=consultation_id)

        if not can_access_consultation_rag(request.user, consultation):
            return Response(
                {"detail": "You do not have permission to query RAG for this consultation."},
                status=403,
            )

        serializer = ConsultationRAGSupportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        question = data.get("question") or _DEFAULT_CONSULTATION_QUESTION
        top_k = data.get("top_k") or getattr(settings, "RAG_DEFAULT_TOP_K", 6)
        object_summary = build_consultation_summary_for_rag(consultation)

        _, rag_response = run_doctor_rag_query(
            doctor=request.user,
            query_text=question,
            service_context=RAGServiceContext.CONSULTATION,
            object_id=consultation.pk,
            top_k=top_k,
            object_summary=object_summary,
            request=request,
        )

        return Response(RAGResponseSerializer(rag_response).data, status=200)


class LabResultRAGSupportView(APIView):
    """POST /api/rag/lab-results/<uuid:lab_result_id>/support/ — RAG support for a lab result."""

    permission_classes = [IsAuthenticated]

    def post(self, request, lab_result_id):
        from apps.lab_orders.models import LabResult

        lab_result = get_object_or_404(LabResult, pk=lab_result_id)

        if not can_access_lab_result_rag(request.user, lab_result):
            return Response(
                {"detail": "You do not have permission to query RAG for this lab result."},
                status=403,
            )

        serializer = LabResultRAGSupportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        question = data.get("question") or _DEFAULT_LAB_RESULT_QUESTION
        top_k = data.get("top_k") or getattr(settings, "RAG_DEFAULT_TOP_K", 6)
        object_summary = build_lab_result_summary_for_rag(lab_result)

        _, rag_response = run_doctor_rag_query(
            doctor=request.user,
            query_text=question,
            service_context=RAGServiceContext.LAB_RESULT,
            object_id=lab_result.pk,
            top_k=top_k,
            object_summary=object_summary,
            request=request,
        )

        return Response(RAGResponseSerializer(rag_response).data, status=200)


class MedicalReportCaseUpdateRAGView(APIView):
    """POST /api/rag/medical-reports/<uuid:report_id>/case-update/.

    Run doctor-facing RAG update using a saved medical report context.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, report_id):
        if not doctor_can_use_rag(request.user):
            return Response(
                {"detail": "Only approved doctors can use RAG case updates."},
                status=403,
            )

        report = get_object_or_404(
            PatientMedicalReport.objects.select_related(
                "patient",
                "consultation",
                "linked_medical_record_entry",
            ),
            pk=report_id,
        )

        serializer = MedicalReportRAGSupportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        top_k = data.get("top_k") or getattr(settings, "RAG_DEFAULT_TOP_K", 6)
        filters = {
            key: value
            for key, value in {
                "document_type": data.get("document_type") or None,
                "specialty": data.get("specialty") or None,
                "language": data.get("language") or None,
                "audience": data.get("audience") or None,
            }.items()
            if value
        }

        try:
            _, rag_response = run_medical_report_case_update_rag(
                doctor=request.user,
                report=report,
                question=data.get("question"),
                top_k=top_k,
                filters=filters,
                request=request,
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(RAGResponseSerializer(rag_response).data, status=200)


class ConsultationDoctorAIAssistantMessageListView(APIView):
    """GET /api/rag/consultations/<uuid:consultation_id>/doctor-ai-messages/."""

    permission_classes = [IsAuthenticated]

    def get(self, request, consultation_id):
        consultation = get_object_or_404(Consultation, pk=consultation_id)
        if not can_list_doctor_ai_messages_for_consultation(request.user, consultation):
            return Response(
                {"detail": "You do not have permission to view AI assistant messages."},
                status=403,
            )

        qs = DoctorAIAssistantMessage.objects.filter(
            consultation=consultation,
            doctor=request.user,
        ).select_related(
            "source_report",
            "source_rag_response",
            "source_medical_record_entry",
        )

        status_value = request.query_params.get("status")
        if status_value:
            qs = qs.filter(status=status_value)

        trigger_type = request.query_params.get("trigger_type")
        if trigger_type:
            qs = qs.filter(trigger_type=trigger_type)

        source_report = request.query_params.get("source_report")
        if source_report:
            qs = qs.filter(source_report_id=source_report)

        return Response(DoctorAIAssistantMessageSerializer(qs, many=True).data, status=200)


class DoctorAIAssistantMessageDetailView(APIView):
    """GET /api/rag/doctor-ai-messages/<uuid:message_id>/."""

    permission_classes = [IsAuthenticated]

    def get(self, request, message_id):
        message = get_object_or_404(
            DoctorAIAssistantMessage.objects.select_related(
                "consultation",
                "source_report",
                "source_rag_response",
                "source_medical_record_entry",
            ),
            pk=message_id,
        )
        if not can_access_doctor_ai_assistant_message(request.user, message):
            return Response(
                {"detail": "You do not have permission to view this AI assistant message."},
                status=403,
            )
        return Response(DoctorAIAssistantMessageSerializer(message).data, status=200)


class MedicalReportDoctorAIAssistantGenerateView(APIView):
    """POST /api/rag/medical-reports/<uuid:report_id>/doctor-ai-message/."""

    permission_classes = [IsAuthenticated]

    def post(self, request, report_id):
        report = get_object_or_404(
            PatientMedicalReport.objects.select_related(
                "patient",
                "consultation",
                "linked_medical_record_entry",
            ),
            pk=report_id,
        )

        serializer = DoctorAIAssistantGenerateFromReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            message = generate_doctor_ai_message_for_report(
                doctor=request.user,
                report=report,
                question=data.get("question"),
                top_k=data.get("top_k"),
                force=data.get("force", False),
                create_if_exists=data.get("create_if_exists", False),
                save_rag_response=data.get("save_rag_response", True),
                request=request,
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(DoctorAIAssistantMessageSerializer(message).data, status=200)


class DoctorAIAssistantMessageMarkReadView(APIView):
    """POST /api/rag/doctor-ai-messages/<uuid:message_id>/mark-read/."""

    permission_classes = [IsAuthenticated]

    def post(self, request, message_id):
        message = get_object_or_404(DoctorAIAssistantMessage, pk=message_id)
        serializer = DoctorAIAssistantMarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated = mark_doctor_ai_message_read(
                message,
                request.user,
                read=serializer.validated_data.get("read", True),
                request=request,
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)

        return Response(DoctorAIAssistantMessageSerializer(updated).data, status=200)


# ---------------------------------------------------------------------------
# Phase 12D — Feedback views
# ---------------------------------------------------------------------------


class RAGResponseFeedbackCreateView(APIView):
    """POST /api/rag/responses/<uuid:rag_response_id>/feedback/ — submit feedback."""

    permission_classes = [IsAuthenticated]

    def post(self, request, rag_response_id):
        if not doctor_can_use_rag(request.user):
            return Response(
                {"detail": "Only approved doctors may submit RAG feedback."},
                status=403,
            )

        rag_response = get_object_or_404(RAGResponse, pk=rag_response_id)

        if rag_response.rag_query.requested_by_id != request.user.pk:
            return Response(
                {"detail": "You can only submit feedback for your own RAG responses."},
                status=403,
            )

        serializer = RAGResponseFeedbackCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        try:
            feedback = submit_rag_response_feedback(
                rag_response=rag_response,
                doctor=request.user,
                rating=d["rating"],
                comment=d.get("comment") or None,
                is_source_grounded=d.get("is_source_grounded"),
                is_clinically_useful=d.get("is_clinically_useful"),
                is_safe=d.get("is_safe", True),
                source_feedback=d.get("source_feedback") or [],
                request=request,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)

        return Response(RAGResponseFeedbackSerializer(feedback).data, status=201)


class RAGResponseSaveToPatientRecordView(APIView):
    """POST /api/rag/responses/<uuid:rag_response_id>/save-to-record/.

    Persist doctor-approved RAG response into the canonical patient record.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, rag_response_id):
        if not doctor_can_use_rag(request.user):
            return Response(
                {"detail": "Only approved doctors may save RAG responses to patient records."},
                status=403,
            )

        rag_response = get_object_or_404(
            RAGResponse.objects.select_related("rag_query"),
            pk=rag_response_id,
        )

        serializer = RAGResponseSaveToRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            entry = save_rag_response_to_patient_record(
                rag_response=rag_response,
                doctor=request.user,
                physician_notes=serializer.validated_data.get("physician_notes", ""),
                request=request,
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        from apps.patient_records.serializers import MedicalRecordEntrySerializer

        return Response(MedicalRecordEntrySerializer(entry).data, status=201)


class MyRAGFeedbackListView(APIView):
    """GET /api/rag/feedback/my/ — list own feedback."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not doctor_can_use_rag(request.user):
            return Response(
                {"detail": "Only approved doctors may view RAG feedback."},
                status=403,
            )

        qs = (
            RAGResponseFeedback.objects.filter(doctor=request.user)
            .select_related("rag_response", "doctor", "reviewed_by")
            .prefetch_related("source_feedback__retrieved_chunk")
        )

        rating = request.query_params.get("rating")
        if rating:
            qs = qs.filter(rating=rating)

        needs_admin_review = request.query_params.get("needs_admin_review")
        if needs_admin_review is not None:
            qs = qs.filter(needs_admin_review=needs_admin_review.lower() == "true")

        review_status = request.query_params.get("review_status")
        if review_status:
            qs = qs.filter(review_status=review_status)

        return Response(RAGResponseFeedbackSerializer(qs, many=True).data, status=200)


class AdminRAGFeedbackListView(APIView):
    """GET /api/rag/admin/feedback/ — staff list all feedback."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not has_staff_capability(request.user, "review_rag_feedback"):
            return Response({"detail": "Permission denied for RAG feedback review."}, status=403)

        qs = (
            RAGResponseFeedback.objects.all()
            .select_related("rag_response", "doctor", "reviewed_by")
            .prefetch_related("source_feedback__retrieved_chunk")
        )

        for field in ["rating", "review_status"]:
            val = request.query_params.get(field)
            if val is not None:
                qs = qs.filter(**{field: val})

        for bool_field in ["is_safe", "needs_admin_review"]:
            val = request.query_params.get(bool_field)
            if val is not None:
                qs = qs.filter(**{bool_field: val.lower() == "true"})

        return Response(RAGResponseFeedbackSerializer(qs, many=True).data, status=200)


class AdminRAGFeedbackReviewView(APIView):
    """POST /api/rag/admin/feedback/<uuid:feedback_id>/review/ — staff review action."""

    permission_classes = [IsAuthenticated]

    def post(self, request, feedback_id):
        if not has_staff_capability(request.user, "review_rag_feedback"):
            return Response({"detail": "Permission denied for RAG feedback review."}, status=403)

        feedback = get_object_or_404(RAGResponseFeedback, pk=feedback_id)

        serializer = RAGFeedbackReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        try:
            updated = review_rag_feedback(
                feedback=feedback,
                reviewer=request.user,
                review_status=d["review_status"],
                review_notes=d.get("review_notes") or None,
                request=request,
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=403)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(RAGResponseFeedbackSerializer(updated).data, status=200)


# ---------------------------------------------------------------------------
# Phase 12E — Analytics and export views
# ---------------------------------------------------------------------------


class AdminRAGAnalyticsSummaryView(APIView):
    """GET /api/rag/admin/analytics/summary/ — RAG analytics for staff."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not has_staff_capability(request.user, "view_rag_analytics"):
            record_security_event(
                actor=request.user,
                action="rag_analytics_access_denied",
                request=request,
                metadata={"reason_code": "policy_denied"},
            )
            return Response({"detail": "Permission denied for RAG analytics."}, status=403)

        from .analytics import get_rag_analytics_summary

        summary = get_rag_analytics_summary()

        create_audit_log(
            actor=request.user,
            action="rag_analytics_viewed",
            metadata={"requested_by": str(request.user.pk)},
            request=request,
        )

        return Response(RAGAnalyticsSummarySerializer(summary).data, status=200)


class AdminRAGDatasetExportView(APIView):
    """POST /api/rag/admin/exports/dataset/ — export evaluation dataset."""

    permission_classes = [IsAuthenticated, CanExportRagDataset]

    def post(self, request):
        if not has_staff_capability(request.user, "export_datasets"):
            record_security_event(
                actor=request.user,
                action="rag_dataset_export_access_denied",
                request=request,
                metadata={"reason_code": "policy_denied"},
            )
            return Response({"detail": "Permission denied for dataset export."}, status=403)

        serializer = RAGDatasetExportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        fmt: str = d["format"]
        include_text: bool = d["include_text"]
        anonymize: bool = d["anonymize"]
        max_rows: int = d["max_rows"]

        from .exporters import export_rag_evaluation_dataset

        try:
            content = export_rag_evaluation_dataset(
                format=fmt,
                include_text=include_text,
                anonymize=anonymize,
                max_rows=max_rows,
            )
        except ValueError as exc:
            record_security_event(
                actor=request.user,
                action="rag_dataset_export_rejected",
                request=request,
                metadata={
                    "reason_code": "invalid_export_scope",
                    "format": fmt,
                    "include_text": include_text,
                    "anonymize": anonymize,
                    "max_rows": max_rows,
                },
            )
            return Response({"detail": str(exc)}, status=400)

        record_count = len(content) if fmt == "json" else max(0, content.count("\n") - 1)

        create_audit_log(
            actor=request.user,
            action="rag_dataset_exported",
            metadata={
                "format": fmt,
                "include_text": include_text,
                "anonymize": anonymize,
                "record_count": record_count,
                "requested_by": str(request.user.pk),
            },
            request=request,
        )

        if fmt == "csv":
            from django.http import HttpResponse

            response = HttpResponse(content, content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="rag_eval_dataset.csv"'
            return response

        return Response({"format": fmt, "record_count": record_count, "data": content}, status=200)
