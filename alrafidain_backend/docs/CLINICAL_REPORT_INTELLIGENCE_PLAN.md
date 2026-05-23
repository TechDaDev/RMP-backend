# Clinical Report Intelligence Plan

## Scope Summary

This document tracks phased delivery of chat-attachment clinical report intelligence.

## Phase 10A (Completed)

Delivered:
- `PatientMedicalReport` candidate model and workflow foundations
- Candidate creation from patient chat attachments (non-blocking)
- Patient and doctor report list/detail/review APIs
- Access control, serializers, admin registration, migration, docs

Not delivered in 10A:
- OCR extraction
- LLM cleanup/classification
- RAG auto-trigger

## Phase 10B (Completed)

Delivered:
- OCR processing service for report candidates
- Security-gate integration via `secure_extracted_report_text`
- OCR status lifecycle and safe metadata persistence
- Optional upload-time OCR trigger via settings
- Doctor-trigger endpoint: `POST /api/doctor/medical-reports/{id}/process-ocr/`
- Audit events for OCR started/completed/rejected/failed/triggered

### OCR Status Lifecycle

- Candidate created: `uploaded` (or `queued` when OCR-on-upload is enabled but deferred)
- OCR started: `ocr_pending`
- OCR accepted by security gate: `ocr_completed`
- OCR rejected by security gate: `rejected`
- OCR failed (missing/unreadable file or processing error): `failed`

### Persisted OCR Metadata

`structured_payload.ocr` stores safe metadata only:
- `accepted`
- `reason`
- `has_prompt_injection`
- `is_medical_report`
- `extractor`
- `phase`

No full OCR text is stored in audit logs.

## Phase 10C (Completed)

Delivered:
- LLM cleanup/classification service for report candidates
- Strict prompt/response JSON contract with schema validation
- Doctor-trigger endpoint: `POST /api/doctor/medical-reports/{id}/classify-llm/`
- Optional OCR accepted-path auto-trigger into LLM classification via settings
- Safe `structured_payload` persistence for `llm`, `structured_data`, and `safety`
- Audit events for LLM started/completed/rejected/failed and doctor manual triggers

### Phase 10C Status Lifecycle Additions

- LLM started: `llm_pending`
- LLM accepted and persisted: `llm_completed`
- LLM rejected (not medical or low confidence): `rejected`
- LLM invalid output or runtime error: `failed`

### Persisted LLM Metadata

`structured_payload.llm` stores safe metadata only:
- `accepted`
- `reason`
- `model`
- `confidence`
- `detected_language`
- `phase`

`structured_payload.safety` stores safe model flags only:
- `contains_prompt_injection`
- `contains_sensitive_personal_data`

Prompt text and raw provider payload are not exposed via report APIs.

## Phase 10D (Completed)

Delivered:
- Canonical save/link service: `save_medical_report_to_patient_record(...)`
- Report-type to record-category mapping for medical record entry creation
- Safe report-to-entry payload builder using cleaned text + bounded structured summary
- Linked-entry idempotency and duplicate prevention (`force=false` returns existing link)
- Update-in-place behavior (`force=true`) for already linked entries
- Doctor-trigger endpoint: `POST /api/doctor/medical-reports/{id}/save-to-record/`
- Verification safeguards:
	- default `self_reported`
	- `doctor_confirmed` only with assigned doctor explicit confirmation
- `linked_medical_record_entry` safe summary exposure in report detail/list serializers

### Phase 10D Behavior Highlights

- `not_medical_report` is never saved into canonical patient records.
- Save requires medical report acceptance/classification state (`llm_completed` / `doctor_reviewed` / `accepted`, with limited OCR fallback).
- Source attribution is persisted on entry (`source_user`, `source_role`) with consultation/message/attachment IDs in entry notes.
- No prompt/provider raw payload/local paths are persisted into canonical entry fields.

## Phase 10E (Completed)

Delivered:
- Doctor-facing report case-update RAG service: `run_medical_report_case_update_rag(...)`
- Safe report case-summary builder for RAG (`build_medical_report_case_summary_for_rag`)
- Access rule enforcement for approved assigned doctors only
- Doctor endpoint: `POST /api/rag/medical-reports/{id}/case-update/`
- Optional filter passthrough (`document_type`, `specialty`, `language`, `audience`) with sanitized routing into existing RAG query flow
- Report context routing via `service_context=report_case_update` and `object_id=report_id`

### Phase 10E Behavior Highlights

- Reuses existing approved knowledge retrieval safeguards and RAG response safety invariants.
- Uses cleaned report text and bounded structured summary; prompt/provider raw internals are not exposed in response payloads.
- Includes linked medical record entry context when available.
- Does not auto-save generated RAG output into patient records.

## Phase 10F (Completed)

Delivered:
- Persistent doctor-only assistant stream model in RAG domain (`DoctorAIAssistantMessage`)
- Assistant generation service from report case-update RAG responses
- Doctor-only assistant APIs:
	- `GET /api/rag/consultations/{id}/doctor-ai-messages/`
	- `POST /api/rag/medical-reports/{id}/doctor-ai-message/`
	- `GET /api/rag/doctor-ai-messages/{id}/`
	- `POST /api/rag/doctor-ai-messages/{id}/mark-read/`
- Assistant message read/unread status workflow
- Safe source summary exposure (citations metadata only)
- Audit logging for assistant message creation and read-status updates
- Doctor-only notification and user-socket realtime event (`doctor_ai.message.created`)

### Phase 10F Safety and Privacy Guarantees

- Assistant messages are strictly doctor-facing and never patient-visible.
- Assistant messages are not written into normal consultation chat messages.
- Assistant APIs do not expose prompts, provider raw payloads, API credentials, or local file paths.
- Assistant output is advisory and does not auto-diagnose, auto-prescribe, auto-change consultation status, or auto-save to patient record.

## Phase 10G.2A (Completed)

Delivered:
- Explicit backend realtime contract for doctor AI assistant stream
- `doctor_ai.message.created` event contract on user websocket (`/ws/user/`)
- `doctor_ai.message.updated` event contract for read/unread state changes
- Safe payload alignment with assistant serializer fields
- Guaranteed doctor-only routing via `user_<doctor_id>` group

Safety guarantees:
- Assistant events are never sent to patient user groups.
- Assistant events are never sent on consultation chat groups.
- Normal chat websocket events remain unchanged.
- Payload excludes prompt/provider raw internals and secrets.

## Deferred Beyond 10F

- Structured lab value extraction
- Frontend integration and UX orchestration for doctor AI panel

## Configuration Flags (Phase 10B)

- `CLINICAL_REPORT_OCR_ON_UPLOAD` (default `False`)
- `CLINICAL_REPORT_OCR_SYNC_ON_UPLOAD` (default `False`)
- `CLINICAL_REPORT_OCR_MAX_INLINE_MB` (default `5`)

When sync upload OCR is disabled, reports remain `queued` for manual trigger.

## Configuration Flags (Phase 10C)

- `CLINICAL_REPORT_LLM_ENABLED` (default `True`)
- `CLINICAL_REPORT_LLM_SYNC_AFTER_OCR` (default `False`)
- `CLINICAL_REPORT_LLM_MODEL` (default `deepseek-chat`)
- `CLINICAL_REPORT_LLM_MAX_INPUT_CHARS` (default `6000`)
- `CLINICAL_REPORT_LLM_MAX_OUTPUT_CHARS` (default `4000`)
- `CLINICAL_REPORT_LLM_MIN_CONFIDENCE` (default `0.55`)
- `CLINICAL_REPORT_LLM_TIMEOUT_SECONDS` (default `25`)
