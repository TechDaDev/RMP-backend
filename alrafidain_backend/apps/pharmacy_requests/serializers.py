from decimal import Decimal

from rest_framework import serializers

from apps.common.choices import VerificationStatus
from apps.common.policies import ClinicalAccessPolicy, RoleAccessPolicy
from apps.pharmacy_inventory.models import PharmacyDrugInventory
from apps.prescriptions.models import Prescription
from apps.profiles.models import PharmacistProfile

from .models import PharmacyPrescriptionRequest, PharmacyPrescriptionRequestItem


class PharmacyPrescriptionRequestItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PharmacyPrescriptionRequestItem
        fields = [
            "id",
            "prescription_item",
            "inventory_item",
            "requested_name_snapshot",
            "quoted_name",
            "quantity",
            "unit_price",
            "total_price",
            "availability_status",
            "substitution_note",
            "pharmacy_note",
            "created_at",
            "updated_at",
        ]


class PharmacyPrescriptionRequestListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PharmacyPrescriptionRequest
        fields = [
            "id",
            "prescription",
            "patient",
            "pharmacy",
            "status",
            "total_price",
            "currency",
            "created_at",
            "updated_at",
        ]


class PharmacyPrescriptionRequestDetailSerializer(PharmacyPrescriptionRequestListSerializer):
    items = PharmacyPrescriptionRequestItemSerializer(many=True, read_only=True)

    class Meta(PharmacyPrescriptionRequestListSerializer.Meta):
        fields = PharmacyPrescriptionRequestListSerializer.Meta.fields + [
            "requested_by",
            "pharmacy_notes",
            "patient_notes",
            "rejection_reason",
            "accepted_at",
            "rejected_at",
            "cancelled_at",
            "completed_at",
            "items",
        ]


class PharmacyPrescriptionRequestCreateSerializer(serializers.Serializer):
    prescription = serializers.PrimaryKeyRelatedField(queryset=Prescription.objects.all())
    pharmacy = serializers.PrimaryKeyRelatedField(queryset=PharmacistProfile.objects.all())
    patient_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        user = self.context["request"].user
        prescription = attrs["prescription"]
        pharmacy = attrs["pharmacy"]

        if not pharmacy.user.is_active:
            raise serializers.ValidationError({"pharmacy": "Pharmacy user is inactive."})

        if pharmacy.verification_status != VerificationStatus.APPROVED:
            raise serializers.ValidationError({"pharmacy": "Pharmacy profile must be approved."})

        if RoleAccessPolicy.is_admin_or_staff(user):
            pass
        elif RoleAccessPolicy.is_patient(user):
            if prescription.patient_id != user.id:
                raise serializers.ValidationError("You can request only your own prescriptions.")
        elif RoleAccessPolicy.is_doctor(user):
            if not ClinicalAccessPolicy.can_user_access_prescription(user, prescription):
                raise serializers.ValidationError("You cannot request this prescription.")
        else:
            raise serializers.ValidationError("You are not allowed to create pharmacy requests.")

        if PharmacyPrescriptionRequest.objects.filter(
            prescription=prescription,
            status__in=[
                PharmacyPrescriptionRequest.Status.ACCEPTED,
                PharmacyPrescriptionRequest.Status.COMPLETED,
            ],
        ).exists():
            raise serializers.ValidationError(
                "Prescription already has an accepted/completed pharmacy request."
            )

        if PharmacyPrescriptionRequest.objects.filter(
            prescription=prescription,
            pharmacy=pharmacy,
            status__in=[
                PharmacyPrescriptionRequest.Status.PENDING,
                PharmacyPrescriptionRequest.Status.QUOTED,
            ],
        ).exists():
            raise serializers.ValidationError(
                "Duplicate active pending/quoted request for this pharmacy is not allowed."
            )

        return attrs


class PharmacyQuoteItemInputSerializer(serializers.Serializer):
    prescription_item = serializers.UUIDField()
    inventory_item = serializers.PrimaryKeyRelatedField(
        queryset=PharmacyDrugInventory.objects.all(), required=False, allow_null=True
    )
    availability_status = serializers.ChoiceField(
        choices=PharmacyPrescriptionRequestItem.AvailabilityStatus.choices
    )
    quoted_name = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    quantity = serializers.IntegerField(required=False, min_value=1)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=0)
    substitution_note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    pharmacy_note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        availability_status = attrs["availability_status"]
        inventory_item = attrs.get("inventory_item")

        if availability_status == PharmacyPrescriptionRequestItem.AvailabilityStatus.UNAVAILABLE:
            attrs["unit_price"] = Decimal("0.00")
            attrs["total_price"] = Decimal("0.00")
            attrs["quantity"] = attrs.get("quantity") or 1
            return attrs

        quantity = attrs.get("quantity")
        unit_price = attrs.get("unit_price")
        if quantity is None or quantity < 1:
            raise serializers.ValidationError({"quantity": "Quantity must be >= 1."})
        if unit_price is None or unit_price < 0:
            raise serializers.ValidationError({"unit_price": "Unit price cannot be negative."})

        if availability_status in {
            PharmacyPrescriptionRequestItem.AvailabilityStatus.AVAILABLE,
            PharmacyPrescriptionRequestItem.AvailabilityStatus.SUBSTITUTED,
        } and inventory_item:
            if not inventory_item.is_active:
                raise serializers.ValidationError({"inventory_item": "Inventory item is inactive."})
            if not inventory_item.is_available:
                raise serializers.ValidationError(
                    {"inventory_item": "Inventory item is unavailable for quoting."}
                )

        attrs["total_price"] = unit_price * quantity
        return attrs


class PharmacyQuoteSerializer(serializers.Serializer):
    pharmacy_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    items = PharmacyQuoteItemInputSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one quote item is required.")

        ids = [str(item["prescription_item"]) for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate prescription_item entries are not allowed.")

        return value
