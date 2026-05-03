from rest_framework import serializers

from apps.common.choices import (
    BloodGroup,
    LabCompletionAttemptStatus,
    LabResultFlag,
    LabResultStatus,
    LabResultValueType,
)

from .models import LabCompletionRecord, LabOrder, LabOrderItem, LabResult, LabResultCorrection, LabTestCatalog

PATIENT_LAB_GUIDANCE = (
    "Show this QR code to any verified laboratory/laboratorian registered in the platform. "
    "The laboratory will scan it and view only the pending requested tests."
)


class _SafeUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField()

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.email


class LabTestCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabTestCatalog
        fields = [
            "id",
            "name",
            "category",
            "code",
            "description",
            "default_sample_type",
            "default_instructions",
            "display_order",
        ]


class LabOrderItemCreateSerializer(serializers.Serializer):
    test = serializers.PrimaryKeyRelatedField(queryset=LabTestCatalog.objects.filter(is_active=True), required=False)
    test_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    category = serializers.ChoiceField(choices=LabOrderItem._meta.get_field("category").choices, required=False)
    sample_type = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    instructions = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        test = attrs.get("test")
        if test is None and (not attrs.get("test_name") or not attrs.get("category")):
            raise serializers.ValidationError("Provide test or both test_name and category.")
        return attrs


class LabOrderCreateSerializer(serializers.Serializer):
    items = LabOrderItemCreateSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one lab test is required.")
        normalized = []
        for item in value:
            test = item.get("test")
            test_name = item.get("test_name") or (test.name if test else "")
            category = item.get("category") or (test.category if test else None)
            sample_type = item.get("sample_type") or (test.default_sample_type if test else "")
            instructions = item.get("instructions") or (test.default_instructions if test else "")
            normalized.append(
                {
                    "test": test,
                    "test_name": test_name,
                    "category": category,
                    "sample_type": sample_type,
                    "instructions": instructions,
                }
            )
        return normalized


class LabOrderRemainingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabOrderItem
        fields = ["id", "test_name", "category", "sample_type", "instructions"]


class LabCompletionRecordSerializer(serializers.ModelSerializer):
    laboratorian = _SafeUserSerializer(read_only=True)
    lab_order_item_id = serializers.UUIDField(source="lab_order_item.id", read_only=True)

    class Meta:
        model = LabCompletionRecord
        fields = ["id", "lab_order_item_id", "laboratorian", "status", "note", "created_at"]


class LabOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabOrderItem
        fields = [
            "id",
            "test",
            "test_name",
            "category",
            "sample_type",
            "instructions",
            "status",
            "completed_at",
            "cancelled_at",
            "created_at",
        ]


class _LabOrderPatientBaseSerializer(serializers.ModelSerializer):
    consultation_id = serializers.UUIDField(source="consultation.id", read_only=True)
    doctor = _SafeUserSerializer(read_only=True)
    issued_at = serializers.DateTimeField(source="created_at", read_only=True)
    test_count = serializers.SerializerMethodField()
    guidance = serializers.SerializerMethodField()
    qr_url = serializers.SerializerMethodField()

    class Meta:
        model = LabOrder
        fields = [
            "id",
            "consultation_id",
            "doctor",
            "status",
            "qr_token",
            "qr_url",
            "test_count",
            "issued_at",
            "expires_at",
            "fully_completed_at",
            "guidance",
        ]

    def get_test_count(self, obj):
        return obj.items.count()

    def get_guidance(self, _obj):
        return PATIENT_LAB_GUIDANCE

    def get_qr_url(self, obj):
        return f"/api/lab-orders/scan/?qr_token={obj.qr_token}"


class LabOrderPatientListSerializer(_LabOrderPatientBaseSerializer):
    pass


class LabOrderPatientDetailSerializer(_LabOrderPatientBaseSerializer):
    pass


class LabOrderDoctorDetailSerializer(serializers.ModelSerializer):
    consultation_id = serializers.UUIDField(source="consultation.id", read_only=True)
    doctor = _SafeUserSerializer(read_only=True)
    patient = _SafeUserSerializer(read_only=True)
    items = LabOrderItemSerializer(many=True, read_only=True)
    completion_records = LabCompletionRecordSerializer(many=True, read_only=True)

    class Meta:
        model = LabOrder
        fields = [
            "id",
            "consultation_id",
            "patient",
            "doctor",
            "status",
            "qr_token",
            "created_at",
            "expires_at",
            "cancelled_at",
            "fully_completed_at",
            "items",
            "completion_records",
        ]


class _LabOrderLaboratorianBasicSerializer(serializers.ModelSerializer):
    doctor = _SafeUserSerializer(read_only=True)
    issued_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = LabOrder
        fields = ["id", "status", "doctor", "issued_at", "expires_at"]


class LabOrderLaboratorianScanSerializer(serializers.Serializer):
    lab_order = _LabOrderLaboratorianBasicSerializer(read_only=True)
    remaining_items = LabOrderRemainingItemSerializer(many=True, read_only=True)
    locked = serializers.BooleanField(read_only=True)
    message = serializers.CharField(read_only=True, allow_null=True)


class CompleteLabOrderItemEntrySerializer(serializers.Serializer):
    lab_order_item_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=LabCompletionAttemptStatus.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class CompleteLabOrderItemsSerializer(serializers.Serializer):
    items = CompleteLabOrderItemEntrySerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value


class LabResultCorrectionHistorySerializer(serializers.ModelSerializer):
    corrected_by = _SafeUserSerializer(read_only=True)

    class Meta:
        model = LabResultCorrection
        fields = ["id", "corrected_by", "previous_data", "new_data", "reason", "created_at"]


class LabResultSerializer(serializers.ModelSerializer):
    patient = _SafeUserSerializer(read_only=True)
    doctor = _SafeUserSerializer(read_only=True)
    laboratorian = _SafeUserSerializer(read_only=True)
    corrections = LabResultCorrectionHistorySerializer(many=True, read_only=True)

    class Meta:
        model = LabResult
        fields = [
            "id",
            "lab_order",
            "lab_order_item",
            "patient",
            "doctor",
            "laboratorian",
            "status",
            "value_type",
            "text_value",
            "numeric_value",
            "blood_group_value",
            "unit",
            "reference_range",
            "flag",
            "result_file",
            "original_file_name",
            "laboratorian_notes",
            "doctor_notes",
            "submitted_at",
            "reviewed_at",
            "released_at",
            "corrected_at",
            "is_linked_to_medical_record",
            "linked_entry",
            "linked_blood_group_record",
            "corrections",
            "created_at",
            "updated_at",
        ]


class LabResultPatientSerializer(serializers.ModelSerializer):
    test_label = serializers.SerializerMethodField()

    class Meta:
        model = LabResult
        fields = [
            "id",
            "lab_order",
            "lab_order_item",
            "test_label",
            "status",
            "value_type",
            "text_value",
            "numeric_value",
            "blood_group_value",
            "unit",
            "reference_range",
            "flag",
            "result_file",
            "released_at",
            "created_at",
        ]

    def get_test_label(self, obj):
        return obj.lab_order_item.test_name


class LabResultCreateSerializer(serializers.Serializer):
    value_type = serializers.ChoiceField(choices=LabResultValueType.choices)
    text_value = serializers.CharField(required=False, allow_blank=True)
    numeric_value = serializers.DecimalField(max_digits=12, decimal_places=4, required=False)
    blood_group_value = serializers.ChoiceField(choices=BloodGroup.choices, required=False)
    unit = serializers.CharField(required=False, allow_blank=True)
    reference_range = serializers.CharField(required=False, allow_blank=True)
    flag = serializers.ChoiceField(choices=LabResultFlag.choices, required=False)
    result_file = serializers.FileField(required=False)
    laboratorian_notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        value_type = attrs.get("value_type")
        if value_type == LabResultValueType.NUMERIC and attrs.get("numeric_value") is None:
            raise serializers.ValidationError({"numeric_value": "This field is required for numeric results."})
        if value_type == LabResultValueType.TEXT and not attrs.get("text_value"):
            raise serializers.ValidationError({"text_value": "This field is required for text results."})
        if value_type == LabResultValueType.BLOOD_GROUP and not attrs.get("blood_group_value"):
            raise serializers.ValidationError({"blood_group_value": "This field is required for blood group results."})
        if value_type == LabResultValueType.FILE_ONLY and attrs.get("result_file") is None:
            raise serializers.ValidationError({"result_file": "This field is required for file-only results."})
        if value_type == LabResultValueType.POSITIVE_NEGATIVE:
            if (attrs.get("text_value") or "").strip().lower() not in {"positive", "negative"}:
                raise serializers.ValidationError({"text_value": "Value must be 'positive' or 'negative'."})
        return attrs


class LabResultCorrectionSerializer(serializers.Serializer):
    reason = serializers.CharField()
    value_type = serializers.ChoiceField(choices=LabResultValueType.choices, required=False)
    text_value = serializers.CharField(required=False, allow_blank=True)
    numeric_value = serializers.DecimalField(max_digits=12, decimal_places=4, required=False)
    blood_group_value = serializers.ChoiceField(choices=BloodGroup.choices, required=False)
    unit = serializers.CharField(required=False, allow_blank=True)
    reference_range = serializers.CharField(required=False, allow_blank=True)
    flag = serializers.ChoiceField(choices=LabResultFlag.choices, required=False)
    laboratorian_notes = serializers.CharField(required=False, allow_blank=True)

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("Reason is required.")
        return value


class LabResultReviewSerializer(serializers.Serializer):
    doctor_notes = serializers.CharField(required=False, allow_blank=True)
    release_to_patient = serializers.BooleanField(default=False)


class LabResultReleaseSerializer(serializers.Serializer):
    pass


class LabResultLinkToMedicalRecordSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True)
