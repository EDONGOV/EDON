# EDON Gateway - Backup & Recovery Guide

Complete guide to backing up and restoring EDON Gateway database.

---

## Overview

EDON Gateway uses SQLite for persistence. Regular backups are essential for production deployments.

---

## Backup Procedures

### Automated Backup (Recommended)

#### Linux/Mac (Cron)

```bash
# Add to crontab (runs daily at 2 AM)
0 2 * * * /path/to/scripts/backup_database.sh
```

#### Windows (Task Scheduler)

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (daily at 2 AM)
4. Action: Start program
5. Program: `powershell.exe`
6. Arguments: `-File "C:\path\to\scripts\backup_database.ps1"`

### Manual Backup

#### Linux/Mac

```bash
cd /path/to/edon-gateway
./scripts/backup_database.sh
```

#### Windows (PowerShell)

```powershell
cd C:\path\to\edon-gateway
.\scripts\backup_database.ps1
```

### Environment Variables

Set these to customize backup location:

```bash
# Linux/Mac
export EDON_DATABASE_PATH=./edon_gateway.db
export EDON_BACKUP_DIR=./backups

# Windows
$env:EDON_DATABASE_PATH = ".\edon_gateway.db"
$env:EDON_BACKUP_DIR = ".\backups"
```

---

## Backup Script Features

- **Automatic compression** - Backups are gzipped
- **Timestamped files** - Format: `edon_gateway_YYYYMMDD_HHMMSS.db.gz`
- **Automatic cleanup** - Removes backups older than 30 days
- **Size reporting** - Shows backup file size

---

## Restore Procedures

### Interactive Restore

#### Linux/Mac

```bash
cd /path/to/edon-gateway
./scripts/restore_database.sh
```

The script will:
1. List available backups
2. Prompt for backup number
3. Confirm restore
4. Backup current database first
5. Restore selected backup

#### Windows (PowerShell)

```powershell
cd C:\path\to\edon-gateway
.\scripts\restore_database.ps1
```

### Direct Restore

#### Linux/Mac

```bash
# Stop gateway first!
docker compose stop edon-gateway

# Restore
gunzip -c backups/edon_gateway_20250127_020000.db.gz > edon_gateway.db

# Start gateway
docker compose start edon-gateway
```

#### Windows (PowerShell)

```powershell
# Stop gateway first!
docker compose stop edon-gateway

# Restore (using .NET compression)
$backup = "backups\edon_gateway_20250127_020000.db.gz"
$compressed = [System.IO.File]::ReadAllBytes($backup)
$decompressed = [System.IO.Compression.GZipStream]::new(
    [System.IO.MemoryStream]::new($compressed),
    [System.IO.Compression.CompressionMode]::Decompress
)
$output = New-Object System.IO.MemoryStream
$decompressed.CopyTo($output)
[System.IO.File]::WriteAllBytes("edon_gateway.db", $output.ToArray())
$decompressed.Close()
$output.Close()

# Start gateway
docker compose start edon-gateway
```

---

## What Gets Backed Up

The database contains:
- **Intents** - Intent contracts and policies
- **Credentials** - Tool credentials (encrypted)
- **Audit Events** - All decisions and actions
- **Decisions** - Quick lookup table
- **Token Bindings** - Token to agent ID mappings
- **Counters** - Rate limiting and metrics

---

## Backup Retention

- **Default:** 30 days
- **Configurable:** Edit cleanup logic in backup scripts
- **Recommendation:** Keep at least 7 daily backups, 4 weekly backups

---

## Disaster Recovery

### Complete System Recovery

1. **Restore database**
   ```bash
   ./scripts/restore_database.sh
   ```

2. **Verify database integrity**
   ```bash
   sqlite3 edon_gateway.db "PRAGMA integrity_check;"
   ```

3. **Restart gateway**
   ```bash
   docker compose restart edon-gateway
   ```

4. **Verify functionality**
   ```bash
   curl http://localhost:8000/health
   ```

### Partial Recovery

If only specific data needs recovery:
- Use SQLite tools to extract specific tables
- Restore from audit logs if needed
- Re-create intents/credentials via API

---

## Best Practices

1. **Automate backups** - Use cron/Task Scheduler
2. **Test restores** - Regularly test restore procedure
3. **Off-site storage** - Copy backups to remote location
4. **Encrypt backups** - If containing sensitive data
5. **Monitor backup success** - Set up alerts
6. **Document recovery** - Keep recovery procedures documented

---

## Backup Verification

### Check Backup Integrity

```bash
# Linux/Mac
gunzip -t backups/edon_gateway_*.db.gz

# Windows
# Use 7-Zip or similar to test archive
```

### Verify Database After Restore

```bash
sqlite3 edon_gateway.db "SELECT COUNT(*) FROM intents;"
sqlite3 edon_gateway.db "SELECT COUNT(*) FROM audit_events;"
sqlite3 edon_gateway.db "PRAGMA integrity_check;"
```

---

## Troubleshooting

### Backup Fails

- Check database file exists
- Verify write permissions on backup directory
- Check disk space

### Restore Fails

- Verify backup file is not corrupted
- Check database file is not locked (stop gateway)
- Ensure sufficient disk space

### Database Locked

If database is locked during backup:
- Stop gateway: `docker compose stop edon-gateway`
- Run backup
- Start gateway: `docker compose start edon-gateway`

---

*Last Updated: 2025-01-27*
