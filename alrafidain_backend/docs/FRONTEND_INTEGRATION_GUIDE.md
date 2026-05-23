# Frontend & Mobile Integration Guide

**Platform**: Al-Rafidain Medical Platform  
**API Version**: v0.1.0  
**Base URL (local)**: `http://localhost:8000/api/`  
**Base URL (production)**: TBD  
**Auth scheme**: Bearer JWT (access + refresh tokens)

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Authentication Flow](#2-authentication-flow)
3. [Standard Response Envelope](#3-standard-response-envelope)
4. [Error Handling](#4-error-handling)
5. [Role-Based App Routing](#5-role-based-app-routing)
6. [Patient Integration Flow](#6-patient-integration-flow)
7. [Doctor Integration Flow](#7-doctor-integration-flow)
8. [Pharmacist Integration Flow](#8-pharmacist-integration-flow)
9. [Laboratorian Integration Flow](#9-laboratorian-integration-flow)
10. [Staff / Admin Integration Flow](#10-staff--admin-integration-flow)
11. [Privacy Rules and Data Visibility](#11-privacy-rules-and-data-visibility)
12. [Notifications](#12-notifications)
13. [WebSocket Realtime Layer (Phase 14)](#13-websocket-realtime-layer-phase-14)
14. [File Uploads](#14-file-uploads)
15. [Pagination](#15-pagination)
16. [Token Storage Recommendations](#16-token-storage-recommendations)
17. [Related Documentation](#related-documentation)

---

## 1. Quick Start

```
GET /api/health/
→ 200 { "status": "ok", "service": "alrafidain-backend", "version": "0.1.0" }
```

Use the health endpoint to verify connectivity and detect the deployed version before initialising your app.

---

## 2. Authentication Flow

### 2.1 Registration

```http
POST /api/accounts/register/
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "first_name": "Ali",
  "last_name": "Hassan",
  "user_type": "patient"          // "patient" | "doctor" | "pharmacist" | "laboratorian"
}
```

Valid `user_type` values: `patient`, `doctor`, `pharmacist`, `laboratorian`.

**Response (201):**
```json
{
  "success": true,
  "message": "Registration successful. Please verify your email.",
  "data": { "email": "user@example.com" }
}
```

After registration the user receives an OTP by email. The account is **inactive** until OTP verification succeeds.

### 2.2 OTP Verification

```http
POST /api/accounts/verify-otp/
Content-Type: application/json

{
  "email": "user@example.com",
  "otp": "123456"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Email verified successfully.",
  "data": {}
}
```

### 2.3 Login

```http
POST /api/accounts/login/
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Login successful.",
  "data": {
    "tokens": {
      "access": "<jwt_access_token>",
      "refresh": "<jwt_refresh_token>"
    },
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "user_type": "patient",
      "first_name": "Ali",
      "last_name": "Hassan",
      "is_active": true
    }
  }
}
```

Store both tokens immediately. Use the `user_type` field to route the user to the correct app screen.

### 2.4 Token Refresh

Access tokens expire (default: 24 hours). Refresh silently:

```http
POST /api/accounts/token/refresh/
Content-Type: application/json

{ "refresh": "<refresh_token>" }
```

**Response (200):**
```json
{ "access": "<new_access_token>" }
```

Implement automatic refresh in your HTTP client interceptor.  
If refresh returns `401`, clear stored tokens and redirect to Login.

### 2.5 Logout

```http
POST /api/accounts/logout/
Authorization: Bearer <access_token>
Content-Type: application/json

{ "refresh": "<refresh_token>" }
```

This blacklists the refresh token server-side. Always call this on explicit logout.

### 2.6 Using the Token

Every protected endpoint requires:

```
Authorization: Bearer <access_token>
```

---

## 3. Standard Response Envelope

All endpoints (except RAG and CSV exports) wrap responses in:

**Success:**
```json
{
  "success": true,
  "message": "Human-readable description.",
  "data": { ... }
}
```

**Error:**
```json
{
  "success": false,
  "message": "Human-readable error description.",
  "errors": { "field_name": ["error detail"] }
}
```

**Exceptions to the envelope:**
- `GET /api/rag/*` endpoints return raw serializer data (no envelope wrapper).
- `POST /api/rag/admin/exports/dataset/` returns `text/csv` or raw JSON list.
- `GET /api/schema/` returns the raw OpenAPI YAML.

---

## 4. Error Handling

| HTTP Status | Meaning | Action |
|---|---|---|
| 400 | Validation error | Show `errors` field details to user |
| 401 | Unauthenticated | Trigger token refresh; redirect to login if refresh fails |
| 403 | Forbidden | Show "Access denied" — user role cannot perform this action |
| 404 | Not found | Show "Not found" message |
| 409 | Conflict | Resource already exists (e.g. duplicate consultation) |
| 500 | Server error | Show generic error; do not expose details |

---

## 5. Role-Based App Routing

After login, use `user_type` from the login response to route:

| `user_type` | App Entry Point |
|---|---|
| `patient` | Patient dashboard — consultations, prescriptions, lab results |
| `doctor` | Doctor dashboard — pending consultations, active cases, notes |
| `pharmacist` | Pharmacist scanner — QR scan → dispense |
| `laboratorian` | Lab scanner — QR scan → create result |
| (staff flag) | Admin panel — knowledge base, RAG feedback, analytics |

For professional roles (`doctor`, `pharmacist`, `laboratorian`), also check `verification_status` from `GET /api/profiles/me/`. A `pending` professional account cannot perform approved-only actions until reviewed by staff.

---

## 6. Patient Integration Flow

```
Register → OTP verify → Login → Dashboard
```

### 6.1 Request a Consultation

**Step 1 — Browse symptom catalog (recommended UX)**

```http
GET /api/consultations/symptom-categories/
```
Returns 18 patient-friendly categories. Display them as a grouped selector.

```http
GET /api/consultations/symptoms/?category=<id>
```
Returns active symptoms for that category. Patients select one or more symptoms (IDs) before submitting.

Alternatively, use `?is_red_flag=true` to surface high-priority emergency prompts.

> **Triage note**: Symptom names use patient-friendly plain language.
> Specialty assignment is automatic and deterministic (not AI, not diagnosis).
> Do **not** ask the patient to select a specialty.

**Step 2 — Submit consultation**

```http
POST /api/consultations/
{
  "duration": "less_than_24_hours",
  "severity": "mild",
  "has_fever": false,
  "has_pain": true,
  "symptom_ids": ["uuid1", "uuid2"]
}
```

The backend assigns `selected_specialty` from the submitted symptoms using weighted routing rules.
Do not ask the patient to choose a specialty in the client.
The create response includes the consultation identifier at `data.id`; use this value for redirect to the detail route.

Patient detail access after creation:
- `GET /api/consultations/{id}/` is allowed for the owning patient immediately after create.
- `GET /api/consultations/{id}/` is denied for other patients.
- Assigned doctors can view detail per consultation access policy.

Future phase note: profile-completion gating before consultation creation will be enforced later (not part of this phase).

### 6.2 View Consultations

Important distinction:
- `GET /api/consultations/doctor/pending/` is a doctor queue endpoint. It returns consultations, not doctors.
- Patients should not use that endpoint after submission.
- The patient flow should go to consultation detail using the `data.id` returned from `POST /api/consultations/`.

If product later requires a patient-visible doctor picker, that needs a dedicated backend endpoint. The current backend does not expose one.

```http
GET /api/consultations/my/
```

Returns list of consultations with backend lifecycle values:
`submitted` → `accepted` → `doctor_responded` → `closed`

### 6.3 Send Messages (Active Consultation)

Send is available only when consultation status is `accepted` or `doctor_responded`.
Read/list is available when status is `accepted`, `doctor_responded`, or `closed`.

```http
POST /api/consultations/{consultation_id}/messages/
{ "body": "I have a headache." }
```

### 6.4 View Prescriptions

```http
GET /api/prescriptions/my/
```

> **Privacy note**: The `items` array (medication names and dosages) is **excluded** from patient responses. Patients see the prescription summary and QR token only.

### 6.5 View Lab Results

```http
GET /api/lab-results/my/
```

> **Privacy note**: Results are only visible after doctor release (`status = released`). Unreleased results do not appear in this list.

### 6.6 Patient Record

```http
GET /api/patient-records/my/
```

Returns the patient's medical history, allergies, and chronic conditions.

---

## 7. Doctor Integration Flow

### 7.1 View Pending Consultations (Queue)

```http
GET /api/consultations/doctor/pending/
```

Returns consultations matching the doctor's profile specialty that are still `submitted` and unassigned.

### 7.2 Accept a Consultation

```http
POST /api/consultations/{consultation_id}/accept/
```

### 7.3 Chat with Patient

```http
GET  /api/consultations/{consultation_id}/messages/
POST /api/consultations/{consultation_id}/messages/
```

### 7.4 View Patient Record (During Consultation)

Only available for authorized doctors with assigned consultation access:

```http
GET /api/patient-records/patients/{patient_id}/
```

### 7.5 Create Prescription

```http
POST /api/consultations/{consultation_id}/prescriptions/
{
  "items": [
    {
      "medication_name": "Paracetamol",
      "strength": "500mg",
      "dosage": "1 tablet",
      "frequency": "3x daily",
      "duration": "3 days",
      "route": "oral",
      "quantity": "9 tablets",
      "instructions": "Take with food"
    }
  ]
}
```

Prescription create requirements:
- Consultation must be assigned to the requesting approved doctor.
- Consultation status must be `accepted` or `doctor_responded`.
- `items` must be non-empty.
- Required per item: `medication_name`, `dosage`, `frequency`, `duration`, `route`.
- Optional per item: `strength`, `quantity`, `instructions`.
- Allowed `route` values: `oral`, `topical`, `inhalation`, `injection`, `eye`, `ear`, `nasal`, `rectal`, `other`.

Validation error example (missing route):
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

### 7.6 Create Lab Order

```http
POST /api/consultations/{consultation_id}/lab-orders/
{
  "items": [
    {
      "test": "lab_test_catalog_uuid",
      "test_name": "CBC",
      "category": "hematology",
      "sample_type": "Blood",
      "instructions": "Fasting 8 hours"
    }
  ]
}
```

### 7.7 Review and Release Lab Result

```http
POST /api/lab-orders/results/{lab_result_id}/review/
{ "doctor_notes": "All normal." }

POST /api/lab-orders/results/{lab_result_id}/release/
```

### 7.8 RAG Clinical Assistant

Approved doctors can query the clinical knowledge base:

```http
POST /api/rag/doctor/query/
{ "query_text": "First-line treatment for hypertension in elderly patients?" }
```

Response is raw (no envelope):
```json
{
  "id": "uuid",
  "query_text": "...",
  "response_text": "...",
  "sources": [...],
  "created_at": "..."
}
```

Submit feedback:
```http
POST /api/rag/responses/{id}/feedback/
{ "rating": "helpful", "comment": "Very accurate." }
```

### 7.9 Close Consultation

```http
POST /api/consultations/{consultation_id}/close/
```

---

## 8. Pharmacist Integration Flow

### 8.1 Scan Prescription QR

The patient presents a QR code which encodes `qr_token`.

```http
POST /api/prescriptions/scan/
{ "qr_token": "..." }
```

Returns the prescription details with `items` visible to the pharmacist.

### 8.2 Dispense Prescription

```http
POST /api/prescriptions/{prescription_id}/dispense/
```

Marks the prescription as dispensed.

### 8.3 View Pharmacist Dispensing History

```http
GET /api/prescriptions/pharmacist/history/?limit=20&offset=0
```

Returns paginated dispensing records for the authenticated approved pharmacist only.

- Includes safe patient summary (`id`, `full_name`, `gender`, `age`)
- Includes safe doctor summary (`id`, `full_name`, `specialty`)
- Includes medication item metadata and dispensing status
- Excludes `qr_token`, internal dispensing notes, and private patient profile fields

Use this endpoint for `/app/pharmacist/history`. Do not generate or rely on fake history data.

> **Boundary rule**: Pharmacists **cannot** access consultations, lab orders, or patient records. Any attempt returns 403 or 404.

---

## 9. Laboratorian Integration Flow

### 9.1 Scan Lab Order QR

```http
POST /api/lab-orders/scan/
{ "qr_token": "..." }
```

Returns lab order details and pending `items`.

### 9.2 Create Lab Result

```http
POST /api/lab-orders/items/{lab_order_item_id}/results/
{
  "value_type": "numeric",
  "numeric_value": "5.7",
  "unit": "mmol/L",
  "reference_range": "3.9-6.1",
  "flag": "normal"
}
```

> **Boundary rule**: Laboratorians **cannot** access prescriptions, consultation messages, or RAG. Any attempt returns 403 or 404.

---

## 10. Staff / Admin Integration Flow

### 10.1 Knowledge Base Management

```http
POST /api/knowledge-base/documents/             // Upload document
GET  /api/knowledge-base/documents/             // List all documents
POST /api/knowledge-base/documents/{id}/process/ // Trigger processing (extract + chunk)
POST /api/knowledge-base/documents/{id}/approve/ // Approve for RAG use
```

**Upload request** is `multipart/form-data` and must include:
- `title`
- `document_type` (`medical_book`, `laboratory_book`, `clinical_guideline`, `drug_reference`, `patient_education`, `platform_policy`, `other`)
- `language` (`english`, `arabic`, `kurdish`, `mixed`, `other`)
- `audience` (`doctor`, `pharmacist`, `laboratorian`, `patient`, `admin`, `mixed`)
- `file` (accepted extensions: `.pdf`, `.docx`, `.txt`)

Compatibility note:
- Backend also accepts file aliases: `reference`, `document`, `document_file`, `upload`.
- Prefer sending `file` as the canonical field.

**Processing workflow:**

1. **Upload** → `POST /api/knowledge-base/documents/` → 201, returns `document_id`
2. **Process** → `POST /api/knowledge-base/documents/{document_id}/process/` → 202 (queued) or 200 (sync)
   - **Production mode** (Celery worker running):
     - Returns 202 with `job_id`
     - Frontend must **poll** `GET /api/knowledge-base/documents/{document_id}/` every 2–5 sec
     - Wait until `processing_status` changes from `uploaded` to `chunked` (or `extracted`)
   - **Development mode** (no Celery worker): Add `?sync=true` to force synchronous processing
     - `POST /api/knowledge-base/documents/{document_id}/process/?sync=true` → 200 immediately
     - Document transitions directly to `chunked` status
3. **Approve** → `POST /api/knowledge-base/documents/{document_id}/approve/` → 200, only after processing_status=chunked
4. **Embed** (optional) → `POST /api/knowledge-base/documents/{document_id}/embed/` → 200, generates vector embeddings

**Frontend error handling:**
- If approve returns 400 with "Cannot approve: Document must be processed", it means processing didn't complete.
  - Recommended: Retry or inform user that system is processing (check status again in a few seconds).

### 10.2 RAG Feedback Review

```http
GET /api/rag/admin/feedback/                    // List all doctor feedback
```

### 10.3 Analytics Summary

```http
GET /api/rag/admin/analytics/summary/
```

### 10.4 Training Dataset Export

```http
POST /api/rag/admin/exports/dataset/
{ "format": "json" }     // "json" | "csv"
```

> Returns raw JSON array or `text/csv`. No envelope wrapper.

### 10.5 Verification Review Queue (Phase 9A Backend)

```http
GET  /api/admin/verifications/
GET  /api/admin/verifications/{role}/{id}/
POST /api/admin/verifications/{role}/{id}/approve/
POST /api/admin/verifications/{role}/{id}/reject/
POST /api/admin/verifications/{role}/{id}/suspend/
```

Notes:
- Staff/admin only (`is_staff` or `is_superuser`).
- Supported roles: `doctor`, `pharmacist`, `laboratorian`.
- Patients are excluded from this queue.
- `status` defaults to `pending` when omitted.
- Filters: `role`, `status`, `search`, `limit`, `offset`.
- Reject/suspend require `reason`.
- Approve accepts optional `note`.
- Self-approval is denied by backend policy.

### 10.6 Medical Report Candidates (Phase 10B)

When a patient uploads a consultation chat attachment, the backend now creates a `PatientMedicalReport` candidate record.

Available endpoints:
- `GET /api/patient/medical-reports/`
- `GET /api/patient/medical-reports/{report_id}/`
- `GET /api/doctor/consultations/{consultation_id}/medical-reports/`
- `GET /api/doctor/medical-reports/{report_id}/`
- `POST /api/doctor/medical-reports/{report_id}/review/`
- `POST /api/doctor/medical-reports/{report_id}/process-ocr/`

Phase 10B behavior contract:
- Candidate creation is non-blocking and does not break chat send flow.
- OCR processing can be triggered by assigned doctors using `process-ocr`.
- If OCR-on-upload settings are enabled server-side, processing may run inline or queued.
- No automatic insertion into canonical patient medical record entries is triggered yet.

Frontend implementation notes:
- Treat these as review candidates, not final verified medical record entries.
- Continue using existing chat message flow; no request-body changes are required.
- Use `file_url` for image/document preview, not storage-relative `file` paths.
- For patient view, show high-level OCR status only; raw OCR text and processing internals are hidden.
- Show OCR statuses as: `uploaded`, `queued`, `ocr_pending`, `ocr_completed`, `rejected`, `failed`.

Deferred after Phase 10B:
- LLM cleanup/classification
- Structured lab value extraction
- Automatic RAG updates from OCR output
- Doctor AI assistant messages based on extracted report context

---

## 11. Privacy Rules and Data Visibility

Critical rules your frontend must enforce (backend enforces these server-side too, but frontend should not display controls for disallowed actions):

| Rule | Applies To | Detail |
|---|---|---|
| Prescription items hidden | Patients | `items` array removed from patient prescription responses |
| Lab order items hidden | Patients | Individual test items hidden until laboratorian scans |
| Lab results gated by release | Patients | Results only visible after `released_to_patient = true` |
| Doctor notes private | Patients | Doctor-side notes fields are excluded from patient serializer |
| Consultation messages | Parties only | Only the assigned patient and doctor can read messages |
| Patient record | Doctor (assigned) | Only the doctor assigned to an active consultation can access |
| RAG endpoints | Doctors only | Patients, pharmacists, laboratorians → 403 |
| RAG admin endpoints | Staff only | Non-staff doctors → 403 |
| Verification review endpoints | Staff only | Non-staff users → 403 |
| Pharmacist isolation | — | Cannot access consultations, lab orders, patient records |
| Laboratorian isolation | — | Cannot access prescriptions, consultation messages |

---

## 12. Notifications

```http
GET  /api/notifications/                          // List all (unread first)
POST /api/notifications/{id}/read/               // Mark single as read
POST /api/notifications/read-all/               // Mark all as read
```

**Notification categories**: `consultation_accepted`, `prescription_ready`, `lab_result_released`, `message_received`, `system`.

For realtime notifications, use WebSocket (Phase 14, see below) to receive `notification.created` and `notification.unread_count` events.

---

## 13. WebSocket Realtime Layer (Phase 14)

### Overview

The backend broadcasts realtime events via WebSocket to keep clients synchronized without polling. **WebSocket is realtime delivery only—all data creation still happens via REST API.**

### Endpoints

```
User Notifications:  ws://localhost:8000/ws/user/?token=<access_token>
Consultation Chat:   ws://localhost:8000/ws/consultations/<id>/messages/?token=<access_token>
```

**Important:** Use `wss://` (secure WebSocket) in production, not `ws://`.

### Event Types

**User Socket Events:**
- `notification.created` — New notification
- `notification.unread_count` — Unread count updated
- `consultation.updated` — Consultation status changed
- `prescription.updated` — Prescription status changed
- `lab_order.updated` — Lab order status changed
- `lab_result.released` — Lab result released to patient

**Consultation Socket Events:**
- `chat.message.created` — New message in consultation
- `chat.messages.read` — Messages marked as read
- `consultation.updated` — Consultation status changed

See [docs/WEBSOCKET_CONTRACT.md](WEBSOCKET_CONTRACT.md) for full payload schemas and integration examples.

### Connection Example (JavaScript)

```javascript
const token = localStorage.getItem('access_token');
const userWs = new WebSocket(`wss://api.example.com/ws/user/?token=${token}`);

userWs.addEventListener('message', (event) => {
  const data = JSON.parse(event.data);
  
  switch(data.type) {
    case 'notification.created':
      console.log('New notification:', data.notification);
      addNotificationToUI(data.notification);
      break;
    case 'notification.unread_count':
      updateBadge(data.unread_count);
      break;
    case 'lab_result.released':
      showLabResultNotification(data.lab_result);
      refreshResultsList();
      break;
  }
});

userWs.addEventListener('close', () => {
  // Reconnect or fallback to polling
  console.log('WebSocket disconnected');
  setTimeout(() => reconnectWebSocket(), 3000);
});
```

### REST + WebSocket Architecture

```
1. User takes action (send message, create prescription, etc.)
         ↓
2. POST to REST API endpoint
         ↓
3. Data validated and saved to database
         ↓
4. Service broadcasts WebSocket event
         ↓
5. Connected clients receive update in real-time
```

**Key Rules:**
- ✅ Use REST API for all data creation/modification
- ✅ Use WebSocket for realtime updates
- ✅ Reconnect WebSocket if disconnected
- ✅ Fallback to REST polling if WebSocket fails
- ❌ Do NOT create messages/data over WebSocket in MVP
- ❌ Do NOT rely only on WebSocket (use REST as source of truth)

### Token Handling

Tokens are passed in the WebSocket URL:
```
/ws/user/?token=<access_token>
```

When token expires:
1. Fetch new access token via REST API refresh endpoint
2. Disconnect old WebSocket
3. Reconnect with new token

### Automatic Reconnection

Implement exponential backoff for reconnection:

```javascript
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const BASE_DELAY = 1000; // 1 second

function reconnectWebSocket() {
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    console.error('Max reconnect attempts reached. Switch to polling.');
    switchToRestPolling();
    return;
  }

  const delay = BASE_DELAY * Math.pow(2, reconnectAttempts);
  reconnectAttempts++;

  setTimeout(() => {
    connectWebSocket();
  }, delay);
}
```

### Priority: REST First, WebSocket Enhancement

Always:
1. Load initial data via REST API (ensures you have latest data)
2. Subscribe to WebSocket for realtime updates
3. If WebSocket fails, use REST polling or refetch

```javascript
// 1. Load initial data
const initialData = await fetch('/api/notifications/').then(r => r.json());
updateUI(initialData.data.results);

// 2. Connect to WebSocket for realtime
connectWebSocket();

// 3. Fallback to polling if WebSocket disconnects
if (websocketFailed) {
  startPolling('/api/notifications/', 30000); // Poll every 30s
}
```

### See Also

- Full contract: [docs/WEBSOCKET_CONTRACT.md](WEBSOCKET_CONTRACT.md)
- Implementation notes: [apps/realtime/README.md](../apps/realtime/README.md) (internal)

---

## 14. File Uploads

Endpoints accepting files use `multipart/form-data`:

- `POST /api/consultations/{id}/messages/` — `content_file` field for image/audio attachments
- `POST /api/lab-orders/{id}/results/` — `file` field for lab result PDF
- `POST /api/knowledge-base/documents/` — `file` field for document

Maximum file sizes are configured in Django settings:
- Knowledge documents: 20 MB
- Clinical attachments: 15 MB
- Profile images: 5 MB

Always set `Content-Type: multipart/form-data` when uploading.

---

## 15. Pagination

List endpoints return paginated responses:

```json
{
  "success": true,
  "data": {
    "count": 42,
    "next": "http://localhost:8000/api/consultations/my/?page=2",
    "previous": null,
    "results": [...]
  }
}
```

Use `?page=N` query param to navigate pages.

---

## 16. Token Storage Recommendations

| Platform | Recommendation |
|---|---|
| Web (React/Vue) | `httpOnly` cookie for refresh token; memory only for access token |
| React Native | `expo-secure-store` or `react-native-keychain` |
| Flutter | `flutter_secure_storage` |
| Avoid | `localStorage` for tokens (XSS risk) |

Always clear tokens on logout and on 401 with failed refresh.

---

## Related Documentation

- [docs/API_REFERENCE.md](API_REFERENCE.md) — Full endpoint reference
- [docs/ENDPOINT_INVENTORY.md](ENDPOINT_INVENTORY.md) — Endpoint inventory table
- [docs/ROLE_PERMISSION_MATRIX.md](ROLE_PERMISSION_MATRIX.md) — Role permission matrix
- [docs/API_RESPONSE_CONTRACT.md](API_RESPONSE_CONTRACT.md) — Response format contract
- [docs/postman/](postman/) — Postman collection and environment
- [docs/openapi-schema.yml](openapi-schema.yml) — OpenAPI 3.0 YAML schema
