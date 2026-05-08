# Doctor Workflow Contract

Phase: 5.0A (Backend audit only)
Repository: TechDaDev/RMP-backend
Base API prefix: `/api`

## 1. Overview

This document defines the backend contract for Doctor Portal workflows based on current backend implementation and runtime smoke validation.

Scope includes:
- Consultations (pending queue, assigned queue, detail, accept, response, close)
- Consultation messaging
- Prescription creation and doctor prescription management
- Lab order creation and doctor lab-result review/release workflow
- Doctor access to patient records
- Verification and privacy rules

Out of scope for this phase:
- Profile-completion gate before patient consultation creation (deferred)
- New RAG/WebSocket/AI triage features
- Frontend code changes

## 2. Doctor Role And Verification

| Item | Current backend contract |
|---|---|
| Doctor role identifier | `user_type = doctor` |
| Specialty source | `DoctorProfile.specialty` |
| Verification field | `DoctorProfile.verification_status` |
| Approved value | `approved` |
| Verification policy helper | `RoleAccessPolicy.is_verified_doctor` |

Clinical-action verification gates:

| Action | Requires approved doctor? | Enforcement point |
|---|---|---|
| List pending consultations | Yes | consultation pending view |
| List assigned consultations | Yes | consultation assigned view |
| Accept consultation | Yes | accept serializer |
| Create prescription | Yes | prescription create view/service |
| Create lab order | Yes | lab-order create view/service |
| View patient medical record | Yes (indirect) | clinical access policy requires verified doctor |

## 3. Consultation Lifecycle Mapping

### Status values

| Status | Meaning |
|---|---|
| `submitted` | Created by patient; not assigned |
| `accepted` | Assigned doctor accepted |
| `doctor_responded` | Doctor posted response |
| `closed` | Consultation closed by assigned doctor |
| `cancelled` | Enum exists, no doctor transition endpoint in consultation app |
| `rejected` | Enum exists, no doctor transition endpoint in consultation app |

### Implemented transitions

| Transition | Trigger endpoint/service |
|---|---|
| `submitted` <- create | `POST /api/consultations/` |
| `accepted` <- accept | `POST /api/consultations/{consultation_id}/accept/` |
| `doctor_responded` <- doctor response | `POST /api/consultations/{consultation_id}/responses/` |
| `closed` <- close | `POST /api/consultations/{consultation_id}/close/` |

## 4. Pending Consultations Contract

| Field | Contract |
|---|---|
| Method | `GET` |
| Path | `/api/consultations/doctor/pending/` |
| Role | Doctor |
| Verification | Must be approved |
| Status filter | Consultation must be `submitted` |
| Assignment filter | `assigned_doctor IS NULL` |
| Specialty filter | Exact match: `consultation.selected_specialty == doctor_profile.specialty` |
| Response | `success_response` with `ConsultationListSerializer[]` |

Notes:
- Matching is exact single-specialty matching.
- Multi-specialty doctors are not supported.
- `specialty_other` only applies via `specialty = other` exact match.

## 5. Assigned Consultations Contract

| Field | Contract |
|---|---|
| Method | `GET` |
| Path | `/api/consultations/doctor/assigned/` |
| Role | Doctor |
| Verification | Must be approved |
| Filter | `assigned_doctor = request.user` |
| Response | `success_response` with `ConsultationListSerializer[]` |

## 6. Accept Consultation Contract

| Field | Contract |
|---|---|
| Method | `POST` |
| Path | `/api/consultations/{consultation_id}/accept/` |
| Role | Doctor |
| Verification | Must be approved |
| Required state | Consultation status must be `submitted`, unassigned |
| Specialty requirement | Doctor specialty must match target specialty (or `other` with `other`) |
| Request payload | Empty object `{}` |
| Response | Success message envelope |
| Side effects | sets `assigned_doctor`, sets status `accepted`, sets `accepted_at`, creates audit log, creates patient notification |

## 7. Consultation Detail Contract

| Field | Contract |
|---|---|
| Method | `GET` |
| Path | `/api/consultations/{consultation_id}/` |
| Roles | Patient owner OR assigned doctor |
| Doctor visibility | Assigned doctor only |
| Serializer for patient | `ConsultationPatientDetailSerializer` |
| Serializer for doctor | `ConsultationDoctorDetailSerializer` |
| Response shape | `success_response({data: consultation_detail})` |
| Forbidden | 403 for unrelated users |

Privacy notes:
- Patient detail excludes doctor-only AI disease fields.
- Doctor detail includes doctor-only AI disease fields.

## 8. Messaging Contract

### Endpoints

| Method | Path | Role | Consultation status requirement |
|---|---|---|---|
| `GET` | `/api/consultations/{consultation_id}/messages/` | Patient owner or assigned doctor | `accepted`, `doctor_responded`, `closed` |
| `POST` | `/api/consultations/{consultation_id}/messages/` | Patient owner or assigned doctor | `accepted`, `doctor_responded` |
| `POST` | `/api/consultations/{consultation_id}/messages/mark-read/` | Patient owner or assigned doctor | Read-allowed statuses (`accepted`, `doctor_responded`, `closed`) |

### Request/response

| Action | Payload | Response |
|---|---|---|
| Send message | `{ "body": "..." }` or multipart with `attachments` | message object in success envelope |
| List messages | none | ordered by `created_at` ascending |
| Mark read | empty `{}` | `{ marked_count: <int> }` |

Notes:
- Send blocked in `submitted`, `cancelled`, `rejected`, `closed`.
- Attachments are supported for message create.
- Unassigned doctors cannot read or send.

## 9. Doctor Response Contract

| Field | Contract |
|---|---|
| Method | `POST` |
| Path | `/api/consultations/{consultation_id}/responses/` |
| Role | Assigned doctor |
| Status requirement | Consultation must be `accepted` or `doctor_responded` |
| Request payload | `{ "response_text": "...", "recommendation_type": "..." }` |
| Response | created response serializer in success envelope |
| Side effects | consultation status -> `doctor_responded`, audit log, patient notification |

## 10. Close Consultation Contract

| Field | Contract |
|---|---|
| Method | `POST` |
| Path | `/api/consultations/{consultation_id}/close/` |
| Role | Assigned doctor |
| Status requirement | `accepted` or `doctor_responded` |
| Request payload | `{}` |
| Response | success message envelope |
| Side effects | status -> `closed`, `closed_at` set, audit log, patient notification |

## 11. Prescription Contract

### Create

| Field | Contract |
|---|---|
| Method | `POST` |
| Path | `/api/consultations/{consultation_id}/prescriptions/` |
| Role | Assigned approved doctor |
| Consultation status requirement | `accepted` or `doctor_responded` |
| Request payload | `{ items: [ { medication_name, strength, dosage, frequency, duration, route, quantity, instructions } ] }` |
| Response | doctor-detail prescription shape in success envelope |

Prescription item payload rules:

| Field | Required | Notes |
|---|---|---|
| `medication_name` | Yes | string |
| `dosage` | Yes | string |
| `frequency` | Yes | string |
| `duration` | Yes | string |
| `route` | Yes | enum; must be one of allowed route values |
| `strength` | No | optional string |
| `quantity` | No | optional string |
| `instructions` | No | optional string |

Allowed route values:
`oral`, `topical`, `inhalation`, `injection`, `eye`, `ear`, `nasal`, `rectal`, `other`

Validation behavior:
- Missing `route` -> 400 field-level error under `errors.items[0].route`
- Invalid `route` -> 400 field-level choice error under `errors.items[0].route`
- Empty `items` -> 400 with `items` validation error

### Doctor detail and cancel

| Method | Path | Role | Rule |
|---|---|---|---|
| `GET` | `/api/prescriptions/doctor/{prescription_id}/` | Prescribing doctor | Full medication items + dispensing records visible |
| `POST` | `/api/prescriptions/doctor/{prescription_id}/cancel/` | Prescribing doctor | Fails if any item already dispensed |

Patient privacy contract:
- Patient list/detail endpoints exclude medication item details.

## 12. Lab Order Contract

### Create

| Field | Contract |
|---|---|
| Method | `POST` |
| Path | `/api/consultations/{consultation_id}/lab-orders/` |
| Role | Assigned approved doctor |
| Consultation status requirement | `accepted` or `doctor_responded` |
| Request payload | `{ items: [ { test OR (test_name+category), sample_type, instructions } ] }` |
| Response | doctor-detail lab-order shape in success envelope |

### Doctor detail and cancel

| Method | Path | Role | Rule |
|---|---|---|---|
| `GET` | `/api/lab-orders/doctor/{lab_order_id}/` | Ordering doctor | Full test items + completion records visible |
| `POST` | `/api/lab-orders/doctor/{lab_order_id}/cancel/` | Ordering doctor | Fails if any item completed |

Patient privacy contract:
- Patient lab-order list/detail excludes test item details.

## 13. Lab Result Review/Release Contract

| Method | Path | Role | Rule |
|---|---|---|---|
| `GET` | `/api/lab-orders/doctor/results/{lab_result_id}/` | Ordering doctor | Full result visibility |
| `POST` | `/api/lab-orders/doctor/results/{lab_result_id}/review/` | Ordering doctor | sets status reviewed (or released when `release_to_patient=true`) |
| `POST` | `/api/lab-orders/doctor/results/{lab_result_id}/release/` | Ordering doctor | sets status released |
| `POST` | `/api/lab-orders/doctor/results/{lab_result_id}/link-medical-record/` | Ordering doctor | allowed only when result is reviewed/released and not already linked |

Patient result visibility:
- Patient sees results only when status is `released`.
- Patient serializers exclude `laboratorian_notes` and `doctor_notes`.

## 14. Patient Record Access Contract

| Field | Contract |
|---|---|
| Method | `GET` |
| Path | `/api/patient-records/patients/{patient_id}/` |
| Role | Doctor |
| Verification | Must be approved doctor |
| Relationship requirement | Must have assigned consultation with patient in one of: `accepted`, `doctor_responded`, `closed` |
| Unauthorized response | 404 |

Related doctor actions:

| Method | Path | Rule |
|---|---|---|
| `POST` | `/api/patient-records/{record_id}/entries/` | Authorized doctor can create doctor-confirmed entry |
| `POST` | `/api/patient-records/entries/{entry_id}/confirm/` | Authorized doctor can confirm/reject entry |
| `POST` | `/api/patient-records/entries/{entry_id}/deactivate/` | Authorized doctor can deactivate entry |
| `POST` | `/api/patient-records/{record_id}/blood-group/` | Authorized doctor can set blood group as doctor_confirmed |

## 15. Notification Side Effects

Doctor workflow events that trigger patient notifications:

| Event | Notification type |
|---|---|
| consultation accepted | consultation |
| consultation response created | consultation |
| consultation closed | consultation |
| doctor message sent | message |
| prescription issued | prescription |
| lab order issued | lab_order |
| lab result released | lab_order |
| lab result linked to medical record | medical_record |

Additional provider notifications:
- Doctor gets notifications for pharmacist dispensing updates and laboratorian completion/result events.

## 16. Privacy Rules

| Rule | Enforcement |
|---|---|
| Consultation detail restricted to owner patient / assigned doctor | consultation detail permissions |
| Unassigned doctor denied consultation detail/messages | participant checks + assigned doctor checks |
| Patient prescription responses hide medication items | patient prescription serializers |
| Patient lab-order responses hide test item details | patient lab-order serializers |
| Patient lab-results visible only when released | lab-result patient queries/status filter |
| Patient record access for doctors is relationship-based | clinical access policy |

## 17. Known Backend Gaps

| Gap | Impact | Recommendation |
|---|---|---|
| No consultation reject endpoint implemented | Frontend cannot support explicit doctor reject action | Add explicit reject API with status transition + audit/notification |
| Accept flow has race window (validate then write without explicit row lock) | Two concurrent accepts may race | Add transactional select-for-update acceptance hardening |
| Pending queue is exact single-specialty match only | No multi-specialty coverage | Add multi-specialty doctor model/support if needed |
| `cancelled`/`rejected` statuses exist but no doctor workflow transitions in consultations module | Contract ambiguity | Either remove unused statuses or add documented transitions |

## 18. Frontend Implementation Recommendations

1. Build doctor dashboard using:
- pending: `GET /api/consultations/doctor/pending/`
- assigned: `GET /api/consultations/doctor/assigned/`

2. Use lifecycle flags directly from backend status values (`submitted`, `accepted`, `doctor_responded`, `closed`) with no client-side renaming.

3. Enable consultation messaging UI only when status in `{accepted, doctor_responded}` for send; allow read in `{accepted, doctor_responded, closed}`.

4. Hide reject button until backend reject endpoint exists.

5. Gate all clinical actions in UI by verification status from profile endpoint, but keep backend as source of truth for authorization failures.

6. For prescription and lab order creation, bind strictly to consultation-scoped create endpoints.

7. For patient records, request by patient id and expect 404 for unauthorized access (do not treat as server error).

8. Keep deferred requirement tracked: patient profile-completion gate before consultation creation will be enforced in a later backend phase.
