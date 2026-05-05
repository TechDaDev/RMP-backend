"""
Management command: seed_lab_tests

Seeds LabTestCatalog records.
Idempotent — safe to run multiple times.
"""

from django.core.management.base import BaseCommand

from apps.common.choices import LabTestCategory
from apps.lab_orders.models import LabTestCatalog

LAB_TESTS = [
    # (name, category, code, description, sample_type)
    ("CBC", LabTestCategory.HEMATOLOGY, "CBC", "Complete Blood Count", "Whole blood"),
    ("ESR", LabTestCategory.HEMATOLOGY, "ESR", "Erythrocyte Sedimentation Rate", "Whole blood"),
    ("Fasting Blood Sugar", LabTestCategory.BIOCHEMISTRY, "FBS", "Fasting Blood Sugar", "Serum"),
    ("Random Blood Sugar", LabTestCategory.BIOCHEMISTRY, "RBS", "Random Blood Sugar", "Serum"),
    ("HbA1c", LabTestCategory.BIOCHEMISTRY, "HBA1C", "Glycated Haemoglobin", "Whole blood"),
    ("Lipid Profile", LabTestCategory.BIOCHEMISTRY, "LIPID", "Cholesterol, TG, HDL, LDL", "Serum"),
    (
        "Liver Function Test",
        LabTestCategory.BIOCHEMISTRY,
        "LFT",
        "ALT, AST, ALP, Bilirubin, Albumin",
        "Serum",
    ),
    (
        "Kidney Function Test",
        LabTestCategory.BIOCHEMISTRY,
        "KFT",
        "Creatinine, Urea, Uric Acid",
        "Serum",
    ),
    ("Electrolytes", LabTestCategory.BIOCHEMISTRY, "ELEC", "Na, K, Cl, CO2", "Serum"),
    ("CRP", LabTestCategory.IMMUNOLOGY, "CRP", "C-Reactive Protein", "Serum"),
    ("Vitamin D", LabTestCategory.IMMUNOLOGY, "VITD", "25-OH Vitamin D", "Serum"),
    ("Thyroid Function Test", LabTestCategory.HORMONES, "TFT", "TSH, T3, T4", "Serum"),
    ("Pregnancy Test", LabTestCategory.HORMONES, "PREG", "Beta-hCG", "Serum or urine"),
    ("Urine Analysis", LabTestCategory.URINE_STOOL, "UA", "Complete Urine Analysis", "Urine"),
    ("Stool Analysis", LabTestCategory.URINE_STOOL, "SA", "Complete Stool Analysis", "Stool"),
    ("Blood Group", LabTestCategory.BLOOD_BANK, "BG", "ABO/Rh Blood Grouping", "Whole blood"),
]


class Command(BaseCommand):
    help = "Seed lab test catalog entries."

    def handle(self, *args, **options):
        created_count = 0
        for order, (name, category, code, description, sample_type) in enumerate(LAB_TESTS):
            _, created = LabTestCatalog.objects.get_or_create(
                name=name,
                defaults={
                    "category": category,
                    "code": code,
                    "description": description,
                    "default_sample_type": sample_type,
                    "display_order": order,
                    "is_active": True,
                },
            )
            if created:
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "seed_lab_tests done: "
                f"{created_count} lab tests created "
                f"(total in db: {LabTestCatalog.objects.count()})."
            )
        )
