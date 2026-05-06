from contextvars import ContextVar

_request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(request_id: str):
    return _request_id_context.set(request_id or "-")


def reset_request_id(token) -> None:
    _request_id_context.reset(token)


def get_request_id() -> str:
    return _request_id_context.get()


class RequestIDLogFilter:
    """Inject request_id from contextvars into each log record."""

    def filter(self, record):
        record.request_id = get_request_id()
        return True
