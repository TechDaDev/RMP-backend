from rest_framework import serializers

from apps.common.choices import DispensingAttemptStatus, MedicationRoute

from .models import DispensingRecord, Prescription, PrescriptionItem


class _SafeUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField()

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.email


# ──────────────────────────────────────────────
# Doctor: create prescription
# ──────────────────────────────────────────────


class PrescriptionItemCreateSerializer(serializers.Serializer):
    medication_name = serializers.CharField(max_length=200)
    strength = serializers.CharField(max_length=100, required=False, default="")
    dosage = serializers.CharField(max_length=200)
    frequency = serializers.CharField(max_length=200)
    duration = serializers.CharField(max_length=200)
    route = serializers.ChoiceField(choices=MedicationRoute.choices)
    quantity = serializers.CharField(max_length=100, required=False, default="")
    instructions = serializers.CharField(required=False, default="")


class PrescriptionCreateSerializer(serializers.Serializer):
    items = PrescriptionItemCreateSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one prescription item is required.")
        return value


# ──────────────────────────────────────────────
# Patient: safe view (no medication details)
# ──────────────────────────────────────────────


class PrescriptionPatientListSerializer(serializers.ModelSerializer):
    doctor = _SafeUserSerializer(read_only=True)
    consultation_id = serializers.UUIDField(source="consultation.id", read_only=True)
    issued_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Prescription
        fields = [
            "id",
            "consultation_id",
            "doctor",
            "status",
            "qr_token",
            "issued_at",
            "expires_at",
            "fully_dispensed_at",
        ]


class PrescriptionPatientDetailSerializer(PrescriptionPatientListSerializer):
    pass


# ──────────────────────────────────────────────
# Doctor: full view
# ──────────────────────────────────────────────


class PrescriptionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = [
            "id",
            "medication_name",
            "strength",
            "dosage",
            "frequency",
            "duration",
            "route",
            "quantity",
            "instructions",
            "status",
            "dispensed_at",
            "cancelled_at",
            "created_at",
        ]


class DispensingRecordSerializer(serializers.ModelSerializer):
    pharmacist = _SafeUserSerializer(read_only=True)
    prescription_item_id = serializers.UUIDField(source="prescription_item.id", read_only=True)

    class Meta:
        model = DispensingRecord
        fields = [
            "id",
            "prescription_item_id",
            "pharmacist",
            "status",
            "dispensed_quantity",
            "note",
            "created_at",
        ]


class PrescriptionDoctorDetailSerializer(serializers.ModelSerializer):
    patient = _SafeUserSerializer(read_only=True)
    doctor = _SafeUserSerializer(read_only=True)
    consultation_id = serializers.UUIDField(source="consultation.id", read_only=True)
    items = PrescriptionItemSerializer(many=True, read_only=True)
    dispensing_records = DispensingRecordSerializer(many=True, read_only=True)
    issued_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Prescription
        fields = [
            "id",
            "consultation_id",
            "patient",
            "doctor",
            "status",
            "qr_token",
            "issued_at",
            "expires_at",
            "cancelled_at",
            "fully_dispensed_at",
            "items",
            "dispensing_records",
        ]


# ──────────────────────────────────────────────
# Pharmacist: scan response
# ──────────────────────────────────────────────


class PrescriptionRemainingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = [
            "id",
            "medication_name",
            "strength",
            "dosage",
            "frequency",
            "duration",
            "route",
            "quantity",
            "instructions",
        ]


class _PrescriptionPharmacistBasicSerializer(serializers.ModelSerializer):
    doctor = _SafeUserSerializer(read_only=True)
    issued_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Prescription
        fields = [
            "id",
            "status",
            "doctor",
            "issued_at",
            "expires_at",
        ]


class PrescriptionPharmacistScanSerializer(serializers.Serializer):
    prescription = _PrescriptionPharmacistBasicSerializer(read_only=True)
    remaining_items = PrescriptionRemainingItemSerializer(many=True, read_only=True)
    locked = serializers.BooleanField(read_only=True)
    message = serializers.CharField(read_only=True, allow_null=True)


# ──────────────────────────────────────────────
# Pharmacist: dispense items input
# ──────────────────────────────────────────────


class DispenseItemEntrySerializer(serializers.Serializer):
    prescription_item_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=DispensingAttemptStatus.choices)
    dispensed_quantity = serializers.CharField(max_length=100, required=False, default="")
    note = serializers.CharField(required=False, default="")


class DispenseItemsSerializer(serializers.Serializer):
    items = DispenseItemEntrySerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value
