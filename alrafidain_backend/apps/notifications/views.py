from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.responses import error_response, success_response

from .models import Notification
from .serializers import NotificationSerializer


@extend_schema(tags=["Notifications"])
class NotificationListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)
        is_read = self.request.query_params.get("is_read")
        notification_type = self.request.query_params.get("notification_type")
        if is_read is not None:
            qs = qs.filter(is_read=is_read.lower() in ("true", "1", "yes"))
        if notification_type:
            qs = qs.filter(notification_type=notification_type)
        return qs

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return success_response("Notifications retrieved.", data=serializer.data)


@extend_schema(tags=["Notifications"])
class UnreadNotificationCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return success_response("Unread count retrieved.", data={"unread_count": count})


@extend_schema(tags=["Notifications"])
class MarkNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id):
        notification = get_object_or_404(Notification, id=notification_id)
        if notification.recipient_id != request.user.id:
            return error_response("Not found.", status_code=404)
        notification.mark_as_read()
        return success_response("Notification marked as read.", data=NotificationSerializer(notification).data)


@extend_schema(tags=["Notifications"])
class MarkAllNotificationsReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        now = timezone.now()
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(
            is_read=True, read_at=now
        )
        return success_response("All notifications marked as read.", data={"updated_count": updated})
