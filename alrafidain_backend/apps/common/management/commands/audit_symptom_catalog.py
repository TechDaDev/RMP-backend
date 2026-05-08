"""
Management command: audit_symptom_catalog

Prints a structural integrity report for the symptom catalog.

Exit codes:
  0 — no critical issues detected.
  1 — critical issues detected (active symptoms with no routing rules,
      or duplicate active symptom names within the same category).

Non-critical warnings (empty categories, cross-category name duplicates,
red-flag symptoms without emergency routing) are printed but do not
cause a non-zero exit.
"""

import sys

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from apps.common.choices import MedicalSpecialty
from apps.consultations.models import Symptom, SymptomCategory, SymptomSpecialtyRule

# Routing examples printed for quick sanity-check.
ROUTING_EXAMPLE_NAMES = [
    "Cough",
    "Chest pain",
    "Severe chest pain",
    "Abdominal pain",
    "Skin rash",
    "Painful urination",
    "Suicidal thoughts",
]


class Command(BaseCommand):
    help = "Audit symptom catalog for coverage and routing integrity."

    def handle(self, *args, **options):
        has_critical_issues = False

        # ------------------------------------------------------------------
        # Summary stats
        # ------------------------------------------------------------------
        cat_count = SymptomCategory.objects.filter(is_active=True).count()
        sym_count = Symptom.objects.filter(is_active=True).count()
        rule_count = SymptomSpecialtyRule.objects.filter(is_active=True).count()
        red_flag_count = Symptom.objects.filter(is_active=True, is_red_flag=True).count()

        self.stdout.write("=== Symptom Catalog Audit ===")
        self.stdout.write(f"  Active categories:    {cat_count}")
        self.stdout.write(f"  Active symptoms:      {sym_count}")
        self.stdout.write(f"  Active routing rules: {rule_count}")
        self.stdout.write(f"  Red-flag symptoms:    {red_flag_count}")
        self.stdout.write("")

        # ------------------------------------------------------------------
        # CRITICAL: active symptoms with no active routing rules
        # ------------------------------------------------------------------
        syms_no_rules = (
            Symptom.objects.annotate(
                active_rule_count=Count(
                    "specialty_rules",
                    filter=Q(specialty_rules__is_active=True),
                )
            )
            .filter(active_rule_count=0, is_active=True)
            .select_related("category")
        )
        if syms_no_rules.exists():
            has_critical_issues = True
            self.stdout.write(
                self.style.ERROR(
                    f"  CRITICAL: {syms_no_rules.count()} active symptom(s) with no routing rules:"
                )
            )
            for sym in syms_no_rules:
                self.stdout.write(f"    - {sym.name!r} (category: {sym.category.name!r})")
        else:
            self.stdout.write(self.style.SUCCESS("  OK: All active symptoms have routing rules."))

        # ------------------------------------------------------------------
        # WARNING: categories with no active symptoms
        # ------------------------------------------------------------------
        empty_cats = SymptomCategory.objects.annotate(
            active_sym_count=Count(
                "symptoms",
                filter=Q(symptoms__is_active=True),
            )
        ).filter(active_sym_count=0, is_active=True)
        if empty_cats.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"  WARN: {empty_cats.count()} active category/ies with no active symptoms:"
                )
            )
            for cat in empty_cats:
                self.stdout.write(f"    - {cat.name!r}")
        else:
            self.stdout.write(self.style.SUCCESS("  OK: All active categories have symptoms."))

        # ------------------------------------------------------------------
        # WARNING: cross-category duplicate active symptom names
        # ------------------------------------------------------------------
        dup_names = (
            Symptom.objects.filter(is_active=True)
            .values("name")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
            .order_by("name")
        )
        if dup_names.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"  WARN: {dup_names.count()} symptom name(s) appear in multiple categories:"
                )
            )
            for d in dup_names:
                self.stdout.write(f"    - {d['name']!r} (appears {d['cnt']} times)")
        else:
            self.stdout.write(self.style.SUCCESS("  OK: No duplicate symptom names detected."))

        # ------------------------------------------------------------------
        # WARNING: red-flag symptoms without emergency_medicine routing
        # ------------------------------------------------------------------
        red_flag_syms = Symptom.objects.filter(is_active=True, is_red_flag=True)
        no_emergency_route = []
        for sym in red_flag_syms:
            has_emergency = SymptomSpecialtyRule.objects.filter(
                symptom=sym,
                specialty=MedicalSpecialty.EMERGENCY_MEDICINE,
                is_active=True,
            ).exists()
            if not has_emergency:
                no_emergency_route.append(sym)

        if no_emergency_route:
            self.stdout.write(
                self.style.WARNING(
                    f"  WARN: {len(no_emergency_route)} red-flag symptom(s) without"
                    " emergency_medicine routing:"
                )
            )
            for sym in no_emergency_route:
                self.stdout.write(f"    - {sym.name!r} (category: {sym.category.name!r})")
        else:
            self.stdout.write(
                self.style.SUCCESS("  OK: All red-flag symptoms have emergency_medicine routing.")
            )

        # ------------------------------------------------------------------
        # Routing examples
        # ------------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write("=== Routing Examples ===")

        # Build a quick infer function inline (mirrors services.infer_specialty)
        for sym_name in ROUTING_EXAMPLE_NAMES:
            syms = Symptom.objects.filter(name=sym_name, is_active=True)
            if not syms.exists():
                self.stdout.write(f"  {sym_name!r}: NOT FOUND in catalog")
                continue
            sym = syms.first()
            rules = SymptomSpecialtyRule.objects.filter(symptom=sym, is_active=True).order_by(
                "-weight"
            )
            if not rules.exists():
                self.stdout.write(f"  {sym_name!r}: NO RULES")
                continue
            routes_str = " | ".join(f"{r.specialty}({r.weight})" for r in rules)
            top = rules.first()
            self.stdout.write(f"  {sym_name!r}: top={top.specialty}  [{routes_str}]")

        # ------------------------------------------------------------------
        # Specialty coverage summary
        # ------------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write("=== Specialty Coverage ===")
        specialty_counts = (
            SymptomSpecialtyRule.objects.filter(is_active=True)
            .values("specialty")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
        )
        for row in specialty_counts:
            self.stdout.write(f"  {row['specialty']:<30} {row['cnt']} rules")

        # ------------------------------------------------------------------
        # Final verdict
        # ------------------------------------------------------------------
        self.stdout.write("")
        if has_critical_issues:
            self.stderr.write(
                self.style.ERROR("Audit FAILED: critical issues detected. Fix before deploying.")
            )
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("Audit PASSED: no critical issues."))
