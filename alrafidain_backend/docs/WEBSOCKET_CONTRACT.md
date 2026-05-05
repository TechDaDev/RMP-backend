# WebSocket Contract

## Phase 14: Realtime Events with Django Channels

This document defines the WebSocket contracts for the Al-Rafidain Medical Platform realtime layer.

**Important:** WebSocket is a **realtime delivery layer only**. All data creation and modification happens via REST API. WebSocket receives events and broadcasts them to connected clients.

---

## Table of Contents

- [Architecture](#architecture)
- [Connection URLs](#connection-urls)
  - [User Notifications Socket](#user-notifications-socket)
  - [Consultation Messages Socket](#consultation-messages-socket)
- [Event Types](#event-types)
- [Permission Rules](#permission-rules)
- [Client Integration Guide](#client-integration-guide)
- [Important: Message Creation](#important-message-creation)
- [Reconnection Strategy](#reconnection-strategy)
- [Token Handling](#token-handling)
- [Error Handling](#error-handling)
- [Production Deployment](#production-deployment)
- [Limitations (MVP Phase)](#limitations-mvp-phase)
- [Support and Debugging](#support-and-debugging)
- [Versioning](#versioning)

---

## Architecture

### REST + WebSocket Model

```
User Action
    ↓
REST API endpoint (data creation/modification)
    ↓
Database (source of truth)
    ↓
Service layer detects status change
    ↓
WebSocket event sent to group
    ↓
Connected clients receive update
```

**Key principle:** REST remains the source of truth. WebSocket only broadcasts realtime notifications of changes that already happened in the database.

---

## Connection URLs

### User Notifications Socket

**URL:**
```
/ws/user/?token=<access_token>
```

**Method:** Query string token (required)

**Alternative:** Authorization header (if client supports it)
```
Authorization: Bearer <access_token>
```

**Requirements:**
- User must be authenticated
- Valid JWT access token required
- Connects to user-level notification group

---

### Consultation Messages Socket

**URL:**
```
/ws/consultations/<consultation_id>/messages/?token=<access_token>
```

**Parameters:**
- `consultation_id` (UUID): Consultation ID
- `token` (query string, required): JWT access token

**Requirements:**
- User must be authenticated
- User must be consultation patient or assigned doctor
- Consultation must be in status: `accepted`, `doctor_responded`, or `closed`
- Only patient owner and assigned doctor have access

---

## Event Types

### 1. notification.created

**Endpoint:** User socket

**When:** A notification is created for the user

**Payload:**
```json
{
  "type": "notification.created",
  "notification": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "notification_type": "prescription",
    "priority": "normal",
    "title": "Prescription issued",
    "message": "A prescription QR code has been issued for you.",
    "data": {},
    "is_read": false,
    "created_at": "2026-05-04T10:30:00Z"
  }
}
```

**Fields:**
- `notification_type`: One of `prescription`, `consultation`, `lab_order`, `message`, `dispensing`
- `priority`: One of `low`, `normal`, `high`, `urgent`
- `is_read`: Boolean, initially `false`
- `data`: JSON object with context (e.g., related IDs)

**Note:** Does NOT include medication details in prescription notifications.

---

### 2. notification.unread_count

**Endpoint:** User socket

**When:** Unread notification count changes

**Payload:**
```json
{
  "type": "notification.unread_count",
  "unread_count": 3
}
```

**Note:** Sent whenever a notification is created or marked as read.

---

### 3. chat.message.created

**Endpoint:** Consultation socket

**When:** A message is sent in the consultation

**Payload:**
```json
{
  "type": "chat.message.created",
  "consultation_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "sender": {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "email": "doctor@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "user_type": "doctor"
    },
    "sender_role": "doctor",
    "message_type": "text",
    "body": "Here is my diagnosis...",
    "attachments": [],
    "is_read": false,
    "created_at": "2026-05-04T10:30:00Z"
  }
}
```

**Fields:**
- `sender_role`: One of `patient`, `doctor`
- `message_type`: One of `text`, `attachment`
- `attachments`: Array of file objects
- `is_read`: Initially `false` for recipients

**Note:** Message creation happens via REST API, not WebSocket. This event is **broadcast-only**.

---

### 4. chat.messages.read

**Endpoint:** Consultation socket

**When:** Messages are marked as read

**Payload:**
```json
{
  "type": "chat.messages.read",
  "consultation_id": "550e8400-e29b-41d4-a716-446655440000",
  "reader_id": "550e8400-e29b-41d4-a716-446655440002",
  "count": 2
}
```

**Fields:**
- `reader_id`: UUID of user who marked messages as read
- `count`: Number of messages marked as read

---

### 5. consultation.updated

**Endpoint:** User socket AND Consultation socket

**When:** Consultation status changes (accepted, doctor_responded, closed)

**Payload:**
```json
{
  "type": "consultation.updated",
  "consultation": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "accepted",
    "created_at": "2026-05-04T09:00:00Z",
    "accepted_at": "2026-05-04T10:00:00Z",
    "closed_at": null
  }
}
```

**Fields:**
- `status`: One of `submitted`, `accepted`, `doctor_responded`, `closed`
- `accepted_at`: ISO timestamp when accepted (null if not accepted)
- `closed_at`: ISO timestamp when closed (null if not closed)

**Note:** Sent to both patient and doctor.

---

### 6. prescription.updated

**Endpoint:** User socket (patient only)

**When:** Prescription status changes

**Payload:**
```json
{
  "type": "prescription.updated",
  "prescription": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "partially_dispensed",
    "expires_at": "2026-06-04T10:30:00Z",
    "fully_dispensed_at": null
  }
}
```

**Fields:**
- `status`: One of `issued`, `partially_dispensed`, `fully_dispensed`, `cancelled`, `expired`
- `expires_at`: ISO timestamp when prescription expires
- `fully_dispensed_at`: ISO timestamp when fully dispensed (null if not)

**Privacy:** Does NOT include medication names, dosages, frequencies, or instructions.

---

### 7. lab_order.updated

**Endpoint:** User socket (patient only)

**When:** Lab order status changes

**Payload:**
```json
{
  "type": "lab_order.updated",
  "lab_order": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "partially_completed",
    "test_count": 3,
    "expires_at": "2026-06-04T10:30:00Z",
    "fully_completed_at": null
  }
}
```

**Fields:**
- `status`: One of `issued`, `partially_completed`, `fully_completed`, `cancelled`, `expired`
- `test_count`: Number of tests in the order
- `expires_at`: ISO timestamp when lab order expires
- `fully_completed_at`: ISO timestamp when fully completed (null if not)

**Privacy:** Does NOT include test names, sample types, or instructions.

---

### 8. lab_result.released

**Endpoint:** User socket (patient only)

**When:** Lab result is released to patient by doctor

**Payload:**
```json
{
  "type": "lab_result.released",
  "lab_result": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "lab_order": "550e8400-e29b-41d4-a716-446655440001",
    "status": "released",
    "released_at": "2026-05-04T10:30:00Z"
  }
}
```

**Fields:**
- `lab_order`: UUID of associated lab order
- `status`: Always `released` in this event
- `released_at`: ISO timestamp when released

**Privacy:** Does NOT include test names, values, reference ranges, or doctor/laboratorian notes.

---

## Permission Rules

### User Socket Access

**Who can connect:**
- Authenticated users only

**What users receive:**
- Events for their own user ID
- Notifications
- Unread counts
- Consultation updates (for consultations they're involved in)
- Prescription updates (for their own prescriptions)
- Lab order updates (for their own lab orders)
- Lab result releases (for their own results)

---

### Consultation Socket Access

**Who can connect:**
- Authenticated users only
- Patient owner of the consultation
- Assigned doctor (once accepted)

**Who cannot connect:**
- Other patients
- Unassigned doctors
- Pharmacists
- Laboratorians
- Anonymous users

**Consultation status requirements:**
- Can connect to: `accepted`, `doctor_responded`, `closed`
- Cannot connect to: `submitted` (no assigned doctor yet)
- Read-only in `closed` status

**What users receive:**
- Chat messages in the consultation
- Messages marked as read
- Consultation status updates
- Other participant messages

---

## Client Integration Guide

### JavaScript/React Example

```javascript
const token = localStorage.getItem('access_token');

// Connect to user notifications
const userWs = new WebSocket(`wss://api.example.com/ws/user/?token=${token}`);

userWs.addEventListener('open', () => {
  console.log('Connected to notifications');
});

userWs.addEventListener('message', (event) => {
  const data = JSON.parse(event.data);
  
  switch(data.type) {
    case 'notification.created':
      console.log('New notification:', data.notification);
      updateUI();
      break;
    case 'notification.unread_count':
      console.log('Unread count:', data.unread_count);
      updateBadge(data.unread_count);
      break;
    case 'prescription.updated':
      console.log('Prescription status:', data.prescription.status);
      refreshPrescriptionList();
      break;
  }
});

userWs.addEventListener('error', (event) => {
  console.error('WebSocket error:', event);
});

userWs.addEventListener('close', () => {
  console.log('Disconnected from notifications');
  // Attempt to reconnect after delay
  setTimeout(() => reconnectWebSocket(), 5000);
});
```

### Connect to Consultation

```javascript
const consultationId = '550e8400-e29b-41d4-a716-446655440000';
const consultationWs = new WebSocket(
  `wss://api.example.com/ws/consultations/${consultationId}/messages/?token=${token}`
);

consultationWs.addEventListener('message', (event) => {
  const data = JSON.parse(event.data);
  
  switch(data.type) {
    case 'chat.message.created':
      addMessageToChat(data.message);
      break;
    case 'chat.messages.read':
      markMessagesAsReadInUI(data.count);
      break;
  }
});
```

---

## Important: Message Creation

**WebSocket does NOT support message creation in this phase.**

If client sends a message to the socket:
```json
{
  "type": "message",
  "body": "Hello"
}
```

**Response:**
```json
{
  "type": "error",
  "message": "Sending messages through WebSocket is not supported. Use REST API."
}
```

**How to send messages (correct way):**
```
POST /api/consultations/<id>/messages/
Content-Type: application/json
Authorization: Bearer <token>

{
  "body": "Hello, doctor"
}
```

---

## Reconnection Strategy

### Automatic Reconnection

When WebSocket disconnects:

1. **Immediate refresh:** Fetch latest data via REST API to fill gap
2. **Retry connection:** After 2-5 second exponential backoff
3. **Token refresh:** If authentication fails, refresh JWT token and retry
4. **Fallback to polling:** If reconnection fails after N attempts, poll REST API

### Example Implementation

```javascript
async function reconnectWebSocket() {
  try {
    // Fetch latest data from REST API
    const response = await fetch('/api/notifications/', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await response.json();
    
    // Update UI with latest data
    updateNotificationUI(data);
    
    // Attempt WebSocket reconnection
    connectWebSocket();
  } catch (error) {
    console.error('Reconnection failed:', error);
    // Retry after delay
    setTimeout(reconnectWebSocket, 5000);
  }
}
```

---

## Token Handling

### Access Token in URL

```
/ws/user/?token=<access_token>
```

**Security notes:**
- Use HTTPS/WSS only (encrypted connection)
- Tokens in URLs may be logged; consider header-based auth if available
- Token must be valid JWT access token
- Token expiration is NOT checked continuously; reconnect on expiration

### Token Refresh

When REST API returns 401 (token expired):

1. Use refresh token to get new access token
2. Reconnect WebSocket with new token
3. Fetch latest data from REST API

```javascript
async function handleTokenExpiration() {
  const newToken = await refreshAccessToken();
  localStorage.setItem('access_token', newToken);
  
  // Disconnect old WebSocket
  userWs.close();
  
  // Reconnect with new token
  connectWebSocket(newToken);
}
```

---

## Error Handling

### Connection Errors

- **401 Unauthorized:** Token invalid or expired. Refresh token and reconnect.
- **403 Forbidden:** User lacks permission. Verify user type and consultation access.
- **404 Not Found:** Consultation doesn't exist or is deleted.
- **500 Server Error:** Temporary issue. Retry with exponential backoff.

### Network Errors

- Connection drops: Auto-reconnect after delay
- No message for X seconds: Connection might be dead. Reconnect.
- Message rate exceeded: Server closing connection. Wait before reconnecting.

---

## Production Deployment

### Requirements

- **TLS/SSL:** Use WSS (WebSocket Secure), not WS
- **Redis:** Production-grade Redis for channel layer
- **CORS:** Configure allowed origins
- **Rate limiting:** Consider rate limits on WebSocket connections
- **Load balancing:** Use sticky sessions or shared channel layer (Redis)
- **Monitoring:** Track connection counts, message latency, errors

### Example NGINX Configuration

```nginx
upstream django_asgi {
    server unix:/tmp/daphne.sock;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /ws/ {
        proxy_pass http://django_asgi;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Optional: connection timeout
        proxy_read_timeout 86400;
    }

    location / {
        proxy_pass http://django_asgi;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Limitations (MVP Phase)

This WebSocket implementation has intentional limitations:

- ❌ No message creation over WebSocket (use REST API)
- ❌ No typing indicators
- ❌ No online/offline presence
- ❌ No WebRTC/audio/video calls
- ❌ No patient-facing AI
- ✅ Realtime event delivery
- ✅ Notification broadcasting
- ✅ Message/consultation status updates
- ✅ Lab result releases
- ✅ Prescription/lab order updates

Future phases may add these capabilities.

---

## Support and Debugging

### Enable Debug Logging

In `settings/local.py`:
```python
LOGGING = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'apps.realtime': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

### Test WebSocket Connection

```bash
# Using wscat (npm install -g wscat)
wscat -c 'wss://api.example.com/ws/user/?token=YOUR_TOKEN'

# Receive a message and see it in console
```

### Monitor Channel Layer

```python
from channels.layers import get_channel_layer

channel_layer = get_channel_layer()
# Check group membership, send test messages, etc.
```

---

## Versioning

**Current Version:** 0.1.0 (Phase 14 MVP)

This contract matches the API contract version `v0.1.0`.

Changes to this contract will be documented in release notes.
