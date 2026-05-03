from collections import defaultdict

from apps.common.choices import MedicalSpecialty

from .models import Symptom, SymptomSpecialtyRule


def recommend_specialty_from_symptoms(symptom_ids):
    symptoms = Symptom.objects.filter(id__in=symptom_ids, is_active=True).select_related("category")
    active_ids = [s.id for s in symptoms]

    scores = defaultdict(int)
    rules = SymptomSpecialtyRule.objects.filter(symptom_id__in=active_ids, is_active=True)
    for rule in rules:
        scores[rule.specialty] += rule.weight

    has_red_flag = any(symptom.is_red_flag for symptom in symptoms)

    if not scores:
        return {
            "recommended_specialty": MedicalSpecialty.GENERAL_MEDICINE,
            "scores": {},
            "has_red_flag": has_red_flag,
        }

    # Deterministic winner: highest score then specialty value ascending
    recommended_specialty = sorted(scores.items(), key=lambda x: (-x[1], x[0]))[0][0]
    return {
        "recommended_specialty": recommended_specialty,
        "scores": dict(scores),
        "has_red_flag": has_red_flag,
    }
