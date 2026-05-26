#!/usr/bin/env python3
"""Standalone LOINC FHIR terminology explorer for RMP lab catalog planning."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import requests

LAB_TERMS = [
    "CBC",
    "Complete Blood Count",
    "HbA1c",
    "Creatinine",
    "Liver Function Test",
    "Urinalysis",
    "Glucose",
]

BASE_URL = "https://fhir.loinc.org/ValueSet/$expand"
TIMEOUT_SECONDS = 20
COUNT = 10

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "outputs"


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def safe_get_json(
    url: str,
    params: dict[str, Any] | None = None,
    auth: tuple[str, str] | None = None,
) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params, auth=auth, timeout=TIMEOUT_SECONDS)
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


def build_field_analysis(raw_results: list[dict[str, Any]], simplified_results: list[dict[str, Any]]) -> dict[str, Any]:
    raw_counter = Counter()
    for entry in raw_results:
        raw_counter.update(collect_keys(entry))

    simplified_counter = Counter()
    for row in simplified_results:
        simplified_counter.update(collect_keys(row))

    return {
        "service": "loinc",
        "records_raw": len(raw_results),
        "records_simplified": len(simplified_results),
        "raw_key_frequency": dict(raw_counter.most_common(200)),
        "simplified_key_frequency": dict(simplified_counter.most_common(200)),
        "notes": [
            "LOINC FHIR expansion typically needs authentication.",
            "Returned properties can vary by term and code system configuration.",
        ],
    }


def simplify_contains(input_term: str, item: dict[str, Any]) -> dict[str, Any]:
    designations = [
        d.get("value")
        for d in item.get("designation", [])
        if isinstance(d, dict) and isinstance(d.get("value"), str)
    ]
    properties = {}
    for prop in item.get("property", []):
        if not isinstance(prop, dict):
            continue
        code = prop.get("code")
        if not isinstance(code, str):
            continue
        properties[code] = prop.get("valueCode") or prop.get("valueString") or prop.get("valueBoolean")

    return {
        "input_term": input_term,
        "loinc_code": item.get("code"),
        "display": item.get("display"),
        "system": item.get("system"),
        "version": item.get("version"),
        "designation_synonyms": designations,
        "properties": properties,
        "source_endpoint_used": "ValueSet/$expand",
    }


def main() -> None:
    username = os.getenv("LOINC_USERNAME")
    password = os.getenv("LOINC_PASSWORD")

    raw_results: list[dict[str, Any]] = []
    simplified_results: list[dict[str, Any]] = []

    if not username or not password:
        raw_results.append(
            {
                "tested": False,
                "reason": "Missing LOINC_USERNAME or LOINC_PASSWORD",
                "input_terms": LAB_TERMS,
                "source_endpoint": "ValueSet/$expand",
            }
        )
        for term in LAB_TERMS:
            simplified_results.append(
                {
                    "input_term": term,
                    "loinc_code": None,
                    "display": None,
                    "system": None,
                    "version": None,
                    "designation_synonyms": [],
                    "properties": {},
                    "source_endpoint_used": "ValueSet/$expand",
                    "note": "Skipped: missing credentials",
                }
            )
    else:
        auth = (username, password)
        for term in LAB_TERMS:
            response = safe_get_json(
                BASE_URL,
                params={
                    "url": "http://loinc.org/vs",
                    "filter": term,
                    "count": COUNT,
                    "_format": "json",
                },
                auth=auth,
            )

            raw_results.append(
                {
                    "tested": True,
                    "input_term": term,
                    "source_endpoint": "ValueSet/$expand",
                    "response": response,
                }
            )

            payload = response.get("json") if response.get("ok") else None
            contains = (
                payload.get("expansion", {}).get("contains", [])
                if isinstance(payload, dict)
                else []
            )

            if not contains:
                simplified_results.append(
                    {
                        "input_term": term,
                        "loinc_code": None,
                        "display": None,
                        "system": None,
                        "version": None,
                        "designation_synonyms": [],
                        "properties": {},
                        "source_endpoint_used": "ValueSet/$expand",
                        "note": "No results or request failed",
                    }
                )
                continue

            for item in contains:
                if isinstance(item, dict):
                    simplified_results.append(simplify_contains(term, item))

    field_analysis = build_field_analysis(raw_results, simplified_results)

    save_json(OUTPUT_DIR / "loinc_raw_results.json", raw_results)
    save_json(OUTPUT_DIR / "loinc_simplified_results.json", simplified_results)
    save_json(OUTPUT_DIR / "loinc_field_analysis.json", field_analysis)

    print(f"Saved LOINC outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
