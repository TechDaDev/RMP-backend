# Al-Rafidain Medical Platform — API Reference

Base URL: `/api/`  
API Docs UI: `/api/docs/`  
OpenAPI Schema: `/api/schema/`  
Health Check: `/api/health/`

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
- **Purpose**: Create a new account (patient, doctor, pharmacist, or laboratorian)

**Request body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "full_name": "John Doe",
  "user_type": "patient"
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "uuid",
    "email": "user@example.com",
    "full_name": "John Doe",
    "user_type": "patient"
  }
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

**Response:**
```json
{
  "status": "success",
  "data": {
    "access": "<jwt_access_token>",
    "refresh": "<jwt_refresh_token>"
  }
}
```

---

### `POST /api/accounts/token/refresh/`

Refresh access token using refresh token.

- **Auth required**: No

**Request body:**
```json
{
  "refresh": "<jwt_refresh_token>"
}
```

---

### `GET /api/accounts/me/`

Get current authenticated user.

- **Auth required**: Yes
- **Allowed roles**: All

---

### `POST /api/accounts/change-password/`

Change account password.

- **Auth required**: Yes
- **Allowed roles**: All

**Request body:**
```json
{
  "old_password": "...",
  "new_password": "..."
}
```

---

### `POST /api/accounts/deactivate/`

Deactivate current account.

- **Auth required**: Yes
- **Allowed roles**: All (self-deactivation only)

---

### `POST /api/accounts/request-deletion/`

Request permanent account deletion.

- **Auth required**: Yes
- **Allowed roles**: All

---

## Profiles

### `GET /api/profiles/me/`

Get the full profile of the current user.

- **Auth required**: Yes
- **Allowed roles**: All
- **Purpose**: Returns user profile, role-specific profile, completion status, and verification status

---

### `PUT/PATCH /api/profiles/user/`

Update UserProfile (phone, gender, DOB, address, etc.).

- **Auth required**: Yes
- **Allowed roles**: All

---

### `PUT/PATCH /api/profiles/patient/`

Update patient-specific profile fields.

- **Auth required**: Yes
- **Allowed roles**: Patient

---

### `PUT/PATCH /api/profiles/doctor/`

Update doctor profile (specialty, license, bio, etc.).

- **Auth required**: Yes
- **Allowed roles**: Doctor

---

### `PUT/PATCH /api/profiles/pharmacist/`

Update pharmacist profile (license, pharmacy info).

- **Auth required**: Yes
- **Allowed roles**: Pharmacist

---

### `PUT/PATCH /api/profiles/laboratorian/`

Update laboratorian profile (license, lab info).

- **Auth required**: Yes
- **Allowed roles**: Laboratorian

---

## Consultations

### `GET /api/consultations/symptoms/`

List all active symptom categories and symptoms.

- **Auth required**: Yes
- **Allowed roles**: All

---

### `GET /api/consultations/symptoms/<id>/`

Get symptom detail including specialty rules.

- **Auth required**: Yes
- **Allowed roles**: All

---

### `POST /api/consultations/`

Create a new consultation.

- **Auth required**: Yes
- **Allowed roles**: Patient

**Request body:**
```json
{
  "selected_specialty": "cardiology",
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

List patient's own consultations.

- **Auth required**: Yes
- **Allowed roles**: Patient

---

### `GET /api/consultations/<id>/`

Get consultation detail.

- **Auth required**: Yes
- **Allowed roles**: Patient (own), Doctor (assigned)

---

### `GET /api/consultations/pending/`

List pending consultations matching doctor's specialty.

- **Auth required**: Yes
- **Allowed roles**: Doctor

---

### `POST /api/consultations/<id>/accept/`

Accept a consultation request.

- **Auth required**: Yes
- **Allowed roles**: Doctor (approved)

---

### `POST /api/consultations/<id>/respond/`

Submit a doctor's medical response.

- **Auth required**: Yes
- **Allowed roles**: Doctor (assigned)

**Request body:**
```json
{
  "response_text": "Based on your symptoms...",
  "recommendation": "needs_lab_test"
}
```

---

### `POST /api/consultations/<id>/close/`

Close a consultation.

- **Auth required**: Yes
- **Allowed roles**: Doctor (assigned), Patient (own)

---

## Messaging

### `GET /api/consultations/<id>/messages/`

List messages in a consultation thread.

- **Auth required**: Yes
- **Allowed roles**: Patient (own), Doctor (assigned)

---

### `POST /api/consultations/<id>/messages/`

Send a message in a consultation.

- **Auth required**: Yes
- **Allowed roles**: Patient (own), Doctor (assigned)

**Request body (multipart for attachments):**
```json
{
  "content": "Can you clarify something?",
  "message_type": "text"
}
```

---

### `GET /api/consultations/<id>/messages/<msg_id>/`

Get message detail.

- **Auth required**: Yes
- **Allowed roles**: Patient (own), Doctor (assigned)

---

## Prescriptions

### `POST /api/prescriptions/`

Create a new prescription.

- **Auth required**: Yes
- **Allowed roles**: Doctor (approved, assigned to consultation)

**Request body:**
```json
{
  "consultation_id": "uuid",
  "items": [
    {
      "medication_name": "Amoxicillin",
      "dosage": "500mg",
      "frequency": "3x daily",
      "duration_days": 7,
      "route": "oral",
      "instructions": "After meals"
    }
  ]
}
```

> **Privacy note**: Medication item details are never included in patient-facing prescription responses.

---

### `GET /api/prescriptions/my/`

List patient's own prescriptions (items hidden).

- **Auth required**: Yes
- **Allowed roles**: Patient

---

### `GET /api/prescriptions/<id>/`

Get prescription detail.

- **Auth required**: Yes
- **Allowed roles**: Doctor (issuer), Patient (own, items hidden)

---

### `GET /api/prescriptions/doctor/`

List prescriptions issued by the doctor.

- **Auth required**: Yes
- **Allowed roles**: Doctor

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

**Response**: Returns only `pending` items for this prescription.

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
      "status": "dispensed"
    }
  ]
}
```

---

### `GET /api/prescriptions/<id>/qr/`

Get QR token for a prescription (for patient to present to pharmacist).

- **Auth required**: Yes
- **Allowed roles**: Patient (own)

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

### `DELETE /api/notifications/<id>/`

Delete a notification.

- **Auth required**: Yes
- **Allowed roles**: All (own notifications)

---

## Patient Records

### `GET /api/patient-records/my/`

Get the current patient's medical record with entries.

- **Auth required**: Yes
- **Allowed roles**: Patient

---

### `GET /api/patient-records/doctor/<patient_id>/`

Get a patient's medical record (doctor view).

- **Auth required**: Yes
- **Allowed roles**: Doctor (approved, must have an accepted consultation with this patient)

---

### `POST /api/patient-records/entries/`

Create a new medical record entry.

- **Auth required**: Yes
- **Allowed roles**: Patient (self-reported), Doctor (doctor-confirmed for assigned patient)

**Request body:**
```json
{
  "category": "chronic_condition",
  "title": "Type 2 Diabetes",
  "description": "Diagnosed 2020",
  "patient_id": "uuid"
}
```

> **Note**: Patients cannot set `verification_status` or `source_role` — these are controlled by the system.

---

### `POST /api/patient-records/entries/<id>/confirm/`

Doctor confirms or rejects a patient-submitted medical record entry.

- **Auth required**: Yes
- **Allowed roles**: Doctor (approved, authorized for this patient)

**Request body:**
```json
{
  "action": "confirm"
}
```

---

### `POST /api/patient-records/entries/<id>/deactivate/`

Deactivate (soft-delete) a medical record entry.

- **Auth required**: Yes
- **Allowed roles**: Patient (own), Doctor (authorized)

---

### `POST /api/patient-records/blood-group/`

Set or update blood group for a patient.

- **Auth required**: Yes
- **Allowed roles**: Patient (self-reported), Doctor

**Request body:**
```json
{
  "blood_group": "o_positive"
}
```

---

### `POST /api/patient-records/blood-group/lab-verify/`

Laboratory-confirmed blood group update.

- **Auth required**: Yes
- **Allowed roles**: Laboratorian (approved)

---

## Lab Orders

### `POST /api/lab-orders/`

Create a new lab order linked to a consultation.

- **Auth required**: Yes
- **Allowed roles**: Doctor (approved, assigned to consultation)

**Request body:**
```json
{
  "consultation_id": "uuid",
  "items": [
    {
      "lab_test_id": "uuid",
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

### `GET /api/lab-orders/<id>/`

Get lab order detail.

- **Auth required**: Yes
- **Allowed roles**: Doctor (issuer), Patient (own, items hidden)

---

### `GET /api/lab-orders/doctor/`

List all lab orders issued by the doctor.

- **Auth required**: Yes
- **Allowed roles**: Doctor

---

### `POST /api/lab-orders/scan/`

Laboratorian scans QR token to access pending lab order items.

- **Auth required**: Yes
- **Allowed roles**: Laboratorian (approved)

**Request body:**
```json
{
  "qr_token": "..."
}
```

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

---

### `GET /api/lab-orders/<id>/qr/`

Get QR token for a lab order.

- **Auth required**: Yes
- **Allowed roles**: Patient (own)

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
- **Restriction**: Result must be in `reviewed` status before release

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

---

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


