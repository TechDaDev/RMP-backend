# RAG Plan — Al-Rafidain Medical Platform

---

## Table of Contents

- [Overview](#overview)
- [Safety Principles](#safety-principles)
- [Phase 12A — Knowledge Base Foundation](#phase-12a--knowledge-base-foundation--current)
- [Phase 12B — pgvector Embeddings and Retrieval](#phase-12b--pgvector-embeddings-and-retrieval--complete)
- [Phase 12C — DeepSeek RAG Doctor Support](#phase-12c--deepseek-rag-doctor-support)
- [Phase 12D — AI Evaluation and Feedback](#phase-12d--ai-evaluation-and-feedback--complete)
- [Phase 12E — Analytics and Training Dataset Preparation](#phase-12e--analytics-and-training-dataset-preparation--complete)
- [Technology Decisions](#technology-decisions)
- [Document Lifecycle](#document-lifecycle)
- [References](#references)

---

## Overview

This document describes the phased plan to add Retrieval-Augmented Generation (RAG) AI support to the Al-Rafidain Medical Platform.

RAG allows the platform to provide medically grounded AI responses to doctors by retrieving relevant passages from an approved knowledge base rather than relying solely on a language model's training data.

---

## Safety Principles

These principles apply across all RAG phases:

- **Only approved documents can be used for RAG.** All documents must pass the admin approval workflow before their chunks are eligible for retrieval.
- **Patient-facing AI is not allowed yet.** RAG and AI responses are restricted to doctors and internal staff until extensive safety review is complete.
- **Doctor-facing AI must cite sources.** Every AI-generated response must include references to the specific knowledge chunks used.
- **AI does not diagnose, prescribe, or replace clinical judgment.** AI is a support tool only. All clinical decisions remain with licensed medical professionals.
- **No personally identifiable information (PII) is included in knowledge chunks.** Knowledge base documents contain general medical/lab knowledge, not patient records.

---

## Phase 12A — Knowledge Base Foundation ✅ (Current)

**Status**: Complete

**What was built:**

- New Django app: `apps/knowledge_base`
- Models: `KnowledgeDocument`, `KnowledgeDocumentText`, `KnowledgeChunk`, `KnowledgeProcessingLog`
- Services: text extraction (PDF/DOCX/TXT), character-based chunking, approval workflow, basic icontains search
- REST API (staff only): upload, list, detail, process, approve, reject, archive, chunk list, chunk search
- Audit logging for all document actions
- 32 tests covering upload, extraction, chunking, approval, search, and security

**Limitations:**

- No vector embeddings
- No pgvector
- No DeepSeek API
- No patient-facing AI
- Search is icontains only (no semantic similarity)
- Processing is synchronous (no Celery)

---

## Phase 12B — pgvector Embeddings and Retrieval ✅ Complete

**Goal**: Add semantic vector search to knowledge chunks.

**What was built:**

- `pgvector/pgvector:pg16` Docker image; migration 0002 enables `vector` extension in PostgreSQL
- New fields on `KnowledgeChunk`: `embedding` (VectorField, dim=384), `embedding_model`, `embedded_at`, `embedding_metadata`; `has_embedding` property
- `apps/knowledge_base/embedding_client.py` — `LocalEmbeddingClient` using `sentence-transformers/all-MiniLM-L6-v2` (lazy-loaded, normalised embeddings)
- Services: `embed_knowledge_chunk`, `embed_document_chunks`, `embed_all_approved_chunks`, `semantic_search_approved_chunks` (CosineDistance via pgvector)
- API endpoint: `POST /api/knowledge-base/documents/<id>/embed/` — embed all active chunks of an approved document
- API endpoint: `GET /api/knowledge-base/chunks/semantic-search/?q=...` — semantic search over embedded approved chunks
- Management command: `python manage.py embed_knowledge_base [--document-id <uuid>] [--force] [--limit N]`
- Settings: `EMBEDDING_MODEL_NAME`, `EMBEDDING_VECTOR_DIMENSION`
- 37 new tests (385 total); all embedding tests mock the client — no real model loaded in CI

**Constraints respected:**
- Only approved + active documents/chunks are eligible for embedding and retrieval
- Raw embedding vectors are never exposed in API responses
- No patient-facing AI; staff/superuser only
- Processing is synchronous (no Celery)

---

## Phase 12C — DeepSeek RAG Doctor Support

**Goal**: Allow doctors to ask medical questions and receive AI-grounded answers citing approved knowledge.

**Planned work:**

- DeepSeek API integration (doctor-facing only)
- Doctor RAG endpoint: `POST /api/ai/ask/`
  - Input: `question`, optional `specialty`, optional `document_type`
  - Retrieval: semantic search over approved active chunks
  - Prompt construction: inject retrieved chunks as context
  - DeepSeek generates answer
  - Response includes answer + source citations (chunk IDs, document titles, page numbers)
- Rate limiting on AI endpoint (per doctor, per day)
- Audit log: every AI query with retrieved chunks and response
- Strict permission: doctor only (not patient, not pharmacist)

**Constraints:**
- AI answers must include citations
- AI must not claim diagnostic certainty
- AI must not prescribe medications
- All queries and responses are logged

---

## Phase 12D — AI Evaluation and Feedback ✅ Complete

**Goal**: Collect doctor feedback on AI response quality for monitoring and improvement.

**Delivered:**

- `RAGResponseFeedback` model: doctor rates each response (helpful/partially_helpful/not_helpful/unsafe)
- `RAGRetrievedChunkFeedback` model: source-level relevance ratings (relevant/partially_relevant/irrelevant)
- Doctor feedback API: `POST /api/rag/feedback/`, `GET /api/rag/feedback/my/`
- Admin review endpoints: `POST /api/rag/admin/feedback/<id>/review/`, `GET /api/rag/admin/feedback/`
- Auto-flag for admin review when `is_safe=False` or `needs_admin_review=True`
- Full audit logging (`rag_feedback_submitted`, `rag_feedback_reviewed`)

---

## Phase 12E — Analytics and Training Dataset Preparation ✅ Complete

**Goal**: Aggregate RAG performance metrics and export anonymized evaluation data for research.

**Delivered:**

- `GET /api/rag/admin/analytics/summary/` — feedback coverage, ratings breakdown, retrieval quality, token usage
- `POST /api/rag/admin/exports/dataset/` — anonymized JSON or CSV export of evaluation records
- Django management command: `python manage.py export_rag_dataset --format json|csv --output PATH`
- SHA-256 anonymization of doctor IDs via configurable `EXPORT_HASH_SALT` setting
- Raw embeddings, patient names, and contact details excluded from all exports
- `include_text=False` by default (query/response text opt-in)
- Full audit logging (`rag_analytics_viewed`, `rag_dataset_exported`)
- See [docs/RAG_EVALUATION_DATASET.md](RAG_EVALUATION_DATASET.md) for dataset field reference

---

## Technology Decisions

| Component | Phase 12A | Phase 12B | Phase 12C |
|-----------|-----------|-----------|-----------|
| Search | icontains | pgvector cosine | pgvector + DeepSeek |
| Embeddings | None | sentence-transformers or OpenAI | Same |
| LLM | None | None | DeepSeek API |
| Processing | Synchronous | Celery async | Celery async |
| Patient access | None | None | None |

---

## Document Lifecycle

```
Staff uploads document
        ↓
  Text extracted (PDF/DOCX/TXT)
        ↓
  Chunked (character-based, Phase 12A)
        ↓
  [Phase 12B: Chunks embedded into vectors]
        ↓
  Medical reviewer approves document
        ↓
  Chunks eligible for retrieval
        ↓
  [Phase 12C: Doctor asks question]
        ↓
  Semantic retrieval of relevant chunks
        ↓
  DeepSeek generates cited answer
        ↓
  Doctor sees answer + sources
```

---

## References

- [docs/API_REFERENCE.md](API_REFERENCE.md) — Current API endpoints
- [docs/OPERATIONAL_NOTES.md](OPERATIONAL_NOTES.md) — Setup and operations
- [docs/SECURITY_NOTES.md](SECURITY_NOTES.md) — Security hardening notes
