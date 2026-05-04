from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.audit.services import create_audit_log
from apps.common.choices import ConsultationStatus, MedicalSpecialty, UserType
from apps.common.responses import error_response, success_response
from apps.notifications.services import create_notification
from apps.common.choices import NotificationType

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
			queryset = Consultation.objects.filter(patient=request.user)
		elif request.user.user_type == UserType.DOCTOR:
			queryset = Consultation.objects.filter(assigned_doctor=request.user)
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
		consultation = get_object_or_404(Consultation, id=consultation_id)

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
			selected_specialty=specialty,
		)

		if specialty == MedicalSpecialty.OTHER:
			queryset = queryset.filter(selected_specialty=MedicalSpecialty.OTHER)

		return success_response(data=ConsultationListSerializer(queryset, many=True).data)


@extend_schema(tags=["Consultations"])
class DoctorAssignedConsultationListView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		if not is_approved_doctor(request.user):
			return error_response(
				message="Only approved doctors can access assigned consultations.",
				status_code=status.HTTP_403_FORBIDDEN,
			)
		queryset = Consultation.objects.filter(assigned_doctor=request.user)
		return success_response(data=ConsultationListSerializer(queryset, many=True).data)


@extend_schema(tags=["Consultations"])
class ConsultationAcceptView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(summary="Accept consultation")
	@transaction.atomic
	def post(self, request, consultation_id):
		consultation = (
			Consultation.objects.select_for_update()
			.select_related("assigned_doctor", "patient")
			.get(id=consultation_id)
		)

		serializer = ConsultationAcceptSerializer(
			data=request.data,
			context={"request": request, "consultation": consultation},
		)
		serializer.is_valid(raise_exception=True)

		consultation.assigned_doctor = request.user
		consultation.status = ConsultationStatus.ACCEPTED
		consultation.accepted_at = timezone.now()
		consultation.save(update_fields=["assigned_doctor", "status", "accepted_at", "updated_at"])

		create_audit_log(
			actor=request.user,
			action="consultation_accepted",
			target=consultation,
			request=request,
		)
		create_notification(
			recipient=consultation.patient,
			notification_type=NotificationType.CONSULTATION,
			title="Consultation accepted",
			message="A doctor has accepted your consultation.",
			data={"consultation_id": str(consultation.id), "doctor_id": str(request.user.id), "status": ConsultationStatus.ACCEPTED},
		)
		
		# Broadcast consultation update event (Phase 14)
		def broadcast_update():
			from apps.realtime.services import broadcast_consultation_updated
			try:
				broadcast_consultation_updated(consultation)
			except Exception as e:
				import logging
				logger = logging.getLogger(__name__)
				logger.error(f"Failed to broadcast consultation.updated event: {e}")
		
		transaction.on_commit(broadcast_update)
		
		return success_response(message="Consultation accepted successfully.")


@extend_schema(tags=["Consultations"])
class ConsultationResponseCreateView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(summary="Create doctor response", request=ConsultationResponseCreateSerializer)
	@transaction.atomic
	def post(self, request, consultation_id):
		consultation = get_object_or_404(Consultation, id=consultation_id)
		serializer = ConsultationResponseCreateSerializer(
			data=request.data,
			context={"request": request, "consultation": consultation},
		)
		serializer.is_valid(raise_exception=True)
		response_obj = serializer.save()
		create_notification(
			recipient=consultation.patient,
			notification_type=NotificationType.CONSULTATION,
			title="Doctor response added",
			message="Your doctor has added a response to your consultation.",
			data={"consultation_id": str(consultation.id), "status": ConsultationStatus.DOCTOR_RESPONDED},
		)
		
		# Broadcast consultation update event (Phase 14)
		def broadcast_update():
			from apps.realtime.services import broadcast_consultation_updated
			try:
				# Refresh consultation to get updated status
				consultation.refresh_from_db()
				broadcast_consultation_updated(consultation)
			except Exception as e:
				import logging
				logger = logging.getLogger(__name__)
				logger.error(f"Failed to broadcast consultation.updated event: {e}")
		
		transaction.on_commit(broadcast_update)
		
		return success_response(
			message="Consultation response added.",
			data=ConsultationResponseSerializer(response_obj).data,
			status_code=status.HTTP_201_CREATED,
		)


@extend_schema(tags=["Consultations"])
class ConsultationCloseView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(summary="Close consultation")
	@transaction.atomic
	def post(self, request, consultation_id):
		consultation = get_object_or_404(Consultation, id=consultation_id)

		serializer = ConsultationCloseSerializer(
			data=request.data,
			context={"request": request, "consultation": consultation},
		)
		serializer.is_valid(raise_exception=True)

		consultation.status = ConsultationStatus.CLOSED
		consultation.closed_at = timezone.now()
		consultation.save(update_fields=["status", "closed_at", "updated_at"])

		create_audit_log(
			actor=request.user,
			action="consultation_closed",
			target=consultation,
			request=request,
		)
		create_notification(
			recipient=consultation.patient,
			notification_type=NotificationType.CONSULTATION,
			title="Consultation closed",
			message="Your consultation has been closed.",
			data={"consultation_id": str(consultation.id), "status": ConsultationStatus.CLOSED},
		)
		
		# Broadcast consultation update event (Phase 14)
		def broadcast_update():
			from apps.realtime.services import broadcast_consultation_updated
			try:
				broadcast_consultation_updated(consultation)
			except Exception as e:
				import logging
				logger = logging.getLogger(__name__)
				logger.error(f"Failed to broadcast consultation.updated event: {e}")
		
		transaction.on_commit(broadcast_update)
		
		return success_response(message="Consultation closed successfully.")
