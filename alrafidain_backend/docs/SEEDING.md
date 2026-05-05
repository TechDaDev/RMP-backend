# Seeding

Seed commands populate the database with initial data for development and testing.
All seed commands are **idempotent** — safe to run multiple times.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Individual Commands](#individual-commands)
  - [Seed Symptom Data](#seed-symptom-data)
  - [Seed Lab Test Catalog](#seed-lab-test-catalog)
  - [Seed Demo Users](#seed-demo-users)
- [Testing Seed Commands](#testing-seed-commands)

---

## Quick Start

Run all seed commands at once:

```bash
python manage.py seed_all --settings=config.settings.local
```

If your local PostgreSQL runs on port 5433:

```bash
DB_PORT=5433 python manage.py seed_all --settings=config.settings.local
```

---

## Individual Commands

### Seed Symptom Data

Creates `SymptomCategory`, `Symptom`, and `SymptomSpecialtyRule` records.

```bash
DB_PORT=5433 python manage.py seed_symptoms --settings=config.settings.local
```

**Creates:**
- 13 symptom categories (General, Respiratory, Cardiac, etc.)
- 22 common symptoms
- Specialty routing rules for each symptom
- Red flag markers for emergency symptoms (chest pain, seizure, etc.)

---

### Seed Lab Test Catalog

Creates `LabTestCatalog` entries for the 16 most common lab tests.

```bash
DB_PORT=5433 python manage.py seed_lab_tests --settings=config.settings.local
```

**Creates:**
- CBC, ESR, Lipid Profile, LFT, KFT, HbA1c, FBS, RBS
- Thyroid Function Test, Vitamin D, CRP
- Urine Analysis, Stool Analysis
- Blood Group
- Pregnancy Test
- Electrolytes

---

### Seed Demo Users

Creates four demo accounts for local development and testing.

```bash
DB_PORT=5433 python manage.py seed_demo_users --settings=config.settings.local
```

**Created accounts:**

| Role | Email | Password |
|---|---|---|
| Patient | `patient@example.com` | `DemoPass123!` |
| Doctor | `doctor@example.com` | `DemoPass123!` |
| Pharmacist | `pharmacist@example.com` | `DemoPass123!` |
| Laboratorian | `laboratorian@example.com` | `DemoPass123!` |

**Notes:**
- All accounts are active.
- Doctor, pharmacist, and laboratorian are approved.
- Demo patient has a `PatientMedicalRecord` created.
- Doctor specialty is set to `internal_medicine`.
- License fields are filled with demo placeholder values.

> **WARNING**: These credentials are for **development only**.  
> Never run `seed_demo_users` in a production environment.

---

## Testing Seed Commands

The test suite covers all seed commands:

```bash
DB_PORT=5433 python manage.py test apps.common.tests.test_seed_commands --settings=config.settings.test
```

Tests verify:
- Commands run without errors
- Key records are created
- Commands are idempotent (running twice does not duplicate data)
- Demo users are active and have correct roles
- Professional demo users are approved
