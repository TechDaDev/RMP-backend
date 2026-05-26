#!/usr/bin/env python3
"""Standalone DrugBank API explorer for RMP integration feasibility checks."""

from __future__ import annotations

import json
import os
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

DEFAULT_BASE_URL = "https://api.drugbank.com/v1"
TIMEOUT_SECONDS = 20

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "outputs"


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def safe_get_json(
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT_SECONDS)
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


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "drugs", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [payload]
    return []


def simplify_row(input_term: str, row: dict[str, Any], endpoint_used: str) -> dict[str, Any]:
    interactions = row.get("interactions")
    if isinstance(interactions, list):
        interactions_summary = interactions[:5]
    elif interactions is None:
        interactions_summary = []
    else:
        interactions_summary = [str(interactions)[:500]]

    return {
        "input_term": input_term,
        "drugbank_id": row.get("drugbank_id") or row.get("id") or row.get("drugbankId"),
        "name": row.get("name") or row.get("drug_name"),
        "description": row.get("description") or row.get("summary"),
        "synonyms": row.get("synonyms") if isinstance(row.get("synonyms"), list) else [],
        "categories": row.get("categories") if isinstance(row.get("categories"), list) else [],
        "interactions": interactions_summary,
        "source_endpoint_used": endpoint_used,
    }


def build_field_analysis(raw_results: list[dict[str, Any]], simplified_results: list[dict[str, Any]]) -> dict[str, Any]:
    raw_counter = Counter()
    for entry in raw_results:
        raw_counter.update(collect_keys(entry))

    simplified_counter = Counter()
    for row in simplified_results:
        simplified_counter.update(collect_keys(row))

    return {
        "service": "drugbank",
        "records_raw": len(raw_results),
        "records_simplified": len(simplified_results),
        "raw_key_frequency": dict(raw_counter.most_common(200)),
        "simplified_key_frequency": dict(simplified_counter.most_common(200)),
        "notes": [
            "DrugBank access patterns vary by commercial plan and endpoint permissions.",
            "This script is exploratory and handles auth or schema mismatches gracefully.",
        ],
    }


def main() -> None:
    api_key = os.getenv("DRUGBANK_API_KEY")
    base_url = os.getenv("DRUGBANK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    raw_results: list[dict[str, Any]] = []
    simplified_results: list[dict[str, Any]] = []

    if not api_key:
        raw_results.append(
            {
                "tested": False,
                "reason": "Missing DRUGBANK_API_KEY",
                "input_terms": DRUG_TERMS,
                "base_url": base_url,
            }
        )
        for term in DRUG_TERMS:
            simplified_results.append(
                {
                    "input_term": term,
                    "drugbank_id": None,
                    "name": None,
                    "description": None,
                    "synonyms": [],
                    "categories": [],
                    "interactions": [],
                    "source_endpoint_used": None,
                    "note": "Skipped: missing DRUGBANK_API_KEY",
                }
            )
    else:
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

        endpoint_attempts = [
            {"path": "/us/drugs", "params_builder": lambda term: {"name": term, "limit": 5}},
            {"path": "/drugs", "params_builder": lambda term: {"q": term, "limit": 5}},
            {"path": "/drugs", "params_builder": lambda term: {"search": term, "limit": 5}},
        ]

        for term in DRUG_TERMS:
            attempts_for_term: list[dict[str, Any]] = []
            selected_rows: list[dict[str, Any]] = []
            selected_endpoint = None

            for attempt in endpoint_attempts:
                endpoint = f"{base_url}{attempt['path']}"
                params = attempt["params_builder"](term)
                response = safe_get_json(endpoint, headers=headers, params=params)

                attempt_result = {
                    "endpoint": endpoint,
                    "params": params,
                    "response": response,
                }
                attempts_for_term.append(attempt_result)

                if response.get("ok") and response.get("json") is not None:
                    rows = extract_rows(response.get("json"))
                    if rows:
                        selected_rows = rows
                        selected_endpoint = endpoint
                        break

            raw_results.append(
                {
                    "tested": True,
                    "input_term": term,
                    "attempts": attempts_for_term,
                    "selected_endpoint": selected_endpoint,
                    "selected_rows_count": len(selected_rows),
                }
            )

            if not selected_rows:
                simplified_results.append(
                    {
                        "input_term": term,
                        "drugbank_id": None,
                        "name": None,
                        "description": None,
                        "synonyms": [],
                        "categories": [],
                        "interactions": [],
                        "source_endpoint_used": selected_endpoint,
                        "note": "No usable response payload from tested endpoints",
                    }
                )
            else:
                for row in selected_rows[:5]:
                    simplified_results.append(simplify_row(term, row, selected_endpoint or "unknown"))

    field_analysis = build_field_analysis(raw_results, simplified_results)

    save_json(OUTPUT_DIR / "drugbank_raw_results.json", raw_results)
    save_json(OUTPUT_DIR / "drugbank_simplified_results.json", simplified_results)
    save_json(OUTPUT_DIR / "drugbank_field_analysis.json", field_analysis)

    print(f"Saved DrugBank outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
