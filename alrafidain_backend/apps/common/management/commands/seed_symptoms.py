"""
Management command: seed_symptoms

Seeds SymptomCategory, Symptom, and SymptomSpecialtyRule records.
Idempotent — safe to run multiple times.

Catalog design:
- 18 patient-friendly categories covering common complaint areas.
- ~127 symptoms using plain patient-language names (not disease names).
- Every active symptom has at least one routing rule.
- Red-flag symptoms always include emergency_medicine routing.
- Specialty routing is deterministic weight-based; AI triage is future work.
- This catalog supports specialty routing and triage, NOT final diagnosis.
  Doctor diagnosis remains the doctor's responsibility.
"""

from django.core.management.base import BaseCommand

from apps.common.choices import MedicalSpecialty
from apps.consultations.models import Symptom, SymptomCategory, SymptomSpecialtyRule

# ---------------------------------------------------------------------------
# Data definitions
# ---------------------------------------------------------------------------

# (category_name, display_order)
CATEGORIES = [
    ("Emergency / Red Flags", 1),
    ("General / Constitutional", 2),
    ("Respiratory", 3),
    ("Cardiovascular", 4),
    ("Gastrointestinal", 5),
    ("Neurological", 6),
    ("Musculoskeletal", 7),
    ("Skin / Dermatology", 8),
    ("Ear, Nose, and Throat", 9),
    ("Eye", 10),
    ("Urinary / Kidney", 11),
    ("Reproductive / Gynecology", 12),
    ("Endocrine / Metabolic", 13),
    ("Mental Health / Sleep", 14),
    ("Pediatric Concerns", 15),
    ("Injury / Trauma", 16),
    ("Dental / Oral", 17),
    ("Allergy / Immunology", 18),
]

# (symptom_name, category_name, is_red_flag)
SYMPTOMS = [
    # ------------------------------------------------------------------ Emergency / Red Flags
    ("Severe chest pain", "Emergency / Red Flags", True),
    ("Loss of consciousness", "Emergency / Red Flags", True),
    ("Seizure", "Emergency / Red Flags", True),
    ("Sudden weakness on one side", "Emergency / Red Flags", True),
    ("Sudden confusion", "Emergency / Red Flags", True),
    ("Severe allergic reaction", "Emergency / Red Flags", True),
    ("Severe bleeding", "Emergency / Red Flags", True),
    ("Severe abdominal pain", "Emergency / Red Flags", True),
    ("Blue lips or face", "Emergency / Red Flags", True),
    ("Sudden severe headache", "Emergency / Red Flags", True),
    ("Suicidal thoughts", "Emergency / Red Flags", True),
    # ------------------------------------------------------------------ General / Constitutional
    ("Fever", "General / Constitutional", False),
    ("Fatigue", "General / Constitutional", False),
    ("Weight loss", "General / Constitutional", False),
    ("Night sweats", "General / Constitutional", False),
    ("Loss of appetite", "General / Constitutional", False),
    ("General weakness", "General / Constitutional", False),
    ("Body aches", "General / Constitutional", False),
    # ------------------------------------------------------------------ Respiratory
    ("Cough", "Respiratory", False),
    ("Shortness of breath", "Respiratory", False),
    ("Severe shortness of breath", "Respiratory", True),
    ("Wheezing", "Respiratory", False),
    ("Chest tightness", "Respiratory", False),
    ("Runny nose", "Respiratory", False),
    ("Nasal congestion", "Respiratory", False),
    ("Coughing blood", "Respiratory", True),
    # ------------------------------------------------------------------ Cardiovascular
    ("Chest pain", "Cardiovascular", False),
    ("Palpitations", "Cardiovascular", False),
    ("Leg swelling", "Cardiovascular", False),
    ("Fainting", "Cardiovascular", False),
    ("High blood pressure reading", "Cardiovascular", False),
    ("Racing heart", "Cardiovascular", False),
    # ------------------------------------------------------------------ Gastrointestinal
    ("Abdominal pain", "Gastrointestinal", False),
    ("Nausea", "Gastrointestinal", False),
    ("Vomiting", "Gastrointestinal", False),
    ("Diarrhea", "Gastrointestinal", False),
    ("Constipation", "Gastrointestinal", False),
    ("Blood in stool", "Gastrointestinal", True),
    ("Heartburn", "Gastrointestinal", False),
    ("Difficulty swallowing", "Gastrointestinal", False),
    ("Jaundice", "Gastrointestinal", False),
    # ------------------------------------------------------------------ Neurological
    ("Headache", "Neurological", False),
    ("Dizziness", "Neurological", False),
    ("Migraine-like headache", "Neurological", False),
    ("Numbness or tingling", "Neurological", False),
    ("Muscle weakness", "Neurological", False),
    ("Tremor", "Neurological", False),
    ("Memory problems", "Neurological", False),
    ("Speech difficulty", "Neurological", True),
    ("Balance problems", "Neurological", False),
    # ------------------------------------------------------------------ Musculoskeletal
    ("Back pain", "Musculoskeletal", False),
    ("Joint pain", "Musculoskeletal", False),
    ("Neck pain", "Musculoskeletal", False),
    ("Muscle pain", "Musculoskeletal", False),
    ("Swelling at joint", "Musculoskeletal", False),
    ("Limited movement", "Musculoskeletal", False),
    ("Bone pain", "Musculoskeletal", False),
    # ------------------------------------------------------------------ Skin / Dermatology
    ("Skin rash", "Skin / Dermatology", False),
    ("Itching", "Skin / Dermatology", False),
    ("Skin wound", "Skin / Dermatology", False),
    ("Burn injury", "Skin / Dermatology", False),
    ("Hair loss", "Skin / Dermatology", False),
    ("Skin discoloration", "Skin / Dermatology", False),
    ("Mole or lesion change", "Skin / Dermatology", False),
    ("Skin infection", "Skin / Dermatology", False),
    # ------------------------------------------------------------------ Ear, Nose, and Throat
    ("Sore throat", "Ear, Nose, and Throat", False),
    ("Ear pain", "Ear, Nose, and Throat", False),
    ("Hearing loss", "Ear, Nose, and Throat", False),
    ("Tinnitus", "Ear, Nose, and Throat", False),
    ("Sinus pain", "Ear, Nose, and Throat", False),
    ("Nosebleed", "Ear, Nose, and Throat", False),
    ("Hoarseness", "Ear, Nose, and Throat", False),
    # ------------------------------------------------------------------ Eye
    ("Eye redness", "Eye", False),
    ("Eye pain", "Eye", False),
    ("Blurred vision", "Eye", False),
    ("Vision loss", "Eye", True),
    ("Eye discharge", "Eye", False),
    ("Light sensitivity", "Eye", False),
    # ------------------------------------------------------------------ Urinary / Kidney
    ("Painful urination", "Urinary / Kidney", False),
    ("Frequent urination", "Urinary / Kidney", False),
    ("Blood in urine", "Urinary / Kidney", False),
    ("Flank pain", "Urinary / Kidney", False),
    ("Reduced urination", "Urinary / Kidney", False),
    ("Urinary leakage", "Urinary / Kidney", False),
    # ------------------------------------------------------------------ Reproductive / Gynecology
    ("Pelvic pain", "Reproductive / Gynecology", False),
    ("Abnormal vaginal bleeding", "Reproductive / Gynecology", False),
    ("Vaginal discharge", "Reproductive / Gynecology", False),
    ("Pregnancy concern", "Reproductive / Gynecology", False),
    ("Breast lump", "Reproductive / Gynecology", False),
    ("Testicular pain", "Reproductive / Gynecology", False),
    ("Erectile dysfunction", "Reproductive / Gynecology", False),
    # ------------------------------------------------------------------ Endocrine / Metabolic
    ("Excessive thirst", "Endocrine / Metabolic", False),
    ("Frequent hunger", "Endocrine / Metabolic", False),
    ("Frequent urination with thirst", "Endocrine / Metabolic", False),
    ("Heat intolerance", "Endocrine / Metabolic", False),
    ("Cold intolerance", "Endocrine / Metabolic", False),
    ("Unexplained weight gain", "Endocrine / Metabolic", False),
    ("Unexplained weight loss", "Endocrine / Metabolic", False),
    # ------------------------------------------------------------------ Mental Health / Sleep
    ("Anxiety", "Mental Health / Sleep", False),
    ("Low mood", "Mental Health / Sleep", False),
    ("Panic attacks", "Mental Health / Sleep", False),
    ("Insomnia", "Mental Health / Sleep", False),
    ("Excessive sleepiness", "Mental Health / Sleep", False),
    ("Irritability", "Mental Health / Sleep", False),
    # ------------------------------------------------------------------ Pediatric Concerns
    ("Child fever", "Pediatric Concerns", False),
    ("Poor feeding in infant", "Pediatric Concerns", False),
    ("Persistent crying in infant", "Pediatric Concerns", False),
    ("Child rash", "Pediatric Concerns", False),
    ("Child breathing difficulty", "Pediatric Concerns", True),
    ("Signs of dehydration in child", "Pediatric Concerns", False),
    # ------------------------------------------------------------------ Injury / Trauma
    ("Fall injury", "Injury / Trauma", False),
    ("Head injury", "Injury / Trauma", True),
    ("Cut wound", "Injury / Trauma", False),
    ("Sprain or strain", "Injury / Trauma", False),
    ("Suspected fracture", "Injury / Trauma", False),
    ("Animal bite", "Injury / Trauma", False),
    # ------------------------------------------------------------------ Dental / Oral
    ("Tooth pain", "Dental / Oral", False),
    ("Gum swelling", "Dental / Oral", False),
    ("Mouth ulcer", "Dental / Oral", False),
    ("Jaw pain", "Dental / Oral", False),
    ("Dental abscess", "Dental / Oral", False),
    # ------------------------------------------------------------------ Allergy / Immunology
    ("Hives", "Allergy / Immunology", False),
    ("Facial or lip swelling", "Allergy / Immunology", True),
    ("Itchy eyes", "Allergy / Immunology", False),
    ("Frequent sneezing", "Allergy / Immunology", False),
    ("Food reaction", "Allergy / Immunology", False),
    ("Medication reaction", "Allergy / Immunology", False),
]

# (symptom_name, specialty, weight)
# Routing principles:
#   - Every symptom has at least one rule.
#   - Red-flag symptoms always include emergency_medicine.
#   - Vague/common symptoms include general_medicine or internal_medicine.
#   - Weights use a 1–100 scale; higher = stronger signal.
SPECIALTY_RULES = [
    # ------------------------------------------------------------------ Emergency / Red Flags
    ("Severe chest pain", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Severe chest pain", MedicalSpecialty.CARDIOLOGY, 80),
    ("Loss of consciousness", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Loss of consciousness", MedicalSpecialty.NEUROLOGY, 50),
    ("Seizure", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Seizure", MedicalSpecialty.NEUROLOGY, 80),
    ("Sudden weakness on one side", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Sudden weakness on one side", MedicalSpecialty.NEUROLOGY, 80),
    ("Sudden confusion", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Sudden confusion", MedicalSpecialty.NEUROLOGY, 70),
    ("Severe allergic reaction", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Severe bleeding", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Severe abdominal pain", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Severe abdominal pain", MedicalSpecialty.GASTROENTEROLOGY, 70),
    ("Blue lips or face", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Blue lips or face", MedicalSpecialty.PULMONOLOGY, 60),
    ("Sudden severe headache", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Sudden severe headache", MedicalSpecialty.NEUROLOGY, 80),
    ("Suicidal thoughts", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Suicidal thoughts", MedicalSpecialty.PSYCHIATRY, 90),
    # ------------------------------------------------------------------ General / Constitutional
    ("Fever", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Fever", MedicalSpecialty.INTERNAL_MEDICINE, 40),
    ("Fatigue", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Fatigue", MedicalSpecialty.INTERNAL_MEDICINE, 40),
    ("Weight loss", MedicalSpecialty.INTERNAL_MEDICINE, 60),
    ("Weight loss", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Night sweats", MedicalSpecialty.INTERNAL_MEDICINE, 60),
    ("Night sweats", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Loss of appetite", MedicalSpecialty.INTERNAL_MEDICINE, 50),
    ("Loss of appetite", MedicalSpecialty.GASTROENTEROLOGY, 30),
    ("Loss of appetite", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("General weakness", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("General weakness", MedicalSpecialty.INTERNAL_MEDICINE, 40),
    ("Body aches", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Body aches", MedicalSpecialty.INTERNAL_MEDICINE, 30),
    # ------------------------------------------------------------------ Respiratory
    ("Cough", MedicalSpecialty.PULMONOLOGY, 70),
    ("Cough", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Shortness of breath", MedicalSpecialty.PULMONOLOGY, 80),
    ("Shortness of breath", MedicalSpecialty.CARDIOLOGY, 50),
    ("Shortness of breath", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Severe shortness of breath", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Severe shortness of breath", MedicalSpecialty.PULMONOLOGY, 80),
    ("Wheezing", MedicalSpecialty.PULMONOLOGY, 80),
    ("Wheezing", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Chest tightness", MedicalSpecialty.PULMONOLOGY, 60),
    ("Chest tightness", MedicalSpecialty.CARDIOLOGY, 60),
    ("Chest tightness", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Runny nose", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Runny nose", MedicalSpecialty.ENT, 40),
    ("Nasal congestion", MedicalSpecialty.ENT, 60),
    ("Nasal congestion", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Coughing blood", MedicalSpecialty.PULMONOLOGY, 90),
    ("Coughing blood", MedicalSpecialty.EMERGENCY_MEDICINE, 70),
    # ------------------------------------------------------------------ Cardiovascular
    ("Chest pain", MedicalSpecialty.CARDIOLOGY, 80),
    ("Chest pain", MedicalSpecialty.EMERGENCY_MEDICINE, 60),
    ("Chest pain", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Palpitations", MedicalSpecialty.CARDIOLOGY, 80),
    ("Palpitations", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Leg swelling", MedicalSpecialty.CARDIOLOGY, 60),
    ("Leg swelling", MedicalSpecialty.INTERNAL_MEDICINE, 50),
    ("Leg swelling", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Fainting", MedicalSpecialty.CARDIOLOGY, 60),
    ("Fainting", MedicalSpecialty.NEUROLOGY, 50),
    ("Fainting", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("High blood pressure reading", MedicalSpecialty.CARDIOLOGY, 70),
    ("High blood pressure reading", MedicalSpecialty.INTERNAL_MEDICINE, 60),
    ("High blood pressure reading", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Racing heart", MedicalSpecialty.CARDIOLOGY, 80),
    ("Racing heart", MedicalSpecialty.GENERAL_MEDICINE, 30),
    # ------------------------------------------------------------------ Gastrointestinal
    ("Abdominal pain", MedicalSpecialty.GASTROENTEROLOGY, 70),
    ("Abdominal pain", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Nausea", MedicalSpecialty.GASTROENTEROLOGY, 60),
    ("Nausea", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Vomiting", MedicalSpecialty.GASTROENTEROLOGY, 60),
    ("Vomiting", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Diarrhea", MedicalSpecialty.GASTROENTEROLOGY, 60),
    ("Diarrhea", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Constipation", MedicalSpecialty.GASTROENTEROLOGY, 60),
    ("Constipation", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Blood in stool", MedicalSpecialty.GASTROENTEROLOGY, 90),
    ("Blood in stool", MedicalSpecialty.EMERGENCY_MEDICINE, 60),
    ("Heartburn", MedicalSpecialty.GASTROENTEROLOGY, 70),
    ("Heartburn", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Difficulty swallowing", MedicalSpecialty.GASTROENTEROLOGY, 80),
    ("Difficulty swallowing", MedicalSpecialty.ENT, 40),
    ("Jaundice", MedicalSpecialty.GASTROENTEROLOGY, 90),
    ("Jaundice", MedicalSpecialty.INTERNAL_MEDICINE, 60),
    # ------------------------------------------------------------------ Neurological
    ("Headache", MedicalSpecialty.NEUROLOGY, 70),
    ("Headache", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Dizziness", MedicalSpecialty.NEUROLOGY, 60),
    ("Dizziness", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Migraine-like headache", MedicalSpecialty.NEUROLOGY, 80),
    ("Migraine-like headache", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Numbness or tingling", MedicalSpecialty.NEUROLOGY, 70),
    ("Numbness or tingling", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Muscle weakness", MedicalSpecialty.NEUROLOGY, 60),
    ("Muscle weakness", MedicalSpecialty.ORTHOPEDICS, 40),
    ("Muscle weakness", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Tremor", MedicalSpecialty.NEUROLOGY, 80),
    ("Memory problems", MedicalSpecialty.NEUROLOGY, 70),
    ("Memory problems", MedicalSpecialty.PSYCHIATRY, 40),
    ("Speech difficulty", MedicalSpecialty.NEUROLOGY, 80),
    ("Speech difficulty", MedicalSpecialty.EMERGENCY_MEDICINE, 60),
    ("Balance problems", MedicalSpecialty.NEUROLOGY, 70),
    ("Balance problems", MedicalSpecialty.ENT, 30),
    # ------------------------------------------------------------------ Musculoskeletal
    ("Back pain", MedicalSpecialty.ORTHOPEDICS, 70),
    ("Back pain", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Back pain", MedicalSpecialty.RHEUMATOLOGY, 30),
    ("Joint pain", MedicalSpecialty.RHEUMATOLOGY, 70),
    ("Joint pain", MedicalSpecialty.ORTHOPEDICS, 60),
    ("Joint pain", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Neck pain", MedicalSpecialty.ORTHOPEDICS, 70),
    ("Neck pain", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Muscle pain", MedicalSpecialty.GENERAL_MEDICINE, 60),
    ("Muscle pain", MedicalSpecialty.ORTHOPEDICS, 40),
    ("Swelling at joint", MedicalSpecialty.ORTHOPEDICS, 70),
    ("Swelling at joint", MedicalSpecialty.RHEUMATOLOGY, 60),
    ("Limited movement", MedicalSpecialty.ORTHOPEDICS, 70),
    ("Limited movement", MedicalSpecialty.RHEUMATOLOGY, 40),
    ("Bone pain", MedicalSpecialty.ORTHOPEDICS, 80),
    ("Bone pain", MedicalSpecialty.INTERNAL_MEDICINE, 40),
    # ------------------------------------------------------------------ Skin / Dermatology
    ("Skin rash", MedicalSpecialty.DERMATOLOGY, 80),
    ("Skin rash", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Itching", MedicalSpecialty.DERMATOLOGY, 70),
    ("Itching", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Skin wound", MedicalSpecialty.GENERAL_MEDICINE, 60),
    ("Skin wound", MedicalSpecialty.DERMATOLOGY, 40),
    ("Burn injury", MedicalSpecialty.EMERGENCY_MEDICINE, 60),
    ("Burn injury", MedicalSpecialty.DERMATOLOGY, 50),
    ("Hair loss", MedicalSpecialty.DERMATOLOGY, 80),
    ("Skin discoloration", MedicalSpecialty.DERMATOLOGY, 80),
    ("Skin discoloration", MedicalSpecialty.INTERNAL_MEDICINE, 30),
    ("Mole or lesion change", MedicalSpecialty.DERMATOLOGY, 90),
    ("Skin infection", MedicalSpecialty.DERMATOLOGY, 70),
    ("Skin infection", MedicalSpecialty.GENERAL_MEDICINE, 50),
    # ------------------------------------------------------------------ Ear, Nose, and Throat
    ("Sore throat", MedicalSpecialty.ENT, 70),
    ("Sore throat", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Ear pain", MedicalSpecialty.ENT, 80),
    ("Ear pain", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Hearing loss", MedicalSpecialty.ENT, 90),
    ("Tinnitus", MedicalSpecialty.ENT, 80),
    ("Sinus pain", MedicalSpecialty.ENT, 80),
    ("Sinus pain", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Nosebleed", MedicalSpecialty.ENT, 70),
    ("Nosebleed", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Hoarseness", MedicalSpecialty.ENT, 70),
    ("Hoarseness", MedicalSpecialty.GENERAL_MEDICINE, 30),
    # ------------------------------------------------------------------ Eye
    ("Eye redness", MedicalSpecialty.OPHTHALMOLOGY, 80),
    ("Eye redness", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Eye pain", MedicalSpecialty.OPHTHALMOLOGY, 90),
    ("Eye pain", MedicalSpecialty.GENERAL_MEDICINE, 20),
    ("Blurred vision", MedicalSpecialty.OPHTHALMOLOGY, 80),
    ("Blurred vision", MedicalSpecialty.NEUROLOGY, 40),
    ("Vision loss", MedicalSpecialty.OPHTHALMOLOGY, 90),
    ("Vision loss", MedicalSpecialty.EMERGENCY_MEDICINE, 60),
    ("Vision loss", MedicalSpecialty.NEUROLOGY, 50),
    ("Eye discharge", MedicalSpecialty.OPHTHALMOLOGY, 80),
    ("Eye discharge", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Light sensitivity", MedicalSpecialty.OPHTHALMOLOGY, 70),
    ("Light sensitivity", MedicalSpecialty.NEUROLOGY, 50),
    # ------------------------------------------------------------------ Urinary / Kidney
    ("Painful urination", MedicalSpecialty.UROLOGY, 80),
    ("Painful urination", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Frequent urination", MedicalSpecialty.UROLOGY, 70),
    ("Frequent urination", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Frequent urination", MedicalSpecialty.ENDOCRINOLOGY, 40),
    ("Blood in urine", MedicalSpecialty.UROLOGY, 90),
    ("Blood in urine", MedicalSpecialty.NEPHROLOGY, 60),
    ("Flank pain", MedicalSpecialty.NEPHROLOGY, 80),
    ("Flank pain", MedicalSpecialty.UROLOGY, 60),
    ("Flank pain", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Reduced urination", MedicalSpecialty.NEPHROLOGY, 90),
    ("Reduced urination", MedicalSpecialty.EMERGENCY_MEDICINE, 50),
    ("Urinary leakage", MedicalSpecialty.UROLOGY, 80),
    # ------------------------------------------------------------------ Reproductive / Gynecology
    ("Pelvic pain", MedicalSpecialty.GYNECOLOGY, 80),
    ("Pelvic pain", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Abnormal vaginal bleeding", MedicalSpecialty.GYNECOLOGY, 90),
    ("Vaginal discharge", MedicalSpecialty.GYNECOLOGY, 80),
    ("Vaginal discharge", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Pregnancy concern", MedicalSpecialty.GYNECOLOGY, 90),
    ("Breast lump", MedicalSpecialty.GYNECOLOGY, 80),
    ("Breast lump", MedicalSpecialty.INTERNAL_MEDICINE, 40),
    ("Testicular pain", MedicalSpecialty.UROLOGY, 90),
    ("Erectile dysfunction", MedicalSpecialty.UROLOGY, 80),
    # ------------------------------------------------------------------ Endocrine / Metabolic
    ("Excessive thirst", MedicalSpecialty.ENDOCRINOLOGY, 80),
    ("Excessive thirst", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Excessive thirst", MedicalSpecialty.INTERNAL_MEDICINE, 40),
    ("Frequent hunger", MedicalSpecialty.ENDOCRINOLOGY, 70),
    ("Frequent hunger", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Frequent urination with thirst", MedicalSpecialty.ENDOCRINOLOGY, 90),
    ("Frequent urination with thirst", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Heat intolerance", MedicalSpecialty.ENDOCRINOLOGY, 80),
    ("Heat intolerance", MedicalSpecialty.INTERNAL_MEDICINE, 40),
    ("Cold intolerance", MedicalSpecialty.ENDOCRINOLOGY, 80),
    ("Cold intolerance", MedicalSpecialty.INTERNAL_MEDICINE, 40),
    ("Unexplained weight gain", MedicalSpecialty.ENDOCRINOLOGY, 70),
    ("Unexplained weight gain", MedicalSpecialty.INTERNAL_MEDICINE, 50),
    ("Unexplained weight loss", MedicalSpecialty.INTERNAL_MEDICINE, 60),
    ("Unexplained weight loss", MedicalSpecialty.ENDOCRINOLOGY, 60),
    ("Unexplained weight loss", MedicalSpecialty.GENERAL_MEDICINE, 30),
    # ------------------------------------------------------------------ Mental Health / Sleep
    ("Anxiety", MedicalSpecialty.PSYCHIATRY, 80),
    ("Anxiety", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Low mood", MedicalSpecialty.PSYCHIATRY, 80),
    ("Low mood", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Panic attacks", MedicalSpecialty.PSYCHIATRY, 80),
    ("Insomnia", MedicalSpecialty.PSYCHIATRY, 70),
    ("Insomnia", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Excessive sleepiness", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Excessive sleepiness", MedicalSpecialty.PSYCHIATRY, 40),
    ("Excessive sleepiness", MedicalSpecialty.NEUROLOGY, 40),
    ("Irritability", MedicalSpecialty.PSYCHIATRY, 70),
    ("Irritability", MedicalSpecialty.GENERAL_MEDICINE, 40),
    # ------------------------------------------------------------------ Pediatric Concerns
    ("Child fever", MedicalSpecialty.PEDIATRICS, 80),
    ("Child fever", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Poor feeding in infant", MedicalSpecialty.PEDIATRICS, 90),
    ("Persistent crying in infant", MedicalSpecialty.PEDIATRICS, 80),
    ("Child rash", MedicalSpecialty.PEDIATRICS, 70),
    ("Child rash", MedicalSpecialty.DERMATOLOGY, 50),
    ("Child breathing difficulty", MedicalSpecialty.EMERGENCY_MEDICINE, 90),
    ("Child breathing difficulty", MedicalSpecialty.PEDIATRICS, 80),
    ("Signs of dehydration in child", MedicalSpecialty.EMERGENCY_MEDICINE, 70),
    ("Signs of dehydration in child", MedicalSpecialty.PEDIATRICS, 80),
    # ------------------------------------------------------------------ Injury / Trauma
    ("Fall injury", MedicalSpecialty.EMERGENCY_MEDICINE, 60),
    ("Fall injury", MedicalSpecialty.ORTHOPEDICS, 60),
    ("Fall injury", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Head injury", MedicalSpecialty.EMERGENCY_MEDICINE, 100),
    ("Head injury", MedicalSpecialty.NEUROLOGY, 60),
    ("Cut wound", MedicalSpecialty.GENERAL_MEDICINE, 60),
    ("Cut wound", MedicalSpecialty.EMERGENCY_MEDICINE, 50),
    ("Sprain or strain", MedicalSpecialty.ORTHOPEDICS, 70),
    ("Sprain or strain", MedicalSpecialty.GENERAL_MEDICINE, 40),
    ("Suspected fracture", MedicalSpecialty.ORTHOPEDICS, 90),
    ("Suspected fracture", MedicalSpecialty.EMERGENCY_MEDICINE, 60),
    ("Animal bite", MedicalSpecialty.GENERAL_MEDICINE, 70),
    ("Animal bite", MedicalSpecialty.EMERGENCY_MEDICINE, 50),
    # ------------------------------------------------------------------ Dental / Oral
    ("Tooth pain", MedicalSpecialty.DENTISTRY, 90),
    ("Tooth pain", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Gum swelling", MedicalSpecialty.DENTISTRY, 80),
    ("Gum swelling", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Mouth ulcer", MedicalSpecialty.DENTISTRY, 60),
    ("Mouth ulcer", MedicalSpecialty.GENERAL_MEDICINE, 60),
    ("Jaw pain", MedicalSpecialty.DENTISTRY, 70),
    ("Jaw pain", MedicalSpecialty.ORTHOPEDICS, 40),
    ("Dental abscess", MedicalSpecialty.DENTISTRY, 90),
    ("Dental abscess", MedicalSpecialty.EMERGENCY_MEDICINE, 40),
    # ------------------------------------------------------------------ Allergy / Immunology
    ("Hives", MedicalSpecialty.DERMATOLOGY, 60),
    ("Hives", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Hives", MedicalSpecialty.INTERNAL_MEDICINE, 30),
    ("Facial or lip swelling", MedicalSpecialty.EMERGENCY_MEDICINE, 90),
    ("Facial or lip swelling", MedicalSpecialty.GENERAL_MEDICINE, 30),
    ("Itchy eyes", MedicalSpecialty.OPHTHALMOLOGY, 60),
    ("Itchy eyes", MedicalSpecialty.GENERAL_MEDICINE, 50),
    ("Frequent sneezing", MedicalSpecialty.GENERAL_MEDICINE, 60),
    ("Frequent sneezing", MedicalSpecialty.ENT, 50),
    ("Food reaction", MedicalSpecialty.GENERAL_MEDICINE, 70),
    ("Food reaction", MedicalSpecialty.INTERNAL_MEDICINE, 40),
    ("Food reaction", MedicalSpecialty.EMERGENCY_MEDICINE, 30),
    ("Medication reaction", MedicalSpecialty.GENERAL_MEDICINE, 70),
    ("Medication reaction", MedicalSpecialty.INTERNAL_MEDICINE, 40),
    ("Medication reaction", MedicalSpecialty.EMERGENCY_MEDICINE, 30),
]


class Command(BaseCommand):
    help = "Seed symptom categories, symptoms, and specialty routing rules."

    def handle(self, *args, **options):
        cat_created = 0
        symptom_created = 0
        rule_created = 0

        # ------------------------------------------------------------------
        # Categories — create or update display_order
        # ------------------------------------------------------------------
        category_map: dict[str, SymptomCategory] = {}
        for name, display_order in CATEGORIES:
            obj, created = SymptomCategory.objects.get_or_create(
                name=name,
                defaults={"display_order": display_order, "is_active": True},
            )
            if not created and obj.display_order != display_order:
                obj.display_order = display_order
                obj.save(update_fields=["display_order"])
            category_map[name] = obj
            if created:
                cat_created += 1

        # ------------------------------------------------------------------
        # Symptoms — create or update is_red_flag
        # ------------------------------------------------------------------
        symptom_map: dict[str, Symptom] = {}
        for name, cat_name, is_red_flag in SYMPTOMS:
            category = category_map.get(cat_name)
            if not category:
                self.stderr.write(f"  WARN: missing category '{cat_name}' for symptom '{name}'")
                continue
            obj, created = Symptom.objects.get_or_create(
                name=name,
                category=category,
                defaults={"is_red_flag": is_red_flag, "is_active": True},
            )
            if not created and obj.is_red_flag != is_red_flag:
                obj.is_red_flag = is_red_flag
                obj.save(update_fields=["is_red_flag"])
            # Key by "CategoryName|SymptomName" for unambiguous lookup
            symptom_map[f"{cat_name}|{name}"] = obj
            if created:
                symptom_created += 1

        # ------------------------------------------------------------------
        # Specialty rules — create or update weight
        # ------------------------------------------------------------------
        # Build a reverse index: symptom_name → list of symptom objects
        name_to_symptoms: dict[str, list[Symptom]] = {}
        for _key, sym in symptom_map.items():
            name_to_symptoms.setdefault(sym.name, []).append(sym)

        for symptom_name, specialty, weight in SPECIALTY_RULES:
            syms = name_to_symptoms.get(symptom_name)
            if not syms:
                self.stderr.write(
                    f"  WARN: symptom '{symptom_name}' not found for rule ({specialty}, {weight})"
                )
                continue
            for symptom in syms:
                rule, created = SymptomSpecialtyRule.objects.get_or_create(
                    symptom=symptom,
                    specialty=specialty,
                    defaults={"weight": weight, "is_active": True},
                )
                if not created and rule.weight != weight:
                    rule.weight = weight
                    rule.save(update_fields=["weight"])
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
