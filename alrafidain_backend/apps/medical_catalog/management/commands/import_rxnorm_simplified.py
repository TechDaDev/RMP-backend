import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.medical_catalog.models import CatalogImportBatch, Drug, DrugAlias


def normalize_whitespace(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


class Command(BaseCommand):
    help = "Import RxNorm simplified JSON into local medical_catalog Drug and DrugAlias tables."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to rxnorm_simplified_results.json")
        parser.add_argument(
            "--source-version",
            default="",
            help="Optional source version label for CatalogImportBatch.",
        )

    def handle(self, *args, **options):
        file_path = options["file"]
        source_version = normalize_whitespace(options.get("source_version") or "")

        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise CommandError(f"File does not exist: {file_path}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON: {exc}") from exc

        if not isinstance(payload, list):
            raise CommandError("JSON root must be a list.")

        batch = CatalogImportBatch.objects.create(
            source_name="rxnorm",
            source_version=source_version or None,
            imported_file=file_path,
            status=CatalogImportBatch.Status.STARTED,
            total_records=0,
            created_records=0,
            updated_records=0,
            skipped_records=0,
        )

        created_records = 0
        updated_records = 0
        skipped_records = 0

        try:
            with transaction.atomic():
                for row in payload:
                    batch.total_records += 1

                    if not isinstance(row, dict):
                        skipped_records += 1
                        continue

                    name = normalize_whitespace(row.get("name"))
                    if not name:
                        skipped_records += 1
                        continue

                    rxcui = normalize_whitespace(row.get("rxcui")) or None
                    tty = normalize_whitespace(row.get("tty"))

                    drug = None
                    if rxcui:
                        drug = (
                            Drug.objects.filter(rxnorm_rxcui=rxcui, name__iexact=name)
                            .order_by("created_at")
                            .first()
                        )

                    if drug is None and not rxcui:
                        # Fallback for rows without RxCUI to keep reruns idempotent when possible.
                        drug = Drug.objects.filter(name__iexact=name, source_name="rxnorm").first()

                    if drug is None:
                        generic_name = name if tty.upper() == "IN" else None
                        drug = Drug.objects.create(
                            name=name,
                            generic_name=generic_name,
                            rxnorm_rxcui=rxcui,
                            source_name="rxnorm",
                            source_code=rxcui,
                            source_version=source_version or None,
                            is_verified=False,
                            is_active=True,
                        )
                        created_records += 1
                    else:
                        updates = []
                        if rxcui and drug.rxnorm_rxcui != rxcui:
                            drug.rxnorm_rxcui = rxcui
                            updates.append("rxnorm_rxcui")
                        if drug.source_name != "rxnorm":
                            drug.source_name = "rxnorm"
                            updates.append("source_name")
                        if drug.source_code != rxcui:
                            drug.source_code = rxcui
                            updates.append("source_code")
                        source_version_value = source_version or None
                        if drug.source_version != source_version_value:
                            drug.source_version = source_version_value
                            updates.append("source_version")
                        if not drug.is_active:
                            drug.is_active = True
                            updates.append("is_active")
                        if drug.is_verified:
                            drug.is_verified = False
                            updates.append("is_verified")
                        if updates:
                            updates.append("updated_at")
                            drug.save(update_fields=updates)
                        updated_records += 1

                    self._create_aliases(drug=drug, row=row)

                batch.created_records = created_records
                batch.updated_records = updated_records
                batch.skipped_records = skipped_records
                batch.status = CatalogImportBatch.Status.COMPLETED
                batch.finished_at = timezone.now()
                batch.notes = (
                    f"Imported from {file_path}. "
                    f"created={created_records}, updated={updated_records}, skipped={skipped_records}."
                )
                batch.save(
                    update_fields=[
                        "total_records",
                        "created_records",
                        "updated_records",
                        "skipped_records",
                        "status",
                        "finished_at",
                        "notes",
                    ]
                )

        except Exception as exc:
            batch.status = CatalogImportBatch.Status.FAILED
            batch.finished_at = timezone.now()
            batch.created_records = created_records
            batch.updated_records = updated_records
            batch.skipped_records = skipped_records
            batch.notes = str(exc)
            batch.save(
                update_fields=[
                    "total_records",
                    "created_records",
                    "updated_records",
                    "skipped_records",
                    "status",
                    "finished_at",
                    "notes",
                ]
            )
            raise CommandError(f"Import failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                "RxNorm import completed: "
                f"total={batch.total_records}, created={created_records}, "
                f"updated={updated_records}, skipped={skipped_records}."
            )
        )

    def _create_aliases(self, *, drug, row):
        input_term = normalize_whitespace(row.get("input_term"))
        synonym = normalize_whitespace(row.get("synonym"))
        synonyms = row.get("synonyms")

        alias_candidates = []
        if input_term:
            alias_candidates.append((input_term, DrugAlias.AliasType.GENERIC))
        if synonym:
            alias_candidates.append((synonym, DrugAlias.AliasType.SYNONYM))
        if isinstance(synonyms, list):
            for value in synonyms:
                normalized = normalize_whitespace(value)
                if normalized:
                    alias_candidates.append((normalized, DrugAlias.AliasType.SYNONYM))

        for alias_text, alias_type in alias_candidates:
            if not alias_text:
                continue
            if len(alias_text) > 255:
                continue
            if alias_text.lower() == (drug.name or "").lower():
                continue
            exists = drug.aliases.filter(alias__iexact=alias_text).exists()
            if exists:
                continue
            DrugAlias.objects.create(
                drug=drug,
                alias=alias_text,
                alias_type=alias_type,
                language="en",
                source_name="rxnorm",
            )
