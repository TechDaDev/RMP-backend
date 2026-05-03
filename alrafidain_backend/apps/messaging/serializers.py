from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import ConsultationMessage, MessageAttachment

User = get_user_model()


class MessageSenderSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "user_type"]
        read_only_fields = fields


class MessageAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = MessageSenderSummarySerializer(read_only=True)

    class Meta:
        model = MessageAttachment
        fields = ["id", "file", "original_name", "uploaded_by", "created_at"]
        read_only_fields = ["id", "original_name", "uploaded_by", "created_at"]


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
        attrs["body"] = body
        attrs["attachments"] = attachments
        return attrs
