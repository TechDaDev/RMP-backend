from __future__ import annotations

import os

from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from config.version import API_VERSION


def _database_ready() -> tuple[bool, str | None]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True, None
    except Exception:
        return False, "database_unavailable"


def _redis_ready() -> tuple[bool, str | None]:
    broker_url = getattr(settings, "CELERY_BROKER_URL", "")
    if not broker_url or not str(broker_url).startswith(("redis://", "rediss://")):
        return True, "redis_not_configured"

    try:
        import redis

        client = redis.Redis.from_url(broker_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return True, None
    except Exception:
        return False, "redis_unavailable"


def _storage_ready() -> tuple[bool, str | None]:
    media_root = str(getattr(settings, "MEDIA_ROOT", ""))
    if not media_root:
        return False, "storage_not_configured"

    try:
        os.makedirs(media_root, exist_ok=True)
    except Exception:
        return False, "storage_unavailable"

    if not os.access(media_root, os.W_OK):
        return False, "storage_not_writable"

    return True, None


@extend_schema(tags=["Health"])
@api_view(["GET"])
@permission_classes([AllowAny])
def health_live(_request):
    return Response(
        {"status": "ok", "service": "alrafidain-backend", "version": API_VERSION},
        status=status.HTTP_200_OK,
    )


@extend_schema(tags=["Health"])
@api_view(["GET"])
@permission_classes([AllowAny])
def health_ready(_request):
    db_ok, db_error = _database_ready()
    if db_ok:
        return Response({"status": "ok", "components": {"database": {"status": "ok"}}})

    return Response(
        {
            "status": "degraded",
            "components": {"database": {"status": "error", "error": db_error}},
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@extend_schema(tags=["Health"])
@api_view(["GET"])
@permission_classes([AllowAny])
def health_deps(_request):
    db_ok, db_error = _database_ready()
    redis_ok, redis_error = _redis_ready()
    storage_ok, storage_error = _storage_ready()

    components = {
        "database": {"status": "ok" if db_ok else "error"},
        "redis": {"status": "ok" if redis_ok else "error"},
        "storage": {"status": "ok" if storage_ok else "error"},
    }

    if db_error:
        components["database"]["error"] = db_error
    if redis_error and not redis_ok:
        components["redis"]["error"] = redis_error
    if storage_error:
        components["storage"]["error"] = storage_error

    overall_ok = db_ok and redis_ok and storage_ok
    return Response(
        {
            "status": "ok" if overall_ok else "degraded",
            "components": components,
        },
        status=status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
