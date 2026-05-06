import uuid

from apps.common.logging import reset_request_id, set_request_id


class RequestIDMiddleware:
    """Attach request IDs to requests and responses for traceability."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.request_id = request_id
        token = set_request_id(request_id)

        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)

        response["X-Request-ID"] = request_id
        return response
