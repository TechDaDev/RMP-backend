from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.common.report_extraction import extract_clinical_report_text


class ClinicalReportExtractionTests(SimpleTestCase):
    def test_extracts_txt_content(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as tmp:
            tmp.write("Hemoglobin is 13.2\n")
            tmp_path = tmp.name

        try:
            text = extract_clinical_report_text(tmp_path)
            self.assertIn("Hemoglobin", text)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @patch("apps.common.report_extraction._run_easyocr_on_image_path")
    def test_extracts_image_with_easyocr(self, mock_ocr):
        mock_ocr.return_value = "نتيجة الأشعة طبيعية"

        with tempfile.NamedTemporaryFile(suffix=".png", mode="wb", delete=False) as tmp:
            tmp.write(b"fake-image")
            tmp_path = tmp.name

        try:
            text = extract_clinical_report_text(tmp_path)
            self.assertEqual(text, "نتيجة الأشعة طبيعية")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @patch("apps.common.report_extraction._extract_ocr_from_pdf_images")
    @patch("apps.common.report_extraction._extract_text_from_pdf")
    def test_combines_pdf_text_and_pdf_image_ocr(self, mock_pdf_text, mock_pdf_ocr):
        mock_pdf_text.return_value = "PDF layer text"
        mock_pdf_ocr.return_value = "Scanned image text"

        with tempfile.NamedTemporaryFile(suffix=".pdf", mode="wb", delete=False) as tmp:
            tmp.write(b"%PDF-1.4")
            tmp_path = tmp.name

        try:
            text = extract_clinical_report_text(tmp_path)
            self.assertIn("PDF layer text", text)
            self.assertIn("Scanned image text", text)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_truncates_when_max_chars_is_small(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as tmp:
            tmp.write("A" * 200)
            tmp_path = tmp.name

        try:
            text = extract_clinical_report_text(tmp_path, max_chars=50)
            self.assertIn("[TRUNCATED]", text)
            self.assertLessEqual(len(text), 70)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
