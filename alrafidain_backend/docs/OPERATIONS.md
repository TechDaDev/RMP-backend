# Operations Guide

This document focuses on safe, provider-neutral runtime operations for staging and production.

## Process Model

Recommended process split:
- web (WSGI): `gunicorn config.wsgi:application`
- asgi (WebSocket): `daphne -b 0.0.0.0 -p 8001 config.asgi:application`
- worker: `celery -A config worker -l info`
- optional scheduler (future): `celery -A config beat -l info`
- reverse proxy (Nginx/Caddy/Ingress): TLS termination and routing to web/asgi

## Local Runtime Commands

```bash
# Django dev server
python manage.py runserver --settings=config.settings.local

# ASGI server
DB_PORT=5433 daphne -b 0.0.0.0 -p 8000 config.asgi:application

# Celery worker
celery -A config worker -l info
```

## Pre-Deploy Commands

```bash
python manage.py check --settings=config.settings.production
python manage.py migrate --settings=config.settings.production
python manage.py collectstatic --noinput --settings=config.settings.production
python manage.py ops_check --settings=config.settings.production
```

## Health Endpoints

- Live: `GET /api/health/live/`
- Ready: `GET /api/health/ready/`
- Dependencies: `GET /api/health/deps/`

Notes:
- `/api/health/live/` is process liveness only.
- `/api/health/ready/` checks database readiness.
- `/api/health/deps/` reports component status (database, redis, storage) without leaking secrets.

## Logging and Traceability

- Request ID middleware adds `X-Request-ID` on every response.
- Structured log format includes `request_id=<value>`.
- Do not log request bodies, tokens, or full clinical payloads.

## Celery / Redis Operations

- Verify worker is active: `celery -A config inspect ping`
- Confirm Redis availability: `redis-cli ping`
- Keep worker and web/asgi logs separated.

## Environment Variables (Ops-Critical)

- `ENVIRONMENT`
- `DEBUG`
- `SECRET_KEY`
- `EXPORT_HASH_SALT`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL` or DB_* vars
- `REDIS_URL` and/or `CELERY_BROKER_URL`
- `PRIVATE_MEDIA_STORAGE`
- `FILE_SCANNING_ENABLED`
- `RAG_EXPORT_MAX_ROWS`
- Optional telemetry: `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`

## Optional Sentry

Sentry is optional in this project.
- Configure `SENTRY_DSN` and `SENTRY_TRACES_SAMPLE_RATE` in environment.
- Keep PII disabled by default.
- Do not send request bodies or sensitive payloads.

## Log Monitoring Basics

Monitor for:
- repeated `permission_denied` and security events
- repeated `rag_dataset_export_rejected`
- worker failures / retries
- rising `/api/health/ready/` or `/api/health/deps/` failures

## Incident First Response

1. Check health endpoints.
2. Check database and Redis connectivity.
3. Check worker status and queue backlog.
4. Review recent deployment/migrations.
5. Run `python manage.py ops_check`.
