from django.contrib import admin

from .models import (
	Consultation,
	ConsultationAttachment,
	ConsultationResponse,
	ConsultationSymptom,
	Symptom,
	SymptomCategory,
	SymptomSpecialtyRule,
)


@admin.register(SymptomCategory)
class SymptomCategoryAdmin(admin.ModelAdmin):
	list_display = ["name", "display_order", "is_active", "created_at"]
	list_filter = ["is_active", "created_at"]
	search_fields = ["name"]


@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
	list_display = ["name", "category", "is_red_flag", "is_active", "display_order"]
	list_filter = ["is_active", "is_red_flag", "category"]
	search_fields = ["name", "category__name"]


@admin.register(SymptomSpecialtyRule)
class SymptomSpecialtyRuleAdmin(admin.ModelAdmin):
	list_display = ["symptom", "specialty", "weight", "is_active", "created_at"]
	list_filter = ["specialty", "is_active", "created_at"]
	search_fields = ["symptom__name", "specialty"]


class ConsultationSymptomInline(admin.TabularInline):
	model = ConsultationSymptom
	extra = 0


class ConsultationAttachmentInline(admin.TabularInline):
	model = ConsultationAttachment
	extra = 0


class ConsultationResponseInline(admin.TabularInline):
	model = ConsultationResponse
	extra = 0


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
	list_display = [
		"id",
		"patient",
		"assigned_doctor",
		"status",
		"recommended_specialty",
		"selected_specialty",
		"severity",
		"duration",
		"has_emergency_warning",
		"created_at",
	]
	list_filter = [
		"status",
		"recommended_specialty",
		"selected_specialty",
		"severity",
		"duration",
		"has_emergency_warning",
		"created_at",
	]
	search_fields = ["patient__email", "assigned_doctor__email", "selected_specialty", "recommended_specialty"]
	inlines = [ConsultationSymptomInline, ConsultationAttachmentInline, ConsultationResponseInline]
	readonly_fields = ["created_at", "updated_at", "accepted_at", "closed_at"]


@admin.register(ConsultationSymptom)
class ConsultationSymptomAdmin(admin.ModelAdmin):
	list_display = ["consultation", "symptom", "created_at"]
	list_filter = ["created_at", "symptom__category"]
	search_fields = ["consultation__id", "symptom__name"]


@admin.register(ConsultationAttachment)
class ConsultationAttachmentAdmin(admin.ModelAdmin):
	list_display = ["consultation", "original_name", "uploaded_by", "created_at"]
	list_filter = ["created_at"]
	search_fields = ["consultation__id", "original_name", "uploaded_by__email"]


@admin.register(ConsultationResponse)
class ConsultationResponseAdmin(admin.ModelAdmin):
	list_display = ["consultation", "doctor", "recommendation_type", "created_at"]
	list_filter = ["recommendation_type", "created_at"]
	search_fields = ["consultation__id", "doctor__email", "response_text"]
