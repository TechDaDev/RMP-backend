#!/usr/bin/env python3
"""Standalone RxNorm/RxNav API explorer for RMP catalog planning."""

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

BASE_URL = "https://rxnav.nlm.nih.gov/REST"
TIMEOUT_SECONDS = 15
MAX_CANDIDATES = 5

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "outputs"


def safe_get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch JSON safely and never raise exceptions to callers."""
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
            key_path = f"{prefix}.{key}" if prefix else key
            counter[key_path] += 1
            counter.update(collect_keys(nested, key_path))
    elif isinstance(value, list):
        for item in value:
            counter.update(collect_keys(item, prefix))
    return counter


def extract_synonyms(allrelated_json: dict[str, Any] | None) -> list[str]:
    synonyms: set[str] = set()
    if not isinstance(allrelated_json, dict):
        return []

    all_related_group = allrelated_json.get("allRelatedGroup") or {}
    concept_groups = all_related_group.get("conceptGroup") or []
    for group in concept_groups:
        for concept in group.get("conceptProperties") or []:
            name = concept.get("name")
            if isinstance(name, str) and name.strip():
                synonyms.add(name.strip())
    return sorted(synonyms)


def build_field_analysis(raw_results: list[dict[str, Any]], simplified_results: list[dict[str, Any]]) -> dict[str, Any]:
    raw_keys = Counter()
    for entry in raw_results:
        raw_keys.update(collect_keys(entry))

    simplified_keys = Counter()
    for row in simplified_results:
        simplified_keys.update(collect_keys(row))

    return {
        "service": "rxnorm",
        "records_raw": len(raw_results),
        "records_simplified": len(simplified_results),
        "raw_key_frequency": dict(raw_keys.most_common(200)),
        "simplified_key_frequency": dict(simplified_keys.most_common(200)),
        "notes": [
            "Approximate term search can return multiple semantic types (TTY).",
            "Some candidates have sparse properties depending on concept granularity.",
        ],
    }


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def main() -> None:
    raw_results: list[dict[str, Any]] = []
    simplified_results: list[dict[str, Any]] = []

    for term in DRUG_TERMS:
        approx_response = safe_get_json(
            f"{BASE_URL}/approximateTerm.json",
            params={"term": term, "maxEntries": MAX_CANDIDATES},
        )

        term_raw: dict[str, Any] = {
            "input_term": term,
            "source_endpoint": "approximateTerm",
            "approximate": approx_response,
            "candidates": [],
        }

        approx_json = approx_response.get("json") if approx_response.get("ok") else None
        candidates = (
            (approx_json or {}).get("approximateGroup", {}).get("candidate", [])
            if isinstance(approx_json, dict)
            else []
        )

        for candidate in candidates:
            rxcui = candidate.get("rxcui")
            properties_response = (
                safe_get_json(f"{BASE_URL}/rxcui/{rxcui}/properties.json")
                if rxcui
                else {"ok": False, "status_code": None, "url": None, "error": "Missing rxcui", "json": None}
            )
            allrelated_response = (
                safe_get_json(f"{BASE_URL}/rxcui/{rxcui}/allrelated.json")
                if rxcui
                else {"ok": False, "status_code": None, "url": None, "error": "Missing rxcui", "json": None}
            )

            candidate_raw = {
                "candidate": candidate,
                "properties": properties_response,
                "allrelated": allrelated_response,
            }
            term_raw["candidates"].append(candidate_raw)

            prop_json = properties_response.get("json") if properties_response.get("ok") else None
            properties = (prop_json or {}).get("properties") if isinstance(prop_json, dict) else {}
            name = properties.get("name") if isinstance(properties, dict) else candidate.get("name")
            tty = properties.get("tty") if isinstance(properties, dict) else candidate.get("tty")
            synonym = properties.get("synonym") if isinstance(properties, dict) else candidate.get("name")
            synonyms = extract_synonyms(
                allrelated_response.get("json") if allrelated_response.get("ok") else None
            )

            simplified_results.append(
                {
                    "input_term": term,
                    "rxcui": rxcui,
                    "name": name,
                    "synonym": synonym,
                    "synonyms": synonyms[:20],
                    "tty": tty,
                    "score": candidate.get("score"),
                    "rank": candidate.get("rank"),
                    "source_endpoint_used": [
                        "approximateTerm",
                        "rxcui/properties",
                        "rxcui/allrelated",
                    ],
                }
            )

        raw_results.append(term_raw)

    field_analysis = build_field_analysis(raw_results, simplified_results)

    save_json(OUTPUT_DIR / "rxnorm_raw_results.json", raw_results)
    save_json(OUTPUT_DIR / "rxnorm_simplified_results.json", simplified_results)
    save_json(OUTPUT_DIR / "rxnorm_field_analysis.json", field_analysis)

    print(f"Saved RxNorm outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
