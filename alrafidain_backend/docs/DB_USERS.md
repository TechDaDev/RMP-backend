# Live DB Users

Generated from the live Postgres database on 2026-05-21.

## Notes

- `Known password` is only shown when the plaintext credential is documented in the repo or was explicitly seeded with a copied known hash.
- `UNKNOWN (hash only in DB)` means the database only contains a password hash; the plaintext password is not recoverable from the DB.
- The `consult-seed-*.@rmp.local` doctors were seeded with the same password hash as `doctor@rmp.local`, so their known password is `Doctor1234!`.

## Doctors

| Email | User Type | Active | Specialty | Verification | Known Password |
|---|---|---:|---|---|---|
| consult-seed-dentistry-01@rmp.local | doctor | Yes | dentistry | approved | Doctor1234! |
| consult-seed-emergency-medicine-01@rmp.local | doctor | Yes | emergency_medicine | approved | Doctor1234! |
| consult-seed-emergency-medicine-02@rmp.local | doctor | Yes | emergency_medicine | approved | Doctor1234! |
| consult-seed-emergency-medicine-03@rmp.local | doctor | Yes | emergency_medicine | approved | Doctor1234! |
| consult-seed-endocrinology-01@rmp.local | doctor | Yes | endocrinology | approved | Doctor1234! |
| consult-seed-ent-01@rmp.local | doctor | Yes | ent | approved | Doctor1234! |
| consult-seed-ent-02@rmp.local | doctor | Yes | ent | approved | Doctor1234! |
| consult-seed-gastroenterology-01@rmp.local | doctor | Yes | gastroenterology | approved | Doctor1234! |
| consult-seed-gastroenterology-02@rmp.local | doctor | Yes | gastroenterology | approved | Doctor1234! |
| consult-seed-gastroenterology-03@rmp.local | doctor | Yes | gastroenterology | approved | Doctor1234! |
| consult-seed-gynecology-01@rmp.local | doctor | Yes | gynecology | approved | Doctor1234! |
| consult-seed-gynecology-02@rmp.local | doctor | Yes | gynecology | approved | Doctor1234! |
| consult-seed-gynecology-03@rmp.local | doctor | Yes | gynecology | approved | Doctor1234! |
| consult-seed-internal-medicine-01@rmp.local | doctor | Yes | internal_medicine | approved | Doctor1234! |
| consult-seed-internal-medicine-02@rmp.local | doctor | Yes | internal_medicine | approved | Doctor1234! |
| consult-seed-internal-medicine-03@rmp.local | doctor | Yes | internal_medicine | approved | Doctor1234! |
| consult-seed-nephrology-01@rmp.local | doctor | Yes | nephrology | approved | Doctor1234! |
| consult-seed-nephrology-02@rmp.local | doctor | Yes | nephrology | approved | Doctor1234! |
| consult-seed-neurology-01@rmp.local | doctor | Yes | neurology | approved | Doctor1234! |
| consult-seed-neurology-02@rmp.local | doctor | Yes | neurology | approved | Doctor1234! |
| consult-seed-neurology-03@rmp.local | doctor | Yes | neurology | approved | Doctor1234! |
| consult-seed-ophthalmology-01@rmp.local | doctor | Yes | ophthalmology | approved | Doctor1234! |
| consult-seed-ophthalmology-02@rmp.local | doctor | Yes | ophthalmology | approved | Doctor1234! |
| consult-seed-orthopedics-01@rmp.local | doctor | Yes | orthopedics | approved | Doctor1234! |
| consult-seed-orthopedics-02@rmp.local | doctor | Yes | orthopedics | approved | Doctor1234! |
| consult-seed-pediatrics-01@rmp.local | doctor | Yes | pediatrics | approved | Doctor1234! |
| consult-seed-pediatrics-02@rmp.local | doctor | Yes | pediatrics | approved | Doctor1234! |
| consult-seed-pediatrics-03@rmp.local | doctor | Yes | pediatrics | approved | Doctor1234! |
| consult-seed-psychiatry-01@rmp.local | doctor | Yes | psychiatry | approved | Doctor1234! |
| consult-seed-psychiatry-02@rmp.local | doctor | Yes | psychiatry | approved | Doctor1234! |
| consult-seed-pulmonology-01@rmp.local | doctor | Yes | pulmonology | approved | Doctor1234! |
| consult-seed-pulmonology-02@rmp.local | doctor | Yes | pulmonology | approved | Doctor1234! |
| consult-seed-pulmonology-03@rmp.local | doctor | Yes | pulmonology | approved | Doctor1234! |
| consult-seed-rheumatology-01@rmp.local | doctor | Yes | rheumatology | approved | Doctor1234! |
| consult-seed-rheumatology-02@rmp.local | doctor | Yes | rheumatology | approved | Doctor1234! |
| consult-seed-urology-01@rmp.local | doctor | Yes | urology | approved | Doctor1234! |
| consult-seed-urology-02@rmp.local | doctor | Yes | urology | approved | Doctor1234! |
| doctor@rmp.local | doctor | Yes | general_medicine | approved | Doctor1234! |
| p53_d_53397bb2@example.com | doctor | Yes | general_medicine | approved | UNKNOWN (hash only in DB) |
| p5a_dm_adee0724@example.com | doctor | Yes | cardiology | approved | UNKNOWN (hash only in DB) |
| p5a_du_adee0724@example.com | doctor | Yes | dermatology | approved | UNKNOWN (hash only in DB) |
| phase5a_doc_match_0a13e40e@example.com | doctor | Yes | cardiology | approved | UNKNOWN (hash only in DB) |
| phase5a_doc_unmatch_0a13e40e@example.com | doctor | Yes | dermatology | approved | UNKNOWN (hash only in DB) |
| smoke-admin-2@example.com | doctor | Yes | _blank_ | _blank_ | UNKNOWN (hash only in DB) |
| smoke-admin-3@example.com | doctor | Yes | dentistry | approved | UNKNOWN (hash only in DB) |
| smoke-admin-4@example.com | doctor | Yes | endocrinology | approved | UNKNOWN (hash only in DB) |
| smoke_doctor_18674f5c@example.com | doctor | Yes | general_medicine | approved | UNKNOWN (hash only in DB) |
| smoke_doctor_1db4429a@example.com | doctor | Yes | general_medicine | approved | UNKNOWN (hash only in DB) |
| smoke-target-3@example.com | doctor | Yes | general_medicine | approved | UNKNOWN (hash only in DB) |
| smoke-target-4@example.com | doctor | Yes | general_medicine | approved | UNKNOWN (hash only in DB) |
| smoketest_doctor@example.com | doctor | No | general_medicine | approved | UNKNOWN (hash only in DB) |

## Laboratorians

| Email | User Type | Active | Lab | Verification | Known Password |
|---|---|---:|---|---|---|
| laboratorian@rmp.local | laboratorian | Yes | Test Laboratory | approved | Lab1234! |
| smoketest_lab@example.com | laboratorian | No | _blank_ | approved | UNKNOWN (hash only in DB) |

## Patients

| Email | User Type | Active | Known Password |
|---|---|---:|---|
| p53_p_53397bb2@example.com | patient | Yes | UNKNOWN (hash only in DB) |
| p5a_p_adee0724@example.com | patient | Yes | UNKNOWN (hash only in DB) |
| patient@rmp.local | patient | Yes | Patient1234! |
| phase5a_patient_0a13e40e@example.com | patient | Yes | UNKNOWN (hash only in DB) |
| smoke_patient_18674f5c@example.com | patient | Yes | UNKNOWN (hash only in DB) |
| smoke_patient_1db4429a@example.com | patient | Yes | UNKNOWN (hash only in DB) |
| smoketest_patient@example.com | patient | No | UNKNOWN (hash only in DB) |

## Pharmacists

| Email | User Type | Active | Pharmacy | Verification | Known Password |
|---|---|---:|---|---|---|
| pharmacist@rmp.local | pharmacist | Yes | Test Pharmacy | approved | Pharmacist1234! |
| smoke_pharma_18674f5c@example.com | pharmacist | Yes | _blank_ | approved | UNKNOWN (hash only in DB) |
| smoke_pharma_1db4429a@example.com | pharmacist | Yes | _blank_ | approved | UNKNOWN (hash only in DB) |

## Staff

| Email | User Type | Active | Staff Role | Known Password |
|---|---|---:|---|---|
| admin@rmp.local | staff | Yes | system_admin | Admin1234! |
| analytics@rmp.local | staff | Yes | analytics_officer | Analytics1234! |
| compliance@rmp.local | staff | Yes | compliance_officer | Compliance1234! |
| kbmanager@rmp.local | staff | Yes | knowledge_base_manager | KBManager1234! |
| support@rmp.local | staff | Yes | support_specialist | Support1234! |
| verifier@rmp.local | staff | Yes | verification_officer | Verifier1234! |