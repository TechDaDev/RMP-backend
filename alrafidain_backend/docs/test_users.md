# Test Users and Profile Mapping

Seed source: `apps/common/management/commands/seed_test_users.py`

## Credentials

| Role | Email | Password |
|---|---|---|
| System Admin | admin@rmp.local | Admin1234! |
| Verification Officer | verifier@rmp.local | Verifier1234! |
| Knowledge Base Manager | kbmanager@rmp.local | KBManager1234! |
| Analytics Officer | analytics@rmp.local | Analytics1234! |
| Support Specialist | support@rmp.local | Support1234! |
| Compliance Officer | compliance@rmp.local | Compliance1234! |
| Patient | patient@rmp.local | Patient1234! |
| Doctor | doctor@rmp.local | Doctor1234! |
| Pharmacist | pharmacist@rmp.local | Pharmacist1234! |
| Laboratorian | laboratorian@rmp.local | Lab1234! |

## User Type and Profile Objects

| Account | `user_type` | Always Has `UserProfile` | Role-Specific Profile |
|---|---|---|---|
| System Admin | `staff` | Yes | `StaffProfile` |
| Verification Officer | `staff` | Yes | `StaffProfile` |
| Knowledge Base Manager | `staff` | Yes | `StaffProfile` |
| Analytics Officer | `staff` | Yes | `StaffProfile` |
| Support Specialist | `staff` | Yes | `StaffProfile` |
| Compliance Officer | `staff` | Yes | `StaffProfile` |
| Patient | `patient` | Yes | `PatientProfile` |
| Doctor | `doctor` | Yes | `DoctorProfile` |
| Pharmacist | `pharmacist` | Yes | `PharmacistProfile` |
| Laboratorian | `laboratorian` | Yes | `LaboratorianProfile` |

Notes:
- `admin@rmp.local` uses `user_type=staff` (new in Phase X).
- Admin access comes from `is_staff=True`, `is_superuser=True`, and `StaffProfile.staff_role=system_admin`.
- Staff users have both `UserProfile` and `StaffProfile` in seeded environments.
- All additional staff accounts are `is_staff=True` and mapped to their matching `staff_role`.

## Profile Field Summary by Type

### Shared Profile (`UserProfile`) for all seeded users
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

### Staff (`StaffProfile`)
- `staff_role` (choices: `system_admin`, `verification_officer`, `knowledge_base_manager`, `analytics_officer`, `support_specialist`, `compliance_officer`)
- `department`
- `supervisor` (FK to another staff user, optional)
- `can_approve_professionals` (bool)
- `can_manage_knowledge_base` (bool)
- `can_export_datasets` (bool)
- `can_view_audit_logs` (bool)
- `hire_date`
- `last_active`
- `is_active`
- `has_completed_training`
- `training_completed_date`