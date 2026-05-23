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

## Deferred Beyond 10B

- LLM text cleanup/normalization
- LLM report-type classification
- Structured lab value extraction
- RAG context auto-update from report OCR
- Doctor AI assistant response generation from extracted report context

## Configuration Flags (Phase 10B)

- `CLINICAL_REPORT_OCR_ON_UPLOAD` (default `False`)
- `CLINICAL_REPORT_OCR_SYNC_ON_UPLOAD` (default `False`)
- `CLINICAL_REPORT_OCR_MAX_INLINE_MB` (default `5`)

When sync upload OCR is disabled, reports remain `queued` for manual trigger.
