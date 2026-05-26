#!/usr/bin/env python3
"""Analyze API exploration outputs and generate a design recommendation report for RMP."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "outputs"
REPORT_PATH = OUTPUT_DIR / "external_medical_sources_report.md"

DRUG_TERMS = [
    "paracetamol",
    "acetaminophen",
    "amoxicillin",
    "metformin",
    "ibuprofen",
    "ceftriaxone",
    "insulin",
]

LAB_TERMS = [
    "CBC",
    "Complete Blood Count",
    "HbA1c",
    "Creatinine",
    "Liver Function Test",
    "Urinalysis",
    "Glucose",
]


def load_json(filename: str) -> Any:
    path = OUTPUT_DIR / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def bool_label(value: bool) -> str:
    return "Yes" if value else "No"


def first_non_empty(values: list[Any]) -> Any:
    for value in values:
        if value:
            return value
    return None


def summarize_rxnorm(simplified: Any) -> dict[str, Any]:
    rows = simplified if isinstance(simplified, list) else []
    has_rxcui = any(bool(row.get("rxcui")) for row in rows if isinstance(row, dict))
    has_synonyms = any(bool(row.get("synonyms")) for row in rows if isinstance(row, dict))
    has_tty = any(bool(row.get("tty")) for row in rows if isinstance(row, dict))

    return {
        "tested": bool(rows),
        "has_rxcui": has_rxcui,
        "has_synonyms": has_synonyms,
        "has_tty": has_tty,
        "sample": first_non_empty([row for row in rows if isinstance(row, dict)]),
    }


def summarize_openfda(simplified: Any) -> dict[str, Any]:
    rows = simplified if isinstance(simplified, list) else []
    has_warnings = any(bool(row.get("warnings")) for row in rows if isinstance(row, dict))
    has_contraindications = any(bool(row.get("contraindications")) for row in rows if isinstance(row, dict))
    has_indications = any(bool(row.get("indications_and_usage")) for row in rows if isinstance(row, dict))

    return {
        "tested": bool(rows),
        "has_warnings": has_warnings,
        "has_contraindications": has_contraindications,
        "has_indications": has_indications,
        "sample": first_non_empty([row for row in rows if isinstance(row, dict)]),
    }


def summarize_loinc(raw: Any, simplified: Any) -> dict[str, Any]:
    raw_rows = raw if isinstance(raw, list) else []
    rows = simplified if isinstance(simplified, list) else []
    skipped = any(
        isinstance(r, dict) and r.get("tested") is False for r in raw_rows
    )
    has_loinc_code = any(bool(row.get("loinc_code")) for row in rows if isinstance(row, dict))

    return {
        "tested": bool(rows) and not skipped,
        "skipped": skipped,
        "has_loinc_code": has_loinc_code,
        "sample": first_non_empty([row for row in rows if isinstance(row, dict) and row.get("loinc_code")]),
    }


def summarize_drugbank(raw: Any, simplified: Any) -> dict[str, Any]:
    raw_rows = raw if isinstance(raw, list) else []
    rows = simplified if isinstance(simplified, list) else []

    skipped = any(
        isinstance(r, dict) and r.get("tested") is False and "DRUGBANK_API_KEY" in str(r.get("reason", ""))
        for r in raw_rows
    )
    has_ids = any(bool(row.get("drugbank_id")) for row in rows if isinstance(row, dict))

    return {
        "tested": bool(rows) and not skipped,
        "skipped": skipped,
        "has_ids": has_ids,
        "sample": first_non_empty([row for row in rows if isinstance(row, dict) and row.get("drugbank_id")]),
    }


def section_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def build_report() -> str:
    rx_raw = load_json("rxnorm_raw_results.json")
    rx_simplified = load_json("rxnorm_simplified_results.json")
    openfda_raw = load_json("openfda_raw_results.json")
    openfda_simplified = load_json("openfda_simplified_results.json")
    loinc_raw = load_json("loinc_raw_results.json")
    loinc_simplified = load_json("loinc_simplified_results.json")
    drugbank_raw = load_json("drugbank_raw_results.json")
    drugbank_simplified = load_json("drugbank_simplified_results.json")

    rx_summary = summarize_rxnorm(rx_simplified)
    openfda_summary = summarize_openfda(openfda_simplified)
    loinc_summary = summarize_loinc(loinc_raw, loinc_simplified)
    drugbank_summary = summarize_drugbank(drugbank_raw, drugbank_simplified)

    drugbank_status = "Skipped (missing API key)" if drugbank_summary["skipped"] else "Tested"
    loinc_status = "Skipped (missing credentials)" if loinc_summary["skipped"] else "Tested"

    report = f"""# External Medical Data Source Analysis for RMP

## Purpose
This analysis phase tests external medical APIs only for import/sync/enrichment decisions. The goal is to decide which fields should later be imported into a local RMP medical catalog used by production doctor/lab/pharmacy workflows. No production integration or model creation was performed in this phase.

Search terms used:
- Drug terms: {", ".join(DRUG_TERMS)}
- Lab terms: {", ".join(LAB_TERMS)}

## Summary Table
| Source | Best Use | Good for Autocomplete? | Good for Clinical Details? | Good for Local Import? | Authentication Needed? | MVP Recommendation |
|---|---|---|---|---|---|---|
| RxNorm / RxNav | Drug normalization, synonym mapping, RxCUI references | Yes | Partial | Yes | No | Primary drug import/normalization source |
| openFDA Drug Label | Clinical label enrichment (warnings, contraindications, ADRs, dosage narrative) | No | Yes | Yes (selective) | No | Enrichment-only source |
| LOINC FHIR Terminology | Lab test terminology and code mapping | Yes | Partial | Yes | Yes | Primary lab terminology source |
| DrugBank | Expanded drug metadata and commercial datasets | Potentially | Yes | Later | Yes (paid/commercial) | Evaluate post-MVP |

## RxNorm Analysis
Endpoints tested:
- `GET /REST/approximateTerm.json`
- `GET /REST/rxcui/{{rxcui}}/properties.json`
- `GET /REST/rxcui/{{rxcui}}/allrelated.json`

Example useful fields:
- `rxcui` (concept identifier): {bool_label(rx_summary['has_rxcui'])}
- `name` and `tty` for display and concept type: {bool_label(rx_summary['has_tty'])}
- `synonym` and related concept names: {bool_label(rx_summary['has_synonyms'])}
- `score`/`rank` for relevance ordering in import preprocessing

RxNorm question analysis:
- Drug concept identifier fields: `rxcui`, `tty`, `name`, related concept names.
- Is RxCUI returned? {bool_label(rx_summary['has_rxcui'])}.
- Is name clear enough for autocomplete? Yes for most tested terms.
- Are generic names available? Often available via concept names and related entries.
- Are synonyms available? {bool_label(rx_summary['has_synonyms'])} via related concepts.
- Are dose form and strength available from tested endpoints? Partially; inferred through related concept naming and TTY-specific records, but not consistently structured in all responses.

Recommended local fields (future):
- Drug table: `name`, `rxnorm_rxcui`, `source_name`, `source_code`, `source_version`, `is_active`, `is_verified`.
- DrugAlias table: `alias`, `alias_type`, `language`, `source_name`.
- Import metadata: ranking/score for dedup and candidate prioritization.

Fields to ignore:
- Endpoint-level transport metadata and verbose wrapper structures.
- Any redundant nested structures that duplicate normalized concept data.

Weaknesses:
- Response schema varies by `tty` and concept granularity.
- Some candidates may not include complete structured dosage/form fields in a single call.

RMP recommendation:
- Use RxNorm as the core normalization source for local drug catalog import.
- Store RxCUI and aliases locally; avoid live per-keystroke external lookup in production.

## openFDA Analysis
Endpoints tested:
- `GET /drug/label.json` with generic/brand name search expressions

Example useful fields:
- `openfda.generic_name`, `openfda.brand_name`, `openfda.manufacturer_name`, `openfda.route`
- `warnings`, `indications_and_usage`, `contraindications`, `adverse_reactions`, `dosage_and_administration`

openFDA question analysis:
- Useful for clinical enrichment? Yes.
- Warnings available? {bool_label(openfda_summary['has_warnings'])}.
- Contraindications available? {bool_label(openfda_summary['has_contraindications'])}.
- Indications available? {bool_label(openfda_summary['has_indications'])}.
- Adverse reactions available? Usually available when label sections are present.
- Dosage instructions available? Often available but long narrative text.
- Generic and brand names available? Usually in `openfda.*` fields.
- Too verbose for direct storage? Yes, full responses are too verbose and repetitive for direct persistence.

Recommended local fields:
- Store directly: selected normalized values for warnings/contraindications/indications/dosage/adverse reactions summaries.
- Optional metadata: full raw label snippets in an auxiliary metadata JSON field or versioned enrichment table.

Fields to ignore:
- Long duplicated narrative sections with low retrieval value for autocomplete.
- Nonessential indexing metadata not tied to catalog features.

Weaknesses:
- Inconsistent completeness across products and labels.
- Text blocks are large and need summarization/cleaning before storage.

RMP recommendation:
- Use openFDA as enrichment-only during background import/sync.
- Do not use as primary autocomplete source.

## LOINC Analysis
Endpoints tested:
- `GET /ValueSet/$expand` with `url=http://loinc.org/vs` and term filter

Credential test status:
- {loinc_status}

Example useful fields:
- `code` (LOINC code), `display`, `system`, `version`
- `designation` values for aliases/synonyms
- `property` values for class/component/system-related metadata when present

LOINC question analysis:
- Fields that identify a lab test: `code`, `display`, plus optional class/component/system fields.
- Is LOINC code returned? {bool_label(loinc_summary['has_loinc_code'])}.
- Is display name useful? Yes for autocomplete.
- Are short names available? Sometimes via properties/designations, depends on response profile.
- Are components/systems/specimen/units/classes available? Partially, depending on endpoint expansion payload.

Recommended local fields (future):
- LabTest table: `name`, `short_name`, `loinc_code`, `category`, `component`, `system`, `sample_type`, `units`, `source_name`, `source_code`, `source_version`.
- LabTestAlias table: `alias`, `alias_type`, `language`, `source_name`.

Fields to ignore:
- Transport wrappers and repetitive expansion metadata not useful for search/indexing.

Weaknesses:
- Access requires credentials and schema richness can vary.
- Some clinically relevant properties may need additional endpoint strategies beyond one `$expand` query.

RMP recommendation:
- Use LOINC as the canonical terminology source for local lab test catalog import.

## DrugBank Analysis
Testing status:
- {drugbank_status}

Reason if skipped:
- If `DRUGBANK_API_KEY` is missing, testing is skipped and output files capture the reason.

If available, recommended use:
- Use as a later-phase paid integration for expanded metadata (interactions, richer pharmacology, commercial datasets).
- Evaluate licensing cost and endpoint coverage against MVP requirements before integration.

## Recommended Future Local Database Fields
Proposed future models (for planning only, not created yet):

Drug:
- id
- name
- generic_name
- brand_name
- form
- strength
- route
- rxnorm_rxcui
- atc_code
- description
- warnings
- contraindications
- dosage_info
- adverse_reactions
- source_name
- source_code
- source_version
- is_active
- is_verified
- created_at
- updated_at

DrugAlias:
- id
- drug
- alias
- alias_type
- language
- source_name

LabTest:
- id
- name
- short_name
- loinc_code
- category
- component
- system
- sample_type
- units
- preparation_required
- normal_range
- source_name
- source_code
- source_version
- is_active
- is_verified
- created_at
- updated_at

LabTestAlias:
- id
- lab_test
- alias
- alias_type
- language
- source_name

CatalogImportBatch:
- id
- source_name
- source_version
- imported_file
- started_at
- finished_at
- status
- total_records
- created_records
- updated_records
- skipped_records
- notes

## Fields to Store Locally
1. Required MVP fields.
- Drug: `name`, `generic_name`, `brand_name`, `rxnorm_rxcui`, `form`, `strength`, `route`, `is_active`.
- LabTest: `name`, `short_name`, `loinc_code`, `category`, `component`, `system`, `units`, `is_active`.
- Alias tables for autocomplete synonyms.
- Source tracking fields: `source_name`, `source_code`, `source_version`.

2. Optional enrichment fields.
- Drug clinical text summaries: warnings, contraindications, dosage, adverse reactions.
- Manufacturer and route variants from openFDA.
- Advanced lab properties (sample type, preparation, normal range) where reliably available.

3. Fields to ignore for now.
- Entire raw API blobs in production query tables.
- Verbose transport wrappers and duplicate narrative sections.
- Unstable or sparse fields without consistent population across results.

## Final Recommendation
- Use RxNorm as the primary drug normalization/import source.
- Use openFDA as an enrichment source, not an autocomplete source.
- Use LOINC as the primary lab terminology source.
- Use DrugBank later only if commercial access and budget justify integration.
- Keep all production autocomplete fully local in the RMP database.
- Do not call external APIs during doctor typing in production; only use scheduled import/sync/enrichment pipelines.
"""
    return report


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Generated report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
