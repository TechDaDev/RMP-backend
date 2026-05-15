from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from io import BytesIO

from django.conf import settings

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_TEXT_EXTENSIONS = {".txt"}
_DOCX_EXTENSIONS = {".docx"}
_PDF_EXTENSIONS = {".pdf"}

_MEDICAL_HINT_TERMS = {
    # English
    "patient",
    "doctor",
    "hospital",
    "clinic",
    "laboratory",
    "lab",
    "result",
    "report",
    "diagnosis",
    "findings",
    "impression",
    "ultrasound",
    "x-ray",
    "xray",
    "cbc",
    "hemoglobin",
    "glucose",
    "hba1c",
    "creatinine",
    "prescription",
    # Arabic
    "المريض",
    "الطبيب",
    "مستشفى",
    "عيادة",
    "مختبر",
    "تحليل",
    "نتيجة",
    "تقرير",
    "تشخيص",
    "أشعة",
    "سونار",
    "هيموغلوبين",
    "سكر",
    "كرياتينين",
    "وصفة",
}

_PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior)\s+instructions",
    r"forget\s+(all\s+)?(previous|prior)\s+instructions",
    r"you\s+are\s+now",
    r"act\s+as\s+",
    r"system\s*:",
    r"developer\s*:",
    r"assistant\s*:",
    r"reveal\s+(the\s+)?(system|hidden)\s+prompt",
    r"print\s+(the\s+)?(system|hidden)\s+prompt",
    r"execute\s+code",
    r"run\s+shell",
    r"curl\s+http",
    r"wget\s+http",
    r"base64",
]


def _normalize_text(text: str) -> str:
    text = (text or "").replace("\x00", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[TRUNCATED]"


def _contains_prompt_injection(text: str) -> bool:
    normalized = (text or "").lower()
    return any(re.search(pattern, normalized) for pattern in _PROMPT_INJECTION_PATTERNS)


def _sanitize_prompt_like_lines(text: str) -> str:
    safe_lines = []
    for line in (text or "").splitlines():
        lower_line = line.lower().strip()
        if any(re.search(pattern, lower_line) for pattern in _PROMPT_INJECTION_PATTERNS):
            continue
        safe_lines.append(line)
    return "\n".join(safe_lines).strip()


def _is_likely_medical_report(text: str, *, min_term_hits: int = 2) -> bool:
    normalized = (text or "").lower()
    hits = sum(1 for term in _MEDICAL_HINT_TERMS if term in normalized)
    return hits >= min_term_hits


def secure_extracted_report_text(text: str) -> dict:
    """
    Security gate for extracted report text before AI prompt usage.

    Returns:
        {
            "accepted": bool,
            "reason": str,
            "sanitized_text": str,
            "is_medical_report": bool,
            "has_prompt_injection": bool,
        }
    """
    normalized = _normalize_text(text)
    if not normalized:
        return {
            "accepted": False,
            "reason": "empty_text",
            "sanitized_text": "",
            "is_medical_report": False,
            "has_prompt_injection": False,
        }

    is_medical_report = _is_likely_medical_report(
        normalized,
        min_term_hits=int(getattr(settings, "OCR_MIN_MEDICAL_TERM_HITS", 2)),
    )
    has_prompt_injection = _contains_prompt_injection(normalized)

    sanitized = _sanitize_prompt_like_lines(normalized)
    sanitized = _normalize_text(sanitized)

    if not is_medical_report:
        return {
            "accepted": False,
            "reason": "not_medical_report",
            "sanitized_text": "",
            "is_medical_report": False,
            "has_prompt_injection": has_prompt_injection,
        }

    if has_prompt_injection and not sanitized:
        return {
            "accepted": False,
            "reason": "prompt_injection_detected",
            "sanitized_text": "",
            "is_medical_report": True,
            "has_prompt_injection": True,
        }

    return {
        "accepted": True,
        "reason": "ok" if not has_prompt_injection else "sanitized_prompt_injection",
        "sanitized_text": sanitized,
        "is_medical_report": True,
        "has_prompt_injection": has_prompt_injection,
    }


def _resolve_path(file_obj) -> str:
    if file_obj is None:
        return ""

    if isinstance(file_obj, str):
        return file_obj

    path = getattr(file_obj, "path", "")
    if path:
        return path

    file_attr = getattr(file_obj, "file", None)
    if file_attr is not None:
        return getattr(file_attr, "name", "") or ""

    return ""


@lru_cache(maxsize=1)
def _get_easyocr_reader():
    try:
        import easyocr
    except Exception:  # pragma: no cover
        logger.warning("easyocr is not installed; OCR extraction will be skipped.")
        return None

    languages = getattr(settings, "OCR_LANGUAGES", ["ar", "en"])
    use_gpu = bool(getattr(settings, "OCR_USE_GPU", False))
    try:
        return easyocr.Reader(list(languages), gpu=use_gpu)
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to initialize EasyOCR reader: %s", exc)
        return None


def _extract_text_from_txt(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as file_handle:
        return file_handle.read()


def _extract_text_from_docx(path: str) -> str:
    from docx import Document

    doc = Document(path)
    paragraphs = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
    return "\n\n".join(paragraphs)


def _extract_text_from_pdf(path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def _run_easyocr_on_image_bytes(image_bytes: bytes) -> str:
    reader = _get_easyocr_reader()
    if reader is None:
        return ""

    try:
        import numpy as np
        from PIL import Image

        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image_np = np.array(image)
        rows = reader.readtext(image_np, detail=0, paragraph=True)
        return "\n".join(str(row).strip() for row in rows if str(row).strip())
    except Exception as exc:
        logger.warning("EasyOCR image extraction failed: %s", exc)
        return ""


def _run_easyocr_on_image_path(path: str) -> str:
    with open(path, "rb") as file_handle:
        return _run_easyocr_on_image_bytes(file_handle.read())


def _extract_ocr_from_pdf_images(path: str) -> str:
    from pypdf import PdfReader

    ocr_blocks: list[str] = []
    reader = PdfReader(path)

    for page in reader.pages:
        for image in getattr(page, "images", []):
            image_bytes = getattr(image, "data", b"")
            if not image_bytes:
                continue
            ocr_text = _run_easyocr_on_image_bytes(image_bytes)
            if ocr_text:
                ocr_blocks.append(ocr_text)

    return "\n\n".join(ocr_blocks)


def extract_clinical_report_text(file_obj, *, max_chars: int | None = None) -> str:
    """
    Extract text from uploaded clinical report files.

    Supports:
    - Images (`.jpg`, `.jpeg`, `.png`, `.webp`) via EasyOCR (`ar`, `en`)
    - PDF via direct extraction + OCR on embedded images
    - DOCX via paragraph text extraction
    - TXT via plain text read
    """
    path = _resolve_path(file_obj)
    if not path or not os.path.exists(path):
        return ""

    if max_chars is None:
        max_chars = int(getattr(settings, "OCR_MAX_EXTRACTED_CHARS", 6000))

    extension = os.path.splitext(path)[1].lower()
    combined_text = ""

    try:
        if extension in _IMAGE_EXTENSIONS:
            combined_text = _run_easyocr_on_image_path(path)
        elif extension in _TEXT_EXTENSIONS:
            combined_text = _extract_text_from_txt(path)
        elif extension in _DOCX_EXTENSIONS:
            combined_text = _extract_text_from_docx(path)
        elif extension in _PDF_EXTENSIONS:
            base_text = _extract_text_from_pdf(path)
            ocr_text = _extract_ocr_from_pdf_images(path)
            combined_text = "\n\n".join(block for block in [base_text, ocr_text] if block)
        else:
            return ""
    except Exception as exc:
        logger.warning("Failed to extract clinical report text from %s: %s", path, exc)
        return ""

    normalized = _normalize_text(combined_text)
    if not normalized:
        return ""
    return _truncate(normalized, max_chars)
