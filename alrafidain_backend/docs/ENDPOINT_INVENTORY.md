# Endpoint Inventory

_Phase 13 — API Contract Freeze — Al-Rafidain Medical Platform_

Generated from: `python manage.py show_urls --settings=config.settings.test`

Legend:
- **Auth required**: JWT Bearer token (`Authorization: Bearer <access_token>`)
- **Status**: `stable` | `internal` | `admin-only`
- **Roles**: `anon` | `patient` | `doctor` | `pharmacist` | `laboratorian` | `staff/admin`

---

## Table of Contents

- [Health / Schema / Docs](#health--schema--docs)
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
- [RAG — Doctor AI Queries](#rag--doctor-ai-queries)
- [RAG Feedback](#rag-feedback)
- [RAG Admin — Feedback Review](#rag-admin--feedback-review)
- [RAG Admin — Analytics & Export](#rag-admin--analytics--export)
- [Total API Endpoint Count](#total-api-endpoint-count)

---

## Health / Schema / Docs

| Method | Path | View | Auth | Roles | Status | Notes |
|---|---|---|---|---|---|---|
| GET | `/api/health/` | `apps.common.health.health_live` | No | All | stable | Compatibility alias for liveness probe |
| GET | `/api/health/live/` | `apps.common.health.health_live` | No | All | stable | Liveness probe; no dependency checks |
| GET | `/api/health/ready/` | `apps.common.health.health_ready` | No | All | stable | Readiness probe; validates database connectivity |
| GET | `/api/health/deps/` | `apps.common.health.health_deps` | No | All | stable | Dependency component statuses (database/redis/storage) |
| GET | `/api/schema/` | `SpectacularAPIView` | No | All | internal | Raw OpenAPI YAML schema download |
| GET | `/api/docs/` | `SpectacularSwaggerView` | No | All | internal | Swagger UI |

---

## Accounts

| Method | Path | View | Auth | Roles | Serializer | Privacy | Status |
|---|---|---|---|---|---|---|---|
| POST | `/api/accounts/register/` | `RegisterView` | No | anon | `RegisterSerializer` | Password never returned | stable |
| POST | `/api/accounts/activate/` | `ActivateAccountView` | No | anon | `ActivateAccountSerializer` | — | stable |
| POST | `/api/accounts/resend-activation-otp/` | `ResendActivationOTPView` | No | anon | — | Generic message (no enumeration) | stable |
| POST | `/api/accounts/login/` | `LoginView` | No | anon | `LoginSerializer` | Returns access + refresh tokens | stable |
| GET | `/api/accounts/me/` | `MeView` | Yes | authenticated | `MeSerializer` | No password field | stable |
| POST | `/api/accounts/password-reset/request/` | `RequestPasswordResetView` | No | anon | — | Generic message (no enumeration) | stable |
| POST | `/api/accounts/password-reset/confirm/` | `ConfirmPasswordResetView` | No | anon | `ConfirmPasswordResetSerializer` | — | stable |

---

## Profiles

| Method | Path | View | Auth | Roles | Serializer | Privacy | Status |
|---|---|---|---|---|---|---|---|
| GET | `/api/profiles/me/` | `MyProfileView` | Yes | authenticated | `MyProfileSerializer` | Returns own profile only | stable |
| PATCH | `/api/profiles/me/user-profile/` | `UpdateUserProfileView` | Yes | authenticated | `UserProfileSerializer` | — | stable |
| PATCH | `/api/profiles/me/patient/` | `UpdatePatientProfileView` | Yes | patient | `PatientProfileSerializer` | — | stable |
| PATCH | `/api/profiles/me/doctor/` | `UpdateDoctorProfileView` | Yes | doctor | `DoctorProfileSerializer` | — | stable |
| PATCH | `/api/profiles/me/pharmacist/` | `UpdatePharmacistProfileView` | Yes | pharmacist | `PharmacistProfileSerializer` | — | stable |
| PATCH | `/api/profiles/me/laboratorian/` | `UpdateLaboratorianProfileView` | Yes | laboratorian | `LaboratorianProfileSerializer` | — | stable |

---

## Consultations

| Method | Path | View | Auth | Roles | Serializer | Privacy | Status |
|---|---|---|---|---|---|---|---|
| POST | `/api/consultations/` | `ConsultationCreateView` | Yes | patient | `ConsultationCreateSerializer` | Patient only | stable |
| GET | `/api/consultations/my/` | `MyConsultationListView` | Yes | patient | `ConsultationListSerializer` | Own consultations only | stable |
| GET | `/api/consultations/doctor/pending/` | `DoctorPendingConsultationListView` | Yes | doctor (approved) | `ConsultationListSerializer` | Filtered by specialty | stable |
| GET | `/api/consultations/doctor/assigned/` | `DoctorAssignedConsultationListView` | Yes | doctor (approved) | `ConsultationListSerializer` | Only accepted by this doctor | stable |
| GET | `/api/consultations/<id>/` | `ConsultationDetailView` | Yes | patient \| doctor | `ConsultationDetailSerializer` | Patient sees own; doctor sees assigned | stable |
| POST | `/api/consultations/<id>/accept/` | `ConsultationAcceptView` | Yes | doctor (approved) | — | — | stable |
| POST | `/api/consultations/<id>/close/` | `ConsultationCloseView` | Yes | doctor (approved) | — | — | stable |
| POST | `/api/consultations/<id>/responses/` | `ConsultationResponseCreateView` | Yes | doctor (approved) | `ConsultationResponseSerializer` | — | stable |
| GET | `/api/consultations/symptom-categories/` | `SymptomCategoryListView` | Yes | patient | — | — | stable |
| GET | `/api/consultations/symptoms/` | `SymptomListView` | Yes | patient | — | — | stable |

---

## Messaging

| Method | Path | View | Auth | Roles | Serializer | Privacy | Status |
|---|---|---|---|---|---|---|---|
| GET/POST | `/api/consultations/<id>/messages/` | `ConsultationMessageListView` | Yes | patient \| doctor | `MessageSerializer` | Participants only | stable |
| POST | `/api/consultations/<id>/messages/mark-read/` | `ConsultationMarkMessagesReadView` | Yes | patient \| doctor | — | — | stable |

---

## Prescriptions

| Method | Path | View | Auth | Roles | Serializer | Privacy | Status |
|---|---|---|---|---|---|---|---|
| POST | `/api/consultations/<id>/prescriptions/` | `PrescriptionCreateView` | Yes | doctor (approved) | `PrescriptionCreateSerializer` | — | stable |
| GET | `/api/prescriptions/my/` | `PatientPrescriptionListView` | Yes | patient | `PatientPrescriptionSerializer` | **No medication items** | stable |
| GET | `/api/prescriptions/my/<id>/` | `PatientPrescriptionDetailView` | Yes | patient | `PatientPrescriptionDetailSerializer` | **No medication items** | stable |
| GET | `/api/prescriptions/doctor/<id>/` | `DoctorPrescriptionDetailView` | Yes | doctor (assigned) | `DoctorPrescriptionDetailSerializer` | Full items visible to doctor | stable |
| POST | `/api/prescriptions/doctor/<id>/cancel/` | `DoctorCancelPrescriptionView` | Yes | doctor (assigned) | — | — | stable |
| POST | `/api/prescriptions/scan/` | `PharmacistPrescriptionScanView` | Yes | pharmacist (approved) | `PharmacistPrescriptionScanSerializer` | **Pending items only** | stable |
| POST | `/api/prescriptions/<id>/dispense/` | `PharmacistDispenseItemsView` | Yes | pharmacist (approved) | `PharmacistDispenseSerializer` | — | stable |

---

## Lab Orders

| Method | Path | View | Auth | Roles | Serializer | Privacy | Status |
|---|---|---|---|---|---|---|---|
| POST | `/api/consultations/<id>/lab-orders/` | `LabOrderCreateView` | Yes | doctor (approved) | `LabOrderCreateSerializer` | — | stable |
| GET | `/api/lab-orders/tests/` | `LabTestCatalogListView` | Yes | doctor \| laboratorian | `LabTestCatalogSerializer` | — | stable |
| GET | `/api/lab-orders/my/` | `PatientLabOrderListView` | Yes | patient | `PatientLabOrderSerializer` | **No test items** | stable |
| GET | `/api/lab-orders/my/<id>/` | `PatientLabOrderDetailView` | Yes | patient | `PatientLabOrderDetailSerializer` | **No test items** | stable |
| GET | `/api/lab-orders/doctor/<id>/` | `DoctorLabOrderDetailView` | Yes | doctor (assigned) | `DoctorLabOrderDetailSerializer` | Full items visible | stable |
| POST | `/api/lab-orders/doctor/<id>/cancel/` | `DoctorCancelLabOrderView` | Yes | doctor (assigned) | — | — | stable |
| POST | `/api/lab-orders/scan/` | `LaboratorianLabOrderScanView` | Yes | laboratorian (approved) | `LaboratorianLabOrderScanSerializer` | **Pending items only** | stable |
| POST | `/api/lab-orders/<id>/complete/` | `LaboratorianCompleteLabOrderItemsView` | Yes | laboratorian (approved) | — | — | stable |

---

## Lab Results

| Method | Path | View | Auth | Roles | Serializer | Privacy | Status |
|---|---|---|---|---|---|---|---|
| POST | `/api/lab-orders/items/<item_id>/results/` | `LabResultCreateView` | Yes | laboratorian (approved) | `LabResultCreateSerializer` | — | stable |
| GET | `/api/lab-orders/results/<id>/` | `LabResultDetailView` | Yes | laboratorian (assigned) \| doctor | `LabResultDetailSerializer` | — | stable |
| POST | `/api/lab-orders/results/<id>/correct/` | `LabResultCorrectionView` | Yes | laboratorian (assigned) | — | — | stable |
| GET | `/api/lab-orders/doctor/results/<id>/` | `DoctorLabResultDetailView` | Yes | doctor (assigned) | `DoctorLabResultDetailSerializer` | — | stable |
| POST | `/api/lab-orders/doctor/results/<id>/review/` | `DoctorReviewLabResultView` | Yes | doctor (assigned) | — | — | stable |
| POST | `/api/lab-orders/doctor/results/<id>/release/` | `DoctorReleaseLabResultView` | Yes | doctor (assigned) | — | — | stable |
| POST | `/api/lab-orders/doctor/results/<id>/link-medical-record/` | `DoctorLinkLabResultToMedicalRecordView` | Yes | doctor (assigned) | — | — | stable |
| GET | `/api/lab-orders/my-results/` | `PatientLabResultListView` | Yes | patient | `PatientLabResultSerializer` | **Released only** | stable |
| GET | `/api/lab-orders/my-results/<id>/` | `PatientLabResultDetailView` | Yes | patient | `PatientLabResultDetailSerializer` | **Released only** | stable |
| GET | `/api/lab-results/my/` | `PatientLabResultListView` | Yes | patient | same | Alias of `/lab-orders/my-results/` | stable |
| GET | `/api/lab-results/my/<id>/` | `PatientLabResultDetailView` | Yes | patient | same | Alias route | stable |

> **Privacy note**: `laboratorian_notes` and `doctor_notes` are excluded from all patient-facing serializers. Patients see lab results only after `released_to_patient=True`.

---

## Patient Records

| Method | Path | View | Auth | Roles | Serializer | Privacy | Status |
|---|---|---|---|---|---|---|---|
| GET | `/api/patient-records/my/` | `MyMedicalRecordView` | Yes | patient | `PatientMedicalRecordSerializer` | Own record only | stable |
| GET | `/api/patient-records/<id>/entries/` (POST) | `MedicalRecordEntryCreateView` | Yes | doctor | `MedicalRecordEntrySerializer` | Assigned doctor only | stable |
| POST | `/api/patient-records/entries/<id>/confirm/` | `MedicalRecordEntryConfirmView` | Yes | doctor (assigned) | — | — | stable |
| POST | `/api/patient-records/entries/<id>/deactivate/` | `MedicalRecordEntryDeactivateView` | Yes | doctor (assigned) | — | — | stable |
| GET | `/api/patient-records/patients/<patient_id>/` | `DoctorPatientMedicalRecordView` | Yes | doctor (with active consultation) | `DoctorMedicalRecordSerializer` | Active consultation required | stable |
| POST | `/api/patient-records/<id>/blood-group/` | `SetBloodGroupView` | Yes | laboratorian (approved) | — | — | stable |
| POST | `/api/patient-records/patients/<patient_id>/blood-group/verify/` | `LaboratorianVerifyBloodGroupView` | Yes | laboratorian (approved) | — | — | stable |

---

## Notifications

| Method | Path | View | Auth | Roles | Serializer | Privacy | Status |
|---|---|---|---|---|---|---|---|
| GET | `/api/notifications/` | `NotificationListView` | Yes | authenticated | `NotificationSerializer` | Own notifications only | stable |
| GET | `/api/notifications/unread-count/` | `UnreadNotificationCountView` | Yes | authenticated | — | — | stable |
| POST | `/api/notifications/<id>/mark-read/` | `MarkNotificationReadView` | Yes | authenticated | — | Own notifications only | stable |
| POST | `/api/notifications/mark-all-read/` | `MarkAllNotificationsReadView` | Yes | authenticated | — | — | stable |

---

## Knowledge Base

> All endpoints require `is_staff=True` or `is_superuser=True`.

| Method | Path | View | Auth | Roles | Serializer | Status |
|---|---|---|---|---|---|---|
| GET/POST | `/api/knowledge-base/documents/` | `KnowledgeDocumentUploadView` | Yes | staff/admin | `KnowledgeDocumentSerializer` | admin-only |
| GET | `/api/knowledge-base/documents/<id>/` | `KnowledgeDocumentDetailView` | Yes | staff/admin | `KnowledgeDocumentDetailSerializer` | admin-only |
| POST | `/api/knowledge-base/documents/<id>/process/` | `KnowledgeDocumentProcessView` | Yes | staff/admin | — | admin-only |
| POST | `/api/knowledge-base/documents/<id>/approve/` | `KnowledgeDocumentApproveView` | Yes | staff/admin | — | admin-only |
| POST | `/api/knowledge-base/documents/<id>/reject/` | `KnowledgeDocumentRejectView` | Yes | staff/admin | — | admin-only |
| POST | `/api/knowledge-base/documents/<id>/archive/` | `KnowledgeDocumentArchiveView` | Yes | staff/admin | — | admin-only |
| POST | `/api/knowledge-base/documents/<id>/embed/` | `KnowledgeDocumentEmbedView` | Yes | staff/admin | — | admin-only |
| GET | `/api/knowledge-base/documents/<id>/chunks/` | `KnowledgeChunkListView` | Yes | staff/admin | `KnowledgeChunkSerializer` | admin-only |
| GET | `/api/knowledge-base/chunks/search/` | `KnowledgeChunkSearchView` | Yes | staff/admin | `KnowledgeChunkSearchSerializer` | admin-only |
| GET | `/api/knowledge-base/chunks/semantic-search/` | `KnowledgeChunkSemanticSearchView` | Yes | staff/admin | — | admin-only |

---

## RAG — Doctor AI Queries

| Method | Path | View | Auth | Roles | Serializer | Status |
|---|---|---|---|---|---|---|
| POST | `/api/rag/doctor/query/` | `DoctorGeneralRAGQueryView` | Yes | doctor (approved) | `RAGQueryRequestSerializer` | stable |
| POST | `/api/rag/consultations/<id>/support/` | `ConsultationRAGSupportView` | Yes | doctor (approved, assigned) | `RAGQueryRequestSerializer` | stable |
| POST | `/api/rag/lab-results/<id>/support/` | `LabResultRAGSupportView` | Yes | doctor (approved, assigned) | `RAGQueryRequestSerializer` | stable |

> Response shape: raw `RAGResponseSerializer` data (not wrapped in `{"success": true, "data": ...}`). See [API Response Contract](API_RESPONSE_CONTRACT.md).

---

## RAG Feedback

| Method | Path | View | Auth | Roles | Serializer | Status |
|---|---|---|---|---|---|---|
| POST | `/api/rag/responses/<id>/feedback/` | `RAGResponseFeedbackCreateView` | Yes | doctor (approved) | `RAGResponseFeedbackCreateSerializer` | stable |
| GET | `/api/rag/feedback/my/` | `MyRAGFeedbackListView` | Yes | doctor (approved) | `RAGResponseFeedbackSerializer` | stable |

---

## RAG Admin — Feedback Review

> All endpoints require `is_staff=True` or `is_superuser=True`.

| Method | Path | View | Auth | Roles | Serializer | Status |
|---|---|---|---|---|---|---|
| GET | `/api/rag/admin/feedback/` | `AdminRAGFeedbackListView` | Yes | staff/admin | `RAGResponseFeedbackSerializer` | admin-only |
| POST | `/api/rag/admin/feedback/<id>/review/` | `AdminRAGFeedbackReviewView` | Yes | staff/admin | `RAGFeedbackReviewSerializer` | admin-only |

---

## RAG Admin — Analytics & Export

> All endpoints require `is_staff=True` or `is_superuser=True`.

| Method | Path | View | Auth | Roles | Serializer | Status |
|---|---|---|---|---|---|---|
| GET | `/api/rag/admin/analytics/summary/` | `AdminRAGAnalyticsSummaryView` | Yes | staff/admin | `RAGAnalyticsSummarySerializer` | admin-only |
| POST | `/api/rag/admin/exports/dataset/` | `AdminRAGDatasetExportView` | Yes | staff/admin | `RAGDatasetExportSerializer` | admin-only |

---

## Total API endpoint count

| Group | Endpoints |
|---|---|
| Health/Schema | 6 |
| Accounts | 7 |
| Profiles | 6 |
| Consultations | 10 |
| Messaging | 2 |
| Prescriptions | 7 |
| Lab Orders | 8 |
| Lab Results | 10 |
| Patient Records | 7 |
| Notifications | 4 |
| Knowledge Base | 10 |
| RAG Queries | 3 |
| RAG Feedback | 2 |
| RAG Admin Feedback | 2 |
| RAG Admin Analytics/Export | 2 |
| **Total** | **86** |
