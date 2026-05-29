# Staff / Admin Profile Integration Guide

**Last Updated:** May 2026  
**API Version:** 0.1.0

---

## Overview

The Al-Rafidain Medical Platform now supports a dedicated **Staff/Admin** user type with granular role-based access control (RBAC). Unlike patient and professional users, staff accounts:

- Do **not** require `UserProfile` (no shared address/phone data).
- Use a role-based `StaffProfile` with explicit permission flags.
- Support role hierarchy (supervisor relationships).
- Track audit and accountability details.

---

## Admin User for Local/Testing

**Credentials:**
```
Email:    admin@rmp.local
Password: Admin1234!
Type:     staff
Role:     System Administrator
```

**Access Level:** Full platform access (all permissions enabled by default).

---

## Staff Profile Structure

When a staff user authenticates via `POST /api/accounts/login/`, the response includes:

```json
{
  "success": true,
  "data": {
    "access": "<jwt_access_token>",
    "refresh": "<jwt_refresh_token>",
    "user": {
      "id": "uuid",
      "email": "admin@rmp.local",
      "first_name": "Admin",
      "last_name": "User",
      "user_type": "staff",
      "is_active": true
    }
  }
}
```

### Fetch Current Staff Profile

```http
GET /api/profiles/me/
Authorization: Bearer <access_token>
```

**Response (staff user):**
```json
{
  "success": true,
  "data": {
    "user": {
      "id": "...",
      "email": "admin@rmp.local",
      "user_type": "staff",
      "first_name": "Admin",
      "full_name": "Admin User",
      ...
    },
    "user_profile": null,
    "role_profile": {
      "id": "...",
      "staff_role": "system_admin",
      "role_display": "System Administrator",
      "department": "Administration",
      "can_approve_professionals": true,
      "can_manage_knowledge_base": true,
      "can_export_datasets": true,
      "can_view_audit_logs": true,
      "hire_date": "2025-01-01",
      "has_completed_training": true,
      "allowed_admin_sections": [
        "finance_dashboard",
        "wallet_transactions",
        "payment_intents",
        "manual_recharge",
        "provider_earnings"
      ]
    },
    "completion": {
      "shared_profile_complete": false,
      "role_profile_complete": false,
      "overall_complete": false,
      "missing_shared_fields": [...],
      "missing_role_fields": []
    },
    "verification": {
      "required": false,
      "status": null,
      "is_approved": null
    }
  }
}
```

**Key observations:**
- `user_profile` is `null` for staff users.
- `role_profile` contains `StaffProfile` data.
- `role_profile.allowed_admin_sections` is the canonical backend list for rendering staff dashboard sections.
- `verification` is not required for staff (always `required: false`).
- `completion` shows overall_complete as false (staff are not completeness-tracked like other roles).

---

## Frontend Implementation Checklist

### 1. **User Login & Routing**

After login, check `user_type`:

```typescript
const loginResponse = await post('/api/accounts/login/', { email, password });
const { user_type } = loginResponse.data.user;

if (user_type === 'staff') {
  // Route to admin/staff dashboard
  navigate('/admin/dashboard');
} else if (user_type === 'patient') {
  navigate('/patient/dashboard');
} else if (user_type === 'doctor') {
  navigate('/doctor/dashboard');
}
// etc.
```

### 2. **Profile Display**

When rendering the user's profile/settings page:

```typescript
const response = await get('/api/profiles/me/');
const { user, role_profile, user_type } = response.data;

if (user_type === 'staff' && role_profile) {
  // Display staff profile fields
  displayText(`Role: ${role_profile.role_display}`);
  displayText(`Department: ${role_profile.department}`);
  displayCheckbox(`Can approve professionals: ${role_profile.can_approve_professionals}`);
  displayCheckbox(`Can manage knowledge base: ${role_profile.can_manage_knowledge_base}`);
  displayCheckbox(`Can export datasets: ${role_profile.can_export_datasets}`);
  displayCheckbox(`Can view audit logs: ${role_profile.can_view_audit_logs}`);
  displayText(`Hire date: ${role_profile.hire_date}`);
  displayText(`Training completed: ${role_profile.has_completed_training}`);
}
```

### 3. **Feature Access Control**

Use the permission flags from `role_profile` to show/hide staff features:

**Verification Review (requires `can_approve_professionals`):**
```typescript
if (user.user_type === 'staff' && role_profile?.can_approve_professionals) {
  // Show /admin/verifications link
}
```

**Knowledge Base Management (requires `can_manage_knowledge_base`):**
```typescript
if (user.user_type === 'staff' && role_profile?.can_manage_knowledge_base) {
  // Show /admin/knowledge-base link
}
```

**Analytics & Exports (requires `can_export_datasets`):**
```typescript
if (user.user_type === 'staff' && role_profile?.can_export_datasets) {
  // Show /admin/analytics, /admin/rag-feedback links
}
```

**Financial Operations (requires finance section access):**
```typescript
const sections = role_profile?.allowed_admin_sections ?? [];
if (user.user_type === 'staff' && sections.includes('finance_dashboard')) {
  // Show finance dashboard entry
}
if (sections.includes('wallet_transactions')) {
  // Show wallet transactions section
}
if (sections.includes('payment_intents')) {
  // Show payment intents section
}
if (sections.includes('manual_recharge')) {
  // Show manual recharge section
}
if (sections.includes('provider_earnings')) {
  // Show provider earnings section
}
```

**Frontend wallet lookup flow for Financial users:**
```typescript
// 1. Search wallets before showing recharge/ledger actions
GET /api/payments/admin/wallets/?search=<email-or-name>

// 2. Render wallet result rows with:
//    id, user, user_email, user_full_name, cached_balance, status

// 3. When finance chooses a wallet:
//    - use wallet.id for transaction drill-down
//    - use wallet.user for manual recharge payloads

GET /api/payments/wallet/transactions/?wallet=<wallet.id>

POST /api/payments/admin/manual-recharge/
{
  "user": wallet.user,
  "amount": "50000.00",
  "description": "Manual recharge"
}
```

**Frontend recharge request flow (patient -> finance review):**
```typescript
// Patient submits request with transfer receipt (multipart/form-data)
POST /api/payments/wallet/recharge-requests/
FormData:
  amount: "50000.00"
  note: "Bank transfer reference 12345"
  receipt_file: <File>

// Patient tracks own requests
GET /api/payments/wallet/recharge-requests/
GET /api/payments/wallet/recharge-requests/<request_id>/

// Finance queue (financial/system admin only)
GET /api/payments/wallet/recharge-requests/?status=pending_review
GET /api/payments/wallet/recharge-requests/?email=<patient-email>

// Finance decision
POST /api/payments/wallet/recharge-requests/<request_id>/approve/
{ "review_note": "Receipt verified" }

POST /api/payments/wallet/recharge-requests/<request_id>/reject/
{ "review_note": "Receipt mismatch" }
```

Recharge request UI rules:
- Patient can submit only one open request at a time.
- Require receipt upload before submit.
- Show `receipt_file_url` to patient only while status is `pending_review`.
- Hide receipt link when patient request becomes `approved` or `rejected`.
- Finance reviewers always receive `receipt_file_url` and can inspect/download.

Recommended frontend behavior:
- Do not ask finance staff to type raw UUIDs manually.
- Add a wallet search box by email / name on the finance dashboard.
- Show wallet ID in the result details panel or copy action for audit/debug use.
- Disable recharge action when wallet status is `frozen` or `closed` unless your UI intentionally supports exception handling.
- Keep the selected wallet in page state and reuse it for wallet transactions, payment intents, and manual recharge actions.

**Audit Logs (requires `can_view_audit_logs`):**
```typescript
if (user.user_type === 'staff' && role_profile?.can_view_audit_logs) {
  // Show /admin/audit-logs link
}
```

### 4. **Admin Dashboard Layout**

Suggested structure for `/admin/` routes:

```
/admin/
├── /dashboard                    # Summary & quick stats
├── /verifications                # Review & approve professionals (requires permission)
├── /knowledge-base/approve       # Approve documents for RAG (requires permission)
├── /knowledge-base/archive       # Archive inactive documents
├── /analytics                    # RAG feedback review, query stats (requires permission)
├── /analytics/export             # Dataset export tool (requires permission)
├── /audit-logs                   # Full platform audit trail (requires permission)
└── /settings/staff               # Manage other staff (superuser only)
```

### 5. **Staff User Management**

Staff creation and management is **not yet available** via public API (planned for Phase X).

Current available endpoints for staff info:
- `GET /api/profiles/me/` — Fetch authenticated user's own staff profile

Future endpoints (to be implemented):
- `POST /api/admin/staff/` — Create new staff user (superuser only)
- `GET /api/admin/staff/` — List staff (superuser only)
- `GET /api/admin/staff/{id}/` — Staff detail (superuser only)
- `PUT /api/admin/staff/{id}/` — Update staff role/permissions (superuser only)

---

## Role Definitions

| Role | Purpose | Default Permissions |
|---|---|---|
| **System Administrator** | Full platform access, all features, staff management | All enabled |
| **Financial** | Payment operations only (wallets/intents/recharge/earnings) | Finance sections only |
| **Verification Officer** | Review and approve professional profiles | ✓ `can_approve_professionals` |
| **Knowledge Base Manager** | Curate documents, approve for RAG | ✓ `can_manage_knowledge_base` |
| **Analytics Officer** | Monitor RAG feedback, export datasets | ✓ `can_export_datasets` |
| **Support Specialist** | User support, escalations | — |
| **Compliance Officer** | Audit log review, security reporting | ✓ `can_view_audit_logs` |

---

## Error Handling

### Unauthorized Access (403)

If a staff user without required permissions attempts to access a restricted feature:

```json
{
  "success": false,
  "message": "Permission denied.",
  "errors": {}
}
```

**Frontend response:** Show alert: "You don't have permission to access this feature. Contact your administrator."

### Invalid User Type (Should Not Happen)

If a user with `user_type != 'staff'` somehow reaches an admin-only route:

```json
{
  "success": false,
  "message": "Only staff members can access this endpoint.",
  "errors": {}
}
```

**Frontend response:** Redirect to appropriate dashboard for that user type.

---

## Testing with Postman

**1. Login as admin:**
```http
POST http://localhost:8000/api/accounts/login/
Content-Type: application/json

{
  "email": "admin@rmp.local",
  "password": "Admin1234!"
}
```

**2. Get staff profile:**
```http
GET http://localhost:8000/api/profiles/me/
Authorization: Bearer <access_token>
```

Expected: `user_type: "staff"`, `role_profile` with `staff_role: "system_admin"`.

---

## Notes for Frontend Team

1. **No user profile completion tracking for staff** — Unlike doctors/pharmacists, staff users don't have a `UserProfile` and aren't checked for completion.

2. **Permission flags + staff role are the source of truth** — Always check boolean flags (`can_approve_professionals`, etc.) and `staff_role` (for financial-only sections) to decide what features to show.

3. **Role field is read-only** — The `staff_role` is assigned server-side; frontend cannot modify it.

4. **Supervisor relationship is optional** — If `supervisor` is provided, display it in staff detail view. For test users, it's `null`.

5. **Last active tracking** — `last_active` is auto-updated on every request. Use it to show "Last active: 5 minutes ago" UI.

---

## Migration from Old Admin Setup

If you had admin as `user_type: doctor`:
- ✅ Old `admin@rmp.local` still works via seed script
- ✅ Profile endpoint handles both old and new setups
- ❌ New staff features only work with `user_type: staff`

To migrate existing admin users:
1. Manually update `user.user_type` from `"doctor"` to `"staff"` in database
2. Create a matching `StaffProfile` with role `system_admin` and all permissions enabled
3. Delete the old `DoctorProfile` (optional, but recommended for cleanliness)

---

## Questions or Issues?

Refer to `/api/docs/` for interactive API reference or contact backend team.
