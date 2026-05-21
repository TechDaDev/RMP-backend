"""
WebSocket consumers for realtime events.

Two consumers:
1. UserRealtimeConsumer: User-level notifications and updates
2. ConsultationMessageConsumer: Consultation-level message and status events
"""

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from apps.consultations.models import Consultation

from .permissions import can_connect_consultation_messages, can_connect_user_socket

logger = logging.getLogger(__name__)


class UserRealtimeConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for user-level realtime events.

    Endpoint: /ws/user/?token=<jwt>

    Events:
    - notification.created
    - notification.unread_count
    - consultation.updated
    - prescription.updated
    - lab_order.updated
    - lab_result.released
    """

    async def connect(self):
        """Handle WebSocket connection."""
        user = self.scope.get("user", AnonymousUser())
        logger.info(
            "Realtime user socket connect attempt",
            extra={"user_id": str(getattr(user, "id", "anonymous"))},
        )

        # Check authentication
        if not can_connect_user_socket(user):
            await self.close()
            return

        self.user_id = user.id
        self.group_name = f"user_{self.user_id}"

        # Join user group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        logger.info(
            "Realtime user socket joined group",
            extra={"user_id": str(self.user_id), "group_name": self.group_name},
        )
        await self.accept()
        logger.debug(f"User {self.user_id} connected to realtime socket")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.debug(f"User {self.user_id} disconnected from realtime socket")

    async def receive_json(self, content):
        """
        Handle incoming WebSocket messages.

        Client should not send messages in MVP.
        Return error if attempted.
        """
        await self.send_json(
            {
                "type": "error",
                "message": "Sending messages through WebSocket is not supported. Use REST API.",
            }
        )

    # ── Event Handlers ─────────────────────────────────────────────────────

    async def notification_created(self, event):
        """Handle notification.created event."""
        logger.info(
            "Delivering notification.created to user socket",
            extra={"user_id": str(self.user_id)},
        )
        await self.send_json(event)

    async def notification_unread_count(self, event):
        """Handle notification.unread_count event."""
        await self.send_json(event)

    async def consultation_updated(self, event):
        """Handle consultation.updated event."""
        logger.info(
            "Delivering consultation.updated to user socket",
            extra={"user_id": str(self.user_id)},
        )
        await self.send_json(event)

    async def prescription_updated(self, event):
        """Handle prescription.updated event."""
        await self.send_json(event)

    async def lab_order_updated(self, event):
        """Handle lab_order.updated event."""
        await self.send_json(event)

    async def lab_result_released(self, event):
        """Handle lab_result.released event."""
        await self.send_json(event)


class ConsultationMessageConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for consultation-level chat and status events.

    Endpoint: /ws/consultations/<consultation_id>/messages/?token=<jwt>

    Events:
    - chat.message.created
    - chat.messages.read
    - consultation.closed

    Access:
    - Patient owner of consultation
    - Assigned doctor (once accepted)
    - No other access (pharmacist, laboratorian, other patients, etc.)
    """

    async def connect(self):
        """Handle WebSocket connection."""
        user = self.scope.get("user", AnonymousUser())
        logger.info(
            "Consultation socket connect attempt",
            extra={
                "user_id": str(getattr(user, "id", "anonymous")),
                "consultation_id": str(self.scope["url_route"]["kwargs"]["consultation_id"]),
            },
        )

        # Check authentication
        if not user.is_authenticated:
            await self.close()
            return

        self.user_id = user.id
        self.consultation_id = self.scope["url_route"]["kwargs"]["consultation_id"]

        # Get consultation from DB
        consultation = await self.get_consultation(self.consultation_id)
        if not consultation:
            await self.close()
            return

        # Check permissions
        has_access = await can_connect_consultation_messages(user, consultation)
        if not has_access:
            logger.warning(
                f"User {self.user_id} denied access to consultation {self.consultation_id}"
            )
            await self.close()
            return

        self.group_name = f"consultation_{self.consultation_id}"

        # Join consultation group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        logger.info(
            "Consultation socket joined group",
            extra={
                "user_id": str(self.user_id),
                "consultation_id": str(self.consultation_id),
                "group_name": self.group_name,
            },
        )
        await self.accept()
        logger.debug(f"User {self.user_id} connected to consultation {self.consultation_id} socket")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.debug(
            f"User {self.user_id} disconnected from consultation {self.consultation_id} socket"
        )

    async def receive_json(self, content):
        """
        Handle incoming WebSocket messages.

        Client should not send messages in MVP.
        Return error if attempted.
        """
        await self.send_json(
            {
                "type": "error",
                "message": "Sending messages through WebSocket is not supported. Use REST API.",
            }
        )

    # ── Event Handlers ─────────────────────────────────────────────────────

    async def chat_message_created(self, event):
        """Handle chat.message.created event."""
        logger.info(
            "Delivering chat.message.created to consultation socket",
            extra={
                "user_id": str(self.user_id),
                "consultation_id": str(self.consultation_id),
                "message_id": str(event.get("message", {}).get("id")),
            },
        )
        await self.send_json(event)

    async def chat_messages_read(self, event):
        """Handle chat.messages.read event."""
        logger.info(
            "Delivering chat.messages.read to consultation socket",
            extra={
                "user_id": str(self.user_id),
                "consultation_id": str(self.consultation_id),
                "reader_id": str(event.get("reader_id")),
            },
        )
        await self.send_json(event)

    async def consultation_closed(self, event):
        """Handle consultation.closed event."""
        await self.send_json(event)

    async def consultation_updated(self, event):
        """Handle consultation.updated event."""
        logger.info(
            "Delivering consultation.updated to consultation socket",
            extra={
                "user_id": str(self.user_id),
                "consultation_id": str(self.consultation_id),
            },
        )
        await self.send_json(event)

    # ── Database Query Helpers ─────────────────────────────────────────────

    @database_sync_to_async
    def get_consultation(self, consultation_id):
        """Get consultation from database."""
        try:
            return Consultation.objects.get(id=consultation_id)
        except Consultation.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error fetching consultation {consultation_id}: {e}")
            return None
