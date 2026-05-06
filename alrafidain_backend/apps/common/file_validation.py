from __future__ import annotations

import mimetypes
import os

from rest_framework import serializers


def validate_file_size(file_obj, max_size_mb: int):
    max_bytes = max_size_mb * 1024 * 1024
    file_size = getattr(file_obj, "size", None)
    if file_size is None:
        return
    if file_size > max_bytes:
        raise serializers.ValidationError(
            f"File is too large. Maximum allowed size is {max_size_mb} MB."
        )


def validate_file_extension(file_obj, allowed_extensions):
    ext = os.path.splitext(getattr(file_obj, "name", ""))[1].lower()
    normalized = {
        e.lower() if str(e).startswith(".") else f".{str(e).lower()}"
        for e in allowed_extensions
    }
    if ext not in normalized:
        allowed = ", ".join(sorted(normalized))
        raise serializers.ValidationError(
            f"Unsupported file extension '{ext or 'unknown'}'. Allowed extensions: {allowed}."
        )


def validate_content_type(file_obj, allowed_content_types):
    allowed = {str(v).lower() for v in allowed_content_types}
    content_type = (getattr(file_obj, "content_type", "") or "").lower()

    if not content_type:
        guessed, _ = mimetypes.guess_type(getattr(file_obj, "name", ""))
        content_type = (guessed or "").lower()

    if not content_type or content_type not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise serializers.ValidationError(
            "Unsupported file content type. "
            f"Allowed content types: {allowed_text}."
        )


def validate_uploaded_file(
    file_obj,
    *,
    allowed_extensions,
    allowed_content_types,
    max_size_mb: int,
):
    validate_file_size(file_obj, max_size_mb=max_size_mb)
    validate_file_extension(file_obj, allowed_extensions=allowed_extensions)
    validate_content_type(file_obj, allowed_content_types=allowed_content_types)
