#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 1
fi

BACKUP_FILE="${1:-backup-$(date +%Y%m%d-%H%M%S).dump}"

pg_dump --format=custom --file="$BACKUP_FILE" "$DATABASE_URL"
echo "Backup created: $BACKUP_FILE"
