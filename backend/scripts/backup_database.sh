#!/usr/bin/env bash
# EDON Gateway — SQLite database backup script
# Produces a timestamped, compressed backup with WAL checkpoint included.
#
# Usage:
#   ./scripts/backup_database.sh [DB_PATH] [BACKUP_DIR]
#
# Environment variables (override defaults):
#   EDON_DATABASE_PATH   Path to the SQLite database (default: /app/data/edon.db)
#   EDON_BACKUP_DIR      Directory to write backups to (default: ./backups)
#   EDON_BACKUP_RETAIN   Number of days to retain backups (default: 30)
#
# HIPAA note: For hospital tenants, retain backups for at least 2190 days (6 years).
# Set EDON_BACKUP_RETAIN=2190 or store off-site with longer retention.
#
# Example (cron — daily at 2am):
#   0 2 * * * /app/scripts/backup_database.sh >> /var/log/edon_backup.log 2>&1

set -euo pipefail

DB_PATH="${1:-${EDON_DATABASE_PATH:-/app/data/edon.db}}"
BACKUP_DIR="${2:-${EDON_BACKUP_DIR:-./backups}}"
RETAIN_DAYS="${EDON_BACKUP_RETAIN:-30}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="edon_backup_${TIMESTAMP}.db"
BACKUP_FILE="${BACKUP_DIR}/${BACKUP_NAME}"
COMPRESSED="${BACKUP_FILE}.gz"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] EDON Gateway backup starting..."
echo "  Source:  ${DB_PATH}"
echo "  Dest:    ${COMPRESSED}"

# Validate source exists
if [ ! -f "${DB_PATH}" ]; then
    echo "ERROR: Database not found at ${DB_PATH}" >&2
    exit 1
fi

# Create backup directory if needed
mkdir -p "${BACKUP_DIR}"

# Use SQLite online backup to get a consistent snapshot even under load.
# .backup checkpoints WAL before copying — safe for live databases.
sqlite3 "${DB_PATH}" ".backup '${BACKUP_FILE}'"

# Verify the backup is a valid SQLite file
INTEGRITY=$(sqlite3 "${BACKUP_FILE}" "PRAGMA integrity_check;" 2>&1)
if [ "${INTEGRITY}" != "ok" ]; then
    echo "ERROR: Backup integrity check failed: ${INTEGRITY}" >&2
    rm -f "${BACKUP_FILE}"
    exit 1
fi

# Compress
gzip -9 "${BACKUP_FILE}"
SIZE=$(du -sh "${COMPRESSED}" | cut -f1)
echo "  Backup complete: ${COMPRESSED} (${SIZE})"

# Purge old backups
DELETED=$(find "${BACKUP_DIR}" -name "edon_backup_*.db.gz" -mtime +"${RETAIN_DAYS}" -print -delete | wc -l)
if [ "${DELETED}" -gt 0 ]; then
    echo "  Purged ${DELETED} backup(s) older than ${RETAIN_DAYS} days"
fi

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backup finished successfully"
