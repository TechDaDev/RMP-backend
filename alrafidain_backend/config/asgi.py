"""
ASGI config for config project.

Supports both HTTP (REST) and WebSocket (realtime).

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

from apps.realtime.middleware import JWTAuthMiddlewareStack
from apps.realtime.routing import websocket_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        # HTTP - uses default Django ASGI app
        "http": django_asgi_app,
        # WebSocket - uses Channels with JWT auth middleware
        "websocket": JWTAuthMiddlewareStack(
            URLRouter(websocket_urlpatterns),
        ),
    }
)

