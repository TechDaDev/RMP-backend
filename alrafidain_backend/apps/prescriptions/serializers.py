from datetime import date

from rest_framework import serializers

from apps.common.choices import DispensingAttemptStatus, MedicationRoute
from apps.medical_catalog.models import Drug

from .models import DispensingRecord, Prescription, PrescriptionItem


class _SafeUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField()

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.email


class _DrugLightSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Drug
        fields = [
            "id",
            "display_name",
            "name",
            "generic_name",
            "brand_name",
            "form",
            "strength",
            "route",
            "rxnorm_rxcui",
        ]

    def get_display_name(self, obj):
        parts = [obj.name]
        if obj.strength:
            parts.append(obj.strength)
        if obj.form:
            parts.append(obj.form)
        return " ".join(parts)


# ──────────────────────────────────────────────
# Doctor: create prescription
# ──────────────────────────────────────────────


class PrescriptionItemCreateSerializer(serializers.Serializer):
    drug = serializers.PrimaryKeyRelatedField(queryset=Drug.objects.all(), required=False, allow_null=True)
    custom_drug_name = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    medication_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    # Backward-compatible alias for legacy payloads that may send drug_name.
    drug_name = serializers.CharField(max_length=200, required=False, allow_blank=True, write_only=True)
    strength = serializers.CharField(max_length=100, required=False, default="")
    dosage = serializers.CharField(max_length=200)
    frequency = serializers.CharField(max_length=200)
    duration = serializers.CharField(max_length=200)
    route = serializers.ChoiceField(choices=MedicationRoute.choices)
    quantity = serializers.CharField(max_length=100, required=False, default="")
    instructions = serializers.CharField(required=False, default="")

    def validate(self, attrs):
        drug = attrs.get("drug")
        custom_drug_name = (attrs.get("custom_drug_name") or "").strip()
        legacy_drug_name = (attrs.get("drug_name") or "").strip()
        medication_name = (attrs.get("medication_name") or "").strip()

        if drug and not drug.is_active:
            raise serializers.ValidationError({"drug": "Selected drug is inactive."})

        resolved_name = medication_name or legacy_drug_name or custom_drug_name
        if not resolved_name and drug:
            resolved_name = drug.name
        if not (drug or resolved_name):
            raise serializers.ValidationError(
                {"medication_name": "A catalog drug or custom drug name is required."}
            )

        if not medication_name and resolved_name:
            attrs["medication_name"] = resolved_name
        attrs["custom_drug_name"] = custom_drug_name or None
        attrs.pop("drug_name", None)
        return attrs


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
    drug_detail = _DrugLightSerializer(source="drug", read_only=True)
    display_drug_name = serializers.CharField(read_only=True)
    drug_name = serializers.CharField(source="medication_name", read_only=True)

    class Meta:
        model = PrescriptionItem
        fields = [
            "id",
            "drug",
            "drug_detail",
            "custom_drug_name",
            "display_drug_name",
            "drug_name",
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
    drug_detail = _DrugLightSerializer(source="drug", read_only=True)
    display_drug_name = serializers.CharField(read_only=True)
    drug_name = serializers.CharField(source="medication_name", read_only=True)

    class Meta:
        model = PrescriptionItem
        fields = [
            "id",
            "drug",
            "drug_detail",
            "custom_drug_name",
            "display_drug_name",
            "drug_name",
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


class _PharmacistHistoryPatientSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.email

    def get_gender(self, obj):
        profile = getattr(obj, "user_profile", None)
        return getattr(profile, "gender", "") or None

    def get_age(self, obj):
        profile = getattr(obj, "user_profile", None)
        dob = getattr(profile, "date_of_birth", None)
        if not dob:
            return None
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class _PharmacistHistoryDoctorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.email

    def get_specialty(self, obj):
        profile = getattr(obj, "doctor_profile", None)
        return getattr(profile, "specialty", "") or None


class PharmacistDispensingHistorySerializer(serializers.ModelSerializer):
    prescription_id = serializers.UUIDField(source="prescription.id", read_only=True)
    prescription_status = serializers.CharField(source="prescription.status", read_only=True)
    item_id = serializers.UUIDField(source="prescription_item.id", read_only=True)
    medication_name = serializers.CharField(
        source="prescription_item.medication_name", read_only=True
    )
    strength = serializers.CharField(source="prescription_item.strength", read_only=True)
    dosage = serializers.CharField(source="prescription_item.dosage", read_only=True)
    frequency = serializers.CharField(source="prescription_item.frequency", read_only=True)
    duration = serializers.CharField(source="prescription_item.duration", read_only=True)
    route = serializers.CharField(source="prescription_item.route", read_only=True)
    quantity = serializers.CharField(source="prescription_item.quantity", read_only=True)
    dispensed_at = serializers.SerializerMethodField()
    patient = serializers.SerializerMethodField()
    doctor = serializers.SerializerMethodField()

    class Meta:
        model = DispensingRecord
        fields = [
            "id",
            "prescription_id",
            "prescription_status",
            "item_id",
            "medication_name",
            "strength",
            "dosage",
            "frequency",
            "duration",
            "route",
            "quantity",
            "dispensed_quantity",
            "status",
            "dispensed_at",
            "patient",
            "doctor",
            "created_at",
            "updated_at",
        ]

    def get_dispensed_at(self, obj):
        return obj.prescription_item.dispensed_at or obj.created_at

    def get_patient(self, obj):
        return _PharmacistHistoryPatientSerializer(obj.prescription.patient).data

    def get_doctor(self, obj):
        return _PharmacistHistoryDoctorSerializer(obj.prescription.doctor).data
