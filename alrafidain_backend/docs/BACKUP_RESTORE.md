# Backup and Restore

This guide is provider-neutral and focuses on PostgreSQL and media/storage safety.

## Database Backup

```bash
pg_dump --format=custom --file=backup.dump "$DATABASE_URL"
```

## Database Restore

```bash
pg_restore --clean --if-exists --dbname="$DATABASE_URL" backup.dump
```

## Recommended Practice

- Encrypt backups at rest.
- Use immutable backup storage when possible.
- Keep retention policy documented (for example: daily 14 days, weekly 8 weeks, monthly 12 months).
- Test restores regularly in staging.

## Media and Object Storage

- Local `media/` backup is for development only.
- Production should use private object storage and its native backup/lifecycle controls.
- Keep file-access controls and signed URL strategy consistent with `docs/FILE_SECURITY.md`.

## Audit Log Preservation

- Audit logs are append-only and hash-chained for new rows.
- Preserve audit tables in every backup.
- After restore, run integrity verification:

```bash
python manage.py ops_check --check-audit-integrity
```

## Restore Validation Checklist

After restoring:
1. Run migrations check.
2. Confirm application boot.
3. Validate `/api/health/ready/` and `/api/health/deps/`.
4. Validate worker connectivity.
5. Validate audit integrity check.
