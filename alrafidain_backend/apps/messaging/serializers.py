from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.common.file_validation import validate_uploaded_file

from .models import ConsultationMessage, MessageAttachment

User = get_user_model()


class MessageSenderSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "user_type"]
        read_only_fields = fields


class MessageAttachmentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(read_only=True, use_url=False)
    file_url = serializers.SerializerMethodField()
    uploaded_by = MessageSenderSummarySerializer(read_only=True)

    class Meta:
        model = MessageAttachment
        fields = ["id", "file", "file_url", "original_name", "uploaded_by", "created_at"]
        read_only_fields = ["id", "original_name", "uploaded_by", "created_at"]

    def get_file_url(self, obj):
        if not obj.file:
            return ""

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.file.url)

        # Fallback for realtime events without HTTP request context.
        url = obj.file.url
        if url and not url.startswith("/"):
            url = f"/{url}"
        return url


class ConsultationMessageSerializer(serializers.ModelSerializer):
    sender = MessageSenderSummarySerializer(read_only=True)
    attachments = MessageAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = ConsultationMessage
        fields = [
            "id",
            "consultation",
            "sender",
            "sender_role",
            "message_type",
            "body",
            "attachments",
            "is_read",
            "read_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ConsultationRealtimeMessageSerializer(serializers.ModelSerializer):
    sender = MessageSenderSummarySerializer(read_only=True)
    attachments = MessageAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = ConsultationMessage
        fields = [
            "id",
            "sender",
            "sender_role",
            "message_type",
            "body",
            "attachments",
            "is_read",
            "created_at",
        ]
        read_only_fields = fields


class ConsultationMessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True)
    attachments = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True,
    )

    def validate(self, attrs):
        body = (attrs.get("body") or "").strip()
        attachments = attrs.get("attachments")
        if attachments is None:
            attachments = self.context.get("attachments", [])
        if not body and len(attachments) == 0:
            raise serializers.ValidationError("At least body or one attachment is required.")

        for file_obj in attachments:
            validate_uploaded_file(
                file_obj,
                allowed_extensions=settings.CLINICAL_ATTACHMENT_ALLOWED_EXTENSIONS,
                allowed_content_types=settings.CLINICAL_ATTACHMENT_ALLOWED_CONTENT_TYPES,
                max_size_mb=settings.MAX_CLINICAL_ATTACHMENT_UPLOAD_MB,
            )

        attrs["body"] = body
        attrs["attachments"] = attachments
        return attrs
