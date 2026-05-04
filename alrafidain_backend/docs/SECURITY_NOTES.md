# Security Notes

## Security Model Overview
This backend applies layered security using JWT authentication, role-based access control, object-level permission checks in service/view logic, and audit logging for sensitive actions.

## Authentication and JWT
- Authentication uses JWT access tokens for API requests.
- Login requires active accounts; inactive users cannot log in.
- Account activation and password reset OTPs are time-bound and one-time use.
- Regenerated OTPs invalidate older unused OTPs for the same purpose.

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
3. Rotate the salt if a previous salt is suspected to be compromised (hashes will change on next export).
