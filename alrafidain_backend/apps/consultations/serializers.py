from django.db import transaction
from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.audit.services import create_audit_log
from apps.common.choices import ConsultationStatus, MedicalSpecialty

from .models import (
    Consultation,
    ConsultationAttachment,
    ConsultationResponse,
    ConsultationSymptom,
    Symptom,
    SymptomCategory,
    SymptomSpecialtyRule,
)
from .permissions import is_approved_doctor, is_assigned_doctor, is_patient
from .services import add_consultation_response, recommend_specialty_from_symptoms


class SymptomCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SymptomCategory
        fields = ["id", "name", "description", "display_order"]


class SymptomSerializer(serializers.ModelSerializer):
    category = SymptomCategorySerializer(read_only=True)

    class Meta:
        model = Symptom
        fields = ["id", "category", "name", "description", "is_red_flag", "display_order"]


class SymptomSpecialtyRuleSerializer(serializers.ModelSerializer):
    symptom = SymptomSerializer(read_only=True)

    class Meta:
        model = SymptomSpecialtyRule
        fields = ["id", "symptom", "specialty", "weight", "is_active"]


class ConsultationAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = UserSerializer(read_only=True)

    class Meta:
        model = ConsultationAttachment
        fields = ["id", "file", "original_name", "uploaded_by", "created_at"]
        read_only_fields = ["id", "original_name", "uploaded_by", "created_at"]


class ConsultationResponseSerializer(serializers.ModelSerializer):
    doctor = UserSerializer(read_only=True)

    class Meta:
        model = ConsultationResponse
        fields = [
            "id",
            "doctor",
            "response_text",
            "recommendation_type",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "doctor", "created_at", "updated_at"]


class ConsultationListSerializer(serializers.ModelSerializer):
    patient = UserSerializer(read_only=True)
    assigned_doctor = UserSerializer(read_only=True)

    class Meta:
        model = Consultation
        fields = [
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
            "updated_at",
        ]


class ConsultationDetailSerializer(serializers.ModelSerializer):
    patient = UserSerializer(read_only=True)
    assigned_doctor = UserSerializer(read_only=True)
    symptoms = serializers.SerializerMethodField()
    responses = ConsultationResponseSerializer(many=True, read_only=True)
    attachments = ConsultationAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Consultation
        fields = [
            "id",
            "patient",
            "assigned_doctor",
            "status",
            "recommended_specialty",
            "selected_specialty",
            "selected_specialty_other",
            "ai_predicted_specialty",
            "ai_predicted_specialty_confidence",
            "duration",
            "severity",
            "has_fever",
            "has_pain",
            "has_breathing_difficulty",
            "has_emergency_warning",
            "previous_visit_for_same_issue",
            "current_medications_related",
            "additional_notes",
            "accepted_at",
            "closed_at",
            "symptoms",
            "responses",
            "attachments",
            "created_at",
            "updated_at",
        ]

    def get_symptoms(self, obj):
        symptom_objs = Symptom.objects.filter(consultation_links__consultation=obj).select_related(
            "category"
        )
        return SymptomSerializer(symptom_objs, many=True).data


class ConsultationPatientDetailSerializer(ConsultationDetailSerializer):
    class Meta(ConsultationDetailSerializer.Meta):
        fields = ConsultationDetailSerializer.Meta.fields


class ConsultationDoctorDetailSerializer(ConsultationDetailSerializer):
    class Meta(ConsultationDetailSerializer.Meta):
        fields = ConsultationDetailSerializer.Meta.fields + [
            "ai_predicted_disease",
            "ai_predicted_disease_confidence",
            "ai_prediction_notes",
        ]


class ConsultationCreateSerializer(serializers.ModelSerializer):
    symptom_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, allow_empty=False
    )
    attachments = serializers.ListField(
        child=serializers.FileField(), write_only=True, required=False
    )

    class Meta:
        model = Consultation
        fields = [
            "id",
            "symptom_ids",
            "duration",
            "severity",
            "has_fever",
            "has_pain",
            "has_breathing_difficulty",
            "previous_visit_for_same_issue",
            "selected_specialty",
            "selected_specialty_other",
            "current_medications_related",
            "additional_notes",
            "attachments",
            "recommended_specialty",
            "has_emergency_warning",
            "status",
            "assigned_doctor",
            "ai_predicted_disease",
            "ai_predicted_disease_confidence",
            "accepted_at",
            "closed_at",
        ]
        read_only_fields = [
            "id",
            "recommended_specialty",
            "has_emergency_warning",
            "status",
            "assigned_doctor",
            "ai_predicted_disease",
            "ai_predicted_disease_confidence",
            "accepted_at",
            "closed_at",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        if not is_patient(request.user):
            raise serializers.ValidationError("Only patients can create consultations.")

        selected_specialty = attrs.get("selected_specialty")
        selected_specialty_other = attrs.get("selected_specialty_other", "")
        if selected_specialty == MedicalSpecialty.OTHER and not selected_specialty_other:
            raise serializers.ValidationError(
                {"selected_specialty_other": "This field is required when specialty is Other."}
            )
        if selected_specialty != MedicalSpecialty.OTHER:
            attrs["selected_specialty_other"] = ""

        symptom_ids = attrs.get("symptom_ids", [])
        active_count = Symptom.objects.filter(id__in=symptom_ids, is_active=True).count()
        if active_count == 0:
            raise serializers.ValidationError(
                {"symptom_ids": "At least one active symptom must be selected."}
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        symptom_ids = validated_data.pop("symptom_ids")
        attachments = validated_data.pop("attachments", [])

        rec = recommend_specialty_from_symptoms(symptom_ids)
        recommended_specialty = rec["recommended_specialty"]
        selected_specialty = validated_data.pop("selected_specialty", None) or recommended_specialty
        has_emergency_warning = rec["has_red_flag"] or validated_data.get(
            "has_breathing_difficulty", False
        )

        consultation = Consultation.objects.create(
            patient=request.user,
            recommended_specialty=recommended_specialty,
            selected_specialty=selected_specialty,
            has_emergency_warning=has_emergency_warning,
            **validated_data,
        )

        symptom_objs = Symptom.objects.filter(id__in=symptom_ids, is_active=True)
        ConsultationSymptom.objects.bulk_create(
            [ConsultationSymptom(consultation=consultation, symptom=s) for s in symptom_objs],
            ignore_conflicts=True,
        )

        for file_obj in attachments:
            ConsultationAttachment.objects.create(
                consultation=consultation,
                file=file_obj,
                original_name=getattr(file_obj, "name", "attachment"),
                uploaded_by=request.user,
            )

        create_audit_log(
            actor=request.user,
            action="consultation_created",
            target=consultation,
            metadata={"symptom_count": symptom_objs.count(), "scores": rec["scores"]},
            request=request,
        )
        return consultation


class ConsultationAcceptSerializer(serializers.Serializer):
    def validate(self, attrs):
        request = self.context["request"]
        consultation = self.context["consultation"]

        if not is_approved_doctor(request.user):
            raise serializers.ValidationError("Only approved doctors can accept consultations.")

        if consultation.status != ConsultationStatus.SUBMITTED:
            raise serializers.ValidationError("Only submitted consultations can be accepted.")

        if consultation.assigned_doctor_id is not None:
            raise serializers.ValidationError("Consultation has already been assigned.")

        doctor_profile = request.user.doctor_profile
        target_specialty = consultation.selected_specialty or consultation.recommended_specialty
        if doctor_profile.specialty == MedicalSpecialty.OTHER:
            if target_specialty != MedicalSpecialty.OTHER:
                raise serializers.ValidationError(
                    "Doctor with Other specialty can only accept Other consultations."
                )
        elif target_specialty and doctor_profile.specialty != target_specialty:
            raise serializers.ValidationError(
                "Doctor specialty does not match consultation specialty."
            )

        return attrs


class ConsultationCloseSerializer(serializers.Serializer):
    def validate(self, attrs):
        request = self.context["request"]
        consultation = self.context["consultation"]
        if not is_assigned_doctor(request.user, consultation):
            raise serializers.ValidationError("Only assigned doctor can close this consultation.")
        if consultation.status not in [
            ConsultationStatus.ACCEPTED,
            ConsultationStatus.DOCTOR_RESPONDED,
        ]:
            raise serializers.ValidationError(
                "Only accepted or doctor_responded consultations can be closed."
            )
        return attrs


class ConsultationResponseCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsultationResponse
        fields = ["response_text", "recommendation_type"]

    def validate(self, attrs):
        request = self.context["request"]
        consultation = self.context["consultation"]

        if not is_assigned_doctor(request.user, consultation):
            raise serializers.ValidationError("Only assigned doctor can add responses.")

        if consultation.status not in [
            ConsultationStatus.ACCEPTED,
            ConsultationStatus.DOCTOR_RESPONDED,
        ]:
            raise serializers.ValidationError(
                "Consultation must be accepted before adding a response."
            )

        return attrs

    def create(self, validated_data):
        consultation = self.context["consultation"]
        request = self.context["request"]
        return add_consultation_response(
            consultation=consultation,
            doctor=request.user,
            response_text=validated_data["response_text"],
            recommendation_type=validated_data["recommendation_type"],
            request=request,
        )
