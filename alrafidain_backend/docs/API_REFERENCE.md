# Al-Rafidain Medical Platform — API Reference

Base URL: `/api/`  
API Docs UI: `/api/docs/`  
OpenAPI Schema: `/api/schema/`  
Health (compat): `/api/health/`  
Health live: `/api/health/live/`  
Health ready: `/api/health/ready/`  
Health deps: `/api/health/deps/`

All authenticated endpoints require:

```
Authorization: Bearer <access_token>
```

All responses follow the standard envelope:

```json
{
  "status": "success" | "error",
  "data": {...} | [...],
  "message": "...",
  "errors": {...}
}
```

---

## Table of Contents

- [Privacy and Role Restrictions](#privacy-and-role-restrictions)
- [Authentication](#authentication)
- [Profiles](#profiles)
- [Admin Verification Review API](#admin-verification-review-api)
- [Consultations](#consultations)
- [Messaging](#messaging)
- [Prescriptions](#prescriptions)
- [Notifications](#notifications)
- [Patient Records](#patient-records)
- [Lab Orders](#lab-orders)
- [Lab Results](#lab-results)
- [Audit / Admin Notes](#audit--admin-notes)
- [Knowledge Base (Phase 12A)](#knowledge-base-phase-12a)
- [Phase 12C — RAG Doctor Support Endpoints](#phase-12c--rag-doctor-support-endpoints)
- [Phase 12D — AI Evaluation and Doctor Feedback](#phase-12d--ai-evaluation-and-doctor-feedback)
- [Phase 12E — Analytics and Training Dataset Preparation](#phase-12e--analytics-and-training-dataset-preparation)

---

## Privacy and Role Restrictions

| Rule | Detail |
|---|---|
| Patients **cannot** see prescription medication items | Prescription item names/dosages are hidden from patient responses |
| Patients **cannot** see lab order test details | Individual test names/items are hidden until after QR scan is not applicable to patient |
| Patients **see lab results only after release** | Results are only visible once doctor explicitly releases them |
| Pharmacists see only pending items after QR scan | Post-scan dispensing shows only `pending` items for the scanned prescription |
| Laboratorians see only pending items after QR scan | Post-scan shows only `pending` lab order items |
| Doctors see full records for assigned patients only | Doctor-specific endpoints enforce patient-doctor relationship |

---

## Authentication

### `POST /api/accounts/register/`

Register a new user account.

- **Auth required**: No
- **Allowed roles**: Public
- **Purpose**: Create a new account (patient, doctor, pharmacist, or laboratorian). Account is inactive until the email OTP is verified.

**Request body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "password_confirm": "SecurePass123!",
  "first_name": "John",
  "last_name": "Doe",
  "user_type": "patient"
}
```

**Response `201`:**
```json
{
  "status": "success",
  "message": "Registration successful. Check your email for the activation OTP."
}
```

---

### `POST /api/accounts/login/`

Obtain JWT token pair.

- **Auth required**: No
- **Allowed roles**: Public

**Request body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response `200`:**
```json
{
  "status": "success",
  "data": {
    "access": "<jwt_access_token>",
    "refresh": "<jwt_refresh_token>",
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "full_name": "John Doe",
      "profile_image": "http://localhost:8000/media/profiles/<user_uuid>/<file>.jpg",
      "user_type": "patient",
      "is_active": true,
      "date_joined": "2025-01-01T00:00:00Z"
    }
  }
}
```

`profile_image` is nullable. When present, it returns an absolute media URL.

---

### `POST /api/accounts/activate/`

Activate account using the OTP sent to email at registration.

- **Auth required**: No

**Request body:**
```json
{
  "email": "user@example.com",
  "code": "123456"
}
```

**Response `200`:** `{ "status": "success", "message": "Account activated successfully." }`

---

### `POST /api/accounts/resend-activation-otp/`

Resend the activation OTP email.

- **Auth required**: No

**Request body:**
```json
{
  "email": "user@example.com"
}
```

**Response `200`:** Generic message (always returns success to prevent user enumeration).

---

### `POST /api/accounts/password-reset/request/`

Request a password reset OTP.

- **Auth required**: No

**Request body:**
```json
{
  "email": "user@example.com"
}
```

**Response `200`:** Generic message (always returns success to prevent user enumeration).

---

### `POST /api/accounts/password-reset/confirm/`

Reset password using the OTP.

- **Auth required**: No

**Request body:**
```json
{
  "email": "user@example.com",
  "code": "123456",
  "new_password": "NewPass123!",
  "new_password_confirm": "NewPass123!"
}
```

**Response `200`:** `{ "status": "success", "message": "Password reset successful." }`

---

### `GET /api/accounts/me/`

Get current authenticated user.

- **Auth required**: Yes
- **Allowed roles**: All
- **Response includes**: `id`, `email`, `first_name`, `last_name`, `full_name`, `profile_image`, `user_type`, `is_active`, `date_joined`

---

## Profiles

### `GET /api/profiles/me/`

Get the full profile of the current user.

- **Auth required**: Yes
- **Allowed roles**: All
- **Purpose**: Returns user profile, role-specific profile, completion status, and verification status

Returned shape includes:
- Shared `user_profile` for all user types
- Role-specific profile (`patient_profile`, `doctor_profile`, `pharmacist_profile`, or `laboratorian_profile`)

Shared `UserProfile` fields:
- `phone_number`, `profile_image`, `gender`, `date_of_birth`, `governorate`, `district`, `address`, `national_id`

---

### `PUT/PATCH /api/profiles/me/user-profile/`

Update UserProfile (phone, gender, DOB, address, etc.).

- **Auth required**: Yes
- **Allowed roles**: All

---

### `PUT/PATCH /api/profiles/me/patient/`

Update patient-specific profile fields.

- **Auth required**: Yes
- **Allowed roles**: Patient

Patient profile fields:
- `social_security_id`
- `emergency_contact_name`
- `emergency_contact_phone`

---

### `PUT/PATCH /api/profiles/me/doctor/`

Update doctor profile (specialty, license, bio, etc.).

- **Auth required**: Yes
- **Allowed roles**: Doctor

Doctor profile fields:
- `medical_license_number`
- `medical_license_image`
- `specialty`
- `specialty_other`
- `subspecialty`
- `professional_title`
- `years_of_experience`
- `bio`
- `work_address`
- `verification_status` (read-only)
- `verified_at` (read-only)
- `verification_notes` (read-only)

---

### `PUT/PATCH /api/profiles/me/pharmacist/`

Update pharmacist profile (license, pharmacy info).

- **Auth required**: Yes
- **Allowed roles**: Pharmacist

Pharmacist profile fields:
- `pharmacist_license_number`
- `pharmacist_license_image`
- `pharmacy_name`
- `pharmacy_license_number`
- `pharmacy_license_image`
- `pharmacy_address`
- `working_hours`
- `verification_status` (read-only)
- `verified_at` (read-only)
- `verification_notes` (read-only)

---

### `PUT/PATCH /api/profiles/me/laboratorian/`

Update laboratorian profile (license, lab info).

- **Auth required**: Yes
- **Allowed roles**: Laboratorian

Laboratorian profile fields:
- `laboratorian_license_number`
- `laboratorian_license_image`
- `laboratory_name`
- `laboratory_license_number`
- `laboratory_license_image`
- `laboratory_address`
- `specialization`
- `working_hours`
- `verification_status` (read-only)
- `verified_at` (read-only)
- `verification_notes` (read-only)

---

## Admin Verification Review API

These endpoints are for staff/admin users only and are intended for reviewing professional role verification profiles.

- **Base path**: `/api/admin/verifications/`
- **Allowed roles**: `is_staff=True` or `is_superuser=True`
- **Included profile roles**: doctor, pharmacist, laboratorian
- **Excluded**: patient profiles
- **Privacy**: no password/token/OTP/QR fields, no patient medical data, no prescription or lab result payloads

### `GET /api/admin/verifications/`

List verification requests.

**Query params:**
- `role=doctor|pharmacist|laboratorian`
- `status=pending|approved|rejected|suspended` (defaults to `pending`)
- `search=<email|name|license|workplace>`
- `limit=<n>`
- `offset=<n>`

**Response `200`:**
```json
{
  "success": true,
  "message": "Verification requests retrieved.",
  "data": {
    "count": 10,
    "next": null,
    "previous": null,
    "results": [
      {
        "id": "uuid",
        "role": "doctor",
        "status": "pending",
        "user": {
          "id": "uuid",
          "email": "doctor@example.com",
          "full_name": "Doctor Name",
          "is_active": true,
          "date_joined": "2026-01-01T00:00:00Z"
        },
        "profile": {
          "license_number": "DOC-100",
          "specialty": "general_medicine",
          "workplace_name": "Senior Doctor",
          "address": "Baghdad Clinic",
          "years_of_experience": 8,
          "phone_number": "07712345678"
        },
        "submitted_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z"
      }
    ]
  }
}
```

### `GET /api/admin/verifications/<role>/<id>/`

Get one verification request detail.

**Response `200`:** same shape as list item plus:
- `verification_notes`
- `verified_at`
- `verified_by` (nullable `{id,email,full_name}`)

### `POST /api/admin/verifications/<role>/<id>/approve/`

Approve a verification request.

**Request body:**
```json
{
  "note": "Optional admin note"
}
```

Effects:
- sets `verification_status=approved`
- sets `verified_by` and `verified_at`
- updates `verification_notes` with optional note
- creates audit log + notification

### `POST /api/admin/verifications/<role>/<id>/reject/`

Reject a verification request.

**Request body:**
```json
{
  "reason": "Required rejection reason"
}
```

Effects:
- sets `verification_status=rejected`
- sets `verified_by` and `verified_at`
- stores reason in `verification_notes`
- creates audit log + notification

### `POST /api/admin/verifications/<role>/<id>/suspend/`

Suspend a verification request.

**Request body:**
```json
{
  "reason": "Required suspension reason"
}
```

Effects:
- sets `verification_status=suspended`
- sets `verified_by` and `verified_at`
- stores reason in `verification_notes`
- creates audit log + notification

### Validation and safety rules

- Non-admin users are denied.
- Admin/staff cannot review their own profile.
- Patients never appear in this queue.
- Endpoint responses intentionally exclude medical-record, prescription-item, and lab-result data.

---

## Consultations

### `GET /api/consultations/symptom-categories/`

List all active symptom categories.

- **Auth required**: Yes
- **Allowed roles**: All

---

### `GET /api/consultations/symptoms/`

List all active symptoms (filterable by `?category=<id>` and `?is_red_flag=true`).

- **Auth required**: Yes
- **Allowed roles**: All

**Catalog design (v2, Phase 4.3A):**

| Dimension | Count |
|---|---|
| Categories | 18 |
| Active symptoms | ~127 |
| Routing rules | ~259 |

The 18 patient-friendly categories are: Emergency / Red Flags, General / Constitutional, Respiratory, Cardiovascular, Gastrointestinal, Neurological, Musculoskeletal, Skin / Dermatology, Ear, Nose, and Throat, Eye, Urinary / Kidney, Reproductive / Gynecology, Endocrine / Metabolic, Mental Health / Sleep, Pediatric Concerns, Injury / Trauma, Dental / Oral, Allergy / Immunology.

Symptom names use patient-friendly plain language, not disease names.
Red-flag symptoms (e.g., Severe chest pain, Suicidal thoughts, Head injury) always include `emergency_medicine` routing.
Specialty assignment is deterministic and weight-based. This is **not** a diagnosis; it is triage support only.

---

### `POST /api/consultations/`

Create a new consultation.

- **Auth required**: Yes
- **Allowed roles**: Patient
- `selected_specialty` is assigned by the backend from the submitted symptoms using weighted routing rules.
- Patients must submit at least one valid `symptom_ids` entry.
- Routing is deterministic (weight-based sum per specialty). AI triage is **not** implemented in this phase.
- Successful responses include a stable consultation `id` at `data.id` for detail-page routing.
- The inferred specialty is not a medical diagnosis. The assigned doctor makes the clinical determination.

**Request body:**
```json
{
  "duration": "one_to_three_days",
  "severity": "moderate",
  "has_fever": false,
  "has_pain": true,
  "additional_notes": "Chest tightness since yesterday",
  "symptom_ids": ["uuid1", "uuid2"]
}
```

---

### `GET /api/consultations/my/`

List consultations for the authenticated user.

- **Auth required**: Yes
- **Allowed roles**: Patient, Doctor

Behavior:
- Patient: own consultations (`patient=request.user`)
- Doctor: assigned consultations (`assigned_doctor=request.user`)

---

### `GET /api/consultations/<id>/`

Get consultation detail.

- **Auth required**: Yes
- **Allowed roles**: Patient (own), Doctor (assigned)
- Patients can view their own consultations across valid lifecycle states (submitted, accepted, doctor_responded, closed).
- Patients cannot view other patients' consultations.
- Doctors can view consultation detail only when assigned under current policy.

Future phase note: backend profile-completion enforcement before consultation creation is planned but not implemented in this phase.

---

### `GET /api/consultations/doctor/pending/`

List pending consultations matching doctor's specialty.

- **Auth required**: Yes
- **Allowed roles**: Doctor

---

### `GET /api/consultations/doctor/assigned/`

List consultations assigned to the doctor.

- **Auth required**: Yes
- **Allowed roles**: Doctor

---

### `POST /api/consultations/<id>/accept/`

Accept a consultation request.

- **Auth required**: Yes
- **Allowed roles**: Doctor (approved)

---

### `POST /api/consultations/<id>/responses/`

Submit a doctor's medical response.

- **Auth required**: Yes
- **Allowed roles**: Doctor (assigned)

**Request body:**
```json
{
  "response_text": "Based on your symptoms...",
  "recommendation_type": "needs_lab_test"
}
```

---

### `POST /api/consultations/<id>/close/`

Close a consultation.

- **Auth required**: Yes
- **Allowed roles**: Doctor (assigned)
- **Allowed statuses**: `accepted`, `doctor_responded`

---

## Messaging

### `GET /api/consultations/<id>/messages/`

List messages in a consultation thread. Also marks incoming unread messages as read.

- **Auth required**: Yes
- **Allowed roles**: Patient (own), Doctor (assigned)
- **Allowed consultation statuses**: `accepted`, `doctor_responded`, `closed`

---

### `POST /api/consultations/<id>/messages/`

Send a message in a consultation.

- **Auth required**: Yes
- **Allowed roles**: Patient (own), Doctor (assigned)
- **Allowed consultation statuses**: `accepted`, `doctor_responded`

**Request body (multipart for attachments):**
```json
{
  "body": "Can you clarify something?",
  "attachments": []
}
```

**Note**: `body` or at least one attachment is required.

---

### `POST /api/consultations/<id>/messages/mark-read/`

Mark all unread messages in this consultation as read (for the requesting user).

- **Auth required**: Yes
- **Allowed roles**: Patient (own), Doctor (assigned)

---

## Prescriptions

### `POST /api/consultations/<consultation_id>/prescriptions/`

Create a new prescription for a consultation.

- **Auth required**: Yes
- **Allowed roles**: Doctor (approved, assigned to consultation)
- **Consultation status required**: `accepted` or `doctor_responded`
- `items` must be a non-empty array.
- Unknown top-level fields (for example `notes`) are not part of the create contract and should not be sent.

**Request body:**
```json
{
  "items": [
    {
      "medication_name": "Amoxicillin",
      "strength": "500mg",
      "dosage": "1 capsule",
      "frequency": "3x daily",
      "duration": "7 days",
      "route": "oral",
      "quantity": "21 capsules",
      "instructions": "After meals"
    }
  ]
}
```

**Item field contract:**

- Required per item: `medication_name`, `dosage`, `frequency`, `duration`, `route`
- Optional per item: `strength`, `quantity`, `instructions`
- Allowed `route` values: `oral`, `topical`, `inhalation`, `injection`, `eye`, `ear`, `nasal`, `rectal`, `other`

**Validation error examples:**

Missing `route`:
```json
{
  "success": false,
  "message": "Invalid input.",
  "errors": {
    "items": [
      {
        "route": ["This field is required."]
      }
    ]
  }
}
```

Invalid `route`:
```json
{
  "success": false,
  "message": "Invalid input.",
  "errors": {
    "items": [
      {
        "route": ["\"by mouth\" is not a valid choice."]
      }
    ]
  }
}
```

> **Privacy note**: Medication item details are never included in patient-facing prescription responses.

---

### `GET /api/prescriptions/my/`

List patient's own prescriptions (items hidden).

- **Auth required**: Yes
- **Allowed roles**: Patient

---

### `GET /api/prescriptions/my/<id>/`

Get prescription detail for patient (items hidden).

- **Auth required**: Yes
- **Allowed roles**: Patient (own)

---

### `GET /api/prescriptions/doctor/<id>/`

Get full prescription detail including medication items.

- **Auth required**: Yes
- **Allowed roles**: Doctor (issuer)

---

### `POST /api/prescriptions/doctor/<id>/cancel/`

Cancel a prescription (only if no items have been dispensed yet).

- **Auth required**: Yes
- **Allowed roles**: Doctor (issuer)

---

### `POST /api/prescriptions/scan/`

Pharmacist scans QR token to access pending prescription items.

- **Auth required**: Yes
- **Allowed roles**: Pharmacist (approved)

**Request body:**
```json
{
  "qr_token": "..."
}
```

**Response**: Returns `prescription` metadata and only `pending` items for the scanned prescription. Also returns `locked: true` if the prescription is no longer dispensable.

---

### `POST /api/prescriptions/<id>/dispense/`

Record dispensing of scanned prescription items.

- **Auth required**: Yes
- **Allowed roles**: Pharmacist (approved, scanner match)

**Request body:**
```json
{
  "items": [
    {
      "prescription_item_id": "uuid",
      "status": "dispensed",
      "dispensed_quantity": "21 capsules",
      "note": ""
    }
  ]
}
```

**Response**: Same shape as scan response (updated `prescription` + remaining `pending` items).

---

### `GET /api/prescriptions/pharmacist/history/`

List dispensing records for the authenticated pharmacist only.

- **Auth required**: Yes
- **Allowed roles**: Pharmacist (approved)
- **Scope**: Only records created by the authenticated pharmacist
- **Ordering**: Newest first
- **Pagination**: DRF limit/offset (`?limit=<n>&offset=<n>`)

**Response envelope:**
```json
{
  "success": true,
  "message": "Dispensing history retrieved.",
  "data": {
    "count": 1,
    "next": null,
    "previous": null,
    "results": [
      {
        "id": "uuid",
        "prescription_id": "uuid",
        "prescription_status": "partially_dispensed",
        "item_id": "uuid",
        "medication_name": "Amoxicillin",
        "strength": "500mg",
        "dosage": "1 capsule",
        "frequency": "3x daily",
        "duration": "7 days",
        "route": "oral",
        "quantity": "21 capsules",
        "dispensed_quantity": "1 box",
        "status": "dispensed",
        "dispensed_at": "2026-05-09T12:30:00Z",
        "patient": {
          "id": "uuid",
          "full_name": "Pat Ient",
          "gender": null,
          "age": null
        },
        "doctor": {
          "id": "uuid",
          "full_name": "Doc Tor",
          "specialty": "general_medicine"
        },
        "created_at": "2026-05-09T12:30:00Z",
        "updated_at": "2026-05-09T12:30:00Z"
      }
    ]
  }
}
```

**Privacy and safety rules:**

- Does not return `qr_token`
- Does not return dispensing internal `note`
- Does not return patient private profile fields (address, national ID, phone, etc.)
- Does not return records created by other pharmacists

---

> **Note**: There is no `GET /api/prescriptions/<id>/qr/` endpoint. Patients present the `qr_token` field from their own prescription detail response directly to the pharmacist.

---

## Notifications

### `GET /api/notifications/`

List all notifications for the current user.

- **Auth required**: Yes
- **Allowed roles**: All

---

### `POST /api/notifications/<id>/mark-read/`

Mark a notification as read.

- **Auth required**: Yes
- **Allowed roles**: All (own notifications)

---

### `POST /api/notifications/mark-all-read/`

Mark all unread notifications as read.

- **Auth required**: Yes
- **Allowed roles**: All

---

### `GET /api/notifications/unread-count/`

Get the count of unread notifications for the current user.

- **Auth required**: Yes
- **Allowed roles**: All

---

## Patient Records

### `GET /api/patient-records/my/`

Get the current patient's medical record with entries.

- **Auth required**: Yes
- **Allowed roles**: Patient

---

### `GET /api/patient-records/patients/<patient_id>/`

Get a patient's medical record (doctor view).

- **Auth required**: Yes
- **Allowed roles**: Doctor (approved, must have assigned consultation in one of: `accepted`, `doctor_responded`, `closed`)

---

### `POST /api/patient-records/<record_id>/entries/`

Create a new medical record entry.

- **Auth required**: Yes
- **Allowed roles**: Patient (self-reported for own record), Doctor (for an authorized patient's record)

**Request body:**
```json
{
  "category": "chronic_condition",
  "title": "Type 2 Diabetes",
  "value": "Diagnosed 2020",
  "notes": "Optional additional notes"
}
```

> **Note**: Patients cannot set `verification_status`, `source_role`, `verified_by`, or `is_active` — these are controlled by the system. The `record_id` in the URL must be the patient's own record.

---

### `POST /api/patient-records/entries/<id>/confirm/`

Doctor confirms or rejects a patient-submitted medical record entry.

- **Auth required**: Yes
- **Allowed roles**: Doctor (approved, authorized for this patient)

**Request body:**
```json
{
  "verification_status": "doctor_confirmed",
  "notes": "Confirmed via consultation review."
}
```

> `verification_status` accepts `"doctor_confirmed"` or `"rejected"`.

---

### `POST /api/patient-records/entries/<id>/deactivate/`

Deactivate (soft-delete) a medical record entry.

- **Auth required**: Yes
- **Allowed roles**: Patient (own), Doctor (authorized)

**Request body:**
```json
{
  "notes": "Optional reason for deactivation"
}
```

---

### `POST /api/patient-records/<record_id>/blood-group/`

Set or update blood group for a patient.

- **Auth required**: Yes
- **Allowed roles**: Patient (self-reported for own record), Doctor

**Request body:**
```json
{
  "blood_group": "o_positive",
  "notes": ""
}
```

---

### `POST /api/patient-records/patients/<patient_id>/blood-group/verify/`

Laboratory-confirmed blood group update.

- **Auth required**: Yes
- **Allowed roles**: Laboratorian (approved)

---

## Lab Orders

### `GET /api/lab-orders/tests/`

List available lab tests in the catalog (filterable by `?category=` and `?search=`).

- **Auth required**: Yes
- **Allowed roles**: All

---

### `POST /api/consultations/<consultation_id>/lab-orders/`

Create a new lab order linked to a consultation.

- **Auth required**: Yes
- **Allowed roles**: Doctor (approved, assigned to consultation)

**Request body:**
```json
{
  "items": [
    {
      "test": "uuid",
      "test_name": "CBC",
      "category": "hematology",
      "sample_type": "Blood",
      "instructions": "Fasting required"
    }
  ]
}
```

> **Privacy note**: Lab order item details (test names) are not included in patient-facing responses.

---

### `GET /api/lab-orders/my/`

List patient's own lab orders.

- **Auth required**: Yes
- **Allowed roles**: Patient

---

### `GET /api/lab-orders/my/<id>/`

Get patient's own lab order detail (items hidden).

- **Auth required**: Yes
- **Allowed roles**: Patient (own)

---

### `GET /api/lab-orders/doctor/<id>/`

Get full lab order detail including test items.

- **Auth required**: Yes
- **Allowed roles**: Doctor (issuer)

---

### `POST /api/lab-orders/doctor/<id>/cancel/`

Cancel a lab order (only if no items have been completed yet).

- **Auth required**: Yes
- **Allowed roles**: Doctor (issuer)

---

### `POST /api/lab-orders/scan/`

Laboratorian scans QR token to access lab order items.

- **Auth required**: Yes
- **Allowed roles**: Laboratorian (approved)

**Request body:**
```json
{
  "qr_token": "..."
}
```

**Response**: Returns `lab_order` metadata including:
- `remaining_items`: List of pending items still to be completed
- `completed_items` (NEW): List of already-completed items with metadata (test name, category, status, timestamps, result_id if available)
- `locked: true` if no pending items remain
- Audit log entry created

---

### `POST /api/lab-orders/<id>/complete/`

Record completion status for scanned lab order items.

- **Auth required**: Yes
- **Allowed roles**: Laboratorian (approved, scanner match)

**Request body:**
```json
{
  "items": [
    {
      "lab_order_item_id": "uuid",
      "status": "completed"
    }
  ]
}
```

**Response**: Same shape as scan response (updated `lab_order` with both `remaining_items` and `completed_items`, status updated).

---

> **Note**: There is no `GET /api/lab-orders/<id>/qr/` endpoint. Patients present the `qr_token` field from their own lab order detail response directly to the laboratorian.

---

## Lab Results

### `POST /api/lab-orders/items/<lab_order_item_id>/results/`

Submit a lab result for a completed lab order item.

- **Auth required**: Yes
- **Allowed roles**: Laboratorian (approved, scanner for this order)

**Request body (numeric example):**
```json
{
  "value_type": "numeric",
  "numeric_value": "7.2",
  "unit": "mmol/L",
  "reference_range": "3.9-6.1",
  "flag": "high",
  "laboratorian_notes": "Repeated twice for accuracy"
}
```

**Request body (blood group):**
```json
{
  "value_type": "blood_group",
  "blood_group_value": "o_positive"
}
```

**Request body (file):**
```json
{
  "value_type": "file_only",
  "result_file": "<multipart file upload>"
}
```

> **Privacy note**: `laboratorian_notes` and `doctor_notes` are never included in patient-facing responses.

---

### `GET /api/lab-orders/results/<id>/`

Get lab result detail (laboratorian view).

- **Auth required**: Yes
- **Allowed roles**: Laboratorian (own), Doctor (ordering doctor)

---

### `POST /api/lab-orders/results/<id>/correct/`

Correct a submitted lab result.

- **Auth required**: Yes
- **Allowed roles**: Laboratorian (original submitter only)
- **Restriction**: Cannot correct a released result after doctor has released it to patient

**Request body:**
```json
{
  "reason": "Equipment calibration error",
  "numeric_value": "6.8"
}
```

---

### `GET /api/lab-orders/doctor/results/<id>/`

Get full lab result detail (doctor view, including laboratorian notes).

- **Auth required**: Yes
- **Allowed roles**: Doctor (ordering doctor for this result)

---

### `POST /api/lab-orders/doctor/results/<id>/review/`

Doctor reviews a lab result.

- **Auth required**: Yes
- **Allowed roles**: Doctor (ordering doctor)

**Request body:**
```json
{
  "doctor_notes": "Values within expected range for this patient.",
  "release_to_patient": false
}
```

---

### `POST /api/lab-orders/doctor/results/<id>/release/`

Doctor releases a lab result to the patient.

- **Auth required**: Yes
- **Allowed roles**: Doctor (ordering doctor)
- **Behavior**: Sets result status to `released` and timestamps `released_at` (also sets `reviewed_at` if empty)

---

### `POST /api/lab-orders/doctor/results/<id>/link-medical-record/`

Doctor links a released lab result to the patient's medical record.

- **Auth required**: Yes
- **Allowed roles**: Doctor (ordering doctor)
- **Restriction**: Result must be released; cannot link twice

**Behavior:**
- Blood group results → update `BloodGroupRecord` as `laboratory_confirmed`
- All other results → create `MedicalRecordEntry` as `laboratory_confirmed`

---

### `GET /api/lab-results/my/`

List released lab results for the current patient.

- **Auth required**: Yes
- **Allowed roles**: Patient
- **Restriction**: Only `released` results are visible; `laboratorian_notes` and `doctor_notes` are excluded

---

### `GET /api/lab-results/my/<id>/`

Get a specific released lab result (patient view).

- **Auth required**: Yes
- **Allowed roles**: Patient (own, released only)

## Audit / Admin Notes

- All significant actions produce an `AuditLog` record (visible in Django admin).
- All user-visible events produce a `Notification` record.
- Admin site is available at `/admin/` for superusers.
- Audit logs capture `actor`, `action`, `target`, `ip_address`, and `extra_data`.
- Audit logs are not exposed via API to non-admin users.

---

## Knowledge Base (Phase 12A)

Base path: `/api/knowledge-base/`

**Access**: Staff/Admin only. No patient access.

### Upload / List Documents

```
POST /api/knowledge-base/documents/   — Upload a new document (PDF, DOCX, TXT)
GET  /api/knowledge-base/documents/   — List documents (filterable)
```

**Upload required fields**: `title`, `document_type`, `language`, `audience`, `file`

**Filters (GET)**: `approval_status`, `processing_status`, `document_type`, `language`, `audience`, `specialty`, `is_active`

### Document Detail

```
GET /api/knowledge-base/documents/<uuid:document_id>/
```

Returns full metadata, processing logs, chunk count.

### Document Workflow

```
POST /api/knowledge-base/documents/<uuid:document_id>/process/   — Extract text + chunk
POST /api/knowledge-base/documents/<uuid:document_id>/approve/   — Approve (must be chunked)
POST /api/knowledge-base/documents/<uuid:document_id>/reject/    — Reject (requires `reason`)
POST /api/knowledge-base/documents/<uuid:document_id>/archive/   — Archive + deactivate chunks
```

### Chunks

```
GET /api/knowledge-base/documents/<uuid:document_id>/chunks/  — List chunks for a document
GET /api/knowledge-base/chunks/search/?q=<query>              — Search approved active chunks
```

**Search query params**: `q` (required), `document_type`, `specialty`, `language`, `limit` (1–50, default 10)

### Document Types

`medical_book`, `laboratory_book`, `clinical_guideline`, `drug_reference`, `patient_education`, `platform_policy`, `other`

### Approval Workflow

```
Uploaded → (process) → Extracted → Chunked → (approve/reject) → Approved / Rejected
Any status → (archive) → Archived
```

Only approved, active documents with active chunks are eligible for future RAG retrieval.

### Audit Actions

- `knowledge_document_uploaded`
- `knowledge_document_processed`
- `knowledge_document_approved`
- `knowledge_document_rejected`
- `knowledge_document_archived`
- `knowledge_chunk_search_performed`

### Limitations (Phase 12A)

- No vector embeddings.
- No pgvector.
- No DeepSeek API calls.
- No patient-facing AI endpoints.
- Search is basic `icontains` text search only.
- Processing is synchronous (no Celery yet).

---

## Phase 12C — RAG Doctor Support Endpoints

Base prefix: `/api/rag/`

All RAG endpoints require an authenticated, **approved doctor** (`user_type=doctor`, `verification_status=approved`).  
Patients, pharmacists, laboratorians, and unapproved doctors receive **403 Forbidden**.

### POST `/api/rag/doctor/query/`

General RAG query — ask any approved medical knowledge base question.

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `question` | string | yes | The doctor's question (max 2000 chars) |
| `document_type` | string | no | Filter by document type |
| `specialty` | string | no | Filter by medical specialty |
| `language` | string | no | Filter by language |
| `audience` | string | no | Filter by audience |
| `top_k` | int | no | Number of chunks to retrieve (default: 6, max: 12) |

**Response:** `RAGResponse` object (see schema below).

---

### POST `/api/rag/consultations/<consultation_id>/support/`

RAG clinical support scoped to a specific consultation.  
The requesting user must be the **assigned doctor** of that consultation.

Backend context enrichment:
- If the patient uploaded consultation attachments (`.jpg/.jpeg/.png/.webp/.pdf/.docx/.txt`), backend extracts report text and injects it into the RAG object summary.
- OCR uses EasyOCR with Arabic + English (`Reader(['ar', 'en'])`) for image-based documents.
- Extracted text is passed through a security gate: non-medical text is dropped and prompt-injection-like lines are sanitized before RAG usage.
- If extracted content is unsafe or not likely medical, backend excludes it from AI context (request still succeeds).

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `question` | string | no | Custom question (defaults to standard consultation summary prompt) |
| `top_k` | int | no | Number of chunks to retrieve |

**Response:** `RAGResponse` object.

---

### POST `/api/rag/lab-results/<lab_result_id>/support/`

RAG clinical support scoped to a specific lab result.  
The requesting user must be the **ordering doctor** (`lab_result.doctor`) for that result.

Backend context enrichment:
- If `result_file` exists for the lab result, backend extracts report text and includes it in the RAG object summary.
- OCR uses EasyOCR with Arabic + English (`Reader(['ar', 'en'])`) for image-based files and scanned PDF images.
- Extracted text is passed through a security gate: non-medical text is dropped and prompt-injection-like lines are sanitized before RAG usage.
- If extracted content is unsafe or not likely medical, backend excludes it from AI context (request still succeeds).

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `question` | string | no | Custom question (defaults to standard lab result explanation prompt) |
| `top_k` | int | no | Number of chunks to retrieve |

**Response:** `RAGResponse` object.

---

### RAGResponse Schema

```json
{
  "id": "uuid",
  "query_id": "uuid",
  "service_context": "general_doctor_query | consultation | lab_result | ...",
  "object_id": "uuid | null",
  "response_text": "AI-generated answer citing approved sources",
  "status": "success | failed | no_context | blocked",
  "safety_level": "doctor_only | patient_safe | unsafe",
  "doctor_review_required": true,
  "patient_visible": false,
  "sources": [
    {
      "chunk_id": "uuid",
      "document_id": "uuid",
      "document_title": "string",
      "document_type": "string",
      "page_number": 1,
      "section_title": "string",
      "rank": 1,
      "score": 0.87
    }
  ],
  "model_name": "deepseek-chat",
  "token_input": 100,
  "token_output": 50,
  "created_at": "2025-01-01T00:00:00Z"
}
```

**Safety invariants (enforced in model.save()):**
- `patient_visible` is **always** `false`.
- `doctor_review_required` is **always** `true`.
- `safety_level` defaults to `doctor_only`.
- `prompt_text` and `raw_response` are **never** included in API responses.

### RAG Status values

| Status | Meaning |
|---|---|
| `success` | LLM returned a valid answer |
| `failed` | LLM call failed (see error log) |
| `no_context` | No approved knowledge chunks found; no LLM call made |
| `blocked` | Query blocked by safety rules |

### Audit Actions

- `rag_query_performed` — every RAG query, with status and chunk count
- `knowledge_semantic_search_performed` — every semantic search call

### Phase 12C Limitations

- No patient-facing RAG endpoints.
- No Celery / async RAG processing.
- DeepSeek is the only supported LLM provider.
- Embeddings use `all-MiniLM-L6-v2` (384 dimensions via sentence-transformers).

Operational note:
- OCR runtime dependency is EasyOCR (`pip install easyocr`) with configured OCR languages defaulting to Arabic + English.

---

## Phase 12D — AI Evaluation and Doctor Feedback

Base prefix: `/api/rag/`

Doctors can submit structured feedback on RAG responses they received. Staff can review flagged feedback.

### POST `/api/rag/responses/<rag_response_id>/feedback/`

Submit feedback on a RAG response.  
**Permission:** Approved doctor (must own the RAG response — one feedback per response).

**Request body:**

```json
{
  "rating": "helpful | partially_helpful | not_helpful | unsafe",
  "comment": "Optional free-text comment.",
  "is_source_grounded": true,
  "is_clinically_useful": true,
  "is_safe": true,
  "source_feedback": [
    {
      "retrieved_chunk_id": "<uuid>",
      "relevance": "relevant | partially_relevant | not_relevant | unknown",
      "comment": "Optional per-chunk comment."
    }
  ]
}
```

**Response `201`:** `RAGResponseFeedback` object (see schema below).

Rules:
- Only the requesting doctor can submit feedback on their own RAG responses.
- One feedback per RAG response (OneToOneField — 400 on duplicate).
- `rating=unsafe` automatically sets `is_safe=false` and `needs_admin_review=true`.
- `is_safe=false` automatically sets `needs_admin_review=true`.
- Source chunk IDs must belong to the same RAG query (400 on mismatch).

---

### GET `/api/rag/feedback/my/`

List own RAG feedback.  
**Permission:** Approved doctor.

**Query params:** `rating`, `review_status`, `needs_admin_review` (true/false).

**Response `200`:** List of `RAGResponseFeedback` objects.

---

### GET `/api/rag/admin/feedback/`

List all RAG feedback.  
**Permission:** Staff / superuser only.

**Query params:** `rating`, `review_status`, `is_safe` (true/false), `needs_admin_review` (true/false).

**Response `200`:** List of `RAGResponseFeedback` objects.

---

### POST `/api/rag/admin/feedback/<feedback_id>/review/`

Review (mark reviewed / dismissed / escalated) a RAG feedback item.  
**Permission:** Staff / superuser only.

**Request body:**

```json
{
  "review_status": "reviewed | dismissed | escalated",
  "review_notes": "Optional staff notes."
}
```

**Response `200`:** Updated `RAGResponseFeedback` object.

---

### RAGResponseFeedback Schema

```json
{
  "id": "<uuid>",
  "rag_response_id": "<uuid>",
  "doctor_email": "doctor@example.com",
  "rating": "helpful",
  "comment": "Very clear explanation.",
  "is_source_grounded": true,
  "is_clinically_useful": true,
  "is_safe": true,
  "needs_admin_review": false,
  "review_status": "pending",
  "reviewed_by_email": null,
  "reviewed_at": null,
  "review_notes": null,
  "source_feedback": [
    {
      "id": "<uuid>",
      "retrieved_chunk_id": "<uuid>",
      "chunk_rank": 1,
      "relevance": "relevant",
      "comment": null,
      "created_at": "2025-01-01T00:00:00Z"
    }
  ],
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z"
}
```

### Rating values

| Value | Meaning |
|---|---|
| `helpful` | Answer was useful |
| `partially_helpful` | Partially useful |
| `not_helpful` | Not useful |
| `unsafe` | Answer was unsafe — triggers admin review |

### Review status values

| Value | Meaning |
|---|---|
| `pending` | Not yet reviewed (default) |
| `reviewed` | Staff reviewed and cleared |
| `dismissed` | Staff dismissed (no action needed) |
| `escalated` | Requires further escalation |

### Phase 12D Audit events

- `rag_feedback_submitted` — doctor submits feedback (rating, is_safe, needs_admin_review recorded)
- `rag_feedback_reviewed` — staff completes a review action

### Phase 12D Limitations

- One feedback per RAG response (no editing after submission).
- Prompt text and raw LLM response are not exposed via the feedback API.
- RAG responses remain `patient_visible=false` regardless of feedback.

---

## Phase 12E — Analytics and Training Dataset Preparation

### GET `/api/rag/admin/analytics/summary/`

Returns aggregated RAG usage, feedback quality, and retrieval performance metrics.

**Auth:** Staff or superuser JWT required.  
**Response:** `200 OK`

```json
{
  "feedback": {
    "total_responses": 42,
    "responses_with_feedback": 18,
    "feedback_coverage_rate": 0.4286,
    "ratings": {"helpful": 10, "partially_helpful": 5, "not_helpful": 2, "unsafe": 1},
    "unsafe_count": 1,
    "needs_admin_review_count": 2,
    "review_status": {"pending": 12, "reviewed": 5, "dismissed": 1, "escalated": 0}
  },
  "retrieval_quality": {
    "total_retrieved_chunks": 84,
    "chunks_with_feedback": 30,
    "source_relevance": {"relevant": 20, "partially_relevant": 7, "irrelevant": 3},
    "average_score": 0.8421,
    "average_rank_of_relevant_sources": 1.8
  },
  "usage": {
    "total_queries": 42,
    "by_service_context": {"general_doctor_query": 30, "consultation": 8, "lab_result": 4},
    "by_status": {"completed": 38, "error": 4},
    "total_token_input": 48000,
    "total_token_output": 12000
  }
}
```

### POST `/api/rag/admin/exports/dataset/`

Exports anonymized RAG evaluation data for model fine-tuning / research.

**Auth:** Staff or superuser JWT required.  
**Request body:**

| Field | Type | Default | Description |
|---|---|---|---|
| `format` | `"json"` \| `"csv"` | `"json"` | Export file format |
| `include_text` | boolean | `false` | Include `query_text` / `response_text` in export |
| `anonymize` | boolean | `true` | Hash doctor ID and object ID with SHA-256 |

**Response (JSON):** `200 OK`

```json
{
  "format": "json",
  "record_count": 42,
  "data": [
    {
      "rag_query_id": "<uuid>",
      "service_context": "general_doctor_query",
      "response_status": "completed",
      "model_name": "deepseek-chat",
      "provider": "deepseek",
      "safety_level": "doctor_only",
      "doctor_review_required": false,
      "patient_visible": false,
      "token_input": 1200,
      "token_output": 320,
      "doctor_id_hash": "<sha256-hex>",
      "object_id_hash": null,
      "created_date": "2025-01-15",
      "feedback": {
        "rating": "helpful",
        "is_source_grounded": true,
        "is_clinically_useful": true,
        "is_safe": true,
        "needs_admin_review": false,
        "review_status": "pending"
      },
      "sources": [
        {
          "chunk_id": "<uuid>",
          "document_id": "<uuid>",
          "document_title": "Clinical Guideline — Hypertension",
          "document_type": "clinical_guideline",
          "rank": 1,
          "score": 0.873214,
          "source_relevance": "relevant"
        }
      ]
    }
  ]
}
```

**Response (CSV):** `200 OK` with `Content-Type: text/csv` and `Content-Disposition: attachment; filename="rag_eval_dataset.csv"`.

### Phase 12E Audit events

- `rag_analytics_viewed` — staff views analytics summary
- `rag_dataset_exported` — staff triggers a dataset export (format, record_count logged)

### Phase 12E Privacy Guarantees

- `doctor_id_hash` is a SHA-256 of `EXPORT_HASH_SALT + ":" + doctor_pk` — raw doctor PKs are never exported when `anonymize=true`.
- Raw embeddings are never included in exports.
- `query_text` and `response_text` are excluded by default (`include_text=false`).


