# Al-Rafidain Medical Platform — Backend

**Current backend MVP version: v0.1.0**

A production-oriented Django REST Framework backend for a medical platform serving patients, doctors, pharmacists, and laboratorians in Iraq.

---

## Implemented Modules (Phases 0–14)

| Module | Description |
|---|---|
| Accounts | Email-based user auth with JWT, registration, password management |
| Profiles | Role-specific profiles (patient, doctor, pharmacist, laboratorian) with verification |
| Consultations | Patient symptom submission → doctor matching → medical response workflow |
| Messaging | REST-based in-consultation threaded messaging |
| Prescriptions | Doctor-issued prescriptions with QR dispensing via pharmacist scan |
| Lab Orders | Doctor-ordered lab tests with QR scan workflow for laboratorians |
| Lab Results | Laboratorian result entry, doctor review/release, patient visibility, medical record linkage |
| Patient Records | Medical record entries (self-reported, doctor-confirmed, laboratory-confirmed) + blood group |
| Notifications | In-app notification system for all significant clinical events |
| Audit Logs | Immutable action log for all sensitive operations |
| **Realtime (Phase 14)** | **WebSocket layer for realtime event delivery via Django Channels + Redis** |

---

## Architecture

- **REST API**: Source of truth for all data creation and modification
- **WebSocket (Phase 14)**: Realtime event delivery to connected clients
- **Database**: Permanent storage (PostgreSQL + pgvector)
- **Redis**: Channel layer for WebSocket broadcasting

### Data Flow

```
REST API creates/modifies data
    ↓
Database saved
    ↓
Service broadcasts WebSocket event
    ↓
Connected clients receive update
```

---

## Stack

- Python 3.12+, Django 5+, Django REST Framework
- PostgreSQL (via Docker Compose)
- SimpleJWT (JWT authentication)
- Django Channels + Daphne (WebSocket support)
- Redis (channel layer for WebSocket)
- drf-spectacular (OpenAPI / Swagger)
- django-extensions + pydot (ER diagram generation)
- django-filter, django-cors-headers, django-cleanup
- python-decouple, Pillow, psycopg

---

## Development Setup

```bash
# 1. Start PostgreSQL and Redis
docker compose up -d

# 2. Create and activate virtualenv
python -m venv venv
source venv/bin/activate

# 3. Install dependencies (recommended for local development)
pip install -r requirements/dev.in

# 4. Copy environment config
cp .env.local.example .env
# Edit .env if needed

# 5. Run migrations
DB_PORT=5433 python manage.py migrate --settings=config.settings.local

# 6. Seed data
DB_PORT=5433 python manage.py seed_all --settings=config.settings.local

# 7. Start development server
DB_PORT=5433 python manage.py runserver --settings=config.settings.local
```

Dependency file structure:
- `requirements/base.in` for core runtime dependencies
- `requirements/dev.in` for local development and quality tooling
- `requirements/prod.in` for production-only additions
- `requirements/ai.in` for AI/RAG dependency set

`requirements.txt` is kept as a backward-compatible entrypoint.

For repeatable, pinned installs in CI/production, generate lock files later using `pip-tools` or `uv`.

> If your system PostgreSQL already uses port 5432, map Docker to 5433 in `docker-compose.yml`.  
> See [docs/OPERATIONAL_NOTES.md](docs/OPERATIONAL_NOTES.md) for details.

## Quality Checks

```bash
ruff check .
ruff format --check .
bandit -r apps config
pip-audit
pytest
```

## Production Safety Notes

- Production requires a strong `SECRET_KEY`.
- Production requires `EXPORT_HASH_SALT`.
- `DEBUG` is forced to `False` in production settings.
- `ALLOWED_HOSTS` must be explicitly configured in production.
- HTTPS/security headers are enabled in production settings.

---

## Docker PostgreSQL

```bash
docker compose up -d    # start
docker compose down     # stop
```

Default port: **5432**. Override with `DB_PORT=5433` if needed.

---

## Migrations

```bash
DB_PORT=5433 python manage.py migrate --settings=config.settings.local

# Check for missing migrations
DB_PORT=5433 python manage.py makemigrations --check --dry-run --settings=config.settings.local
```

---

## Tests

```bash
pytest
```

Current test count: **288+ tests** across all apps.

---

## Seed Data

```bash
DB_PORT=5433 python manage.py seed_all --settings=config.settings.local
```

Demo credentials (development only):

| Role | Email | Password |
|---|---|---|
| Patient | `patient@example.com` | `DemoPass123!` |
| Doctor | `doctor@example.com` | `DemoPass123!` |
| Pharmacist | `pharmacist@example.com` | `DemoPass123!` |
| Laboratorian | `laboratorian@example.com` | `DemoPass123!` |

See [docs/SEEDING.md](docs/SEEDING.md) for full details.

---

## API Documentation

| Resource | URL |
|---|---|
| Swagger UI | http://127.0.0.1:8000/api/docs/ |
| ReDoc | http://127.0.0.1:8000/api/redoc/ |
| OpenAPI Schema | http://127.0.0.1:8000/api/schema/ |
| Health Check | http://127.0.0.1:8000/api/health/ |

Full endpoint reference: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)

---

## Database Diagram Generation

Requires `graphviz` installed on the system (`sudo apt install graphviz`).

```bash
mkdir -p docs/diagrams

# Core app diagram
DB_PORT=5433 python manage.py graph_models \
  accounts profiles consultations messaging \
  prescriptions lab_orders patient_records \
  notifications audit \
  -g -o docs/diagrams/database_schema_core.png \
  --settings=config.settings.local

# Full schema
DB_PORT=5433 python manage.py graph_models -a -g \
  -o docs/diagrams/database_schema_full.png \
  --settings=config.settings.local
```

Generated files:
- `docs/diagrams/database_schema_core.png`
- `docs/diagrams/database_schema_full.png`

---

## Privacy and Security Rules

- Patients **never** see prescription medication item details.
- Patients **never** see lab order test item details.
- Patients see lab results **only after** the ordering doctor explicitly releases them.
- Patients never see `laboratorian_notes` or `doctor_notes` in lab result responses.
- Pharmacists see only `pending` prescription items after QR scan.
- Laboratorians see only `pending` lab order items after QR scan.
- Doctors can only access records for patients they have an accepted consultation with.
- All sensitive actions are recorded in the immutable audit log.

Phase 11 hardening additions:
- Scoped rate limiting is enabled for login, OTP, password reset, and QR scan endpoints.
- QR tokens are opaque random values and never encode medical details.
- Privacy boundaries are documented in [docs/SECURITY_NOTES.md](docs/SECURITY_NOTES.md).

---

## Knowledge Base (Phase 12A)

A medical/laboratory knowledge base foundation for future RAG (Retrieval-Augmented Generation) support.

**Features:**
- Staff-only upload of PDF, DOCX, and TXT documents
- Automatic text extraction (pypdf, python-docx)
- Character-based text chunking with configurable size and overlap
- Approval workflow: `pending → chunked → approved` (or rejected/archived)
- Basic icontains text search over approved, active chunks
- Full audit logging of all document actions

**No AI yet:** No embeddings, no pgvector, no DeepSeek, no patient-facing AI in this phase.

See [docs/RAG_PLAN.md](docs/RAG_PLAN.md) for the full AI roadmap.

---

## RAG Analytics & Dataset Export (Phase 12E)

Admin-only analytics dashboard and anonymized evaluation dataset export.

**Features:**
- `GET /api/rag/admin/analytics/summary/` — aggregated feedback, retrieval quality, and usage metrics
- `POST /api/rag/admin/exports/dataset/` — export anonymized evaluation dataset (JSON or CSV)
- Django management command `export_rag_dataset` for file-based exports
- SHA-256 anonymization of doctor IDs with configurable salt (`EXPORT_HASH_SALT`)
- Raw embeddings and patient-identifiable fields are never exported

See [docs/RAG_EVALUATION_DATASET.md](docs/RAG_EVALUATION_DATASET.md) for dataset field reference and privacy notes.

---

## Further Reading

- [docs/API_REFERENCE.md](docs/API_REFERENCE.md) — Full endpoint reference
- [docs/SEEDING.md](docs/SEEDING.md) — Seed commands and demo credentials
- [docs/OPERATIONAL_NOTES.md](docs/OPERATIONAL_NOTES.md) — Setup, troubleshooting, diagram generation
- [docs/RAG_PLAN.md](docs/RAG_PLAN.md) — AI/RAG roadmap
- [docs/RAG_EVALUATION_DATASET.md](docs/RAG_EVALUATION_DATASET.md) — Dataset field reference and privacy notes
- [docs/SECURITY_NOTES.md](docs/SECURITY_NOTES.md) — Security model, privacy boundaries, throttling, and MVP limitations
- [docs/FILE_SECURITY.md](docs/FILE_SECURITY.md) — File upload validation, malware scanning, and private storage guidance
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — Runtime process model, health endpoints, and ops checks
- [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md) — Database and media backup/restore guidance
- [docs/DEPLOYMENT_CHECKLIST.md](docs/DEPLOYMENT_CHECKLIST.md) — Production deployment hardening checklist