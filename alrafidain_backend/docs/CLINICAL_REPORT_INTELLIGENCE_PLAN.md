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

## Deferred Beyond 10C

- Structured lab value extraction
- RAG context auto-update from report OCR
- Doctor AI assistant response generation from extracted report context

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
