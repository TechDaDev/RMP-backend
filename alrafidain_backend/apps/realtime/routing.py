"""
WebSocket URL routing for realtime events.
"""

from django.urls import path

from .consumers import ConsultationMessageConsumer, UserRealtimeConsumer

websocket_urlpatterns = [
    path("ws/user/", UserRealtimeConsumer.as_asgi()),
    path(
        "ws/consultations/<uuid:consultation_id>/messages/",
        ConsultationMessageConsumer.as_asgi(),
    ),
]
