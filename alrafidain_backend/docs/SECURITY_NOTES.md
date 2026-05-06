# Security Notes

---

## Table of Contents

- [Security Model Overview](#security-model-overview)
- [Authentication and JWT](#authentication-and-jwt)
- [WebSocket Transport Security](#websocket-transport-security)
- [Role-Based Access Rules](#role-based-access-rules)
- [Professional Verification](#professional-verification)
- [Consultation Privacy](#consultation-privacy)
- [Prescription QR Privacy](#prescription-qr-privacy)
- [Lab Order QR Privacy](#lab-order-qr-privacy)
- [Lab Result Release Rules](#lab-result-release-rules)
- [Patient Medical Record Access](#patient-medical-record-access)
- [Notification Privacy](#notification-privacy)
- [Realtime Event Privacy](#realtime-event-privacy)
- [Audit Logging](#audit-logging)
- [Rate Limiting](#rate-limiting)
- [Known MVP Limitations](#known-mvp-limitations)
- [Future Security Work](#future-security-work)
- [Phase 12E — Dataset Export Privacy & Security](#phase-12e--dataset-export-privacy--security)

---

## Security Model Overview
This backend applies layered security using JWT authentication, role-based access control, object-level permission checks in service/view logic, and audit logging for sensitive actions.

## Authentication and JWT
- Authentication uses JWT access tokens for API requests.
- WebSocket authentication uses the same JWT validation path (SimpleJWT) via custom Channels middleware.
- Login requires active accounts; inactive users cannot log in.
- Account activation and password reset OTPs are time-bound and one-time use.
- Regenerated OTPs invalidate older unused OTPs for the same purpose.

## WebSocket Transport Security
- Production must use `wss://` (TLS) for all realtime connections.
- Do not expose authenticated WebSocket endpoints over plain `ws://` outside local development.
- JWT tokens used in WebSocket connection setup should be short-lived access tokens.
- On token refresh, clients should reconnect using a new access token.

## Role-Based Access Rules
- Access is constrained by user role: patient, doctor, pharmacist, laboratorian.
- Clinical endpoints enforce role checks and ownership/assignment checks.
- Unauthorized access returns denied/not found style responses to reduce information leakage.

## Professional Verification
- Professional actions require approved profile status.
- Unapproved doctors cannot accept consultations or create prescriptions/lab orders.
- Unapproved pharmacists/laboratorians cannot process QR scan workflows.

## Consultation Privacy
- Patients can access only their own consultations.
- Doctors can access only consultations assigned to them.
- Disease prediction fields are not exposed in patient consultation detail serializer.
- Consultation chat sockets enforce the same boundaries: only consultation patient and assigned doctor can connect.

## Prescription QR Privacy
- Prescription QR token is generated with `secrets.token_urlsafe(32)` and stored as a unique token.
- Token payload contains no medication details.
- Patient prescription responses do not expose medication item fields.
- Pharmacists can scan only when authenticated and approved.
- Scan responses include only pending items; dispensed items are hidden.
- Locked/expired/cancelled prescriptions return no remaining items.

## Lab Order QR Privacy
- Lab order QR token is generated with `secrets.token_urlsafe(32)` and stored as a unique token.
- Token payload contains no lab test details.
- Patient lab order responses do not expose test item details.
- Laboratorians can scan only when authenticated and approved.
- Scan responses include only pending tests; completed tests are hidden.
- Locked/expired/cancelled lab orders return no remaining items.

## Lab Result Release Rules
- Patients can view lab results only after doctor release.
- Patient result serializer excludes `laboratorian_notes` and `doctor_notes`.
- Only the ordering doctor can review/release/link results.
- Only the original result laboratorian can correct the result in MVP.

## Patient Medical Record Access
- Patients can access only their own medical record endpoint.
- Doctors can access patient record only when authorized by consultation-based checks.
- Laboratorians cannot access full medical records; they only verify blood group through dedicated endpoint.
- Pharmacists cannot access medical records.

## Notification Privacy
- Users list/read only their own notifications.
- Notification payloads for prescriptions/lab orders/lab results use IDs and status metadata, not sensitive values.
- Prescription notifications do not include medication details.
- Lab order notifications do not include test instructions/details.
- Lab result release notifications do not include result values.

## Realtime Event Privacy
- WebSocket is delivery-only in this phase; data creation remains REST-only.
- Realtime events are emitted after database commit (`transaction.on_commit`) to avoid inconsistent state exposure.
- User socket events are scoped by `user_<id>` channel group.
- Consultation socket events are scoped by `consultation_<id>` channel group.
- Event payloads intentionally exclude sensitive clinical detail for patient-facing updates.

## Audit Logging
- Sensitive actions are recorded in audit logs (authentication, consultation actions, scans, dispensing/completion, record updates).
- Audit logs support traceability and incident investigation.

## Rate Limiting
- Global DRF throttles:
  - `anon`: `100/hour`
  - `user`: `1000/hour`
- Scoped throttles for sensitive endpoints:
  - `login`: `10/minute`
  - `otp`: `5/minute`
  - `password_reset`: `5/minute`
  - `qr_scan`: `30/minute`
- Applied to login/OTP/password reset endpoints and QR scan endpoints.
- WebSocket connection/message rate limiting is not yet enforced at Channels middleware/consumer level in MVP.
- Recommended production hardening: connection caps per IP/user at reverse proxy (for example NGINX) and short idle timeouts.

## Known MVP Limitations
- AI/RAG is not implemented yet.
- No external SMS/email/push integration yet.
- No facility directory yet.
- No production-grade deployment hardening yet.

## Future Security Work
- Object-level permission audit middleware.
- Field-level encryption for selected medical data.
- Refresh token rotation and blacklisting.
- Two-factor authentication for professionals/admins.
- Device/session management.
- Production audit retention policy.
- External penetration testing.
- Full OWASP API Security review.

---

## Phase 12E — Dataset Export Privacy & Security

### Anonymization

- Doctor PKs and consultation/lab object IDs are hashed with SHA-256 when `anonymize=True` (the default).
- The hash input is `EXPORT_HASH_SALT + ":" + value` so that re-identification from the hash alone is infeasible without the salt.
- Set `EXPORT_HASH_SALT` to a strong random value in production (not the `SECRET_KEY` default).

### What is never exported

- Patient names, emails, phone numbers, or national IDs.
- Raw pgvector embeddings.
- Raw doctor PKs (when `anonymize=True`).
- Raw prescription or lab values tied to patient identity.

### Access control

- Analytics and export endpoints require `is_staff` or `is_superuser`.
- All export actions are logged via `AuditLog` (`rag_dataset_exported`).
- The management command (`export_rag_dataset`) should only be executed by trusted operators with server access.

### Recommended production steps

1. Generate a random `EXPORT_HASH_SALT` with `openssl rand -hex 32`.
2. Store it in your secret manager and inject via environment.
---

## Known Dependency Vulnerability — CVE-2026-42304 (Twisted 25.5.0)

**Status**: Accepted temporary risk, pending upstream stable release.  
**Last reviewed**: 2026-05-06  

### Dependency path

```
requirements/base.in
  └── daphne (direct)
        └── twisted 25.5.0 (transitive)
```

### CVE details

| Field | Value |
|---|---|
| CVE | CVE-2026-42304 |
| Affected | twisted 25.5.0 |
| Reported fix | 26.4.0rc2 (release candidate — not stable) |
| Latest stable on PyPI | 25.5.0 |
| Source | pip-audit |

### Reachability assessment

- **REACHABLE IN PRODUCTION** — Twisted is used by Daphne, which is the ASGI server for HTTP + WebSocket traffic.
- The project requires WebSockets for realtime consultation messaging (`ws/consultations/<id>/messages/`) and user events (`ws/user/`). Daphne cannot be removed without losing this functionality.
- Daphne is deployed on a **separate internal port** (8001) behind a reverse proxy (Nginx/Caddy/Ingress), which provides TLS termination and traffic filtering.
- Clients do not connect directly to Daphne; all connections pass through the reverse proxy.

### Why upgrade was not performed

- The only known fix is `26.4.0rc2`, a release candidate not suited for production without explicit testing.
- `pip index versions twisted` confirms no stable version newer than 25.5.0 is available on PyPI as of 2026-05-06.
- Upgrading to an RC without stability guarantees is a higher risk than the documented mitigations below.

### Mitigations in place

1. Daphne is bound to an internal interface/port only; not directly internet-facing.
2. TLS termination is handled at the reverse proxy (wss:// required in production per WebSocket security notes).
3. JWT authentication is required on all WebSocket endpoints; unauthenticated connections are rejected at the Channels middleware layer.
4. Rate limiting and connection caps are recommended at the reverse proxy level (see Known MVP Limitations).
5. Request-ID correlation is active for all ASGI traffic for incident traceability.

### Remediation action

- **Monitor** the upstream Twisted project for a stable 26.x.x release.
- **Pin** `twisted>=26.x.x` in `requirements/base.in` when a stable fix is released and tests confirm compatibility.
- **Do not suppress** this finding in pip-audit; keep it visible for operator awareness.
- Review this entry again when the next stable Twisted release is published.3. Rotate the salt if a previous salt is suspected to be compromised (hashes will change on next export).
