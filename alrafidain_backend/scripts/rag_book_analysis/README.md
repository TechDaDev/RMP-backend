# RAG Book Analysis: Lab Manual

## What This Script Does
`analyze_lab_manual_rag.py` evaluates whether the existing RAG/knowledge-base data contains useful retrievable content for:

- McGraw-Hill Manual of Laboratory and Diagnostic Tests (Denise D. Wilson)
- Lab-test enrichment use cases (CBC, HbA1c, Creatinine, LFT, Urinalysis, Glucose)

It performs retrieval-only analysis and generates structured outputs and a markdown evaluation report.

## Scope and Safety
- No production model changes.
- No migrations.
- No bulk import into DB.
- No long copyrighted excerpts.
- Only short excerpts (max 300 characters) are saved for verification.

## Assumptions About Existing RAG System
- Django project is available locally.
- Existing `apps.knowledge_base` models/services are present.
- Retrieval service (`semantic_search_approved_chunks`) is configured.
- If semantic retrieval fails in the current environment, the script falls back to approved chunk text search (`search_approved_chunks`).

## How To Run
From `alrafidain_backend`:

```bash
/home/zeus3000/PycharmProjects/RMP_backend/.venv/bin/python scripts/rag_book_analysis/analyze_lab_manual_rag.py
```

## Output Files
Generated under `scripts/rag_book_analysis/outputs/`:

- `lab_manual_rag_raw_matches.json`
  - Query-level retrieval outputs and match metadata.
- `lab_manual_rag_field_matrix.json`
  - Field suitability matrix for LabTestClinicalInfo enrichment fields.
- `lab_manual_rag_evaluation.md`
  - Human-readable evaluation report with recommendation and ratings.

## How To Interpret The Report
Use the report to decide if the book should be used as:
- direct import source (expected: no)
- reviewed-summary enrichment source (expected: yes)
- pure RAG reference only

Recommended pattern:
- Keep LOINC as canonical lab terminology source.
- Use book-derived content only as reviewed, source-traceable summaries.
