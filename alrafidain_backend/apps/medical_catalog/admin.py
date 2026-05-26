from django.contrib import admin

from .models import CatalogImportBatch, Drug, DrugAlias


@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "generic_name",
        "brand_name",
        "form",
        "strength",
        "route",
        "rxnorm_rxcui",
        "source_name",
        "is_active",
        "is_verified",
    )
    search_fields = (
        "name",
        "generic_name",
        "brand_name",
        "rxnorm_rxcui",
        "aliases__alias",
    )
    list_filter = ("source_name", "is_active", "is_verified", "route", "form")


@admin.register(DrugAlias)
class DrugAliasAdmin(admin.ModelAdmin):
    list_display = ("alias", "drug", "alias_type", "language", "source_name")
    search_fields = ("alias", "drug__name")
    list_filter = ("alias_type", "language", "source_name")


@admin.register(CatalogImportBatch)
class CatalogImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "source_name",
        "source_version",
        "status",
        "started_at",
        "finished_at",
        "total_records",
        "created_records",
        "updated_records",
        "skipped_records",
    )
    search_fields = ("source_name", "source_version", "imported_file")
    list_filter = ("source_name", "status")
