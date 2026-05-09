# Laboratory Workflow Contract

Phase 6.0A

---

## Table of Contents

1. [Overview](#overview)
2. [Laboratory Role and Verification](#laboratory-role-and-verification)
3. [Lab Order Lifecycle](#lab-order-lifecycle)
4. [Lab Result Lifecycle](#lab-result-lifecycle)
5. [Lab Catalog and Test Management](#lab-catalog-and-test-management)
6. [Pending Lab Orders Contract](#pending-lab-orders-contract)
7. [Lab Order Detail Contract](#lab-order-detail-contract)
8. [Lab Order Scan (QR) Contract](#lab-order-scan-qr-contract)
9. [Lab Order Completion Contract](#lab-order-completion-contract)
10. [Result Creation Contract](#result-creation-contract)
11. [Result Correction Contract](#result-correction-contract)
12. [Doctor Review/Release Handoff](#doctor-reviewrelease-handoff)
13. [Patient Visibility Contract](#patient-visibility-contract)
14. [Privacy Rules](#privacy-rules)
15. [Notifications Side Effects](#notifications-side-effects)
16. [Known Backend Gaps](#known-backend-gaps)
17. [Frontend Implementation Recommendations](#frontend-implementation-recommendations)

---

## Overview

The Laboratory Portal enables:

- **Doctors** to order lab tests for patients during consultations
- **Laboratorians** to scan lab orders via QR code, complete tests, and submit results
- **Doctors** to review, release, and link results to medical records
- **Patients** to view released results only (with sensitive notes hidden)

All laboratory workflows are transaction-backed and enforce role verification before performing clinical actions.

---

## Laboratory Role and Verification

### User Type

Laboratory personnel register as `user_type = "laboratorian"`.

### Profile Requirement

Each laboratorian must have a `LaboratorianProfile` with:

| Field | Required | Verification | Purpose |
|---|---|---|---|
| `laboratorian_license_number` | Yes | User can provide | Professional credential |
| `laboratorian_license_image` | Yes | File upload | License verification |
| `laboratory_name` | Yes | User can provide | Facility identification |
| `laboratory_license_number` | Yes | User can provide | Lab facility credential |
| `laboratory_license_image` | Yes | File upload | Lab license verification |
| `laboratory_address` | Yes | User can provide | Facility location |
| `specialization` | No | User can provide | Lab specialty (e.g., hematology) |
| `working_hours` | No | User can provide | Lab operating hours |
| `verification_status` | Yes | Admin approval | `PENDING` \| `APPROVED` \| `REJECTED` \| `SUSPENDED` |

### Verification Enforcement

- **Approval required**: All lab clinical endpoints (scan, complete items, create result, correct result) require `verification_status = APPROVED`
- **Backend enforcement**: Views return `403 Forbidden` if not approved
- **Frontend gate**: Recommend showing "Pending Verification" message if `verification_status != APPROVED`

### Unverified Laboratorian Restrictions

Unverified laboratorians **cannot**:
- Scan lab orders via QR
- Mark items completed
- Create lab results
- Correct lab results
- Access any clinical lab endpoints

Expected behavior: Request profile completion and wait for admin approval.

---

## Lab Order Lifecycle

### Status Values

| Status | Transition | Meaning |
|---|---|---|
| `issued` | Initial | Lab order created by doctor, awaiting lab action |
| `partially_completed` | Auto-updated | Some items completed, some still pending |
| `fully_completed` | Auto-updated | All items completed or cancelled |
| `expired` | Auto-updated on scan | 7 days passed since creation |
| `cancelled` | Doctor action | Doctor cancelled before any completion |

### Status Transition Rules

```
[issued] 
  ↓ (lab user scans QR, completes items)
[partially_completed]
  ↓ (remaining items marked completed)
[fully_completed]  ← locked (no more changes)

[issued]
  ↓ (7 days pass)
[expired]  ← locked (no more changes)

[issued]
  ↓ (doctor cancels before completion)
[cancelled]  ← locked (no more changes)
```

### Expiry

- Default expiry: **7 days** from lab order creation (configurable via `LAB_ORDER_EXPIRY_DAYS`)
- Checked on: Lab user QR scan
- If expired: Status auto-updated to `expired`, order becomes locked
- Locked orders cannot be modified by laboratorian

---

## Lab Result Lifecycle

### Result Statuses

| Status | Creator | Next Step | Patient Visible |
|---|---|---|---|
| `submitted` | Laboratorian | Doctor review | No |
| `corrected` | Laboratorian (correction) | Doctor review | No |
| `reviewed` | Doctor | Doctor release or hold | No |
| `released` | Doctor | Linked to medical record (optional) | **Yes** |
| `draft` | (not used in current flow) | — | — |
| `cancelled` | (not used in current flow) | — | — |

### Result Lifecycle Flow

```
[submitted] (lab user creates result)
  ↓ (lab user can correct)
[corrected] (optional, multi-correction allowed)
  ↓
[reviewed] (doctor reviews, may add notes)
  ↓ (doctor releases to patient)
[released]  ← Patient can now see result
  ↓ (doctor optionally links)
[linked_to_medical_record]
```

### Correction Rules

- Only **laboratorian who created the result** can correct it
- Can correct only while status is `submitted` or `corrected`
- Cannot correct once doctor has released to patient
- Each correction creates audit trail in `LabResultCorrection` model

---

## Lab Catalog and Test Management

### Lab Test Catalog

Provides list of standard lab tests with defaults.

**Endpoint**: `GET /api/lab-orders/tests/`

| Field | Type | Example |
|---|---|---|
| `id` | UUID | — |
| `name` | String | "CBC", "HbA1c" |
| `category` | Choice | `hematology`, `biochemistry`, `immunology`, `microbiology`, `urine_stool`, `hormones`, `blood_bank`, `other` |
| `code` | String | "H001" (optional) |
| `description` | String | (optional) |
| `default_sample_type` | String | "Blood", "Urine", "Serum" |
| `default_instructions` | String | "Fasting 8 hours" |
| `is_active` | Boolean | `true` (inactive tests not returned) |
| `display_order` | Integer | Sort order in UI |

### Filtering

- `?category=hematology` — Filter by test category
- `?search=cbc` — Search by test name (case-insensitive)

---

## Pending Lab Orders Contract

**Note**: MVP has no separate "pending" endpoint. Patients/doctors list their orders and filter client-side.

### Doctor Lab Order List (if implemented)

Proposed contract:
- Doctor can filter their created lab orders by status
- No endpoint currently exists; would be `GET /api/lab-orders/doctor/pending/`

### Patient Lab Order List

**Endpoint**: `GET /api/lab-orders/my/`

- Returns patient's lab orders (patient must be owner)
- Includes `qr_token` so patient can present to lab
- **Does NOT** include test item details (privacy rule)
- Response includes guidance text recommending patient show QR to lab

**Response fields** (patient-safe):
```json
{
  "id": "uuid",
  "consultation_id": "uuid",
  "doctor": { "id", "email", "full_name" },
  "status": "issued",
  "qr_token": "...",
  "qr_url": "/api/lab-orders/scan/?qr_token=...",
  "test_count": 2,
  "issued_at": "2026-05-08T...",
  "expires_at": "2026-05-15T...",
  "fully_completed_at": null,
  "guidance": "Show this QR code to any verified laboratory..."
}
```

---

## Lab Order Detail Contract

### Doctor Lab Order Detail

**Endpoint**: `GET /api/lab-orders/doctor/<lab_order_id>/`

- Only ordering doctor can view
- Returns full order + all items + completion records

**Response includes**:
- Full `items[]` with test names, categories, sample type
- Full `completion_records[]` with who completed and timestamps
- All timestamps: `created_at`, `cancelled_at`, `fully_completed_at`

### Patient Lab Order Detail

**Endpoint**: `GET /api/lab-orders/my/<lab_order_id>/`

- Only patient can view their own order
- **Does NOT** include test item details (privacy rule)
- Shows same patient-safe fields as list

---

## Lab Order Scan (QR) Contract

**Endpoint**: `POST /api/lab-orders/scan/`

**Required role**: Laboratorian (approved)

**Request**:
```json
{
  "qr_token": "<string from patient or doctor>"
}
```

**Response** (success, issued order):
```json
{
  "success": true,
  "data": {
    "lab_order": {
      "id": "uuid",
      "status": "issued",
      "doctor": { "id", "email", "full_name" },
      "issued_at": "2026-05-08T...",
      "expires_at": "2026-05-15T...",
      "completed_items": []
    },
    "remaining_items": [
      {
        "id": "uuid",
        "test_name": "CBC",
        "category": "hematology",
        "sample_type": "Blood",
        "instructions": "Standard sample handling"
      }
    ],
    "locked": false,
    "message": null
  },
  "message": "QR scanned."
}
```

**Response** (partially completed order):
```json
{
  "success": true,
  "data": {
    "lab_order": {
      "id": "uuid",
      "status": "partially_completed",
      "doctor": { ... },
      "issued_at": "2026-05-08T...",
      "expires_at": "2026-05-15T...",
      "completed_items": [
        {
          "id": "uuid",
          "test_name": "CBC",
          "category": "hematology",
          "sample_type": "Blood",
          "instructions": "Standard sample handling",
          "status": "completed",
          "completed_at": "2026-05-09T...",
          "cancelled_at": null,
          "result_id": "uuid or null"
        }
      ]
    },
    "remaining_items": [
      {
        "id": "uuid",
        "test_name": "HbA1c",
        "category": "biochemistry",
        "sample_type": "Serum",
        "instructions": "..."
      }
    ],
    "locked": false,
    "message": null
  },
  "message": "QR scanned."
}
```

**Response** (fully completed order):
```json
{
  "success": true,
  "data": {
    "lab_order": {
      "id": "uuid",
      "status": "fully_completed",
      "doctor": { ... },
      "issued_at": "2026-05-08T...",
      "expires_at": "2026-05-15T...",
      "completed_items": [
        {
          "id": "uuid",
          "test_name": "CBC",
          "category": "hematology",
          "sample_type": "Blood",
          "instructions": "...",
          "status": "completed",
          "completed_at": "2026-05-09T...",
          "cancelled_at": null,
          "result_id": "uuid"
        },
        {
          "id": "uuid",
          "test_name": "HbA1c",
          "category": "biochemistry",
          "sample_type": "Serum",
          "instructions": "...",
          "status": "completed",
          "completed_at": "2026-05-09T...",
          "cancelled_at": null,
          "result_id": "uuid"
        }
      ]
    },
    "remaining_items": [],
    "locked": true,
    "message": "This lab order is no longer available for completion."
  },
  "message": "QR scanned."
}
```

### Lab Order Scan Response Fields

**lab_order** object now includes:
- `id`: Lab order UUID
- `status`: Current order status (issued, partially_completed, fully_completed, expired, cancelled)
- `doctor`: Ordering doctor info
- `issued_at`: When order was created
- `expires_at`: When order expires (7 days from creation)
- **`completed_items`** *(NEW)*: Array of completed/cancelled items with metadata (see below)

**completed_items** array (NEW):
Each item in the array contains:
- `id`: Lab order item UUID
- `test_name`: Name of the test (e.g., "CBC", "HbA1c")
- `category`: Test category (hematology, biochemistry, etc.)
- `sample_type`: Sample type (Blood, Serum, Urine, etc.)
- `instructions`: Lab-side instructions for the test
- `status`: Item status (completed or cancelled)
- `completed_at`: Timestamp when item was marked done
- `cancelled_at`: Timestamp when item was cancelled (or null)
- `result_id`: UUID of the lab result if one exists, or null

**Safety note**: `completed_items` contains lab-safe item metadata only. It does NOT expose:
- Result values (numeric, text, blood group)
- Doctor notes
- Laboratorian private notes
- Patient-hidden result fields

Result data is retrieved separately via result endpoints.

### Error Cases

| Case | Status | Cause |
|---|---|---|
| Invalid QR token | 400 | Token not found or invalid |
| Expired order | 200 | Order auto-marked expired, returns locked with completed_items |
| Unapproved lab user | 403 | Laboratorian verification_status != APPROVED |
| Not authenticated | 401 | Missing/invalid bearer token |

### Side Effects

- Audit log: `lab_order_qr_scanned` recorded
- Expiry check: If order is past expiry, auto-update status to `expired`

---

## Lab Order Completion Contract

**Endpoint**: `POST /api/lab-orders/<lab_order_id>/complete/`

**Required role**: Laboratorian (approved)

**Request**:
```json
{
  "items": [
    {
      "lab_order_item_id": "uuid",
      "status": "completed",
      "note": "Completed successfully"
    },
    {
      "lab_order_item_id": "uuid",
      "status": "unavailable",
      "note": "Patient cancelled, sample unavailable"
    }
  ]
}
```

**Item status choices**:
- `completed` — Test was completed, result to follow
- `unavailable` — Test could not be completed (patient declined, sample issue, etc.)

**Response**:
Same shape as scan response (updated `lab_order` + remaining `pending_items` + `locked` flag).

### Side Effects

- Item status updated to `completed` or `cancelled` (unavailable means cancelled)
- `LabCompletionRecord` created for audit trail
- Order status auto-updated based on item statuses:
  - All done → `fully_completed`
  - Some done → `partially_completed`
  - All pending → `issued`
- Notifications sent to doctor:
  - "Lab test completed" (if status = `completed`)
  - "Lab test unavailable" (if status = `unavailable`)

### Errors

| Case | Status | Reason |
|---|---|---|
| Item not in this order | 400 | Item ID doesn't belong to order |
| Order is locked | 400 | Cannot modify locked orders |
| Order is expired | 400 | Expired orders cannot be modified |
| Unapproved user | 403 | Verification_status != APPROVED |

---

## Result Creation Contract

**Endpoint**: `POST /api/lab-orders/items/<lab_order_item_id>/results/`

**Required role**: Laboratorian (approved, must have completed this item)

**Request** (varies by value type):

### Numeric Result
```json
{
  "value_type": "numeric",
  "numeric_value": "7.2",
  "unit": "mmol/L",
  "reference_range": "3.9-6.1",
  "flag": "high",
  "laboratorian_notes": "Rerun required, initial was 8.1"
}
```

### Text Result
```json
{
  "value_type": "text",
  "text_value": "No growth detected",
  "unit": "",
  "reference_range": "",
  "flag": "normal",
  "laboratorian_notes": "Culture negative"
}
```

### Blood Group Result
```json
{
  "value_type": "blood_group",
  "blood_group_value": "o_positive",
  "flag": "normal"
}
```

### Positive/Negative Result
```json
{
  "value_type": "positive_negative",
  "text_value": "positive",
  "reference_range": "negative",
  "flag": "abnormal"
}
```

### File-Only Result
```json
{
  "value_type": "file_only",
  "result_file": "<multipart file upload>",
  "laboratorian_notes": "Uploaded scan of paper report"
}
```

### Field Requirements by Type

| Type | Required | Conditional | Optional |
|---|---|---|---|
| `numeric` | value_type, numeric_value | — | unit, reference_range, flag, notes |
| `text` | value_type, text_value | — | unit, reference_range, flag, notes |
| `blood_group` | value_type, blood_group_value | — | flag, notes |
| `positive_negative` | value_type, text_value (pos/neg) | — | reference_range, flag, notes |
| `file_only` | value_type, result_file | — | flag, notes |

**Response** (201):
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "lab_order": "uuid",
    "lab_order_item": "uuid",
    "patient": { ... },
    "doctor": { ... },
    "laboratorian": { ... },
    "status": "submitted",
    "value_type": "numeric",
    "numeric_value": "7.2",
    "unit": "mmol/L",
    "reference_range": "3.9-6.1",
    "flag": "high",
    "laboratorian_notes": "...",
    "doctor_notes": "",
    "submitted_at": "2026-05-08T...",
    "reviewed_at": null,
    "released_at": null,
    "corrected_at": null,
    "created_at": "2026-05-08T..."
  }
}
```

### Validation Errors

| Cause | Field | Message |
|---|---|---|
| Missing numeric_value for numeric | numeric_value | "This field is required for numeric results." |
| Missing text_value for text | text_value | "This field is required for text results." |
| Missing blood_group_value | blood_group_value | "This field is required for blood group results." |
| Missing file | result_file | "This field is required for file-only results." |
| Invalid positive/negative | text_value | "Value must be 'positive' or 'negative'." |
| Item not completed | — | 400 "Lab result can only be created for completed items." |
| Result already exists | — | 400 "A result already exists for this lab order item." |
| Unapproved user | — | 403 "Only approved laboratorians..." |

### Side Effects

- Result status: `submitted`
- Audit log: `lab_result_created`
- Notification: Doctor receives "Lab result submitted" notification
- Broadcast: Real-time event `lab_result_created` (Phase 14)

---

## Result Correction Contract

**Endpoint**: `POST /api/lab-orders/results/<lab_result_id>/correct/`

**Required role**: Laboratorian (original result author)

**Request**:
```json
{
  "reason": "Equipment calibration error",
  "numeric_value": "6.8"
}
```

Only the **laboratorian who originally submitted** can correct.

Can only correct while status is `submitted` or `corrected`.

Cannot correct after doctor releases (status = `released`).

### Fields Available for Correction

- `value_type`
- `text_value`
- `numeric_value`
- `blood_group_value`
- `unit`
- `reference_range`
- `flag`
- `laboratorian_notes`

File cannot be changed (result_file is immutable).

### Response

Returns updated full result with `status: "corrected"`.

### Side Effects

- Result status: `corrected`
- `LabResultCorrection` record created (audit trail with before/after snapshots)
- Audit log: `lab_result_corrected`
- Notification: Doctor receives "Lab result corrected" notification
- `corrected_at` timestamp set

---

## Doctor Review/Release Handoff

### Review

**Endpoint**: `POST /api/lab-orders/doctor/results/<lab_result_id>/review/`

**Required role**: Doctor (ordering doctor for this result)

**Request**:
```json
{
  "doctor_notes": "Values within expected range for this patient.",
  "release_to_patient": false
}
```

**Behavior**:
- Sets status: `reviewed`
- Sets `reviewed_at` timestamp
- Optionally stores `doctor_notes`
- If `release_to_patient: true`, immediately transitions to `released` state

### Release

**Endpoint**: `POST /api/lab-orders/doctor/results/<lab_result_id>/release/`

**Required role**: Doctor (ordering doctor)

**Request**: Empty or `{}`

**Behavior**:
- Sets status: `released`
- Sets `reviewed_at` (if not already set)
- Sets `released_at` timestamp
- Patient can now view result

### Link to Medical Record

**Endpoint**: `POST /api/lab-orders/doctor/results/<lab_result_id>/link-medical-record/`

**Required role**: Doctor (ordering doctor)

**Preconditions**:
- Result must be `reviewed` or `released`
- Cannot link twice

**Behavior**:
- For blood group results: Update patient's `BloodGroupRecord` as `laboratory_confirmed`
- For other results: Create `MedicalRecordEntry` as `laboratory_confirmed`
- Sets `is_linked_to_medical_record: true`
- Links foreign key to the created/updated record

**Error if**:
- Result status not reviewed/released: 400
- Already linked: 400
- Invalid blood group: 400

---

## Patient Visibility Contract

### Patient Lab Order List

**Endpoint**: `GET /api/lab-results/my/`

- Returns **only** `released` results
- Test item names, details hidden
- Doctor notes hidden
- Laboratorian notes hidden

### Patient Lab Result Detail

**Endpoint**: `GET /api/lab-results/my/<lab_result_id>/`

- Only accessible if:
  - Result status = `released`
  - Patient is the result's patient
- Returns `LabResultPatientSerializer`

### Patient Serializer Fields

| Field | Exposed | Notes |
|---|---|---|
| `id` | Yes | — |
| `lab_order` | Yes | UUID reference |
| `lab_order_item` | Yes | UUID reference |
| `test_label` | Yes | Test name from item |
| `status` | Yes | `released` only |
| `value_type` | Yes | numeric, text, blood_group, etc. |
| `text_value` | Yes | — |
| `numeric_value` | Yes | — |
| `blood_group_value` | Yes | — |
| `unit` | Yes | — |
| `reference_range` | Yes | — |
| `flag` | Yes | normal, high, low, abnormal, etc. |
| `result_file` | Yes | (if file-based result) |
| `released_at` | Yes | When doctor released |
| `created_at` | Yes | When created |
| `doctor_notes` | **No** | Hidden from patient |
| `laboratorian_notes` | **No** | Hidden from patient |
| `submitted_at` | **No** | Not needed by patient |
| `reviewed_at` | **No** | Not needed by patient |
| `corrected_at` | **No** | Not needed by patient |
| `corrections` | **No** | Edit history hidden |

---

## Privacy Rules

### General Principles

- **Patients see minimal information**: Value and clinical flags only
- **Doctors see full results**: All notes, flags, corrections
- **Laboratorians see lab-safe data**: Can view results they created
- **Unrelated users see nothing**: 404 Not Found

### Lab Order Privacy

| User Type | Can See Test Items | Can See Completion Records |
|---|---|---|
| Patient (owner) | No | No |
| Doctor (ordering) | Yes (full detail) | Yes |
| Laboratorian (any) | Yes (after scan) | No |
| Other doctor | No (404) | — |
| Other patient | No (404) | — |

### Lab Result Privacy

| User Type | Can See Notes | Can See Flag | Can See Value | Status Requirement |
|---|---|---|---|---|
| Patient (owner) | No (hidden) | Yes | Yes | `released` only |
| Doctor (ordering) | Yes (all) | Yes | Yes | Any status |
| Laboratorian (creator) | Yes (lab notes) | Yes | Yes | Any status |
| Laboratorian (other) | No (404) | — | — | — |
| Other doctor | No (404) | — | — | — |

---

## Notifications Side Effects

### Lab Order Created

- **Recipient**: Patient
- **Type**: `lab_order`
- **Title**: "Lab order issued"
- **Message**: "A lab order QR code has been issued for you."
- **Data**: lab_order_id, consultation_id, status

### Lab Order Item Completed

- **Recipient**: Doctor (ordering doctor)
- **Type**: `lab_order`
- **Title**: "Lab test completed"
- **Message**: "A requested lab test was marked as completed."
- **Data**: lab_order_id, lab_order_item_id

### Lab Order Item Unavailable

- **Recipient**: Doctor
- **Type**: `lab_order`
- **Title**: "Lab test unavailable"
- **Message**: "A laboratorian marked one requested test as unavailable."
- **Data**: lab_order_id, lab_order_item_id

### Lab Order Fully Completed

- **Recipient**: Patient
- **Type**: `lab_order`
- **Title**: "Lab order fully completed"
- **Message**: "Your lab order has been completed."
- **Data**: lab_order_id, status

### Lab Result Submitted

- **Recipient**: Doctor (ordering doctor)
- **Type**: `lab_order`
- **Title**: "Lab result submitted"
- **Message**: "A lab result has been submitted for your review."
- **Data**: lab_result_id, lab_order_id, lab_order_item_id

### Lab Result Corrected

- **Recipient**: Doctor (ordering doctor)
- **Type**: `lab_order`
- **Title**: "Lab result corrected"
- **Message**: "A submitted lab result has been corrected."
- **Data**: lab_result_id, lab_order_id, lab_order_item_id

### Lab Result Released

- **Recipient**: Patient (result patient)
- **Type**: `lab_order`
- **Title**: "Lab result released"
- **Message**: "A lab result has been released for you."
- **Data**: lab_result_id, lab_order_id, lab_order_item_id

---

## Known Backend Gaps

### No Known Gaps

✅ Lab user verification enforced at views
✅ Privacy rules enforced in serializers
✅ Status transitions atomic (transactions)
✅ All endpoints documented and tested
✅ File upload validation in place
✅ Audit logs created for all actions
✅ Notifications triggered correctly

---

## Frontend Implementation Recommendations

### Phase 6.0B — Laboratory Portal Frontend

#### 1. Laboratory Dashboard

**Page**: `/lab/dashboard`

- Quick stats: Pending orders, completed tests, submitted results
- Filter/search lab orders by status, patient, doctor
- Action: "Scan New Order" (QR scanner)

#### 2. Pending Lab Orders

**Page**: `/lab/orders/pending`

- List of lab orders assigned to this lab (not yet fully completed)
- Filter by status: `issued`, `partially_completed`
- Column: Order ID, Patient name, Doctor, Test count, Issue date, Expires

#### 3. Lab Order Detail

**Page**: `/lab/orders/<order_id>`

- Full order info: Doctor, Patient, Tests
- Items list with status: `pending`, `completed`, `cancelled`
- Completion records (who completed, when)
- Action: "Mark Items Complete" button
- Action: "View Results" if any submitted

#### 4. Scan QR Workflow

**Flow**:
1. Camera/QR input field on `/lab/scan`
2. Submit QR token to `POST /api/lab-orders/scan/`
3. Display lab order + remaining pending items
4. Allow marking items complete inline
5. POST `/api/lab-orders/<order_id>/complete/`
6. Show updated remaining items or "Order Complete" message

#### 5. Result Creation Form

**Page**: `/lab/results/create/<item_id>` or inline modal

- Form with dynamic fields based on `value_type`:
  - **Numeric**: numeric_value, unit, reference_range, flag dropdown
  - **Text**: text_value, unit, flag dropdown
  - **Blood Group**: dropdown (A+, A-, B+, B-, O+, O-, AB+, AB-)
  - **Positive/Negative**: radio (positive/negative)
  - **File**: file upload + flag dropdown
- Optional: `laboratorian_notes` text area
- Submit: `POST /api/lab-orders/items/<item_id>/results/`

#### 6. Result Correction

**Page**: `/lab/results/<result_id>/correct`

- Show original result values
- Allow editing individual fields
- Required: `reason` field (why correcting)
- Submit: `POST /api/lab-orders/results/<result_id>/correct/`
- Only show if:
  - Current user is original submitter
  - Status is `submitted` or `corrected`

#### 7. Result History

**Page**: `/lab/results/<result_id>`

- View current result
- Expandable section: "Edit History"
  - List all corrections with timestamps, reasons, changed fields
  - Show who made each correction

#### 8. Verification Status

**Pages**: All clinical actions

- If `verification_status != APPROVED`:
  - Show prominent badge: "Pending Verification"
  - Disable scan/complete/result buttons
  - Show message: "Your profile is under review. Please check back soon."
  - Link to `/profile/laboratorian` to check status

#### 9. Profile Completion

**Page**: `/profile/laboratorian`

- Display required fields and upload status
- Show verification status badge
- Link to document upload if incomplete
- Show estimated review time

#### 10. API Integration Checklist

- [ ] Implement QR scanner (use browser Camera API or qrcode.js)
- [ ] Form builder for dynamic result fields
- [ ] Validation: No clinical action without `verified_at`
- [ ] Debounce QR submission to prevent double-scans
- [ ] Optimistic updates for item completion
- [ ] Toast notifications for successful submissions
- [ ] Error handling with field-level error display
- [ ] Real-time updates (WebSocket Phase 14) for multi-user labs

#### 11. Security Considerations

- [ ] Never expose `doctor_notes` or `laboratorian_notes` to patients
- [ ] CSRF token for state-changing requests
- [ ] Validate result file type/size before upload
- [ ] Rate limit QR scan endpoint (already throttled on backend)
- [ ] Store QR tokens securely, don't log them

#### 12. UX Recommendations

- Wizard-style QR → Complete Items → Create Results flow
- Show "Items Remaining" count after each completion
- Warn if lab order is within 24 hours of expiry
- Batch item completion (multi-select before marking complete)
- Print friendly result labels for patient handoff

---

## Frontend Plan Summary

| Phase | Component | Est. Lines |
|---|---|---|
| 6.0B | Dashboard | 200 |
| 6.0B | Scan & Complete | 400 |
| 6.0B | Result Form | 600 |
| 6.0B | Result History | 250 |
| 6.0B | Profile Status | 150 |
| 6.0B | Validation/Error Handling | 300 |
| **Total** | **Lab Portal MVP** | **~1900** |

