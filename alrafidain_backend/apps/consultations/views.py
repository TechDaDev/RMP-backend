from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.choices import ConsultationStatus, MedicalSpecialty, NotificationType, UserType
from apps.common.responses import error_response, success_response
from apps.notifications.services import create_notification

from .models import Consultation, Symptom, SymptomCategory
from .permissions import is_approved_doctor, is_assigned_doctor, is_consultation_patient
from .serializers import (
    ConsultationAcceptSerializer,
    ConsultationCloseSerializer,
    ConsultationCreateSerializer,
    ConsultationDoctorDetailSerializer,
    ConsultationListSerializer,
    ConsultationPatientDetailSerializer,
    ConsultationResponseCreateSerializer,
    ConsultationResponseSerializer,
    SymptomCategorySerializer,
    SymptomSerializer,
)
from .services import accept_consultation, close_consultation


@extend_schema(tags=["Symptoms"])
class SymptomCategoryListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SymptomCategorySerializer

    def get_queryset(self):
        return SymptomCategory.objects.filter(is_active=True).order_by("display_order", "name")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        return success_response(data=self.get_serializer(queryset, many=True).data)


@extend_schema(tags=["Symptoms"])
class SymptomListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SymptomSerializer

    def get_queryset(self):
        queryset = Symptom.objects.filter(is_active=True).select_related("category")
        category = self.request.query_params.get("category")
        is_red_flag = self.request.query_params.get("is_red_flag")

        if category:
            queryset = queryset.filter(category_id=category)

        if is_red_flag is not None:
            is_red_flag_value = is_red_flag.lower() in ["1", "true", "yes"]
            queryset = queryset.filter(is_red_flag=is_red_flag_value)

        return queryset.order_by("category__display_order", "display_order", "name")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        return success_response(data=self.get_serializer(queryset, many=True).data)


@extend_schema(tags=["Consultations"])
class ConsultationCreateView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConsultationCreateSerializer

    @extend_schema(summary="Create consultation", request=ConsultationCreateSerializer)
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        consultation = serializer.save()
        create_notification(
            recipient=request.user,
            notification_type=NotificationType.CONSULTATION,
            title="Consultation submitted",
            message="Your consultation request has been submitted.",
            data={"consultation_id": str(consultation.id), "status": consultation.status},
        )
        data = ConsultationPatientDetailSerializer(consultation).data
        return success_response(
            message="Consultation created successfully.",
            data=data,
            status_code=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Consultations"])
class MyConsultationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_type == UserType.PATIENT:
            queryset = Consultation.objects.filter(patient=request.user).select_related(
                "patient", "assigned_doctor"
            )
        elif request.user.user_type == UserType.DOCTOR:
            queryset = Consultation.objects.filter(assigned_doctor=request.user).select_related(
                "patient", "assigned_doctor"
            )
        else:
            return error_response(
                message="You do not have consultation access.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        data = ConsultationListSerializer(queryset, many=True).data
        return success_response(data=data)


@extend_schema(tags=["Consultations"])
class ConsultationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get consultation detail")
    def get(self, request, consultation_id):
        consultation = get_object_or_404(
            Consultation.objects.select_related("patient", "assigned_doctor").prefetch_related(
                "responses__doctor",
                "attachments__uploaded_by",
                "consultation_symptoms__symptom__category",
            ),
            id=consultation_id,
        )

        if is_consultation_patient(request.user, consultation):
            return success_response(data=ConsultationPatientDetailSerializer(consultation).data)

        if is_assigned_doctor(request.user, consultation):
            return success_response(data=ConsultationDoctorDetailSerializer(consultation).data)

        return error_response(
            message="You do not have access to this consultation.",
            status_code=status.HTTP_403_FORBIDDEN,
        )


@extend_schema(tags=["Consultations"])
class DoctorPendingConsultationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="List pending consultations for doctor specialty")
    def get(self, request):
        if not is_approved_doctor(request.user):
            return error_response(
                message="Only approved doctors can access pending consultations.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        specialty = request.user.doctor_profile.specialty
        queryset = Consultation.objects.filter(
            status=ConsultationStatus.SUBMITTED,
            assigned_doctor__isnull=True,
        ).select_related("patient", "assigned_doctor")
        matching_consultations = [
            consultation for consultation in queryset if consultation.matches_specialty(specialty)
        ]

        return success_response(data=ConsultationListSerializer(matching_consultations, many=True).data)


@extend_schema(tags=["Consultations"])
class DoctorAssignedConsultationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_approved_doctor(request.user):
            return error_response(
                message="Only approved doctors can access assigned consultations.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        queryset = Consultation.objects.filter(assigned_doctor=request.user).select_related(
            "patient", "assigned_doctor"
        )
        return success_response(data=ConsultationListSerializer(queryset, many=True).data)


@extend_schema(tags=["Consultations"])
class ConsultationAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Accept consultation")
    def post(self, request, consultation_id):
        consultation = Consultation.objects.select_related("assigned_doctor", "patient").prefetch_related(
            "responses__doctor",
            "attachments__uploaded_by",
            "consultation_symptoms__symptom__category",
        ).get(id=consultation_id)

        serializer = ConsultationAcceptSerializer(
            data=request.data,
            context={"request": request, "consultation": consultation},
        )
        serializer.is_valid(raise_exception=True)

        accept_consultation(consultation=consultation, doctor=request.user, request=request)

        return success_response(
            message="Consultation accepted successfully.",
            data=ConsultationDoctorDetailSerializer(consultation).data,
        )


@extend_schema(tags=["Consultations"])
class ConsultationResponseCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Create doctor response", request=ConsultationResponseCreateSerializer)
    def post(self, request, consultation_id):
        consultation = get_object_or_404(Consultation, id=consultation_id)
        serializer = ConsultationResponseCreateSerializer(
            data=request.data,
            context={"request": request, "consultation": consultation},
        )
        serializer.is_valid(raise_exception=True)
        response_obj = serializer.save()

        return success_response(
            message="Consultation response added.",
            data=ConsultationResponseSerializer(response_obj).data,
            status_code=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Consultations"])
class ConsultationCloseView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Close consultation")
    def post(self, request, consultation_id):
        consultation = get_object_or_404(Consultation, id=consultation_id)

        serializer = ConsultationCloseSerializer(
            data=request.data,
            context={"request": request, "consultation": consultation},
        )
        serializer.is_valid(raise_exception=True)

        close_consultation(consultation=consultation, doctor=request.user, request=request)

        return success_response(message="Consultation closed successfully.")
