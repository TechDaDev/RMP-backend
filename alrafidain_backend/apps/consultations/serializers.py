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
            "recommended_specialties",
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
            "recommended_specialties",
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
        prefetched = getattr(obj, "_prefetched_objects_cache", {})
        if "consultation_symptoms" in prefetched:
            symptom_objs = [
                cs.symptom for cs in prefetched["consultation_symptoms"] if cs.symptom_id
            ]
        else:
            symptom_objs = Symptom.objects.filter(
                consultation_links__consultation=obj
            ).select_related("category")
        return SymptomSerializer(symptom_objs, many=True).data


class ConsultationPatientDetailSerializer(ConsultationDetailSerializer):
    class Meta(ConsultationDetailSerializer.Meta):
        fields = ConsultationDetailSerializer.Meta.fields


class ConsultationDoctorDetailSerializer(ConsultationDetailSerializer):
    ai_case_summary = serializers.SerializerMethodField()

    class Meta(ConsultationDetailSerializer.Meta):
        fields = ConsultationDetailSerializer.Meta.fields + [
            "ai_predicted_disease",
            "ai_predicted_disease_confidence",
            "ai_prediction_notes",
            "ai_case_summary",
        ]

    def get_ai_case_summary(self, obj):
        return obj.get_ai_case_summary()


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
            "recommended_specialties",
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
            "selected_specialty",
            "selected_specialty_other",
            "recommended_specialty",
            "recommended_specialties",
            "has_emergency_warning",
            "status",
            "assigned_doctor",
            "ai_predicted_disease",
            "ai_predicted_disease_confidence",
            "accepted_at",
            "closed_at",
        ]

    def validate_symptom_ids(self, value):
        unique_ids = list(dict.fromkeys(value))
        active_symptoms = Symptom.objects.filter(id__in=unique_ids, is_active=True)
        active_ids = {symptom.id for symptom in active_symptoms}
        missing_ids = [str(symptom_id) for symptom_id in unique_ids if symptom_id not in active_ids]

        if missing_ids:
            raise serializers.ValidationError(
                f"Invalid or inactive symptom IDs: {', '.join(missing_ids)}"
            )

        return unique_ids

    def validate(self, attrs):
        request = self.context.get("request")
        if not is_patient(request.user):
            raise serializers.ValidationError("Only patients can create consultations.")

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        symptom_ids = validated_data.pop("symptom_ids")
        attachments = validated_data.pop("attachments", [])

        rec = recommend_specialty_from_symptoms(symptom_ids)
        recommended_specialty = rec["recommended_specialty"]
        has_emergency_warning = rec["has_red_flag"] or validated_data.get(
            "has_breathing_difficulty", False
        )

        consultation = Consultation.objects.create(
            patient=request.user,
            recommended_specialty=recommended_specialty,
            recommended_specialties=rec["recommended_specialties"],
            selected_specialty=recommended_specialty,
            selected_specialty_other="",
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
            metadata={
                "symptom_count": symptom_objs.count(),
                "scores": rec["scores"],
                "recommended_specialties": rec["recommended_specialties"],
                "routing_method": rec["routing_method"],
                "llm_usage": rec.get("llm_usage", {}),
            },
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
        target_specialties = consultation.get_recommended_specialties()
        if doctor_profile.specialty == MedicalSpecialty.OTHER:
            if MedicalSpecialty.OTHER not in target_specialties:
                raise serializers.ValidationError(
                    "Doctor with Other specialty can only accept Other consultations."
                )
        elif target_specialties and doctor_profile.specialty not in target_specialties:
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
