# EDON Gateway — SQLite database backup script (PowerShell / Windows)
# Produces a timestamped, compressed backup with integrity check included.
#
# Usage:
#   .\scripts\backup_database.ps1 [-DbPath <path>] [-BackupDir <dir>] [-RetainDays <n>]
#
# Parameters can also be set via environment variables:
#   EDON_DATABASE_PATH, EDON_BACKUP_DIR, EDON_BACKUP_RETAIN
#
# HIPAA note: For hospital tenants, retain backups for at least 2190 days (6 years).
#
# Example (Task Scheduler — daily at 2am):
#   Action: powershell.exe -File C:\edon\scripts\backup_database.ps1

param(
    [string]$DbPath    = $env:EDON_DATABASE_PATH ?? ".\data\edon.db",
    [string]$BackupDir = $env:EDON_BACKUP_DIR    ?? ".\backups",
    [int]   $RetainDays = [int]($env:EDON_BACKUP_RETAIN ?? "30")
)

$ErrorActionPreference = "Stop"
$Timestamp  = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupName = "edon_backup_$Timestamp.db"
$BackupFile = Join-Path $BackupDir $BackupName
$Compressed = "$BackupFile.gz"

Write-Host "[$(Get-Date -Format 'u')] EDON Gateway backup starting..."
Write-Host "  Source:  $DbPath"
Write-Host "  Dest:    $Compressed"

# Validate source
if (-not (Test-Path $DbPath)) {
    Write-Error "Database not found at $DbPath"
    exit 1
}

# Create backup directory if needed
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

# SQLite online backup via sqlite3 CLI (must be on PATH)
# Falls back to file copy if sqlite3 not available (less safe — no WAL checkpoint)
if (Get-Command sqlite3 -ErrorAction SilentlyContinue) {
    & sqlite3 $DbPath ".backup '$BackupFile'"
} else {
    Write-Warning "sqlite3 not found on PATH — using file copy (install sqlite3 for safer backups)"
    Copy-Item $DbPath $BackupFile
}

# Integrity check
if (Get-Command sqlite3 -ErrorAction SilentlyContinue) {
    $Integrity = & sqlite3 $BackupFile "PRAGMA integrity_check;"
    if ($Integrity -ne "ok") {
        Remove-Item $BackupFile -Force
        Write-Error "Backup integrity check failed: $Integrity"
        exit 1
    }
}

# Compress with built-in .NET GZip
$InStream  = [System.IO.File]::OpenRead($BackupFile)
$OutStream = [System.IO.File]::Create($Compressed)
$GzStream  = [System.IO.Compression.GZipStream]::new($OutStream, [System.IO.Compression.CompressionLevel]::Optimal)
$InStream.CopyTo($GzStream)
$GzStream.Close(); $OutStream.Close(); $InStream.Close()
Remove-Item $BackupFile -Force

$SizeMB = [math]::Round((Get-Item $Compressed).Length / 1MB, 2)
Write-Host "  Backup complete: $Compressed ($SizeMB MB)"

# Purge old backups
$Cutoff = (Get-Date).AddDays(-$RetainDays)
$Deleted = Get-ChildItem $BackupDir -Filter "edon_backup_*.db.gz" |
    Where-Object { $_.LastWriteTime -lt $Cutoff } |
    ForEach-Object { Remove-Item $_.FullName -Force; $_ }
if ($Deleted.Count -gt 0) {
    Write-Host "  Purged $($Deleted.Count) backup(s) older than $RetainDays days"
}

Write-Host "[$(Get-Date -Format 'u')] Backup finished successfully"
