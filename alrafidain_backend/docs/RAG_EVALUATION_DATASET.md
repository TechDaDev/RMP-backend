# RAG Evaluation Dataset — Field Reference

_Phase 12E — Analytics and Training Dataset Preparation_

This document describes the structure and privacy guarantees of the anonymized RAG evaluation dataset exported by:

- `POST /api/rag/admin/exports/dataset/` (API)
- `python manage.py export_rag_dataset` (management command)

---

## Table of Contents

- [Top-level fields (per record)](#top-level-fields-per-record)
- [`feedback` object](#feedback-object)
- [`sources` array (per element)](#sources-array-per-element)
- [JSON example](#json-example)
- [CSV format](#csv-format)
- [Privacy guarantees](#privacy-guarantees)
- [Limitations](#limitations)

---

## Top-level fields (per record)

| Field | Type | Description |
|---|---|---|
| `rag_query_id` | UUID string | Identifier of the RAGQuery object |
| `service_context` | string | One of `general_doctor_query`, `consultation`, `lab_result` |
| `response_status` | string | One of `completed`, `error`, `no_results` |
| `model_name` | string | LLM model used (e.g. `deepseek-chat`) |
| `provider` | string | LLM provider (e.g. `deepseek`) |
| `safety_level` | string | `doctor_only`, `all_staff`, etc. |
| `doctor_review_required` | boolean | Whether manual review was flagged |
| `patient_visible` | boolean | Always `false` in current phases |
| `token_input` | integer | Prompt token count |
| `token_output` | integer | Completion token count |
| `doctor_id_hash` | string | SHA-256 hex of doctor PK (when `anonymize=true`); raw UUID otherwise |
| `object_id_hash` | string \| null | SHA-256 hex of object ID (consultation/lab result PK), or null |
| `created_date` | date string | ISO-8601 date of the query (time truncated) |
| `query_text` | string | _(opt-in)_ Query text — only present when `include_text=true` |
| `response_text` | string | _(opt-in)_ LLM response text — only present when `include_text=true` |
| `feedback` | object \| null | Doctor feedback record, or `null` if no feedback submitted |
| `sources` | array | Retrieved knowledge chunks used in the response |

---

## `feedback` object

| Field | Type | Description |
|---|---|---|
| `rating` | string | `helpful`, `partially_helpful`, `not_helpful`, `unsafe` |
| `is_source_grounded` | boolean \| null | Doctor confirmed sources supported the answer |
| `is_clinically_useful` | boolean \| null | Answer was clinically actionable |
| `is_safe` | boolean \| null | No harmful content detected |
| `needs_admin_review` | boolean | Doctor flagged for staff review |
| `review_status` | string | `pending`, `reviewed`, `dismissed`, `escalated` |

---

## `sources` array (per element)

| Field | Type | Description |
|---|---|---|
| `chunk_id` | UUID string | Knowledge chunk PK |
| `document_id` | UUID string | Parent knowledge document PK |
| `document_title` | string | Document title |
| `document_type` | string | E.g. `clinical_guideline`, `laboratory_book` |
| `rank` | integer | Retrieval rank (1 = most relevant) |
| `score` | float | Cosine similarity score |
| `source_relevance` | string \| null | Doctor-rated relevance: `relevant`, `partially_relevant`, `irrelevant`, or `null` |

> **Note:** Raw embeddings are never included in exports.

---

## JSON example

```json
[
  {
    "rag_query_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "service_context": "general_doctor_query",
    "response_status": "completed",
    "model_name": "deepseek-chat",
    "provider": "deepseek",
    "safety_level": "doctor_only",
    "doctor_review_required": false,
    "patient_visible": false,
    "token_input": 1200,
    "token_output": 320,
    "doctor_id_hash": "a3f1c8b2d7e9...(64 hex chars)",
    "object_id_hash": null,
    "created_date": "2025-01-15",
    "feedback": {
      "rating": "helpful",
      "is_source_grounded": true,
      "is_clinically_useful": true,
      "is_safe": true,
      "needs_admin_review": false,
      "review_status": "pending"
    },
    "sources": [
      {
        "chunk_id": "00000000-0000-0000-0000-000000000010",
        "document_id": "00000000-0000-0000-0000-000000000001",
        "document_title": "Clinical Guideline — Hypertension",
        "document_type": "clinical_guideline",
        "rank": 1,
        "score": 0.873214,
        "source_relevance": "relevant"
      }
    ]
  }
]
```

---

## CSV format

The CSV flattens nested objects. Each row is one `RAGResponse`. Sources are pipe-delimited within a single cell:

| Column | Description |
|---|---|
| `rag_query_id` | Same as JSON |
| `service_context` | Same as JSON |
| `response_status` | Same as JSON |
| `model_name` | Same as JSON |
| `provider` | Same as JSON |
| `safety_level` | Same as JSON |
| `doctor_review_required` | Same as JSON |
| `patient_visible` | Same as JSON |
| `token_input` | Same as JSON |
| `token_output` | Same as JSON |
| `doctor_id_hash` | Same as JSON |
| `object_id_hash` | Same as JSON |
| `created_date` | Same as JSON |
| `feedback_rating` | From `feedback.rating` |
| `feedback_is_source_grounded` | From `feedback.is_source_grounded` |
| `feedback_is_clinically_useful` | From `feedback.is_clinically_useful` |
| `feedback_is_safe` | From `feedback.is_safe` |
| `feedback_needs_admin_review` | From `feedback.needs_admin_review` |
| `feedback_review_status` | From `feedback.review_status` |
| `source_chunk_ids` | Pipe-delimited chunk UUIDs |
| `source_document_ids` | Pipe-delimited document UUIDs |
| `source_document_titles` | Pipe-delimited document titles |
| `source_document_types` | Pipe-delimited document types |
| `source_ranks` | Pipe-delimited rank integers |
| `source_scores` | Pipe-delimited scores |
| `source_relevances` | Pipe-delimited relevance values |
| `query_text` _(opt-in)_ | First column when `include_text=true` |
| `response_text` _(opt-in)_ | Second column when `include_text=true` |

---

## Privacy guarantees

1. **Doctor PKs** are hashed with SHA-256 using `EXPORT_HASH_SALT` when `anonymize=true` (the default). The hash is not reversible without the salt.
2. **Object IDs** (consultation/lab result PKs) are also hashed when present and `anonymize=true`.
3. **Patient names, emails, phone numbers, and national IDs** are never included in any export.
4. **Raw pgvector embeddings** are never included in any export.
5. **Query and response text** are excluded by default (`include_text=false`). Enable with care — text may contain clinical details.

---

## Limitations

- Records with no doctor feedback have `feedback: null` — these are lower quality training examples.
- `created_date` is date-only (no time) to reduce re-identification risk.
- Source relevance is only present when the doctor rated that specific source; most sources will have `source_relevance: null`.
- The export is a point-in-time snapshot; run regularly for incremental training data collection.
