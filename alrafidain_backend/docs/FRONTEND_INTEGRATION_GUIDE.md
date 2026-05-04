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
13. [File Uploads](#13-file-uploads)
14. [Pagination](#14-pagination)
15. [Token Storage Recommendations](#15-token-storage-recommendations)

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

Access tokens expire (default: 60 min). Refresh silently:

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

For doctors and non-patient roles, also check `verification_status` from `GET /api/profiles/me/`. A `pending` doctor cannot take actions until approved by staff.

---

## 6. Patient Integration Flow

```
Register → OTP verify → Login → Dashboard
```

### 6.1 Request a Consultation

```http
POST /api/consultations/request/
{ "selected_specialty": "general_medicine", "duration": "less_than_24_hours", "severity": "mild" }
```

Returns `consultation_id`. Poll or push-notify for status changes.

### 6.2 View Consultations

```http
GET /api/consultations/my/
```

Returns list of consultations with `status` field:  
`pending` → `accepted` → `closed`

### 6.3 Send Messages (Active Consultation)

Only available when `status == "accepted"`:

```http
POST /api/consultations/{consultation_id}/messages/
{ "message_type": "text", "content": "I have a headache." }
```

### 6.4 View Prescriptions

```http
GET /api/prescriptions/my/
```

> **Privacy note**: The `items` array (medication names and dosages) is **excluded** from patient responses. Patients see the prescription summary and QR token only.

### 6.5 View Lab Results

```http
GET /api/lab-orders/my/results/
```

> **Privacy note**: Results are only visible after the doctor has explicitly released them (`released_to_patient = true`). Unreleased results do not appear in this list.

### 6.6 Patient Record

```http
GET /api/patient-records/my/
```

Returns the patient's medical history, allergies, and chronic conditions.

---

## 7. Doctor Integration Flow

### 7.1 View Pending Consultations (Queue)

```http
GET /api/consultations/available/
```

Returns consultations matching the doctor's specialty that are still `pending`.

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

Only available for the assigned doctor:

```http
GET /api/patient-records/doctor/view/
Body: { "consultation_id": "..." }
```

### 7.5 Create Prescription

```http
POST /api/prescriptions/create/
{
  "consultation": "consultation_id",
  "notes": "Take with food.",
  "items": [
    { "medication_name": "Paracetamol", "dosage": "500mg", "frequency": "3x daily" }
  ]
}
```

### 7.6 Create Lab Order

```http
POST /api/lab-orders/create/
{
  "consultation": "consultation_id",
  "notes": "Fasting 8 hours.",
  "items": [
    { "test_name": "CBC", "description": "Complete blood count" }
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
POST /api/rag/doctor/feedback/
{ "rag_response": "uuid", "rating": 5, "comment": "Very accurate." }
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
GET /api/prescriptions/scan/{qr_token}/
```

Returns the prescription details with `items` visible to the pharmacist.

### 8.2 Dispense Prescription

```http
POST /api/prescriptions/{prescription_id}/dispense/
```

Marks the prescription as dispensed.

> **Boundary rule**: Pharmacists **cannot** access consultations, lab orders, or patient records. Any attempt returns 403 or 404.

---

## 9. Laboratorian Integration Flow

### 9.1 Scan Lab Order QR

```http
GET /api/lab-orders/scan/{qr_token}/
```

Returns lab order details and pending `items`.

### 9.2 Create Lab Result

```http
POST /api/lab-orders/{lab_order_id}/results/
{
  "result_summary": "All values within normal range.",
  "notes": "",
  "file": <multipart/form-data>     // optional attachment
}
```

> **Boundary rule**: Laboratorians **cannot** access prescriptions, consultation messages, or RAG. Any attempt returns 403 or 404.

---

## 10. Staff / Admin Integration Flow

### 10.1 Knowledge Base Management

```http
POST /api/knowledge-base/documents/upload/      // Upload PDF/document
GET  /api/knowledge-base/documents/             // List all documents
POST /api/knowledge-base/documents/{id}/process/ // Trigger vectorisation
POST /api/knowledge-base/documents/{id}/approve/ // Approve for RAG use
```

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

Poll every 30s or implement WebSocket/SSE if available in a future release.

---

## 13. File Uploads

Endpoints accepting files use `multipart/form-data`:

- `POST /api/consultations/{id}/messages/` — `content_file` field for image/audio attachments
- `POST /api/lab-orders/{id}/results/` — `file` field for lab result PDF
- `POST /api/knowledge-base/documents/upload/` — `file` field for document

Maximum file sizes are configured in Django settings (default: 10 MB). Always set `Content-Type: multipart/form-data` when uploading.

---

## 14. Pagination

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

## 15. Token Storage Recommendations

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
