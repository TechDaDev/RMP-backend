# Deployment Checklist

## Security Baseline

- [ ] `DEBUG=False`
- [ ] Strong `SECRET_KEY`
- [ ] Strong `EXPORT_HASH_SALT`
- [ ] `ALLOWED_HOSTS` configured
- [ ] `CSRF_TRUSTED_ORIGINS` configured
- [ ] HTTPS termination configured

## Infrastructure

- [ ] Database configured and reachable
- [ ] Redis/Celery broker configured and reachable
- [ ] Worker process running (`celery -A config worker -l info`)
- [ ] ASGI process configured if websocket features are used
- [ ] Reverse proxy routes web/asgi appropriately

## Storage and File Safety

- [ ] `PRIVATE_MEDIA_STORAGE` reviewed and set for production strategy
- [ ] `FILE_SCANNING_ENABLED` configured intentionally
- [ ] Media/object storage backup/lifecycle policy configured

## Application Readiness

- [ ] `python manage.py migrate --settings=config.settings.production`
- [ ] `python manage.py collectstatic --noinput --settings=config.settings.production`
- [ ] `python manage.py check --settings=config.settings.production`
- [ ] `python manage.py ops_check --settings=config.settings.production`
- [ ] Health endpoints pass (`/api/health/live/`, `/api/health/ready/`, `/api/health/deps/`)

## Data Governance

- [ ] Demo users removed outside development
- [ ] Backup and restore process documented and tested
- [ ] Audit integrity verification scheduled periodically
- [ ] RAG export limits reviewed (`RAG_EXPORT_MAX_ROWS`)

## Monitoring and Alerts

- [ ] Structured logging enabled and collected
- [ ] Request ID propagation visible in logs
- [ ] Alerting for readiness/dependency failures
- [ ] Alerting for repeated security events
- [ ] Optional telemetry configured if used (`SENTRY_DSN`)

## Known Risk Tracking

- [ ] Track `pip-audit` Twisted `25.5.0` advisory (`CVE-2026-42304`) in risk register until stable fix path is approved
