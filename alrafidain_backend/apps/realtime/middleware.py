"""
JWT Authentication Middleware for WebSocket connections.

Supports token extraction from query string or Authorization header.
"""

import logging
from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

logger = logging.getLogger(__name__)


@database_sync_to_async
def get_user_from_token(token_str):
    """
    Validate JWT token and return user.

    Args:
        token_str: JWT access token string

    Returns:
        User object if token is valid, AnonymousUser otherwise
    """
    try:
        jwt_auth = JWTAuthentication()
        validated_token = jwt_auth.get_validated_token(token_str)
        user = jwt_auth.get_user(validated_token)
        return user
    except InvalidToken as e:
        logger.debug(f"Invalid WebSocket token: {e}")
        return AnonymousUser()
    except Exception as e:
        logger.error(f"Error validating WebSocket token: {e}")
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Custom middleware for JWT authentication in WebSocket connections.

    Supports:
    1. Query string token: /ws/.../?token=<access_token>
    2. Authorization header: Authorization: Bearer <access_token>
    """

    async def __call__(self, scope, receive, send):
        # Extract token from query string or header
        token = self._get_token_from_scope(scope)

        if token:
            # Validate token and set user
            scope["user"] = await get_user_from_token(token)
        else:
            # No token provided
            scope["user"] = AnonymousUser()

        await super().__call__(scope, receive, send)

    @staticmethod
    def _get_token_from_scope(scope):
        """
        Extract JWT token from scope.

        Priority:
        1. Query string: ?token=<token>
        2. Authorization header: Authorization: Bearer <token>

        Args:
            scope: ASGI scope dict

        Returns:
            Token string or None
        """
        # Try query string first
        if scope["type"] == "websocket":
            query_string = scope.get("query_string", b"").decode()
            if query_string:
                query_params = parse_qs(query_string)
                if "token" in query_params and query_params["token"]:
                    return query_params["token"][0]

            # Try Authorization header
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            if auth_header.startswith("Bearer "):
                return auth_header[7:]  # Remove "Bearer " prefix

        return None


def JWTAuthMiddlewareStack(inner):
    """
    Wrapper to apply JWT auth middleware to ASGI application.

    Usage:
        application = ProtocolTypeRouter({
            "websocket": JWTAuthMiddlewareStack(
                URLRouter(websocket_urlpatterns)
            ),
        })
    """
    return JWTAuthMiddleware(AuthMiddlewareStack(inner))
