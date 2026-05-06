from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Run non-invasive operational checks for deployment readiness."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-audit-integrity",
            action="store_true",
            help="Verify audit hash chain integrity (can be expensive on large datasets).",
        )

    def _check_database(self) -> tuple[bool, str]:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return True, "ok"
        except Exception as exc:
            return False, f"error: {exc.__class__.__name__}"

    def _check_redis(self) -> tuple[bool, str]:
        broker_url = getattr(settings, "CELERY_BROKER_URL", "")
        if not broker_url or not str(broker_url).startswith(("redis://", "rediss://")):
            return True, "not_configured"

        try:
            import redis

            client = redis.Redis.from_url(broker_url, socket_connect_timeout=1, socket_timeout=1)
            client.ping()
            return True, "ok"
        except Exception as exc:
            return False, f"error: {exc.__class__.__name__}"

    def handle(self, *args, **options):
        checks: list[tuple[str, bool, str]] = []

        env = getattr(settings, "ENVIRONMENT", "local")
        checks.append(("environment", True, env))

        debug = bool(getattr(settings, "DEBUG", True))
        debug_ok = not debug if env in {"production", "staging"} else True
        checks.append(("debug", debug_ok, str(debug)))

        secret_key = getattr(settings, "SECRET_KEY", "")
        checks.append(("secret_key_present", bool(secret_key), "set" if secret_key else "missing"))

        export_salt = getattr(settings, "EXPORT_HASH_SALT", None)
        export_ok = bool(export_salt) if env == "production" else True
        checks.append(("export_hash_salt", export_ok, "set" if export_salt else "missing"))

        db_ok, db_msg = self._check_database()
        checks.append(("database", db_ok, db_msg))

        redis_ok, redis_msg = self._check_redis()
        checks.append(("redis", redis_ok, redis_msg))

        private_media = bool(getattr(settings, "PRIVATE_MEDIA_STORAGE", False))
        private_media_ok = private_media if env == "production" else True
        checks.append(("private_media_storage", private_media_ok, str(private_media)))

        checks.append(
            (
                "file_scanning_enabled",
                True,
                str(getattr(settings, "FILE_SCANNING_ENABLED", False)),
            )
        )

        celery_ok = bool(getattr(settings, "CELERY_BROKER_URL", "")) and bool(
            getattr(settings, "CELERY_RESULT_BACKEND", "")
        )
        checks.append(("celery_config", celery_ok, "configured" if celery_ok else "missing"))

        if options.get("check_audit_integrity"):
            try:
                from apps.audit.services import verify_audit_log_integrity

                result = verify_audit_log_integrity()
                checks.append(("audit_integrity", bool(result.get("valid")), str(result)))
            except Exception as exc:
                checks.append(("audit_integrity", False, f"error: {exc.__class__.__name__}"))

        all_ok = True
        for name, ok, message in checks:
            all_ok = all_ok and ok
            symbol = "OK" if ok else "FAIL"
            self.stdout.write(f"[{symbol}] {name}: {message}")

        if not all_ok:
            self.stdout.write(self.style.ERROR("ops_check failed"))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("ops_check passed"))
