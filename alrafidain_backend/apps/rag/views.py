from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.choices import RAGServiceContext

from .permissions import can_access_consultation_rag, can_access_lab_result_rag
from .serializers import (
    ConsultationRAGSupportSerializer,
    DoctorRAGQuerySerializer,
    LabResultRAGSupportSerializer,
    RAGResponseSerializer,
)
from .services import (
    build_consultation_summary_for_rag,
    build_lab_result_summary_for_rag,
    doctor_can_use_rag,
    run_doctor_rag_query,
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
    """POST /api/rag/consultations/<uuid:consultation_id>/support/ — RAG support for a specific consultation."""

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
