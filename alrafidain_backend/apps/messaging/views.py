from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.audit.services import create_audit_log
from apps.common.responses import error_response, success_response
from apps.consultations.models import Consultation

from .models import ConsultationMessage
from .permissions import can_read_messages, can_send_messages
from .serializers import (
	ConsultationMessageCreateSerializer,
	ConsultationMessageSerializer,
)
from .services import create_consultation_message, mark_messages_as_read


@extend_schema(tags=["Messaging"])
class ConsultationMessageCreateView(APIView):
	permission_classes = [IsAuthenticated]

	def create_message(self, request, consultation):
		if not can_send_messages(request.user, consultation):
			return error_response(
				message="You are not allowed to send messages for this consultation.",
				status_code=status.HTTP_403_FORBIDDEN,
			)

		attachments = request.FILES.getlist("attachments") if hasattr(request, "FILES") else []
		serializer = ConsultationMessageCreateSerializer(
			data=request.data,
			context={"request": request, "attachments": attachments},
		)
		serializer.is_valid(raise_exception=True)

		message = create_consultation_message(
			consultation=consultation,
			sender=request.user,
			body=serializer.validated_data.get("body"),
			attachments=serializer.validated_data.get("attachments", []),
			request=request,
		)
		return success_response(
			message="Message sent successfully.",
			data=ConsultationMessageSerializer(message).data,
			status_code=status.HTTP_201_CREATED,
		)


@extend_schema(tags=["Messaging"])
class ConsultationMessageListView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(summary="List consultation messages")
	def get(self, request, consultation_id):
		consultation = get_object_or_404(Consultation, id=consultation_id)
		if not can_read_messages(request.user, consultation):
			return error_response(
				message="You are not allowed to view messages for this consultation.",
				status_code=status.HTTP_403_FORBIDDEN,
			)

		# Mark incoming unread messages as read when listing.
		mark_messages_as_read(consultation, request.user)

		queryset = ConsultationMessage.objects.filter(consultation=consultation).order_by("created_at")
		return success_response(data=ConsultationMessageSerializer(queryset, many=True).data)

	@extend_schema(summary="Create consultation message", request=ConsultationMessageCreateSerializer)
	def post(self, request, consultation_id):
		consultation = get_object_or_404(Consultation, id=consultation_id)
		return ConsultationMessageCreateView().create_message(request, consultation)


@extend_schema(tags=["Messaging"])
class ConsultationMarkMessagesReadView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(summary="Mark messages as read")
	def post(self, request, consultation_id):
		consultation = get_object_or_404(Consultation, id=consultation_id)
		if not can_read_messages(request.user, consultation):
			return error_response(
				message="You are not allowed to mark messages for this consultation.",
				status_code=status.HTTP_403_FORBIDDEN,
			)

		marked_count = mark_messages_as_read(consultation, request.user)
		create_audit_log(
			actor=request.user,
			action="consultation_messages_marked_read",
			target=consultation,
			metadata={
				"consultation_id": str(consultation.id),
				"reader_id": str(request.user.id),
				"marked_count": marked_count,
			},
			request=request,
		)
		return success_response(
			message="Messages marked as read.",
			data={"marked_count": marked_count},
		)
