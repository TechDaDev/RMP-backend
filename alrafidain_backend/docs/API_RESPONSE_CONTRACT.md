# API Response Contract

_Phase 13 — API Contract Freeze — Al-Rafidain Medical Platform_

This document defines the standard response envelope used by custom API views in the Al-Rafidain backend, and documents known exceptions.

---

## Table of Contents

- [Standard Success Response](#standard-success-response)
- [Standard Error Response](#standard-error-response)
- [Validation Error Format](#validation-error-format)
- [Authentication Error Format](#authentication-error-format)
- [Pagination Format](#pagination-format)
- [RAG Endpoints — Exception (Non-standard Shape)](#rag-endpoints--exception-non-standard-shape)
- [Health Endpoint (200 OK)](#health-endpoint-200-ok)
- [File Upload Notes](#file-upload-notes)
- [CSV Export Exception](#csv-export-exception)
- [Summary Table](#summary-table)

---

## Standard Success Response

All custom views in: `accounts`, `profiles`, `consultations`, `messaging`, `prescriptions`, `lab_orders`, `lab_results`, `patient_records`, `notifications`, `knowledge_base`

```json
{
  "success": true,
  "message": "Optional human-readable message",
  "data": { ... }
}
```

- `success`: always `true` for 2xx responses
- `message`: present on action responses (create, update, close); omitted on pure data reads in some views
- `data`: serialized object or array; omitted if there is nothing to return

Implemented via `apps.common.responses.success_response()`.

---

## Standard Error Response

```json
{
  "success": false,
  "message": "Human-readable error description",
  "errors": {
    "field_name": ["Error detail 1", "Error detail 2"]
  }
}
```

- `errors`: present when there are field-level validation errors; may be omitted for non-field errors
- `message`: always present on error responses

Implemented via `apps.common.responses.error_response()`.

---

## Validation Error Format

DRF serializer validation errors surfaced via `serializer.is_valid(raise_exception=True)` use DRF's default exception handler, which returns:

```json
{
  "field_name": ["This field is required."]
}
```

> **Note:** When `raise_exception=True` is used, the response is **not** wrapped in the `{"success": false, ...}` envelope. This affects validation error responses across all apps. Frontend clients should handle both shapes when receiving `400 Bad Request`.

---

## Authentication Error Format

DRF SimpleJWT returns standard 401/403 responses:

```json
{
  "detail": "Authentication credentials were not provided.",
  "code": "not_authenticated"
}
```

```json
{
  "detail": "Given token not valid for any token type",
  "code": "token_not_valid",
  "messages": [...]
}
```

These are **not** wrapped in the standard envelope.

---

## Pagination Format

Not implemented in MVP. All list views return flat arrays.

> Future versions may add cursor or page-number pagination. The `data` key will contain the paginated result object when introduced.

---

## RAG Endpoints — Exception (Non-standard Shape)

The `apps/rag/views.py` module uses raw DRF `Response()` objects directly and does **not** use `success_response()` / `error_response()`. This is a documented inconsistency.

### RAG Query Response (200 OK)

```json
{
  "id": "<uuid>",
  "rag_query_id": "<uuid>",
  "response_text": "...",
  "status": "completed",
  "safety_level": "doctor_only",
  "doctor_review_required": false,
  "patient_visible": false,
  "model_name": "deepseek-chat",
  "provider": "deepseek",
  "token_input": 1200,
  "token_output": 320,
  "sources": [ ... ],
  "created_at": "2025-01-15T12:00:00Z"
}
```

### RAG Error Response (400 / 403)

```json
{
  "detail": "Human-readable error message"
}
```

### RAG Analytics Summary Response (200 OK)

```json
{
  "feedback": { ... },
  "retrieval_quality": { ... },
  "usage": { ... }
}
```

### RAG Dataset Export — JSON (200 OK)

```json
{
  "format": "json",
  "record_count": 42,
  "data": [ ... ]
}
```

### RAG Dataset Export — CSV (200 OK)

- `Content-Type: text/csv; charset=utf-8`
- `Content-Disposition: attachment; filename="rag_eval_dataset.csv"`
- Body is raw CSV text (not JSON)

---

## Health Endpoint (200 OK)

```json
{
  "status": "ok",
  "service": "alrafidain-backend",
  "version": "0.1.0"
}
```

Not wrapped in the standard envelope. Always returns 200.

---

## File Upload Notes

- Document uploads (`POST /api/knowledge-base/documents/`) use `multipart/form-data`.
- All other endpoints use `application/json`.
- Message attachments (if any future phase adds them) will use `multipart/form-data`.

---

## CSV Export Exception

`POST /api/rag/admin/exports/dataset/` with `{"format": "csv"}` returns a binary CSV response, not JSON. Frontend must check `Content-Type` header to determine format before parsing.

---

## Summary Table

| Endpoint group | Envelope | Error shape | Notes |
|---|---|---|---|
| Accounts | `{success, message?, data?}` | `{success:false, message, errors?}` | Validation: bare DRF format |
| Profiles | `{success, message?, data?}` | same | — |
| Consultations | `{success, message?, data?}` | same | — |
| Messaging | `{success, message?, data?}` | same | — |
| Prescriptions | `{success, message?, data?}` | same | — |
| Lab Orders | `{success, message?, data?}` | same | — |
| Lab Results | `{success, message?, data?}` | same | — |
| Patient Records | `{success, message?, data?}` | same | — |
| Notifications | `{success, message?, data?}` | same | — |
| Knowledge Base | `{success, message?, data?}` | same | — |
| RAG Queries | raw serializer data | `{detail: "..."}` | No standard envelope |
| RAG Feedback | raw serializer data | `{detail: "..."}` | No standard envelope |
| RAG Admin | raw serializer data | `{detail: "..."}` | No standard envelope |
| Health | `{status, service, version}` | — | Always 200 |
| Schema/Docs | OpenAPI | — | Third-party |
