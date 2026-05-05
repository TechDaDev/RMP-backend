from django.contrib import admin

from .models import ConsultationMessage, MessageAttachment


class MessageAttachmentInline(admin.TabularInline):
    model = MessageAttachment
    extra = 0
    readonly_fields = ["created_at", "updated_at", "uploaded_by", "original_name"]


@admin.register(ConsultationMessage)
class ConsultationMessageAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "consultation",
        "sender",
        "sender_role",
        "message_type",
        "is_read",
        "created_at",
    ]
    list_filter = ["sender_role", "message_type", "is_read", "created_at"]
    search_fields = ["consultation__id", "sender__email", "body"]
    readonly_fields = [
        "consultation",
        "sender",
        "sender_role",
        "message_type",
        "body",
        "is_read",
        "read_at",
        "created_at",
        "updated_at",
    ]
    inlines = [MessageAttachmentInline]


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ["id", "message", "original_name", "uploaded_by", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["message__consultation__id", "uploaded_by__email", "original_name"]
    readonly_fields = [
        "message",
        "file",
        "original_name",
        "uploaded_by",
        "created_at",
        "updated_at",
    ]
