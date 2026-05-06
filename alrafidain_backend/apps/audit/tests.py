import uuid

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.audit.admin import AuditLogAdmin
from apps.audit.models import AuditLog
from apps.audit.services import (
    create_audit_log,
    record_security_event,
    sanitize_audit_metadata,
    verify_audit_log_integrity,
)


class AuditLogImmutabilityTests(TestCase):
    def setUp(self):
        raw_password = str(uuid.uuid4())
        self.user = User.objects.create_user(
            email="audit-immutability@example.com",
            first_name="Audit",
            last_name="User",
            user_type="doctor",
        )
        self.user.set_password(raw_password)
        self.user.save(update_fields=["password"])

    def test_audit_log_can_be_created(self):
        create_audit_log(actor=self.user, action="unit_test_event", metadata={"ok": True})
        self.assertEqual(AuditLog.objects.count(), 1)

    def test_audit_log_cannot_be_updated(self):
        create_audit_log(actor=self.user, action="unit_test_event")
        log = AuditLog.objects.first()
        log.action = "mutated"
        with self.assertRaises(ValidationError):
            log.save()

    def test_audit_log_cannot_be_deleted(self):
        create_audit_log(actor=self.user, action="unit_test_event")
        log = AuditLog.objects.first()
        with self.assertRaises(ValidationError):
            log.delete()


class AuditAdminReadOnlyTests(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.model_admin = AuditLogAdmin(AuditLog, self.site)
        self.factory = RequestFactory()
        raw_password = str(uuid.uuid4())
        self.user = User.objects.create_user(
            email="admin-audit@example.com",
            first_name="Admin",
            last_name="User",
            user_type="admin",
        )
        self.user.set_password(raw_password)
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=["password", "is_staff", "is_superuser"])
        self.request = self.factory.get("/admin/")
        self.request.user = self.user
        create_audit_log(actor=self.user, action="admin_test")
        self.log = AuditLog.objects.first()

    def test_admin_disallows_change_for_existing_object(self):
        self.assertFalse(self.model_admin.has_change_permission(self.request, self.log))

    def test_admin_disallows_delete(self):
        self.assertFalse(self.model_admin.has_delete_permission(self.request, self.log))

    def test_admin_disallows_add(self):
        self.assertFalse(self.model_admin.has_add_permission(self.request))


class AuditSanitizerTests(TestCase):
    def test_sensitive_keys_are_redacted(self):
        password_value = str(uuid.uuid4())
        token_value = str(uuid.uuid4())
        nested_secret_value = str(uuid.uuid4())
        sanitized = sanitize_audit_metadata(
            {
                "password": password_value,
                "token": token_value,
                "safe": "value",
                "nested": {"secret": nested_secret_value, "ok": 1},
            }
        )
        self.assertEqual(sanitized["password"], "[REDACTED]")
        self.assertEqual(sanitized["token"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["secret"], "[REDACTED]")
        self.assertEqual(sanitized["safe"], "value")

    def test_long_strings_are_truncated(self):
        long_value = "x" * 2000
        sanitized = sanitize_audit_metadata({"query": long_value})
        self.assertTrue(len(sanitized["query"]) < 600)


class AuditHashChainTests(TestCase):
    def setUp(self):
        raw_password = str(uuid.uuid4())
        self.user = User.objects.create_user(
            email="audit-chain@example.com",
            first_name="Chain",
            last_name="User",
            user_type="doctor",
        )
        self.user.set_password(raw_password)
        self.user.save(update_fields=["password"])

    def test_hash_is_generated_on_create(self):
        create_audit_log(actor=self.user, action="hash_create", metadata={"a": 1})
        log = AuditLog.objects.first()
        self.assertEqual(len(log.current_hash), 64)

    def test_chain_verifies_for_valid_logs(self):
        create_audit_log(actor=self.user, action="event_one", metadata={"step": 1})
        create_audit_log(actor=self.user, action="event_two", metadata={"step": 2})
        result = verify_audit_log_integrity()
        self.assertTrue(result["valid"])
        self.assertEqual(result["error"], None)

    def test_tampered_metadata_fails_verification(self):
        create_audit_log(actor=self.user, action="event_one", metadata={"step": 1})
        log = AuditLog.objects.first()
        AuditLog.objects.filter(pk=log.pk).update(metadata={"step": 999})

        result = verify_audit_log_integrity()
        self.assertFalse(result["valid"])
        self.assertEqual(result["error"], "current_hash_mismatch")

    def test_tampered_hash_fails_verification(self):
        create_audit_log(actor=self.user, action="event_one", metadata={"step": 1})
        log = AuditLog.objects.first()
        AuditLog.objects.filter(pk=log.pk).update(current_hash="0" * 64)

        result = verify_audit_log_integrity()
        self.assertFalse(result["valid"])
        self.assertEqual(result["error"], "current_hash_mismatch")


class SecurityEventHelperTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        raw_password = str(uuid.uuid4())
        self.user = User.objects.create_user(
            email="security-event@example.com",
            first_name="Sec",
            last_name="User",
            user_type="doctor",
        )
        self.user.set_password(raw_password)
        self.user.save(update_fields=["password"])

    def test_record_security_event_writes_safe_metadata(self):
        request = self.factory.post(
            "/fake-path",
            HTTP_USER_AGENT="UnitTestBrowser/1.0",
            HTTP_X_REQUEST_ID="req-123",
            REMOTE_ADDR="127.0.0.1",
        )
        token_value = str(uuid.uuid4())
        record_security_event(
            actor=self.user,
            action="security_event_test",
            request=request,
            metadata={"reason_code": "test_reason", "token": token_value},
        )

        log = AuditLog.objects.get(action="security_event_test")
        self.assertEqual(log.metadata["token"], "[REDACTED]")
        self.assertEqual(log.metadata["reason_code"], "test_reason")
        self.assertEqual(log.metadata["request_id"], "req-123")
        self.assertEqual(log.metadata["category"], "security")
        self.assertEqual(log.ip_address, "127.0.0.1")
