"""
Management command: export_rag_dataset

Exports anonymized RAG evaluation data to a JSON or CSV file.

Usage:
    python manage.py export_rag_dataset [--format json|csv] [--output PATH]
                                        [--include-text] [--no-anonymize]

Defaults:
    --format json
    --output exports/rag_eval.json (or .csv)
    include_text = False (safe default)
    anonymize   = True  (safe default)

Examples:
    python manage.py export_rag_dataset --settings=config.settings.local

    python manage.py export_rag_dataset \\
        --format csv \\
        --output exports/rag_eval.csv \\
        --settings=config.settings.local

    python manage.py export_rag_dataset \\
        --format json \\
        --output exports/rag_eval_with_text.json \\
        --include-text \\
        --no-anonymize \\
        --settings=config.settings.local
"""

from __future__ import annotations

import json
import os

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Export an anonymized RAG evaluation dataset to JSON or CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            dest="format",
            default="json",
            choices=["json", "csv"],
            help="Output format: json (default) or csv.",
        )
        parser.add_argument(
            "--output",
            dest="output",
            default=None,
            help=(
                "Output file path. Defaults to exports/rag_eval.json "
                "or exports/rag_eval.csv depending on format."
            ),
        )
        parser.add_argument(
            "--include-text",
            dest="include_text",
            action="store_true",
            default=False,
            help=(
                "Include query_text and response_text in the export. "
                "WARNING: these may contain clinician-generated free text. "
                "Off by default."
            ),
        )
        parser.add_argument(
            "--no-anonymize",
            dest="no_anonymize",
            action="store_true",
            default=False,
            help=(
                "Disable anonymization. Raw IDs will be included. "
                "Use only in secure, internal contexts."
            ),
        )

    def handle(self, *args, **options):
        fmt: str = options["format"]
        include_text: bool = options["include_text"]
        anonymize: bool = not options["no_anonymize"]

        # Resolve output path
        output_path: str = options["output"] or f"exports/rag_eval.{fmt}"

        # Create output directory if it does not exist
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        self.stdout.write(
            self.style.NOTICE(
                f"Exporting RAG evaluation dataset "
                f"(format={fmt}, include_text={include_text}, anonymize={anonymize}) "
                f"→ {output_path}"
            )
        )

        from apps.rag.exporters import export_rag_evaluation_dataset

        content = export_rag_evaluation_dataset(
            format=fmt,
            include_text=include_text,
            anonymize=anonymize,
        )

        if fmt == "json":
            with open(output_path, "w", encoding="utf-8") as fh:
                json.dump(content, fh, ensure_ascii=False, indent=2)
            record_count = len(content)
        else:
            with open(output_path, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
            # Count CSV rows (subtract 1 for header)
            record_count = max(0, content.count("\n") - 1)

        self.stdout.write(
            self.style.SUCCESS(f"Done — {record_count} record(s) written to {output_path}")
        )
