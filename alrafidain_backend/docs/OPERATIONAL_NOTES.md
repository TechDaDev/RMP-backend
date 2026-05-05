# Operational Notes

---

## Table of Contents

- [Local Development Setup](#local-development-setup)
- [Port 5432 vs 5433 Issue](#port-5432-vs-5433-issue)
- [Environment Variables](#environment-variables)
- [Running Migrations](#running-migrations)
- [Running Tests](#running-tests)
- [Django System Check](#django-system-check)
- [Seeding Data](#seeding-data)
- [Generating Database Diagrams](#generating-database-diagrams)
- [API Documentation](#api-documentation)
- [Security and Privacy Notes](#security-and-privacy-notes)
- [Running the Development Server](#running-the-development-server)
- [Common Troubleshooting](#common-troubleshooting)
- [Knowledge Base Module (Phase 12A)](#knowledge-base-module-phase-12a)

---

## Local Development Setup

### Prerequisites

- Python 3.12+
- Docker and Docker Compose (for PostgreSQL and Redis)
- pip (inside a virtual environment)

### 1. Clone and set up virtualenv

```bash
git clone <repo_url>
cd alrafidain_backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Copy environment file

```bash
cp .env.example .env
# Edit .env and set your SECRET_KEY, DB credentials, etc.
```

### 3. Start infrastructure with Docker

```bash
docker compose up -d
```

This starts:
- PostgreSQL (default host port **5432**)
- Redis for Django Channels (default host port **6379**)

> If port 5432 is already occupied on your machine, edit `docker-compose.yml`  
> and change the host port mapping to `5433:5432`. Then prefix your commands  
> with `DB_PORT=5433`.

---

## Port 5432 vs 5433 Issue

If your system already has PostgreSQL installed and running on port 5432, the Docker container will conflict.

**Solution**: Change the mapped port in `docker-compose.yml`:

```yaml
ports:
  - "5433:5432"
```

Then all management commands must be prefixed:

```bash
DB_PORT=5433 python manage.py <command> --settings=config.settings.local
```

---

## Environment Variables

Key variables used by the project (set in `.env`):

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | Django secret key | `your-secret-key-here` |
| `DEBUG` | Enable debug mode | `True` |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts | `127.0.0.1,localhost` |
| `DB_NAME` | PostgreSQL database name | `alrafidain_db` |
| `DB_USER` | PostgreSQL user | `postgres` |
| `DB_PASSWORD` | PostgreSQL password | `postgres` |
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` or `5433` |
| `REDIS_HOST` | Redis host for channel layer | `127.0.0.1` |
| `REDIS_PORT` | Redis port for channel layer | `6379` |

---

## Running Migrations

```bash
DB_PORT=5433 python manage.py migrate --settings=config.settings.local
```

Check for pending migrations:

```bash
DB_PORT=5433 python manage.py makemigrations --check --dry-run --settings=config.settings.local
```

---

## Running Tests

Full test suite (uses SQLite in-memory — no DB_PORT needed for test settings):

```bash
DB_PORT=5433 python manage.py test apps --settings=config.settings.test
```

Run a specific app:

```bash
DB_PORT=5433 python manage.py test apps.lab_orders --settings=config.settings.test
```

Run seed command tests:

```bash
DB_PORT=5433 python manage.py test apps.common.tests.test_seed_commands --settings=config.settings.test
```

---

## Django System Check

```bash
DB_PORT=5433 python manage.py check --settings=config.settings.local
```

---

## Seeding Data

```bash
DB_PORT=5433 python manage.py seed_all --settings=config.settings.local
```

See [SEEDING.md](SEEDING.md) for details.

---

## Generating Database Diagrams

Requires `django-extensions` and `pydot` (both included in `requirements.txt`).

> For PNG output, `graphviz` must also be installed on the system:
> ```bash
> sudo apt install graphviz   # Ubuntu/Debian
> brew install graphviz       # macOS
> ```

### Full schema diagram

```bash
DB_PORT=5433 python manage.py graph_models -a -g -o docs/diagrams/database_schema_full.png --settings=config.settings.local
```

### Core app diagram (recommended)

```bash
mkdir -p docs/diagrams

DB_PORT=5433 python manage.py graph_models \
  accounts profiles consultations messaging \
  prescriptions lab_orders patient_records \
  notifications audit \
  -g -o docs/diagrams/database_schema_core.png \
  --settings=config.settings.local
```

### If PNG fails, generate DOT first

```bash
DB_PORT=5433 python manage.py graph_models \
  accounts profiles consultations messaging \
  prescriptions lab_orders patient_records \
  notifications audit \
  -g -o docs/diagrams/database_schema_core.dot \
  --settings=config.settings.local

dot -Tpng docs/diagrams/database_schema_core.dot -o docs/diagrams/database_schema_core.png
```

---

## API Documentation

Swagger UI: [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/)  
ReDoc: [http://localhost:8000/api/redoc/](http://localhost:8000/api/redoc/)  
OpenAPI Schema: [http://localhost:8000/api/schema/](http://localhost:8000/api/schema/)

Security notes: [SECURITY_NOTES.md](SECURITY_NOTES.md)

---

## Security and Privacy Notes

- Sensitive endpoints use scoped DRF throttling for login, OTP, password reset, and QR scan actions.
- QR tokens are random opaque tokens and do not include medical details.
- Privacy boundaries enforced by serializers and permissions:
  - Patients do not receive prescription item medication fields.
  - Patients do not receive lab order item test details.
  - Patients receive lab results only after doctor release.
  - Pharmacists/laboratorians receive only pending QR workflow items.

---

## Running the Development Server

```bash
DB_PORT=5433 python manage.py runserver --settings=config.settings.local
```

For WebSocket support in an ASGI process (recommended for local realtime testing), run Daphne:

```bash
DB_PORT=5433 daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

WebSocket endpoints:
- `/ws/user/?token=<access_token>`
- `/ws/consultations/<consultation_id>/messages/?token=<access_token>`

---

## Common Troubleshooting

### `django.db.utils.OperationalError: could not connect to server`

PostgreSQL is not running. Start it:

```bash
docker compose up -d
```

### `Address already in use` on port 5432

Another PostgreSQL instance is running. Switch to port 5433 (see above).

### `No module named 'django_extensions'`

Install missing dependency:

```bash
pip install django-extensions
```

### `pydot is not installed`

```bash
pip install pydot
```

### `graphviz executable not found` when generating diagrams

```bash
sudo apt install graphviz   # Ubuntu/Debian
```

### Migrations out of sync

```bash
DB_PORT=5433 python manage.py migrate --settings=config.settings.local
```

### Tests fail with import errors

Ensure you are in the `alrafidain_backend/` directory and your venv is activated.

### Realtime events are not delivered

Check Redis and channel layer settings:

```bash
docker compose ps
redis-cli -h 127.0.0.1 -p 6379 ping
```

Expected Redis response: `PONG`.

Also verify app settings include:
- `ASGI_APPLICATION = "config.asgi.application"`
- `CHANNEL_LAYERS` configured to Redis backend.

---

## Knowledge Base Module (Phase 12A)

### Supported Upload File Types

| Extension | Library | Notes |
|-----------|---------|-------|
| `.pdf` | `pypdf` | Extracts text page by page |
| `.docx` | `python-docx` | Extracts paragraph text |
| `.txt` | built-in | UTF-8, errors replaced |

### Processing Workflow

```
1. Upload document  →  approval_status=pending, processing_status=uploaded
2. POST .../process/  →  Extracts text (KnowledgeDocumentText), chunks (KnowledgeChunk)
                         processing_status=chunked
3. POST .../approve/  →  approval_status=approved  (document must have chunks)
4. Chunks now eligible for future RAG retrieval
```

### Approval Rules

- Only staff or superuser may upload, process, approve, reject, or archive.
- Documents must be chunked before approval.
- Archived documents and their chunks become inactive.
- Only `approved` + `is_active=True` documents with `is_active=True` chunks are used in future RAG.

### No AI Yet

- Phase 12A has no vector embeddings.
- Phase 12A has no pgvector.
- Phase 12A has no DeepSeek calls.
- Phase 12A has no patient-facing AI endpoints.
- Search is basic `icontains` text search.

### Running Knowledge Base Commands

```bash
# Upload and process via API (staff JWT required)
POST /api/knowledge-base/documents/
POST /api/knowledge-base/documents/<id>/process/
POST /api/knowledge-base/documents/<id>/approve/

# Search approved chunks
GET /api/knowledge-base/chunks/search/?q=crp&document_type=laboratory_book
```

---

### Phase 12E — RAG Dataset Export (management command)

Exports an anonymized RAG evaluation dataset to a file for offline use.

```bash
# Basic JSON export (anonymized, no text, output to ./rag_eval.json)
python manage.py export_rag_dataset --output ./rag_eval.json

# CSV export
python manage.py export_rag_dataset --format csv --output ./rag_eval.csv

# Include query + response text (handle with care — staff only)
python manage.py export_rag_dataset --include-text --output ./rag_eval_with_text.json

# Disable anonymization (use only in controlled environments)
python manage.py export_rag_dataset --no-anonymize --output ./rag_raw.json
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--format` | `json` | `json` or `csv` |
| `--output` | `./rag_eval_export.json` | Output file path (directory created if missing) |
| `--include-text` | off | Include `query_text` + `response_text` |
| `--no-anonymize` | off | Disable SHA-256 hashing of doctor IDs |

Set `EXPORT_HASH_SALT` in your `.env` to a secret random value before exporting in production.

