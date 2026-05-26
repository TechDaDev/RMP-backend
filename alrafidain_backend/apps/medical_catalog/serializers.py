from rest_framework import serializers

from .models import Drug, DrugAlias


class DrugAliasSerializer(serializers.ModelSerializer):
    class Meta:
        model = DrugAlias
        fields = ["id", "alias", "alias_type", "language", "source_name", "created_at"]


class DrugListSerializer(serializers.ModelSerializer):
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
            "is_verified",
        ]

    def get_display_name(self, obj):
        parts = [obj.name]
        if obj.strength:
            parts.append(obj.strength)
        if obj.form:
            parts.append(obj.form)
        return " ".join(parts)


class DrugDetailSerializer(DrugListSerializer):
    aliases = DrugAliasSerializer(many=True, read_only=True)

    class Meta(DrugListSerializer.Meta):
        fields = DrugListSerializer.Meta.fields + [
            "atc_code",
            "description",
            "warnings",
            "contraindications",
            "dosage_info",
            "adverse_reactions",
            "source_name",
            "source_code",
            "source_version",
            "is_active",
            "aliases",
            "created_at",
            "updated_at",
        ]


class DrugCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Drug
        fields = [
            "name",
            "generic_name",
            "brand_name",
            "form",
            "strength",
            "route",
            "rxnorm_rxcui",
            "atc_code",
            "description",
            "warnings",
            "contraindications",
            "dosage_info",
            "adverse_reactions",
            "source_name",
            "source_code",
            "source_version",
            "is_active",
            "is_verified",
        ]
