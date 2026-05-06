from unittest.mock import patch

from django.test import TestCase

from apps.common.logging import (
    RequestIDLogFilter,
    get_request_id,
    reset_request_id,
    set_request_id,
)


class HealthEndpointsTest(TestCase):
    def test_live_returns_200(self):
        resp = self.client.get("/api/health/live/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_ready_returns_ok_with_test_db(self):
        resp = self.client.get("/api/health/ready/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("database", body["components"])

    def test_deps_returns_structured_components(self):
        resp = self.client.get("/api/health/deps/")
        self.assertIn(resp.status_code, (200, 503))
        body = resp.json()
        self.assertIn("status", body)
        self.assertIn("components", body)
        self.assertIn("database", body["components"])
        self.assertIn("redis", body["components"])
        self.assertIn("storage", body["components"])

    def test_deps_does_not_expose_secrets(self):
        resp = self.client.get("/api/health/deps/")
        body = str(resp.json()).lower()
        self.assertNotIn("password", body)
        self.assertNotIn("secret", body)
        self.assertNotIn("token", body)


class RequestIDMiddlewareTest(TestCase):
    def test_response_has_request_id_header(self):
        resp = self.client.get("/api/health/live/")
        self.assertIn("X-Request-ID", resp)
        self.assertTrue(resp["X-Request-ID"])

    def test_log_filter_injects_request_id(self):
        token = set_request_id("test-request-id")
        try:

            class DummyRecord:
                pass

            record = DummyRecord()
            filt = RequestIDLogFilter()
            self.assertTrue(filt.filter(record))
            self.assertEqual(record.request_id, "test-request-id")
        finally:
            reset_request_id(token)

    def test_request_id_context_defaults_to_dash(self):
        self.assertEqual(get_request_id(), "-")


class OpsCheckCommandTest(TestCase):
    @patch("apps.common.management.commands.ops_check.Command._check_redis")
    def test_ops_check_passes_with_mocked_redis(self, mock_redis):
        mock_redis.return_value = (True, "ok")
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("ops_check", stdout=out)
        self.assertIn("ops_check passed", out.getvalue())
