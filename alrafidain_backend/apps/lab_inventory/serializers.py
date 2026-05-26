from rest_framework import serializers

from apps.lab_catalog.models import LabTest
from apps.profiles.models import LaboratorianProfile

from .models import LabTestOffering


class _LabTestLightSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = LabTest
        fields = [
            "id",
            "display_name",
            "name",
            "short_name",
            "loinc_code",
            "category",
            "sample_type",
            "units",
        ]


class LabTestOfferingListSerializer(serializers.ModelSerializer):
    lab_test_detail = _LabTestLightSerializer(source="lab_test", read_only=True)
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = LabTestOffering
        fields = [
            "id",
            "lab",
            "lab_test",
            "lab_test_detail",
            "custom_test_name",
            "local_name",
            "display_name",
            "sample_type_override",
            "preparation_notes",
            "estimated_turnaround_time",
            "price",
            "currency",
            "is_available",
            "is_active",
        ]


class LabTestOfferingDetailSerializer(LabTestOfferingListSerializer):
    class Meta(LabTestOfferingListSerializer.Meta):
        fields = LabTestOfferingListSerializer.Meta.fields + [
            "notes",
            "created_at",
            "updated_at",
        ]


class LabTestOfferingCreateUpdateSerializer(serializers.ModelSerializer):
    lab = serializers.PrimaryKeyRelatedField(
        queryset=LaboratorianProfile.objects.all(),
        required=False,
        write_only=True,
    )

    class Meta:
        model = LabTestOffering
        fields = [
            "lab",
            "lab_test",
            "custom_test_name",
            "local_name",
            "sample_type_override",
            "preparation_notes",
            "estimated_turnaround_time",
            "price",
            "currency",
            "is_available",
            "notes",
        ]

    def validate(self, attrs):
        instance = getattr(self, "instance", None)

        lab_test = attrs.get("lab_test", instance.lab_test if instance else None)
        custom_test_name = attrs.get(
            "custom_test_name",
            (instance.custom_test_name if instance else None),
        )
        custom_test_name = (custom_test_name or "").strip()

        if not lab_test and not custom_test_name:
            raise serializers.ValidationError(
                {"custom_test_name": "Provide either a catalog lab_test or custom_test_name."}
            )

        if lab_test and not lab_test.is_active:
            raise serializers.ValidationError({"lab_test": "Selected catalog lab test is inactive."})

        price = attrs.get("price", instance.price if instance else None)
        if price is not None and price < 0:
            raise serializers.ValidationError({"price": "Price cannot be negative."})

        lab = attrs.get("lab") or self.context.get("resolved_lab")
        if not lab and instance:
            lab = instance.lab

        if lab and lab_test:
            duplicate_qs = LabTestOffering.objects.filter(
                lab=lab,
                lab_test=lab_test,
                is_active=True,
            )
            if instance:
                duplicate_qs = duplicate_qs.exclude(id=instance.id)
            if duplicate_qs.exists():
                raise serializers.ValidationError(
                    {"lab_test": "An active offering already exists for this lab and lab test."}
                )

        attrs["custom_test_name"] = custom_test_name or None

        local_name = attrs.get("local_name", instance.local_name if instance else None)
        attrs["local_name"] = (local_name or "").strip() or None

        sample_type_override = attrs.get(
            "sample_type_override",
            instance.sample_type_override if instance else None,
        )
        attrs["sample_type_override"] = (sample_type_override or "").strip() or None

        estimated_turnaround_time = attrs.get(
            "estimated_turnaround_time",
            instance.estimated_turnaround_time if instance else None,
        )
        attrs["estimated_turnaround_time"] = (estimated_turnaround_time or "").strip() or None

        return attrs
