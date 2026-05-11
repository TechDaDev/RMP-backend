# Test Users and Profile Mapping

Seed source: `apps/common/management/commands/seed_test_users.py`

## Credentials

| Role | Email | Password |
|---|---|---|
| Admin/Superuser | admin@rmp.local | Admin1234! |
| Patient | patient@rmp.local | Patient1234! |
| Doctor | doctor@rmp.local | Doctor1234! |
| Pharmacist | pharmacist@rmp.local | Pharmacist1234! |
| Laboratorian | laboratorian@rmp.local | Lab1234! |

## User Type and Profile Objects

| Account | `user_type` | Always Has `UserProfile` | Role-Specific Profile |
|---|---|---|---|
| Admin/Superuser | `doctor` (for model compatibility) | Yes | `DoctorProfile` |
| Patient | `patient` | Yes | `PatientProfile` |
| Doctor | `doctor` | Yes | `DoctorProfile` |
| Pharmacist | `pharmacist` | Yes | `PharmacistProfile` |
| Laboratorian | `laboratorian` | Yes | `LaboratorianProfile` |

Notes:
- There is no separate `admin` user type in the `UserType` enum.
- Admin access comes from `is_staff=True` and `is_superuser=True`.

## Profile Field Summary by Type

### Shared Profile (`UserProfile`) for all users
- `phone_number`
- `profile_image`
- `gender`
- `date_of_birth`
- `governorate`
- `district`
- `address`
- `national_id`

### Patient (`PatientProfile`)
- `social_security_id`
- `emergency_contact_name`
- `emergency_contact_phone`

### Doctor (`DoctorProfile`)
- `medical_license_number`
- `medical_license_image`
- `specialty`
- `specialty_other`
- `subspecialty`
- `professional_title`
- `years_of_experience`
- `bio`
- `work_address`
- `verification_status`
- `verified_at`
- `verified_by`
- `verification_notes`

### Pharmacist (`PharmacistProfile`)
- `pharmacist_license_number`
- `pharmacist_license_image`
- `pharmacy_name`
- `pharmacy_license_number`
- `pharmacy_license_image`
- `pharmacy_address`
- `working_hours`
- `verification_status`
- `verified_at`
- `verified_by`
- `verification_notes`

### Laboratorian (`LaboratorianProfile`)
- `laboratorian_license_number`
- `laboratorian_license_image`
- `laboratory_name`
- `laboratory_license_number`
- `laboratory_license_image`
- `laboratory_address`
- `specialization`
- `working_hours`
- `verification_status`
- `verified_at`
- `verified_by`
- `verification_notes`