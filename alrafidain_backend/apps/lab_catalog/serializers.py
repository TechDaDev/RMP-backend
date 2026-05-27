from rest_framework import serializers

from .models import LabTest, LabTestAlias, LabTestClinicalInfo


class LabTestAliasSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabTestAlias
        fields = ["id", "alias", "alias_type", "language", "source_name", "created_at"]


class LabTestClinicalInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabTestClinicalInfo
        fields = [
            "id",
            "purpose_summary",
            "patient_preparation",
            "specimen_type",
            "sample_collection_notes",
            "clinical_significance",
            "interpretation_summary",
            "interfering_factors",
            "safety_notes",
            "patient_explanation",
            "provider_notes",
            "source_name",
            "source_type",
            "review_status",
            "reviewed_at",
            "created_at",
            "updated_at",
        ]


class LabTestListSerializer(serializers.ModelSerializer):
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
            "is_verified",
        ]


class LabTestDetailSerializer(LabTestListSerializer):
    aliases = LabTestAliasSerializer(many=True, read_only=True)
    clinical_info = serializers.SerializerMethodField()

    class Meta(LabTestListSerializer.Meta):
        fields = LabTestListSerializer.Meta.fields + [
            "component",
            "system",
            "source_name",
            "source_code",
            "source_version",
            "is_active",
            "aliases",
            "clinical_info",
            "created_at",
            "updated_at",
        ]

    def get_clinical_info(self, obj):
        try:
            return LabTestClinicalInfoSerializer(obj.clinical_info).data
        except LabTestClinicalInfo.DoesNotExist:
            return None


class LabTestCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabTest
        fields = [
            "name",
            "short_name",
            "loinc_code",
            "category",
            "component",
            "system",
            "sample_type",
            "units",
            "source_name",
            "source_code",
            "source_version",
            "is_active",
            "is_verified",
        ]
