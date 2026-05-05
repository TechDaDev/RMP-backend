from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler


def _message_from_response(response):
    data = response.data
    if isinstance(data, dict):
        message = data.get("detail")
        if isinstance(message, (str, int, float)):
            return str(message)
    return "Request failed."


def _build_error_payload(code, message, details, request_id):
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "request_id": request_id,
    }


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    request = context.get("request")
    request_id = getattr(request, "request_id", None)

    if response is None:
        message = "An unexpected error occurred."
        if settings.ENVIRONMENT in {"local", "test"}:
            message = str(exc) or message
        return Response(
            _build_error_payload(
                code="server_error",
                message=message,
                details={},
                request_id=request_id,
            ),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    status_code = response.status_code
    details = {}
    code = "error"
    message = _message_from_response(response)

    if isinstance(exc, ValidationError):
        code = "validation_error"
        message = "Validation failed."
        if isinstance(response.data, dict):
            details = response.data
    elif isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        code = "authentication_failed"
    elif isinstance(exc, PermissionDenied):
        code = "permission_denied"
    elif isinstance(exc, NotFound):
        code = "not_found"
    elif isinstance(exc, Throttled):
        code = "throttled"
    elif status_code >= 500:
        code = "server_error"
        if settings.ENVIRONMENT in {"production", "staging"}:
            message = "An unexpected error occurred."

    response.data = _build_error_payload(
        code=code,
        message=message,
        details=details,
        request_id=request_id,
    )
    return response
