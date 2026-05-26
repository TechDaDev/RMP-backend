#!/usr/bin/env python3
"""Standalone openFDA drug label API explorer for RMP catalog enrichment planning."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import requests

DRUG_TERMS = [
    "paracetamol",
    "acetaminophen",
    "amoxicillin",
    "metformin",
    "ibuprofen",
    "ceftriaxone",
    "insulin",
]

BASE_URL = "https://api.fda.gov/drug/label.json"
TIMEOUT_SECONDS = 20
RESULT_LIMIT = 5
TEXT_TRUNCATE = 500

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "outputs"


def safe_get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
        payload: Any = None
        parse_error = None
        try:
            payload = response.json()
        except ValueError as exc:
            parse_error = f"Invalid JSON: {exc}"

        return {
            "ok": response.ok,
            "status_code": response.status_code,
            "url": response.url,
            "error": None if response.ok else response.text[:500],
            "parse_error": parse_error,
            "json": payload,
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "status_code": None,
            "url": url,
            "error": str(exc),
            "parse_error": None,
            "json": None,
        }


def collect_keys(value: Any, prefix: str = "") -> Counter:
    counter: Counter = Counter()
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else key
            counter[path] += 1
            counter.update(collect_keys(nested, path))
    elif isinstance(value, list):
        for item in value:
            counter.update(collect_keys(item, prefix))
    return counter


def first_list_strings(payload: Any, max_items: int = 2) -> list[str]:
    if not isinstance(payload, list):
        return []

    output: list[str] = []
    for value in payload[:max_items]:
        if isinstance(value, str):
            output.append(value[:TEXT_TRUNCATE])
        else:
            output.append(str(value)[:TEXT_TRUNCATE])
    return output


def simplify_result(input_term: str, row: dict[str, Any]) -> dict[str, Any]:
    openfda = row.get("openfda") or {}
    return {
        "input_term": input_term,
        "generic_names": openfda.get("generic_name", []),
        "brand_names": openfda.get("brand_name", []),
        "manufacturer_name": openfda.get("manufacturer_name", []),
        "route": openfda.get("route", []),
        "warnings": first_list_strings(row.get("warnings")),
        "indications_and_usage": first_list_strings(row.get("indications_and_usage")),
        "contraindications": first_list_strings(row.get("contraindications")),
        "adverse_reactions": first_list_strings(row.get("adverse_reactions")),
        "dosage_and_administration": first_list_strings(row.get("dosage_and_administration")),
        "active_ingredient": first_list_strings(row.get("active_ingredient")),
        "source_endpoint_used": "drug/label",
    }


def build_field_analysis(raw_results: list[dict[str, Any]], simplified_results: list[dict[str, Any]]) -> dict[str, Any]:
    raw_counter = Counter()
    for entry in raw_results:
        raw_counter.update(collect_keys(entry))

    simplified_counter = Counter()
    for row in simplified_results:
        simplified_counter.update(collect_keys(row))

    return {
        "service": "openfda",
        "records_raw": len(raw_results),
        "records_simplified": len(simplified_results),
        "raw_key_frequency": dict(raw_counter.most_common(200)),
        "simplified_key_frequency": dict(simplified_counter.most_common(200)),
        "notes": [
            "The openFDA response can be verbose and is not ideal for direct full-text local storage.",
            "Many fields are list-based and may include long narrative text.",
        ],
    }


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def main() -> None:
    raw_results: list[dict[str, Any]] = []
    simplified_results: list[dict[str, Any]] = []

    for term in DRUG_TERMS:
        search_query = f'(openfda.generic_name:"{term}"+openfda.brand_name:"{term}")'
        response = safe_get_json(BASE_URL, params={"search": search_query, "limit": RESULT_LIMIT})

        term_raw = {
            "input_term": term,
            "source_endpoint": "drug/label",
            "search_query": search_query,
            "response": response,
        }
        raw_results.append(term_raw)

        payload = response.get("json") if response.get("ok") else None
        rows = payload.get("results", []) if isinstance(payload, dict) else []
        if not rows:
            simplified_results.append(
                {
                    "input_term": term,
                    "generic_names": [],
                    "brand_names": [],
                    "manufacturer_name": [],
                    "route": [],
                    "warnings": [],
                    "indications_and_usage": [],
                    "contraindications": [],
                    "adverse_reactions": [],
                    "dosage_and_administration": [],
                    "active_ingredient": [],
                    "source_endpoint_used": "drug/label",
                    "note": "No results or request failed",
                }
            )
            continue

        for row in rows:
            if isinstance(row, dict):
                simplified_results.append(simplify_result(term, row))

    field_analysis = build_field_analysis(raw_results, simplified_results)

    save_json(OUTPUT_DIR / "openfda_raw_results.json", raw_results)
    save_json(OUTPUT_DIR / "openfda_simplified_results.json", simplified_results)
    save_json(OUTPUT_DIR / "openfda_field_analysis.json", field_analysis)

    print(f"Saved openFDA outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
