from rest_framework import status as http_status
from rest_framework.response import Response


def success_response(message: str = None, data=None, status_code: int = http_status.HTTP_200_OK) -> Response:
    payload = {"success": True}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return Response(payload, status=status_code)


def error_response(message: str = None, errors=None, status_code: int = http_status.HTTP_400_BAD_REQUEST) -> Response:
    payload = {"success": False}
    if message is not None:
        payload["message"] = message
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=status_code)
