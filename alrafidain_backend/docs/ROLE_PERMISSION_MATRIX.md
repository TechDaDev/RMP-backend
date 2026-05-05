# Role Permission Matrix

_Phase 13 — API Contract Freeze — Al-Rafidain Medical Platform_

---

## Table of Contents

- [Role Definitions](#role-definitions)
- [Accounts](#accounts)
- [Profiles](#profiles)
- [Consultations](#consultations)
- [Messaging](#messaging)
- [Prescriptions](#prescriptions)
- [Lab Orders](#lab-orders)
- [Lab Results](#lab-results)
- [Patient Records](#patient-records)
- [Notifications](#notifications)
- [Knowledge Base](#knowledge-base)
- [RAG (Doctor AI Queries)](#rag-doctor-ai-queries)
- [RAG Feedback](#rag-feedback)
- [RAG Analytics & Export](#rag-analytics--export)
- [Summary: What Each Role Cannot Do](#summary-what-each-role-cannot-do)

---

## Role Definitions

| Role | Description |
|---|---|
| `anon` | Unauthenticated request |
| `patient` | Active patient account |
| `doctor-pending` | Doctor with `verification_status = PENDING` |
| `doctor-approved` | Doctor with `verification_status = APPROVED` |
| `pharmacist-pending` | Pharmacist with `verification_status = PENDING` |
| `pharmacist-approved` | Pharmacist with `verification_status = APPROVED` |
| `laboratorian-pending` | Laboratorian with `verification_status = PENDING` |
| `laboratorian-approved` | Laboratorian with `verification_status = APPROVED` |
| `staff/admin` | `is_staff=True` or `is_superuser=True` |

Legend: ✅ Allowed | ❌ Denied | ⚠️ Partial (see notes)

---

## Accounts

| Action | anon | patient | doctor (any) | pharmacist (any) | laboratorian (any) | staff/admin |
|---|---|---|---|---|---|---|
| Register | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Activate account | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Login | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| View own user (`/me/`) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Password reset | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Profiles

| Action | patient | doctor | pharmacist | laboratorian | staff/admin |
|---|---|---|---|---|---|
| View own profile | ✅ | ✅ | ✅ | ✅ | ✅ |
| Update user profile | ✅ | ✅ | ✅ | ✅ | ✅ |
| Update patient profile | ✅ | ❌ | ❌ | ❌ | ❌ |
| Update doctor profile | ❌ | ✅ | ❌ | ❌ | ❌ |
| Update pharmacist profile | ❌ | ❌ | ✅ | ❌ | ❌ |
| Update laboratorian profile | ❌ | ❌ | ❌ | ✅ | ❌ |

---

## Consultations

| Action | patient | doctor-pending | doctor-approved | pharmacist | laboratorian | staff/admin |
|---|---|---|---|---|---|---|
| Create consultation | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| List own consultations | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| View consultation detail | ✅ (own) | ❌ | ✅ (assigned) | ❌ | ❌ | ❌ |
| List pending (matching specialty) | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| List assigned consultations | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Accept consultation | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Close consultation | ❌ | ❌ | ✅ (assigned) | ❌ | ❌ | ❌ |
| Add consultation response | ❌ | ❌ | ✅ (assigned) | ❌ | ❌ | ❌ |
| List symptom categories | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| List symptoms | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## Messaging

| Action | patient | doctor-approved | pharmacist | laboratorian | staff/admin |
|---|---|---|---|---|---|
| List/send messages | ✅ (own consultation) | ✅ (assigned consultation) | ❌ | ❌ | ❌ |
| Mark messages read | ✅ (own) | ✅ (own) | ❌ | ❌ | ❌ |

---

## Prescriptions

| Action | patient | doctor-pending | doctor-approved | pharmacist-pending | pharmacist-approved | laboratorian | staff/admin |
|---|---|---|---|---|---|---|---|
| Create prescription | ❌ | ❌ | ✅ (assigned) | ❌ | ❌ | ❌ | ❌ |
| List own prescriptions | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| View own prescription (no items) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| View prescription (full, with items) | ❌ | ❌ | ✅ (creator) | ❌ | ❌ | ❌ | ❌ |
| Cancel prescription | ❌ | ❌ | ✅ (creator) | ❌ | ❌ | ❌ | ❌ |
| Scan QR → pending items | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Dispense items | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |

> **Privacy rule**: Patients never receive prescription medication items in any serializer response. The QR code (`prescription_qr_token`) is included in the patient prescription detail.

---

## Lab Orders

| Action | patient | doctor-pending | doctor-approved | pharmacist | laboratorian-pending | laboratorian-approved | staff/admin |
|---|---|---|---|---|---|---|---|
| Create lab order | ❌ | ❌ | ✅ (assigned) | ❌ | ❌ | ❌ | ❌ |
| List test catalog | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ |
| List own orders (no items) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| View own order (no items) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| View order (full, with items) | ❌ | ❌ | ✅ (creator) | ❌ | ❌ | ❌ | ❌ |
| Cancel order | ❌ | ❌ | ✅ (creator) | ❌ | ❌ | ❌ | ❌ |
| Scan QR → pending items | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Complete items | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |

> **Privacy rule**: Patients never receive lab order test items in any serializer response.

---

## Lab Results

| Action | patient | doctor-approved | laboratorian-approved | staff/admin |
|---|---|---|---|---|
| Create result | ❌ | ❌ | ✅ (assigned to order) | ❌ |
| View result (full) | ❌ | ✅ (assigned doctor) | ✅ (creator) | ❌ |
| Correct result | ❌ | ❌ | ✅ (creator, before review) | ❌ |
| Review result | ❌ | ✅ (assigned) | ❌ | ❌ |
| Release to patient | ❌ | ✅ (assigned) | ❌ | ❌ |
| Link to medical record | ❌ | ✅ (assigned) | ❌ | ❌ |
| View own released results | ✅ (released only) | ❌ | ❌ | ❌ |

> **Privacy rule**: Patients only see results with `released_to_patient=True`. `laboratorian_notes` and `doctor_notes` are never included in patient-facing serializers.

---

## Patient Records

| Action | patient | doctor-approved | laboratorian-approved | pharmacist | staff/admin |
|---|---|---|---|---|---|
| View own record | ✅ | ❌ | ❌ | ❌ | ❌ |
| Add entry | ❌ | ✅ (active consultation) | ❌ | ❌ | ❌ |
| Confirm/deactivate entry | ❌ | ✅ (creator) | ❌ | ❌ | ❌ |
| View patient record | ❌ | ✅ (active consultation) | ❌ | ❌ | ❌ |
| Set blood group | ❌ | ❌ | ✅ | ❌ | ❌ |
| Verify blood group | ❌ | ❌ | ✅ | ❌ | ❌ |

> **Privacy rule**: Doctors can only view a patient's medical record when there is an active accepted consultation between them.

---

## Notifications

| Action | patient | doctor | pharmacist | laboratorian | staff/admin |
|---|---|---|---|---|---|
| List own notifications | ✅ | ✅ | ✅ | ✅ | ✅ |
| View unread count | ✅ | ✅ | ✅ | ✅ | ✅ |
| Mark read | ✅ (own) | ✅ (own) | ✅ (own) | ✅ (own) | ✅ |
| Mark all read | ✅ | ✅ | ✅ | ✅ | ✅ |

> All notification endpoints are self-service only. Users cannot read other users' notifications.

---

## Knowledge Base

| Action | patient | doctor | pharmacist | laboratorian | staff/admin |
|---|---|---|---|---|---|
| Upload document | ❌ | ❌ | ❌ | ❌ | ✅ |
| View document | ❌ | ❌ | ❌ | ❌ | ✅ |
| Process document | ❌ | ❌ | ❌ | ❌ | ✅ |
| Approve/reject document | ❌ | ❌ | ❌ | ❌ | ✅ |
| Archive document | ❌ | ❌ | ❌ | ❌ | ✅ |
| Embed document | ❌ | ❌ | ❌ | ❌ | ✅ |
| List chunks | ❌ | ❌ | ❌ | ❌ | ✅ |
| Text search | ❌ | ❌ | ❌ | ❌ | ✅ |
| Semantic search | ❌ | ❌ | ❌ | ❌ | ✅ |

---

## RAG (Doctor AI Queries)

| Action | patient | doctor-pending | doctor-approved | pharmacist | laboratorian | staff/admin |
|---|---|---|---|---|---|---|
| General RAG query | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Consultation RAG support | ❌ | ❌ | ✅ (assigned) | ❌ | ❌ | ❌ |
| Lab result RAG support | ❌ | ❌ | ✅ (assigned) | ❌ | ❌ | ❌ |

> **Privacy rule**: Patients cannot use any RAG endpoint. RAG is exclusively for approved doctors.

---

## RAG Feedback

| Action | patient | doctor-pending | doctor-approved | pharmacist | laboratorian | staff/admin |
|---|---|---|---|---|---|---|
| Submit response feedback | ❌ | ❌ | ✅ (own responses) | ❌ | ❌ | ❌ |
| List own feedback | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |

---

## RAG Analytics & Export

| Action | patient | doctor | pharmacist | laboratorian | staff/admin |
|---|---|---|---|---|---|
| View analytics summary | ❌ | ❌ | ❌ | ❌ | ✅ |
| List all feedback (admin) | ❌ | ❌ | ❌ | ❌ | ✅ |
| Review feedback | ❌ | ❌ | ❌ | ❌ | ✅ |
| Export dataset | ❌ | ❌ | ❌ | ❌ | ✅ |

> **Privacy rule**: Dataset exports use SHA-256 anonymization of doctor IDs by default. Raw embeddings are never exported. `query_text` and `response_text` are excluded unless explicitly enabled by staff.

---

## Summary: What Each Role Cannot Do

### Patient
- Cannot view prescription medication items
- Cannot view lab order test items
- Cannot view unreleased lab results
- Cannot view `laboratorian_notes` or `doctor_notes`
- Cannot access RAG endpoints
- Cannot view other patients' data
- Cannot access knowledge base

### Doctor (Pending)
- Cannot create prescriptions, lab orders, RAG queries, or consult records
- Can only update own profile

### Doctor (Approved)
- Cannot view patients' data outside an active consultation
- Cannot access knowledge base
- Cannot access RAG admin/analytics endpoints

### Pharmacist
- Can only scan a specific prescription QR and see pending items
- Cannot view full prescription details outside QR scan
- Cannot view lab orders, lab results, or medical records
- Cannot access RAG

### Laboratorian
- Can only scan a specific lab order QR and see pending items
- Cannot view prescriptions, messages, or full medical records
- Cannot access RAG

### Staff/Admin
- Has full access to knowledge base and RAG analytics
- Does not have a dedicated patient/doctor workflow role
- Access to Django admin panel
