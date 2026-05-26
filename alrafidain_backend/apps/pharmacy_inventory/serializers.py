from rest_framework import serializers

from apps.medical_catalog.models import Drug
from apps.profiles.models import PharmacistProfile

from .models import PharmacyDrugInventory


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


class PharmacyDrugInventoryListSerializer(serializers.ModelSerializer):
    drug_detail = _DrugLightSerializer(source="drug", read_only=True)
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = PharmacyDrugInventory
        fields = [
            "id",
            "pharmacy",
            "drug",
            "drug_detail",
            "custom_drug_name",
            "display_name",
            "brand_name",
            "form",
            "strength",
            "route",
            "price",
            "currency",
            "stock_status",
            "quantity",
            "is_available",
            "is_active",
        ]


class PharmacyDrugInventoryDetailSerializer(PharmacyDrugInventoryListSerializer):
    class Meta(PharmacyDrugInventoryListSerializer.Meta):
        fields = PharmacyDrugInventoryListSerializer.Meta.fields + [
            "notes",
            "created_at",
            "updated_at",
        ]


class PharmacyDrugInventoryCreateUpdateSerializer(serializers.ModelSerializer):
    pharmacy = serializers.PrimaryKeyRelatedField(
        queryset=PharmacistProfile.objects.all(),
        required=False,
        write_only=True,
    )

    class Meta:
        model = PharmacyDrugInventory
        fields = [
            "pharmacy",
            "drug",
            "custom_drug_name",
            "brand_name",
            "form",
            "strength",
            "route",
            "price",
            "currency",
            "stock_status",
            "quantity",
            "is_available",
            "notes",
        ]

    def validate(self, attrs):
        instance = getattr(self, "instance", None)

        drug = attrs.get("drug", instance.drug if instance else None)
        custom_drug_name = attrs.get(
            "custom_drug_name",
            (instance.custom_drug_name if instance else None),
        )
        custom_drug_name = (custom_drug_name or "").strip()

        if not drug and not custom_drug_name:
            raise serializers.ValidationError(
                {"custom_drug_name": "Provide either a catalog drug or custom_drug_name."}
            )

        if drug and not drug.is_active:
            raise serializers.ValidationError({"drug": "Selected catalog drug is inactive."})

        price = attrs.get("price", instance.price if instance else None)
        if price is not None and price < 0:
            raise serializers.ValidationError({"price": "Price cannot be negative."})

        stock_status = attrs.get("stock_status", instance.stock_status if instance else None)
        quantity = attrs.get("quantity", instance.quantity if instance else None)

        if quantity == 0 and stock_status != PharmacyDrugInventory.StockStatus.UNAVAILABLE:
            attrs["stock_status"] = PharmacyDrugInventory.StockStatus.OUT_OF_STOCK
            stock_status = attrs["stock_status"]

        if stock_status in {
            PharmacyDrugInventory.StockStatus.OUT_OF_STOCK,
            PharmacyDrugInventory.StockStatus.UNAVAILABLE,
        }:
            attrs["is_available"] = False

        pharmacy = attrs.get("pharmacy") or self.context.get("resolved_pharmacy")
        if not pharmacy and instance:
            pharmacy = instance.pharmacy

        if pharmacy and drug:
            duplicate_qs = PharmacyDrugInventory.objects.filter(
                pharmacy=pharmacy,
                drug=drug,
                is_active=True,
            )
            if instance:
                duplicate_qs = duplicate_qs.exclude(id=instance.id)
            if duplicate_qs.exists():
                raise serializers.ValidationError(
                    {"drug": "An active inventory entry already exists for this pharmacy and drug."}
                )

        attrs["custom_drug_name"] = custom_drug_name or None
        return attrs
