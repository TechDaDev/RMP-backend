from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.lab_catalog.models import LabCatalogImportBatch, LabTest, LabTestAlias

LAB_TESTS_SEED = [
    {
        "name": "Complete Blood Count",
        "short_name": "CBC",
        "category": "Hematology",
        "sample_type": "Blood",
        "aliases": [
            ("CBC", "short_name"),
            ("Complete Blood Count", "synonym"),
            ("Full Blood Count", "synonym"),
            ("FBC", "synonym"),
        ],
    },
    {
        "name": "Hemoglobin A1c",
        "short_name": "HbA1c",
        "category": "Chemistry",
        "sample_type": "Blood",
        "aliases": [
            ("HbA1c", "short_name"),
            ("A1C", "synonym"),
            ("Glycated Hemoglobin", "synonym"),
        ],
    },
    {
        "name": "Fasting Blood Sugar",
        "short_name": "FBS",
        "category": "Chemistry",
        "sample_type": "Blood",
        "aliases": [
            ("FBS", "short_name"),
            ("Fasting Glucose", "synonym"),
            ("Fasting Blood Glucose", "synonym"),
        ],
    },
    {
        "name": "Random Blood Sugar",
        "short_name": "RBS",
        "category": "Chemistry",
        "sample_type": "Blood",
        "aliases": [
            ("RBS", "short_name"),
            ("Random Glucose", "synonym"),
            ("Random Blood Glucose", "synonym"),
        ],
    },
    {
        "name": "Creatinine",
        "short_name": None,
        "category": "Kidney Function",
        "sample_type": "Blood",
        "aliases": [
            ("Serum Creatinine", "synonym"),
            ("Creatinine Test", "synonym"),
        ],
    },
    {
        "name": "Urea",
        "short_name": None,
        "category": "Kidney Function",
        "sample_type": "Blood",
        "aliases": [
            ("Blood Urea", "synonym"),
            ("BUN", "synonym"),
            ("Urea Nitrogen", "synonym"),
        ],
    },
    {
        "name": "Liver Function Test",
        "short_name": "LFT",
        "category": "Liver Function",
        "sample_type": "Blood",
        "aliases": [
            ("LFT", "short_name"),
            ("Liver Panel", "synonym"),
            ("Liver Profile", "synonym"),
        ],
    },
    {
        "name": "Lipid Profile",
        "short_name": None,
        "category": "Chemistry",
        "sample_type": "Blood",
        "aliases": [
            ("Lipid Panel", "synonym"),
            ("Cholesterol Test", "synonym"),
        ],
    },
    {
        "name": "Urinalysis",
        "short_name": None,
        "category": "Urine Test",
        "sample_type": "Urine",
        "aliases": [
            ("Urine Analysis", "synonym"),
            ("Urine R/E", "synonym"),
            ("Routine Urine Examination", "synonym"),
        ],
    },
    {
        "name": "Thyroid Stimulating Hormone",
        "short_name": "TSH",
        "category": "Hormones",
        "sample_type": "Blood",
        "aliases": [
            ("TSH", "short_name"),
            ("Thyroid Stimulating Hormone", "synonym"),
        ],
    },
    {
        "name": "Triiodothyronine",
        "short_name": "T3",
        "category": "Hormones",
        "sample_type": "Blood",
        "aliases": [
            ("T3", "short_name"),
            ("Triiodothyronine", "synonym"),
        ],
    },
    {
        "name": "Thyroxine",
        "short_name": "T4",
        "category": "Hormones",
        "sample_type": "Blood",
        "aliases": [
            ("T4", "short_name"),
            ("Thyroxine", "synonym"),
        ],
    },
    {
        "name": "Vitamin D",
        "short_name": None,
        "category": "Vitamins",
        "sample_type": "Blood",
        "aliases": [
            ("Vitamin D", "synonym"),
            ("25-OH Vitamin D", "synonym"),
            ("25 Hydroxy Vitamin D", "synonym"),
        ],
    },
    {
        "name": "C-Reactive Protein",
        "short_name": "CRP",
        "category": "Inflammation",
        "sample_type": "Blood",
        "aliases": [
            ("CRP", "short_name"),
            ("C Reactive Protein", "synonym"),
        ],
    },
    {
        "name": "Erythrocyte Sedimentation Rate",
        "short_name": "ESR",
        "category": "Hematology",
        "sample_type": "Blood",
        "aliases": [
            ("ESR", "short_name"),
            ("Sed Rate", "synonym"),
        ],
    },
    {
        "name": "Blood Group",
        "short_name": None,
        "category": "Blood Bank",
        "sample_type": "Blood",
        "aliases": [
            ("Blood Type", "synonym"),
            ("ABO", "synonym"),
            ("Rh", "synonym"),
        ],
    },
    {
        "name": "Pregnancy Test",
        "short_name": None,
        "category": "Hormones",
        "sample_type": "Urine/Blood",
        "aliases": [
            ("Pregnancy Test", "synonym"),
            ("hCG", "synonym"),
            ("Beta hCG", "synonym"),
        ],
    },
    {
        "name": "Electrolytes",
        "short_name": None,
        "category": "Chemistry",
        "sample_type": "Blood",
        "aliases": [
            ("Electrolyte Panel", "synonym"),
            ("Na K Cl", "synonym"),
            ("Sodium Potassium Chloride", "synonym"),
        ],
    },
]


class Command(BaseCommand):
    help = "Seed a curated MVP list of common lab tests into the lab_catalog."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-version",
            default="mvp-1",
            help="Source version label for LabCatalogImportBatch (default: mvp-1).",
        )

    def handle(self, *args, **options):
        source_version = options.get("source_version") or "mvp-1"

        batch = LabCatalogImportBatch.objects.create(
            source_name="manual_seed",
            source_version=source_version,
            status=LabCatalogImportBatch.Status.STARTED,
        )

        created_tests = 0
        updated_tests = 0
        created_aliases = 0
        skipped_aliases = 0

        try:
            with transaction.atomic():
                for entry in LAB_TESTS_SEED:
                    batch.total_records += 1

                    name = entry["name"]
                    short_name = entry.get("short_name")

                    existing = LabTest.objects.filter(name__iexact=name).first()
                    if not existing and short_name:
                        existing = LabTest.objects.filter(
                            short_name__iexact=short_name
                        ).first()

                    if existing:
                        updated_tests += 1
                        lab_test = existing
                    else:
                        lab_test = LabTest.objects.create(
                            name=name,
                            short_name=short_name,
                            category=entry.get("category"),
                            sample_type=entry.get("sample_type"),
                            source_name="manual_seed",
                            is_verified=False,
                        )
                        created_tests += 1

                    for alias_text, alias_type in entry.get("aliases", []):
                        alias_lower = alias_text.lower()
                        already_exists = lab_test.aliases.filter(
                            alias__iexact=alias_lower
                        ).exists()
                        if already_exists:
                            skipped_aliases += 1
                        else:
                            LabTestAlias.objects.create(
                                lab_test=lab_test,
                                alias=alias_text,
                                alias_type=alias_type,
                                source_name="manual_seed",
                            )
                            created_aliases += 1

                batch.created_records = created_tests
                batch.updated_records = updated_tests
                batch.skipped_records = skipped_aliases
                batch.finished_at = timezone.now()
                batch.status = LabCatalogImportBatch.Status.COMPLETED
                batch.notes = (
                    f"Created {created_tests} tests, updated {updated_tests} existing, "
                    f"created {created_aliases} aliases, skipped {skipped_aliases} duplicate aliases."
                )
                batch.save()

        except Exception as exc:
            batch.status = LabCatalogImportBatch.Status.FAILED
            batch.finished_at = timezone.now()
            batch.notes = str(exc)
            batch.save()
            self.stderr.write(self.style.ERROR(f"Seed failed: {exc}"))
            raise

        self.stdout.write(self.style.SUCCESS(
            f"seed_lab_tests completed: "
            f"created={created_tests}, updated={updated_tests}, "
            f"aliases_created={created_aliases}, aliases_skipped={skipped_aliases}"
        ))
