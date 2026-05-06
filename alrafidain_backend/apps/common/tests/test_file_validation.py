import io

from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.test import TestCase
from rest_framework.serializers import ValidationError

from apps.common.file_validation import (
    validate_content_type,
    validate_file_extension,
    validate_file_size,
    validate_uploaded_file,
)


def _make_file(name="test.txt", size_bytes=100, content_type="text/plain"):
    data = b"x" * size_bytes
    buf = io.BytesIO(data)
    return InMemoryUploadedFile(buf, "file", name, content_type, size_bytes, None)


class ValidateFileSizeTests(TestCase):
    def test_under_limit_passes(self):
        f = _make_file(size_bytes=1024)
        # Should not raise
        validate_file_size(f, max_size_mb=1)

    def test_over_limit_raises(self):
        f = _make_file(size_bytes=2 * 1024 * 1024 + 1)
        with self.assertRaises(ValidationError):
            validate_file_size(f, max_size_mb=2)

    def test_exactly_at_limit_passes(self):
        f = _make_file(size_bytes=1 * 1024 * 1024)
        validate_file_size(f, max_size_mb=1)


class ValidateFileExtensionTests(TestCase):
    def test_allowed_extension_passes(self):
        f = SimpleUploadedFile("doc.pdf", b"data", content_type="application/pdf")
        validate_file_extension(f, allowed_extensions=[".pdf", ".txt"])

    def test_disallowed_extension_raises(self):
        f = SimpleUploadedFile("malware.exe", b"data", content_type="application/octet-stream")
        with self.assertRaises(ValidationError):
            validate_file_extension(f, allowed_extensions=[".pdf", ".txt"])

    def test_case_insensitive(self):
        f = SimpleUploadedFile("image.PDF", b"data", content_type="application/pdf")
        validate_file_extension(f, allowed_extensions=[".pdf"])


class ValidateContentTypeTests(TestCase):
    def test_allowed_content_type_passes(self):
        f = SimpleUploadedFile("doc.txt", b"data", content_type="text/plain")
        validate_content_type(f, allowed_content_types=["text/plain"])

    def test_disallowed_content_type_raises(self):
        f = SimpleUploadedFile("bad.exe", b"data", content_type="application/x-msdownload")
        with self.assertRaises(ValidationError):
            validate_content_type(f, allowed_content_types=["text/plain"])

    def test_empty_content_type_falls_back_to_mimeguess(self):
        f = SimpleUploadedFile("doc.pdf", b"data", content_type="")
        # mimetypes.guess_type("doc.pdf") → "application/pdf"
        validate_content_type(f, allowed_content_types=["application/pdf"])


class ValidateUploadedFileTests(TestCase):
    def test_valid_file_passes(self):
        f = _make_file("report.pdf", size_bytes=1024, content_type="application/pdf")
        validate_uploaded_file(
            f,
            allowed_extensions=[".pdf"],
            allowed_content_types=["application/pdf"],
            max_size_mb=5,
        )

    def test_bad_extension_raises(self):
        f = _make_file("script.js", size_bytes=100, content_type="text/javascript")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(
                f,
                allowed_extensions=[".pdf"],
                allowed_content_types=["application/pdf"],
                max_size_mb=5,
            )

    def test_bad_content_type_raises(self):
        f = _make_file("report.pdf", size_bytes=100, content_type="text/javascript")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(
                f,
                allowed_extensions=[".pdf"],
                allowed_content_types=["application/pdf"],
                max_size_mb=5,
            )

    def test_oversized_raises(self):
        f = _make_file("report.pdf", size_bytes=6 * 1024 * 1024, content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(
                f,
                allowed_extensions=[".pdf"],
                allowed_content_types=["application/pdf"],
                max_size_mb=5,
            )
