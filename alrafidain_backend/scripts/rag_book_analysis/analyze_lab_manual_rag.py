#!/usr/bin/env python3
"""Evaluate RAG coverage for McGraw-Hill Manual of Laboratory and Diagnostic Tests.

This script performs retrieval-only analysis against the existing local RAG/knowledge base,
then writes structured JSON outputs and a human-readable markdown report.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402


django.setup()

from django.db.models import Count, Q  # noqa: E402

from apps.common.choices import KnowledgeApprovalStatus  # noqa: E402
from apps.knowledge_base.models import KnowledgeChunk, KnowledgeDocument  # noqa: E402
from apps.knowledge_base.services import search_approved_chunks, semantic_search_approved_chunks  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "outputs"

RAW_MATCHES_PATH = OUTPUT_DIR / "lab_manual_rag_raw_matches.json"
FIELD_MATRIX_PATH = OUTPUT_DIR / "lab_manual_rag_field_matrix.json"
REPORT_PATH = OUTPUT_DIR / "lab_manual_rag_evaluation.md"

BOOK_TITLE = "McGraw-Hill Manual of Laboratory and Diagnostic Tests"
BOOK_AUTHOR_HINT = "Denise D. Wilson"

BOOK_IDENTIFICATION_QUERIES = [
    "McGraw-Hill Manual of Laboratory and Diagnostic Tests Denise D. Wilson",
    "Denise D. Wilson laboratory diagnostic tests",
    "McGraw-Hill laboratory diagnostic tests",
    "Manual of Laboratory and Diagnostic Tests",
]

LAB_TEST_QUERIES = {
    "CBC": "Complete Blood Count CBC purpose preparation interpretation",
    "HbA1c": "HbA1c purpose preparation interpretation",
    "Creatinine": "Creatinine test purpose specimen normal range interpretation",
    "Liver Function Test": "Liver Function Test purpose preparation interpretation",
    "Urinalysis": "Urinalysis specimen collection interpretation",
    "Glucose": "Glucose test fasting preparation interpretation",
}

FIELD_DETECTION_PATTERNS = {
    "purpose_summary": [r"purpose", r"used to", r"indication", r"clinical use"],
    "patient_preparation": [r"preparation", r"fasting", r"before test", r"patient should"],
    "specimen_type": [r"specimen", r"sample", r"serum", r"plasma", r"urine", r"blood"],
    "sample_collection_notes": [r"collection", r"collect", r"tube", r"handling", r"timing"],
    "clinical_significance": [r"significance", r"associated with", r"suggests", r"clinical"],
    "interpretation_summary": [r"interpret", r"elevated", r"decreased", r"normal", r"abnormal"],
    "interfering_factors": [r"interfer", r"false", r"artifact", r"affect result"],
    "safety_notes": [r"safety", r"precaution", r"hazard", r"biohazard", r"warning"],
    "patient_explanation": [r"patient", r"explain", r"education", r"what this test means"],
    "provider_notes": [r"provider", r"clinician", r"consider", r"recommend", r"follow-up"],
}

TOP_K = 8
EXCERPT_MAX = 300


def clean_excerpt(text: str, max_len: int = EXCERPT_MAX) -> str:
    compact = re.sub(r"\s+", " ", (text or "")).strip()
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip() + "..."


def detect_topic(text: str) -> str:
    lowered = (text or "").lower()
    topic_patterns = [
        ("patient_preparation", ["fasting", "preparation", "before test"]),
        ("specimen_collection", ["specimen", "sample", "collection", "tube"]),
        ("clinical_significance", ["clinical", "significance", "indicates", "associated"]),
        ("interpretation", ["interpret", "normal", "abnormal", "elevated", "decreased"]),
        ("interfering_factors", ["interfer", "false positive", "false negative", "artifact"]),
        ("safety_notes", ["safety", "hazard", "biohazard", "precaution"]),
    ]
    for topic, needles in topic_patterns:
        if any(n in lowered for n in needles):
            return topic
    return "general"


def normalize_author(doc: KnowledgeDocument) -> str | None:
    source = (doc.source_authority or "").strip()
    if source:
        return source

    for candidate in [BOOK_AUTHOR_HINT, "Denise Wilson"]:
        if candidate.lower() in (doc.title or "").lower():
            return candidate
    return None


def run_retrieval(query: str, top_k: int) -> tuple[list[dict[str, Any]], str]:
    """Try semantic retrieval first and fallback to icontains text search."""
    try:
        semantic_hits = semantic_search_approved_chunks(query=query, limit=top_k)
        rows = []
        for hit in semantic_hits:
            chunk = hit["chunk"]
            rows.append(
                {
                    "chunk": chunk,
                    "score": hit.get("score"),
                    "distance": hit.get("distance"),
                    "rank": hit.get("rank"),
                    "retrieval_mode": "semantic",
                }
            )
        return rows, "semantic"
    except Exception as exc:
        text_hits = search_approved_chunks(query=query, limit=top_k)
        rows = []
        for idx, chunk in enumerate(text_hits, start=1):
            rows.append(
                {
                    "chunk": chunk,
                    "score": None,
                    "distance": None,
                    "rank": idx,
                    "retrieval_mode": "text_icontains",
                    "fallback_reason": f"semantic_error:{type(exc).__name__}",
                }
            )
        return rows, "text_icontains"


def is_book_match(document_title: str, source_filename: str | None) -> bool:
    title = (document_title or "").lower()
    source = (source_filename or "").lower()
    return "mcgraw-hill" in title or "manual of laboratory and diagnostic tests" in title or "mcgraw-hill" in source


def score_query_usefulness(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    top = rows[:3]
    book_hits = sum(1 for row in top if row.get("is_book_match"))
    clinically_structured_hits = sum(
        1
        for row in top
        if row.get("detected_topic")
        in {
            "patient_preparation",
            "specimen_collection",
            "clinical_significance",
            "interpretation",
            "interfering_factors",
            "safety_notes",
        }
    )

    if book_hits == 0:
        return 1
    if book_hits == 1 and clinically_structured_hits <= 1:
        return 2
    if book_hits >= 2 and clinically_structured_hits >= 1:
        return 3
    if book_hits >= 2 and clinically_structured_hits >= 2:
        return 4
    if book_hits >= 3 and clinically_structured_hits >= 2:
        return 5
    return 3


def detect_fields_from_rows(rows: list[dict[str, Any]]) -> dict[str, bool]:
    aggregate_text = " ".join((row.get("excerpt") or "") for row in rows).lower()
    support = {}
    for field_name, patterns in FIELD_DETECTION_PATTERNS.items():
        support[field_name] = any(re.search(pattern, aggregate_text) for pattern in patterns)
    return support


def field_matrix_rows(field_support: dict[str, bool]) -> list[dict[str, Any]]:
    rows = []
    for field_name, supported in field_support.items():
        if supported:
            rows.append(
                {
                    "field": field_name,
                    "supported_by_retrieved_content": True,
                    "store_directly": False,
                    "store_as_reviewed_summary": True,
                    "ignore": False,
                    "notes": "Use clinician-reviewed rewritten summary with source traceability.",
                }
            )
        else:
            rows.append(
                {
                    "field": field_name,
                    "supported_by_retrieved_content": False,
                    "store_directly": False,
                    "store_as_reviewed_summary": False,
                    "ignore": True,
                    "notes": "Insufficient signal in retrieved excerpts for this run.",
                }
            )
    return rows


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True, default=str), encoding="utf-8")


def run_analysis() -> tuple[dict[str, Any], dict[str, Any], str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_queries = BOOK_IDENTIFICATION_QUERIES + list(LAB_TEST_QUERIES.values())

    documents_snapshot = list(
        KnowledgeDocument.objects.annotate(active_chunk_count=Count("chunks", filter=Q(chunks__is_active=True))).values(
            "id",
            "title",
            "source_authority",
            "original_filename",
            "approval_status",
            "processing_status",
            "active_chunk_count",
        )
    )

    book_docs = [
        doc
        for doc in documents_snapshot
        if is_book_match(doc.get("title") or "", doc.get("original_filename") or "")
    ]

    query_results: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    query_to_rows: dict[str, list[dict[str, Any]]] = {}

    for query in all_queries:
        rows, retrieval_mode = run_retrieval(query=query, top_k=TOP_K)
        structured_rows = []
        for row in rows:
            chunk = row["chunk"]
            doc = chunk.document
            excerpt = clean_excerpt(chunk.text, EXCERPT_MAX)
            source_filename = getattr(doc, "original_filename", None)
            entry = {
                "query": query,
                "document_title": doc.title,
                "source_filename": source_filename,
                "author": normalize_author(doc),
                "page_number": chunk.page_number,
                "chunk_id": str(chunk.id),
                "chunk_index": chunk.chunk_index,
                "similarity_score": row.get("score"),
                "distance": row.get("distance"),
                "rank": row.get("rank"),
                "retrieval_mode": row.get("retrieval_mode", retrieval_mode),
                "excerpt": excerpt,
                "detected_topic": detect_topic(excerpt),
                "section_title": chunk.section_title,
                "is_book_match": is_book_match(doc.title, source_filename),
            }
            structured_rows.append(entry)
            all_rows.append(entry)

        query_to_rows[query] = structured_rows
        useful = any(r.get("is_book_match") for r in structured_rows)
        top_score = next(
            (
                r.get("similarity_score")
                for r in sorted(
                    structured_rows,
                    key=lambda x: ((x.get("similarity_score") is None), -(x.get("similarity_score") or -1)),
                )
                if r.get("similarity_score") is not None
            ),
            None,
        )
        query_results.append(
            {
                "query": query,
                "retrieval_mode": retrieval_mode,
                "result_count": len(structured_rows),
                "book_match_count": sum(1 for r in structured_rows if r.get("is_book_match")),
                "top_score": top_score,
                "useful": useful,
                "notes": "Book-matching chunks found" if useful else "No clear book-specific chunks in top results",
            }
        )

    matching_chunk_ids = {row["chunk_id"] for row in all_rows if row.get("is_book_match")}
    matched_chunks_count = len(matching_chunk_ids)

    book_presence_status = "yes" if book_docs and matched_chunks_count > 0 else "uncertain"
    if not book_docs:
        book_presence_status = "no"

    test_scores = {}
    test_field_support = {}
    for test_name, query in LAB_TEST_QUERIES.items():
        rows = query_to_rows.get(query, [])
        score = score_query_usefulness(rows)
        test_scores[test_name] = score
        test_field_support[test_name] = detect_fields_from_rows(rows)

    aggregate_field_support = {key: False for key in FIELD_DETECTION_PATTERNS}
    for support in test_field_support.values():
        for field_name, value in support.items():
            aggregate_field_support[field_name] = aggregate_field_support[field_name] or value

    fields_supported_count = sum(1 for value in aggregate_field_support.values() if value)

    rag_reference_usefulness = min(10, max(1, round((matched_chunks_count / max(1, len(all_queries) * 2)) * 10)))
    database_enrichment_usefulness = min(10, max(1, round((fields_supported_count / 10) * 10)))
    direct_import_suitability = 1
    risk_level = "medium"

    if rag_reference_usefulness >= 7 and database_enrichment_usefulness >= 6:
        risk_level = "low"

    overall_use = "Useful for reviewed summaries"

    raw_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "book_target": {
            "title": BOOK_TITLE,
            "author": BOOK_AUTHOR_HINT,
        },
        "documents_snapshot": documents_snapshot,
        "book_documents_detected": book_docs,
        "book_presence": {
            "status": book_presence_status,
            "matching_chunks_count": matched_chunks_count,
            "evidence_document_count": len(book_docs),
            "evidence": [
                {
                    "document_id": str(doc.get("id")),
                    "title": doc.get("title"),
                    "source_authority": doc.get("source_authority"),
                    "original_filename": doc.get("original_filename"),
                    "approval_status": doc.get("approval_status"),
                    "processing_status": doc.get("processing_status"),
                    "active_chunk_count": doc.get("active_chunk_count"),
                }
                for doc in book_docs
            ],
        },
        "queries": query_results,
        "matches": all_rows,
        "lab_test_scores": test_scores,
        "lab_test_field_support": test_field_support,
    }

    field_matrix_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "field_support": aggregate_field_support,
        "matrix": field_matrix_rows(aggregate_field_support),
        "should_not_store": [
            "full paragraphs",
            "copyrighted wording",
            "long monographs",
            "full reference ranges as final truth",
            "outdated clinical recommendations without review",
            "content without source traceability",
        ],
        "usage_decision": overall_use,
    }

    report = build_markdown_report(
        raw_payload=raw_payload,
        field_matrix_payload=field_matrix_payload,
        aggregate_field_support=aggregate_field_support,
        test_scores=test_scores,
        rag_reference_usefulness=rag_reference_usefulness,
        database_enrichment_usefulness=database_enrichment_usefulness,
        direct_import_suitability=direct_import_suitability,
        risk_level=risk_level,
        overall_use=overall_use,
    )

    return raw_payload, field_matrix_payload, report


def markdown_bool(value: bool) -> str:
    return "Yes" if value else "No"


def build_markdown_report(
    raw_payload: dict[str, Any],
    field_matrix_payload: dict[str, Any],
    aggregate_field_support: dict[str, bool],
    test_scores: dict[str, int],
    rag_reference_usefulness: int,
    database_enrichment_usefulness: int,
    direct_import_suitability: int,
    risk_level: str,
    overall_use: str,
) -> str:
    book_presence = raw_payload["book_presence"]
    matches = raw_payload["matches"]
    queries = raw_payload["queries"]

    top_match_per_query = {}
    grouped = defaultdict(list)
    for row in matches:
        grouped[row["query"]].append(row)

    for query, rows in grouped.items():
        rows_sorted = sorted(
            rows,
            key=lambda r: ((r.get("similarity_score") is None), -(r.get("similarity_score") or -1)),
        )
        top_match_per_query[query] = rows_sorted[0] if rows_sorted else None

    lab_rows = []
    for test_name, query in LAB_TEST_QUERIES.items():
        rows = grouped.get(query, [])
        retrieved = bool(rows)
        score = test_scores.get(test_name, 0)
        useful_fields = [
            field
            for field, supported in raw_payload["lab_test_field_support"].get(test_name, {}).items()
            if supported
        ]
        problems = []
        if not rows:
            problems.append("No retrieved chunks")
        if rows and not any(r.get("is_book_match") for r in rows):
            problems.append("Top hits not clearly from target book")
        if score <= 1:
            problems.append("Weak signal")

        lab_rows.append(
            {
                "test_name": test_name,
                "retrieved": retrieved,
                "score": score,
                "useful_fields": useful_fields,
                "problems": problems,
            }
        )

    retrieval_table_lines = [
        "| Query | Matching document/source | Top score if available | Useful? | Notes |",
        "|---|---|---:|---|---|",
    ]
    for item in queries:
        top_row = top_match_per_query.get(item["query"])
        doc_src = "None"
        if top_row:
            doc_src = f"{top_row.get('document_title') or 'Unknown'} / {top_row.get('source_filename') or 'Unknown file'}"
        top_score = item["top_score"]
        top_score_text = f"{top_score:.4f}" if isinstance(top_score, (int, float)) else "N/A"
        retrieval_table_lines.append(
            f"| {item['query']} | {doc_src} | {top_score_text} | {'Yes' if item['useful'] else 'No'} | {item['notes']} |"
        )

    coverage_table_lines = [
        "| Test | Retrieved? | Quality score 0-5 | Useful fields found | Problems |",
        "|---|---|---:|---|---|",
    ]
    for row in lab_rows:
        fields_str = ", ".join(row["useful_fields"]) if row["useful_fields"] else "None"
        problems_str = "; ".join(row["problems"]) if row["problems"] else "None"
        coverage_table_lines.append(
            f"| {row['test_name']} | {'Yes' if row['retrieved'] else 'No'} | {row['score']} | {fields_str} | {problems_str} |"
        )

    matrix_lines = [
        "| Field | Supported by retrieved content? | Store directly? | Store as reviewed summary? | Ignore? | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for row in field_matrix_payload["matrix"]:
        matrix_lines.append(
            "| {field} | {supported} | {direct} | {reviewed} | {ignore} | {notes} |".format(
                field=row["field"],
                supported=markdown_bool(row["supported_by_retrieved_content"]),
                direct=markdown_bool(row["store_directly"]),
                reviewed=markdown_bool(row["store_as_reviewed_summary"]),
                ignore=markdown_bool(row["ignore"]),
                notes=row["notes"],
            )
        )

    report = f"""# RAG Evaluation: McGraw-Hill Manual of Laboratory and Diagnostic Tests

## Purpose
This report evaluates whether the McGraw-Hill lab manual in the existing RAG knowledge base can support RMP's future LabTestClinicalInfo enrichment layer. This is retrieval and analysis only; no production import or model changes were performed.

## Book Presence Check
- Presence status: **{book_presence['status']}**
- Matching chunks (book-linked): **{book_presence['matching_chunks_count']}**
- Matching documents detected: **{book_presence['evidence_document_count']}**
- Evidence source title: **{BOOK_TITLE}**

## Retrieval Summary Table
{chr(10).join(retrieval_table_lines)}

## Lab Test Coverage Table
{chr(10).join(coverage_table_lines)}

## Field Suitability Matrix
{chr(10).join(matrix_lines)}

## Copyright and Safety Assessment
- The book content should not be copied wholesale into the database.
- Only short, reviewed, rewritten summaries should be stored.
- Source traceability must be preserved (document id, chunk id, title, and where available page number).
- Lab reference ranges should not be treated as final truth; performing labs should control reference ranges.
- Do not store long monographs or copyrighted paragraphs in production fields.

## Recommended RMP Database Use
Use LOINC as canonical terminology; use this manual as a secondary enrichment source.

LabTest (canonical structure):
- name
- short_name
- loinc_code
- category
- component
- system
- sample_type
- units

LabTestClinicalInfo (reviewed summaries only):
- purpose_summary
- patient_preparation
- sample_collection_notes
- clinical_significance
- interpretation_summary
- interfering_factors
- safety_notes
- source_name
- source_type
- source_version
- review_status
- reviewed_by
- reviewed_at

## Final Rating
- RAG reference usefulness: **{rag_reference_usefulness}/10**
- Database enrichment usefulness: **{database_enrichment_usefulness}/10**
- Direct database import suitability: **{direct_import_suitability}/10**
- Risk level: **{risk_level}**
- Recommendation class: **{overall_use}**

Final recommendation:
- Use LOINC as the canonical lab terminology source.
- Use the McGraw-Hill manual only as a secondary RAG/enrichment source.
- Do not import full text into production tables.
- Store only reviewed summaries in a separate LabTestClinicalInfo table.
- Preserve source metadata and review status.
- Keep lab-specific reference ranges controlled by each lab.
"""
    return report


def main() -> None:
    raw_payload, field_matrix_payload, report = run_analysis()
    save_json(RAW_MATCHES_PATH, raw_payload)
    save_json(FIELD_MATRIX_PATH, field_matrix_payload)
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"Saved: {RAW_MATCHES_PATH}")
    print(f"Saved: {FIELD_MATRIX_PATH}")
    print(f"Saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
