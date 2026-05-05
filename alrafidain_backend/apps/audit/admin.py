from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["action", "actor", "target_type", "target_id", "ip_address", "created_at"]
    list_filter = ["action", "created_at"]
    search_fields = ["actor__email", "action", "target_id"]
    readonly_fields = [
        "id",
        "actor",
        "action",
        "target_type",
        "target_id",
        "metadata",
        "ip_address",
        "user_agent",
        "created_at",
        "updated_at",
    ]
