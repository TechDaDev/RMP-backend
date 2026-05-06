#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 1
fi

BACKUP_FILE="${1:-}"
if [[ -z "$BACKUP_FILE" ]]; then
  echo "Usage: $0 <backup.dump>" >&2
  exit 1
fi

pg_restore --clean --if-exists --dbname="$DATABASE_URL" "$BACKUP_FILE"
echo "Restore completed from: $BACKUP_FILE"
