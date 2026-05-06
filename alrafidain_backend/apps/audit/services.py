from __future__ import annotations

import hashlib
import json
from datetime import UTC
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from django.http import HttpRequest


def _get_client_ip(request: HttpRequest) -> str | None:
    if request is None:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _get_user_agent(request: HttpRequest) -> str:
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")


def _get_request_id(request: HttpRequest, metadata: dict | None = None) -> str:
    if request is not None:
        request_id = (
            request.META.get("HTTP_X_REQUEST_ID")
            or request.META.get("X_REQUEST_ID")
            or request.headers.get("X-Request-ID", "")
            if hasattr(request, "headers")
            else ""
        )
        if request_id:
            return str(request_id)

    if metadata:
        maybe_id = metadata.get("request_id")
        if maybe_id:
            return str(maybe_id)

    return ""


_SENSITIVE_KEY_TOKENS = {
    "password",
    "token",
    "access",
    "refresh",
    "secret",
    "key",
    "file_content",
    "content",
    "raw_text",
    "extracted_text",
    "diagnosis_detail",
    "medication_details",
}
_MAX_METADATA_DEPTH = 3
_MAX_STRING_LENGTH = 512
_MAX_LIST_ITEMS = 20


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    if normalized in _SENSITIVE_KEY_TOKENS:
        return True
    return any(token in normalized for token in ("password", "token", "secret"))


def _truncate(value: str, max_len: int = _MAX_STRING_LENGTH) -> str:
    if len(value) <= max_len:
        return value
    return f"{value[:max_len]}..."


def _sanitize_value(value, depth: int):
    if depth > _MAX_METADATA_DEPTH:
        return "[TRUNCATED]"

    if value is None or isinstance(value, bool | int | float):
        return value

    if isinstance(value, str):
        return _truncate(value)

    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            key_str = str(key)
            if _is_sensitive_key(key_str):
                sanitized[key_str] = "[REDACTED]"
                continue
            sanitized[key_str] = _sanitize_value(item, depth + 1)
        return sanitized

    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item, depth + 1) for item in list(value)[:_MAX_LIST_ITEMS]]

    return _truncate(str(value), 200)


def sanitize_audit_metadata(metadata: dict | None) -> dict:
    if not metadata:
        return {}

    sanitized = _sanitize_value(metadata, depth=0)
    if not isinstance(sanitized, dict):
        return {"summary": _sanitize_value(sanitized, depth=1)}
    return sanitized


def _build_hash_payload(
    *,
    previous_hash: str,
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str,
    created_at,
    metadata: dict,
    request_id: str,
) -> str:
    normalized_created_at = created_at.astimezone(UTC).isoformat(timespec="seconds")
    canonical = {
        "previous_hash": previous_hash,
        "actor_id": actor_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "created_at": normalized_created_at,
        "metadata": metadata,
        "request_id": request_id,
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash_payload(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_audit_log(
    actor=None,
    action: str = "",
    target=None,
    metadata: dict | None = None,
    request=None,
) -> None:
    from .models import AuditLog

    target_type = ""
    target_id = ""
    if target is not None:
        target_type = type(target).__name__
        target_id = str(getattr(target, "pk", ""))

    sanitized_metadata = sanitize_audit_metadata(metadata or {})
    request_id = _get_request_id(request, sanitized_metadata)
    created_at = timezone.now()

    with transaction.atomic():
        previous_log = AuditLog.objects.select_for_update().order_by("-created_at", "-id").first()
        previous_hash = previous_log.current_hash if previous_log else ""
        payload = _build_hash_payload(
            previous_hash=previous_hash,
            actor_id=str(getattr(actor, "pk", "") or ""),
            action=action,
            target_type=target_type,
            target_id=target_id,
            created_at=created_at,
            metadata=sanitized_metadata,
            request_id=request_id,
        )
        current_hash = _hash_payload(payload)

        AuditLog.objects.create(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata=sanitized_metadata,
            ip_address=_get_client_ip(request),
            user_agent=_get_user_agent(request),
            previous_hash=previous_hash,
            current_hash=current_hash,
            created_at=created_at,
        )


def record_security_event(
    *,
    actor=None,
    action: str,
    target=None,
    request=None,
    metadata: dict | None = None,
) -> None:
    safe_metadata = sanitize_audit_metadata(metadata or {})
    safe_metadata.setdefault("category", "security")

    request_id = _get_request_id(request, safe_metadata)
    if request_id:
        safe_metadata.setdefault("request_id", request_id)

    if request is not None:
        ip_address = _get_client_ip(request)
        user_agent = _get_user_agent(request)
        if ip_address:
            safe_metadata.setdefault("ip_address", ip_address)
        if user_agent:
            safe_metadata.setdefault("user_agent", _truncate(user_agent, 256))

    if target is not None:
        safe_metadata.setdefault("target_model", type(target).__name__)
        safe_metadata.setdefault("target_id", str(getattr(target, "pk", "")))

    create_audit_log(
        actor=actor,
        action=action,
        target=target,
        metadata=safe_metadata,
        request=request,
    )


def verify_audit_log_integrity(limit: int | None = None) -> dict:
    from .models import AuditLog

    logs_qs = AuditLog.objects.order_by("created_at", "id")
    if limit is not None:
        logs_qs = logs_qs[:limit]

    checked = 0
    expected_previous_hash = ""

    for log in logs_qs:
        checked += 1

        if not log.current_hash and not log.previous_hash:
            # Legacy rows from before hash-chaining rollout.
            continue

        sanitized_metadata = sanitize_audit_metadata(log.metadata or {})
        request_id = _get_request_id(None, sanitized_metadata)
        expected_payload = _build_hash_payload(
            previous_hash=expected_previous_hash,
            actor_id=str(log.actor_id or ""),
            action=log.action,
            target_type=log.target_type,
            target_id=log.target_id,
            created_at=log.created_at,
            metadata=sanitized_metadata,
            request_id=request_id,
        )
        expected_hash = _hash_payload(expected_payload)

        if log.previous_hash != expected_previous_hash:
            return {
                "valid": False,
                "checked": checked,
                "first_error_id": str(log.pk),
                "error": "previous_hash_mismatch",
            }

        if log.current_hash != expected_hash:
            return {
                "valid": False,
                "checked": checked,
                "first_error_id": str(log.pk),
                "error": "current_hash_mismatch",
            }

        expected_previous_hash = log.current_hash

    return {
        "valid": True,
        "checked": checked,
        "first_error_id": None,
        "error": None,
    }
