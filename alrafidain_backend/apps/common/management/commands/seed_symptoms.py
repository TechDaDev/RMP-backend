"""
Management command: seed_symptoms

Seeds SymptomCategory, Symptom, and SymptomSpecialtyRule records.
Idempotent — safe to run multiple times.
"""

from django.core.management.base import BaseCommand

from apps.common.choices import MedicalSpecialty
from apps.consultations.models import Symptom, SymptomCategory, SymptomSpecialtyRule

# ---------------------------------------------------------------------------
# Data definitions
# ---------------------------------------------------------------------------

CATEGORIES = [
    ("General", 1),
    ("Respiratory", 2),
    ("Cardiac", 3),
    ("Digestive", 4),
    ("Neurological", 5),
    ("Skin", 6),
    ("Urinary", 7),
    ("Musculoskeletal", 8),
    ("ENT", 9),
    ("Eye", 10),
    ("Women's Health", 11),
    ("Mental Health", 12),
    ("Emergency", 13),
]

# (symptom_name, category_name, is_red_flag)
SYMPTOMS = [
    ("Fever", "General", False),
    ("Fatigue", "General", False),
    ("Cough", "Respiratory", False),
    ("Shortness of breath", "Respiratory", False),
    ("Chest pain", "Cardiac", True),
    ("Severe shortness of breath", "Respiratory", True),
    ("Headache", "Neurological", False),
    ("Dizziness", "Neurological", False),
    ("Abdominal pain", "Digestive", False),
    ("Vomiting", "Digestive", False),
    ("Diarrhea", "Digestive", False),
    ("Skin rash", "Skin", False),
    ("Itching", "Skin", False),
    ("Burning urination", "Urinary", False),
    ("Back pain", "Musculoskeletal", False),
    ("Joint pain", "Musculoskeletal", False),
    ("Sore throat", "ENT", False),
    ("Ear pain", "ENT", False),
    ("Eye redness", "Eye", False),
    ("Loss of consciousness", "Emergency", True),
    ("Seizure", "Emergency", True),
    ("Severe bleeding", "Emergency", True),
]

# (symptom_name, specialty, weight)
SPECIALTY_RULES = [
    ("Chest pain", MedicalSpecialty.CARDIOLOGY, 3),
    ("Chest pain", MedicalSpecialty.EMERGENCY_MEDICINE, 2),
    ("Shortness of breath", MedicalSpecialty.PULMONOLOGY, 3),
    ("Shortness of breath", MedicalSpecialty.EMERGENCY_MEDICINE, 2),
    ("Severe shortness of breath", MedicalSpecialty.PULMONOLOGY, 3),
    ("Severe shortness of breath", MedicalSpecialty.EMERGENCY_MEDICINE, 3),
    ("Skin rash", MedicalSpecialty.DERMATOLOGY, 3),
    ("Itching", MedicalSpecialty.DERMATOLOGY, 2),
    ("Burning urination", MedicalSpecialty.UROLOGY, 3),
    ("Abdominal pain", MedicalSpecialty.GASTROENTEROLOGY, 3),
    ("Abdominal pain", MedicalSpecialty.INTERNAL_MEDICINE, 2),
    ("Headache", MedicalSpecialty.NEUROLOGY, 3),
    ("Headache", MedicalSpecialty.INTERNAL_MEDICINE, 1),
    ("Dizziness", MedicalSpecialty.NEUROLOGY, 2),
    ("Sore throat", MedicalSpecialty.ENT, 3),
    ("Sore throat", MedicalSpecialty.GENERAL_MEDICINE, 1),
    ("Ear pain", MedicalSpecialty.ENT, 3),
    ("Eye redness", MedicalSpecialty.OPHTHALMOLOGY, 3),
    ("Joint pain", MedicalSpecialty.ORTHOPEDICS, 3),
    ("Joint pain", MedicalSpecialty.RHEUMATOLOGY, 2),
    ("Back pain", MedicalSpecialty.ORTHOPEDICS, 2),
    ("Fever", MedicalSpecialty.GENERAL_MEDICINE, 1),
    ("Fatigue", MedicalSpecialty.INTERNAL_MEDICINE, 1),
    ("Loss of consciousness", MedicalSpecialty.EMERGENCY_MEDICINE, 3),
    ("Seizure", MedicalSpecialty.EMERGENCY_MEDICINE, 3),
    ("Seizure", MedicalSpecialty.NEUROLOGY, 3),
    ("Severe bleeding", MedicalSpecialty.EMERGENCY_MEDICINE, 3),
    ("Vomiting", MedicalSpecialty.GASTROENTEROLOGY, 2),
    ("Diarrhea", MedicalSpecialty.GASTROENTEROLOGY, 2),
]


class Command(BaseCommand):
    help = "Seed symptom categories, symptoms, and specialty rules."

    def handle(self, *args, **options):
        cat_created = 0
        symptom_created = 0
        rule_created = 0

        # Categories
        category_map = {}
        for _order, (name, display_order) in enumerate(CATEGORIES):
            obj, created = SymptomCategory.objects.get_or_create(
                name=name,
                defaults={"display_order": display_order},
            )
            category_map[name] = obj
            if created:
                cat_created += 1

        # Symptoms
        symptom_map = {}
        for name, cat_name, is_red_flag in SYMPTOMS:
            category = category_map.get(cat_name)
            if not category:
                self.stderr.write(f"  Missing category: {cat_name}")
                continue
            obj, created = Symptom.objects.get_or_create(
                name=name,
                category=category,
                defaults={"is_red_flag": is_red_flag},
            )
            if not created and obj.is_red_flag != is_red_flag:
                obj.is_red_flag = is_red_flag
                obj.save(update_fields=["is_red_flag"])
            symptom_map[name] = obj
            if created:
                symptom_created += 1

        # Specialty rules
        for symptom_name, specialty, weight in SPECIALTY_RULES:
            symptom = symptom_map.get(symptom_name)
            if not symptom:
                self.stderr.write(f"  Missing symptom: {symptom_name}")
                continue
            _, created = SymptomSpecialtyRule.objects.get_or_create(
                symptom=symptom,
                specialty=specialty,
                defaults={"weight": weight},
            )
            if created:
                rule_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"seed_symptoms done: "
                f"{cat_created} categories, "
                f"{symptom_created} symptoms, "
                f"{rule_created} specialty rules created."
            )
        )
