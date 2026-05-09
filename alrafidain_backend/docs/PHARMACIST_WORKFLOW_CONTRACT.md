# Pharmacist Workflow Contract

Phase 7.0A

---

## Table of Contents

1. [Overview](#overview)
2. [Pharmacist Role and Verification](#pharmacist-role-and-verification)
3. [Prescription Lifecycle](#prescription-lifecycle)
4. [Prescription Item Lifecycle](#prescription-item-lifecycle)
5. [Prescription QR Code Contract](#prescription-qr-code-contract)
6. [Pharmacist Prescription Scan Contract](#pharmacist-prescription-scan-contract)
7. [Dispensing Contract](#dispensing-contract)
8. [Dispensing History](#dispensing-history)
9. [Patient Visibility Contract](#patient-visibility-contract)
10. [Doctor Visibility Contract](#doctor-visibility-contract)
11. [Pharmacist Privacy Rules](#pharmacist-privacy-rules)
12. [Notifications and Audit](#notifications-and-audit)
13. [Known Backend Gaps](#known-backend-gaps)
14. [Frontend Implementation Recommendations](#frontend-implementation-recommendations)

---

## Overview

The Pharmacy Portal enables:

- **Doctors** to issue prescriptions for patients during consultations
- **Patients** to access prescriptions and present QR codes to pharmacies
- **Pharmacists** to scan prescription QR codes and dispense medications
- **Doctors** to track dispensing status and receive notifications
- **Patients** to view dispensed status (optional; not currently returned to patient)

All pharmacy workflows are transaction-backed and enforce role verification before performing clinical actions.

---

## Pharmacist Role and Verification

### User Type

Pharmacy personnel register as `user_type = "pharmacist"`.

### Profile Requirement

Each pharmacist must have a `PharmacistProfile` with:

| Field | Required | Verification | Purpose |
|---|---|---|---|
| `pharmacist_license_number` | Yes | User can provide | Professional credential |
| `pharmacist_license_image` | Yes | File upload | License verification |
| `pharmacy_name` | Yes | User can provide | Facility identification |
| `pharmacy_license_number` | Yes | User can provide | Pharmacy facility credential |
| `pharmacy_license_image` | Yes | File upload | Pharmacy license verification |
| `pharmacy_address` | Yes | User can provide | Facility location |
| `working_hours` | No | User can provide | Pharmacy operating hours |
| `verification_status` | Yes | Admin approval | `PENDING` \| `APPROVED` \| `REJECTED` \| `SUSPENDED` |

### Verification Enforcement

- **Approval required**: All pharmacist clinical endpoints (scan, dispense) require `verification_status = APPROVED`
- **Backend enforcement**: Views return `403 Forbidden` if not approved
- **Frontend gate**: Recommend showing "Pending Verification" message if `verification_status != APPROVED`

### Unverified Pharmacist Restrictions

Unverified pharmacists **cannot**:
- Scan prescription QR codes
- Dispense medications
- Mark items unavailable
- Access any clinical pharmacy endpoints

Expected behavior: Request profile completion and wait for admin approval.

---

## Prescription Lifecycle

### Status Values

| Status | Transition | Meaning |
|---|---|---|
| `issued` | Initial | Prescription created by doctor, awaiting pharmacist action |
| `partially_dispensed` | Auto-updated | Some items dispensed, some still pending |
| `fully_dispensed` | Auto-updated | All items dispensed or cancelled |
| `expired` | Auto-updated on scan | 7 days passed since creation |
| `cancelled` | Doctor action | Doctor cancelled before any dispensing |

### Status Transition Rules

```
[issued]
  ↓ (pharmacist scans QR, dispenses items)
[partially_dispensed]
  ↓ (remaining items marked dispensed)
[fully_dispensed]  ← locked (no more changes)

[issued]
  ↓ (7 days pass)
[expired]  ← locked (no more changes)

[issued]
  ↓ (doctor cancels before dispensing)
[cancelled]  ← locked (no more changes)
```

### Expiry

- Default expiry: **7 days** from prescription creation (configurable via `PRESCRIPTION_EXPIRY_DAYS`)
- Checked on: Pharmacist QR scan
- If expired: Status auto-updated to `expired`, prescription becomes locked
- Locked prescriptions cannot be modified by pharmacist

---

## Prescription Item Lifecycle

### Item Statuses

| Status | Meaning | Pharmacist Action |
|---|---|---|
| `pending` | Item not yet dispensed | Pharmacist can dispense or mark unavailable |
| `dispensed` | Item was dispensed | Item locked, no further action |
| `cancelled` | Item was cancelled (usually by doctor) | Item locked, cannot dispense |

### Item Dispensing Flow

```
[pending]
  ↓ (pharmacist marks dispensed)
[dispensed]  ← locked

[pending]
  ↓ (pharmacist marks unavailable)
[cancelled]  ← locked
```

### Item Dispensing Rules

- Only pending items can be dispensed
- Once dispensed or cancelled, item cannot change status
- Doctor cannot cancel items after dispensing has begun
- Pharmacist records reason in dispensing record (optional note field)

---

## Prescription QR Code Contract

### QR Code Generation

- Generated automatically when prescription is created
- Unique per prescription: `qr_token` field is unique in database
- Format: URL-safe string (base64-like), length ~43 characters
- Stored in plaintext in Prescription model (not hashed)
- Never expires (expiry is on prescription itself, not QR code)

### QR Code Delivery

- Patient receives QR code in prescription detail response
- Patient presents QR code to pharmacist (physical print or screen)
- Pharmacist scans using device camera or manual text input

### QR Code Reusability

- Reusable: Pharmacist can scan same QR multiple times
- Each scan creates audit log entry
- Multiple pharmacies can scan same QR (no pharmacy binding)
- Expired/locked prescriptions still have scannable QR but return locked status

### QR Token Exposure

⚠️ **Security note**: QR tokens are returned in patient prescription list/detail. Treat them as patient data. Do not log or expose publicly.

---

## Pharmacist Prescription Scan Contract

**Endpoint**: `POST /api/prescriptions/scan/`

**Required role**: Pharmacist (approved)

**Request**:
```json
{
  "qr_token": "<string from patient>"
}
```

**Response** (success):
```json
{
  "success": true,
  "data": {
    "prescription": {
      "id": "uuid",
      "status": "issued",
      "doctor": { "id", "email", "full_name" },
      "issued_at": "2026-05-09T...",
      "expires_at": "2026-05-16T..."
    },
    "remaining_items": [
      {
        "id": "uuid",
        "medication_name": "Amoxicillin",
        "strength": "500mg",
        "dosage": "1 capsule",
        "frequency": "3x daily",
        "duration": "7 days",
        "route": "oral",
        "quantity": "21 capsules",
        "instructions": "After meals"
      }
    ],
    "locked": false,
    "message": null
  },
  "message": "QR scanned."
}
```

**Response** (locked prescription):
```json
{
  "success": true,
  "data": {
    "prescription": { ... },
    "remaining_items": [],
    "locked": true,
    "message": "This prescription is no longer available for dispensing."
  },
  "message": "QR scanned."
}
```

### Error Cases

| Case | Status | Cause |
|---|---|---|
| Invalid QR token | 400 | Token not found or invalid |
| Expired prescription | 200 | Prescription auto-marked expired, returns locked |
| Unapproved pharmacist | 403 | Pharmacist verification_status != APPROVED |
| Not authenticated | 401 | Missing/invalid bearer token |
| Rate limited | 429 | Too many QR scans (QRScanRateThrottle) |

### Side Effects

- Audit log: `prescription_qr_scanned` recorded
- Expiry check: If prescription is past expiry, auto-update status to `expired`

---

## Dispensing Contract

**Endpoint**: `POST /api/prescriptions/<prescription_id>/dispense/`

**Required role**: Pharmacist (approved)

**Request**:
```json
{
  "items": [
    {
      "prescription_item_id": "uuid",
      "status": "dispensed",
      "dispensed_quantity": "21 capsules",
      "note": "Dispensed as written"
    },
    {
      "prescription_item_id": "uuid",
      "status": "unavailable",
      "dispensed_quantity": "",
      "note": "Out of stock"
    }
  ]
}
```

### Item Dispensing Status Values

- `dispensed` — Medication was dispensed to patient
- `unavailable` — Medication could not be dispensed (out of stock, discontinued, contraindicated)

### Required and Optional Fields

| Field | Required | Type | Example |
|---|---|---|---|
| `prescription_item_id` | Yes | UUID | — |
| `status` | Yes | Enum | `"dispensed"` or `"unavailable"` |
| `dispensed_quantity` | No | String | `"21 capsules"` or `"empty if unavailable"` |
| `note` | No | String | `"Dispensed with generic equivalent"` |

### Response

```json
{
  "success": true,
  "data": {
    "prescription": {
      "id": "uuid",
      "status": "partially_dispensed",
      "doctor": { ... },
      "issued_at": "...",
      "expires_at": "..."
    },
    "remaining_items": [
      {
        "id": "uuid",
        "medication_name": "...",
        "status": "pending"
      }
    ],
    "locked": false,
    "message": null
  },
  "message": "Items processed."
}
```

### Item Dispensing Rules

- Only `pending` items can be dispensed
- Cannot dispense already-dispensed or cancelled items
- If item status is `dispensed`:
  - Item.status updated to `dispensed`
  - Item.dispensed_at timestamp set
  - DispensingRecord created with status `"dispensed"`
- If item status is `unavailable`:
  - Item.status updated to `cancelled`
  - Item.cancelled_at timestamp set
  - DispensingRecord created with status `"unavailable"`
- Prescription status auto-updated based on remaining items

### Prescription Status Auto-Update

After dispense action, prescription status is recalculated:

| Condition | New Status |
|---|---|
| All items dispensed or cancelled | `fully_dispensed` |
| Some items dispensed, some pending | `partially_dispensed` |
| No items dispensed yet | `issued` |
| All items cancelled (none dispensed) | `cancelled` |

### Validation Errors

| Case | Status | Reason |
|---|---|---|
| Item not in this prescription | 400 | Item ID doesn't belong to prescription |
| Prescription is locked | 400 | Cannot dispense locked prescriptions |
| Prescription is expired | 400 (auto-updates to expired) | Expired prescriptions cannot be dispensed |
| Item not pending | 400 | Cannot dispense already-dispensed or cancelled items |
| Unapproved pharmacist | 403 | Pharmacist verification_status != APPROVED |
| At least one item required | 400 | Empty items array not allowed |

### Side Effects

- DispensingRecord created for each item with:
  - Pharmacist ID
  - Dispensing status (`dispensed` or `unavailable`)
  - Optional dispensed_quantity
  - Optional note
  - Timestamp (created_at)
- Audit logs created:
  - `prescription_item_dispensed` if status=dispensed
  - `prescription_item_unavailable` if status=unavailable
  - `prescription_fully_dispensed` if prescription status transitions to fully_dispensed
- Notifications sent to doctor:
  - "Medication item dispensed" if status=dispensed
  - "Medication unavailable" if status=unavailable

---

## Dispensing History

### Pharmacist Dispensing History Endpoint

**Endpoint**: `GET /api/prescriptions/pharmacist/history/`

- **Auth required**: Yes (JWT)
- **Role required**: Pharmacist
- **Approval required**: `verification_status = APPROVED`
- **Scope**: Only dispensing records where `pharmacist_id == request.user.id`
- **Ordering**: Newest first (`-created_at`)
- **Pagination**: Limit/offset (`?limit=...&offset=...`)

**Response shape**:
```json
{
  "success": true,
  "message": "Dispensing history retrieved.",
  "data": {
    "count": 10,
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

**Forbidden fields**:

- `qr_token`
- dispensing internal `note`
- doctor private notes
- patient private profile fields (phone, address, national ID, etc.)
- records from other pharmacists

### Doctor Dispensing Records View

Doctor can see dispensing records in prescription detail response via `dispensing_records` array:

```json
{
  "dispensing_records": [
    {
      "id": "uuid",
      "prescription_item_id": "uuid",
      "pharmacist": { "id", "email", "full_name" },
      "status": "dispensed",
      "dispensed_quantity": "21 capsules",
      "note": "Dispensed with generic equivalent",
      "created_at": "2026-05-09T12:30:00Z"
    }
  ]
}
```

### Patient Dispensing Visibility

Patients **cannot** currently see dispensing records. Prescription detail for patients returns only:
- Prescription ID, status, qr_token, issued_at, expires_at, fully_dispensed_at
- Doctor info
- **No items**
- **No dispensing records**

This is by design for Phase 7.0A. Phase 7.0B frontend may add optional visibility if desired.

---

## Patient Visibility Contract

### Patient Prescription List

**Endpoint**: `GET /api/prescriptions/my/`

- Returns **only prescriptions** created for this patient
- Returns **only metadata** (no items, no dispensing records)
- Returns `qr_token` for patient to present to pharmacist

**Response fields** (patient-safe):
```json
{
  "id": "uuid",
  "consultation_id": "uuid",
  "doctor": { "id", "email", "full_name" },
  "status": "issued|partially_dispensed|fully_dispensed|expired|cancelled",
  "qr_token": "...",
  "issued_at": "2026-05-09T...",
  "expires_at": "2026-05-16T...",
  "fully_dispensed_at": "2026-05-09T... or null"
}
```

### Patient Prescription Detail

**Endpoint**: `GET /api/prescriptions/my/<prescription_id>/`

- Only patient who is prescription recipient can view
- Same fields as list response
- **Does NOT include** medication item details
- **Does NOT include** dispensing records
- **Does NOT include** doctor notes (none currently exist)

### Patient Privacy

Patients see minimal information by design:
- Prescription status (so patient can track)
- When issued and when expires
- Doctor info (basic)
- **NOT** medication details (items are dispensary-side information)
- **NOT** dispensing records (internal pharmacy workflow)

---

## Doctor Visibility Contract

### Doctor Prescription Creation

**Endpoint**: `POST /api/consultations/<consultation_id>/prescriptions/`

Doctor can create prescriptions only for assigned patients in accepted/doctor_responded consultations.

### Doctor Prescription Detail

**Endpoint**: `GET /api/prescriptions/doctor/<prescription_id>/`

Doctor who issued prescription can see full details:

**Response fields**:
```json
{
  "id": "uuid",
  "consultation_id": "uuid",
  "patient": { "id", "email", "full_name" },
  "doctor": { "id", "email", "full_name" },
  "status": "issued|partially_dispensed|fully_dispensed|expired|cancelled",
  "qr_token": "...",
  "issued_at": "2026-05-09T...",
  "expires_at": "2026-05-16T...",
  "cancelled_at": "... or null",
  "fully_dispensed_at": "... or null",
  "items": [
    {
      "id": "uuid",
      "medication_name": "Amoxicillin",
      "strength": "500mg",
      "dosage": "1 capsule",
      "frequency": "3x daily",
      "duration": "7 days",
      "route": "oral",
      "quantity": "21 capsules",
      "instructions": "After meals",
      "status": "pending|dispensed|cancelled",
      "dispensed_at": "... or null",
      "cancelled_at": "... or null",
      "created_at": "..."
    }
  ],
  "dispensing_records": [
    {
      "id": "uuid",
      "prescription_item_id": "uuid",
      "pharmacist": { "id", "email", "full_name" },
      "status": "dispensed|unavailable",
      "dispensed_quantity": "21 capsules or empty",
      "note": "Optional pharmacist note",
      "created_at": "2026-05-09T..."
    }
  ]
}
```

### Doctor Prescription Cancellation

**Endpoint**: `POST /api/prescriptions/doctor/<prescription_id>/cancel/`

Doctor can cancel prescription only if:
- No items have been dispensed yet
- Prescription is not already cancelled/expired/fully_dispensed

When cancelled:
- Prescription status → `cancelled`
- All pending items → `cancelled` with cancelled_at timestamp
- Already-dispensed items remain dispensed (cannot uncancell)

---

## Pharmacist Privacy Rules

### What Pharmacist Can See

| Data | Visible | Method |
|---|---|---|
| Prescription status | Yes | After QR scan |
| Patient name (context) | No (not returned in scan) | Privacy by omission |
| Doctor info | Yes (basic) | Doctor ID, name, email in scan response |
| Medication items | Yes (pending only) | Only remaining_items in scan response |
| Already-dispensed items | No | Filtered out of remaining_items |
| Doctor notes | No | Not created yet in backend |
| Patient profile | No | No patient data in scan response |

### What Pharmacist Cannot See

- Patient full profile information
- Patient medical history (separate system)
- Doctor's clinical notes
- Other patient's prescriptions

---

## Notifications and Audit

### Prescription Created Notification

- **Recipient**: Patient
- **Type**: `PRESCRIPTION`
- **Title**: "Prescription issued"
- **Message**: "Your doctor has issued a prescription for your consultation."
- **Data**: prescription_id, consultation_id, status

### Prescription Scanned Audit

- **Action**: `prescription_qr_scanned`
- **Actor**: Pharmacist
- **Target**: Prescription
- **Metadata**: prescription_id, consultation_id, patient_id, doctor_id, pharmacist_id, status

### Item Dispensed Notification

- **Recipient**: Doctor (prescriber)
- **Type**: `DISPENSING`
- **Title**: "Medication item dispensed"
- **Message**: "A medication item in your prescription has been dispensed."
- **Data**: prescription_id, item_id

### Item Unavailable Notification

- **Recipient**: Doctor (prescriber)
- **Type**: `DISPENSING`
- **Title**: "Medication unavailable"
- **Message**: "A medication item in your prescription is unavailable."
- **Data**: prescription_id, item_id

### Item Dispensed Audit

- **Action**: `prescription_item_dispensed`
- **Actor**: Pharmacist
- **Target**: DispensingRecord
- **Metadata**: prescription_id, consultation_id, patient_id, doctor_id, pharmacist_id, item_id, status

### Item Unavailable Audit

- **Action**: `prescription_item_unavailable`
- **Actor**: Pharmacist
- **Target**: DispensingRecord
- **Metadata**: prescription_id, consultation_id, patient_id, doctor_id, pharmacist_id, item_id, status

### Prescription Fully Dispensed Audit

- **Action**: `prescription_fully_dispensed`
- **Actor**: Pharmacist (whoever dispensed last item)
- **Target**: Prescription
- **Metadata**: prescription_id, consultation_id, patient_id, doctor_id

### Prescription Cancelled Audit

- **Action**: `prescription_cancelled`
- **Actor**: Doctor
- **Target**: Prescription
- **Metadata**: prescription_id, consultation_id, patient_id, doctor_id

---

## Known Backend Gaps

### Resolved in Phase 7.4A

✅ Added `GET /api/prescriptions/pharmacist/history/` for pharmacist-scoped dispensing history
✅ Pharmacist history now supports pagination with the standard response envelope
✅ History excludes QR token and internal dispensing notes
✅ Role and approval gates match scan/dispense clinical endpoints

### Minor Enhancement Opportunities (Not Phase 7.0A)

1. **Partial dispensing with quantity tracking**: Currently dispensed_quantity is free text. Could be structured (quantity + unit) for better UX.
2. **Prescription suspension/hold**: Currently only issued/expired/cancelled/dispensed. Could add hold status for insurance pre-approval.
3. **Pharmacist substitution notes**: Could store which generic/alternative was dispensed instead of original.
4. **Patient notification on partial dispensing**: Currently patient doesn't see dispensing status. Phase 7.0B could add visibility.

---

## Frontend Implementation Recommendations

### Phase 7.0B — Pharmacist Portal Frontend

**Estimated scope**: ~2500 lines of UI code

#### 1. Pharmacist Dashboard

**Page**: `/pharmacist/dashboard`

- Quick stats: Pending prescriptions, items dispensed today, unavailable items
- Recent activity: Dispensed prescriptions, partially dispensed orders
- Verification status badge

#### 2. Prescription QR Scanner

**Page**: `/pharmacist/scan`

- Camera/QR input field for scanning
- Manual text input fallback for QR code
- Submit QR token to `POST /api/prescriptions/scan/`
- Display prescription metadata + remaining items
- Show locked status with message if prescription expired/cancelled

#### 3. Prescription Detail View

**Page**: `/pharmacist/prescriptions/<prescription_id>`

- Prescription info: Patient context, doctor, issued/expires dates
- Items list with current status (pending, dispensed, cancelled, unavailable)
- Dispensing records (if any) showing history with pharmacist name, quantity, notes
- Doctor info (optional expansion)

#### 4. Dispensing Workflow

**Flow**: QR Scan → View Pending Items → Mark Dispensed/Unavailable

1. Scan QR → See remaining_items list
2. For each item:
   - Mark `dispensed` with quantity
   - Mark `unavailable` with reason (optional note)
3. Submit to `POST /api/prescriptions/<id>/dispense/`
4. Receive updated prescription status
5. Show result: "Items processed" with new status (issued/partially_dispensed/fully_dispensed)

**UI pattern**: Inline item cards with toggle (dispensed/unavailable) and optional text fields (quantity, note)

#### 5. Dispensing History

**Page**: `/pharmacist/prescriptions/<prescription_id>/history`

- List of dispensing records by date descending
- For each record: Medication (from item), status, quantity, note, timestamp
- Shows which pharmacist dispensed (if multiple at same location)

#### 6. Verification Status Gate

**Pages**: All clinical actions

- If `verification_status != APPROVED`:
  - Show prominent badge: "Pending Verification"
  - Disable scan/dispense buttons
  - Show message: "Your profile is under review. Please check back soon."
  - Link to `/profile/pharmacist` to check status and upload docs

#### 7. Profile Completion

**Page**: `/profile/pharmacist`

- Display required fields and upload status
- Show verification status badge
- Link to document upload if incomplete
- Show estimated review time

#### 8. API Integration Checklist

- [ ] Implement QR scanner (use browser Camera API or qr-scanner.js)
- [ ] Form builder for dispensing items (toggle + optional text)
- [ ] Validation: No clinical action without `approved` verification
- [ ] Debounce QR submission to prevent double-scans
- [ ] Optimistic updates for item dispensing
- [ ] Toast notifications for successful submissions
- [ ] Error handling with field-level error display
- [ ] Real-time updates (WebSocket Phase 14) for multi-user pharmacies
- [ ] Offline queue for QR scans (optional, nice-to-have)

#### 9. Security Considerations

- [ ] CSRF token for state-changing requests
- [ ] Do not log QR tokens or prescription details
- [ ] Rate limit awareness: QRScanRateThrottle active (429 responses)
- [ ] Input validation: prescription_item_id must be UUID
- [ ] Item quantity must match dispense amount (optional business rule)

#### 10. UX Recommendations

- Wizard-style QR → Items → Confirm → Success flow
- Show "Items Remaining" count after each action
- Warn if prescription within 48 hours of expiry
- Batch item dispensing (multi-select before marking all as dispensed)
- Print dispensing receipt for patient handoff
- Search/filter prescriptions by patient name, date, status

---

## Frontend Plan Summary

| Component | Est. Lines | Priority |
|---|---|---|
| Dashboard | 300 | P1 |
| QR Scanner | 400 | P1 |
| Dispensing Form | 500 | P1 |
| Detail View | 350 | P2 |
| History View | 250 | P2 |
| Profile Status | 150 | P2 |
| Validation/Error | 300 | P1 |
| **Subtotal** | **2,250** | — |

---

## Notes for Phase 7.0B

1. **QR Scanning**: Use `qr-scanner.js` or native Camera API. Test with patient-printed QR codes.
2. **Offline support**: Consider local queue for scans (sync when online). Optional but useful for pharmacies with spotty connectivity.
3. **Bulk dispensing**: Allow batch-selecting multiple items and marking all dispensed at once.
4. **Dispensing history export**: Nice-to-have for pharmacist audit trail.
5. **Notification integration**: Listen for real-time prescription status updates (Phase 14 WebSocket when available).

---

