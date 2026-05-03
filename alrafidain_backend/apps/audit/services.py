from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest


def _get_client_ip(request: "HttpRequest") -> str | None:
    if request is None:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _get_user_agent(request: "HttpRequest") -> str:
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")


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

    AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata or {},
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )
