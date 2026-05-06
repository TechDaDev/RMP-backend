from django.contrib import admin

from .models import BackgroundJob


@admin.register(BackgroundJob)
class BackgroundJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "task_name",
        "status",
        "created_by",
        "created_at",
        "started_at",
        "finished_at",
    )
    list_filter = ("status", "task_name")
    search_fields = ("id", "task_name", "celery_task_id", "created_by__email")
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
        "error_message",
    )
