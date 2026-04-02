# Fix .env file encoding to UTF-8

$envPath = Join-Path $PSScriptRoot ".env"

if (Test-Path $envPath) {
    Write-Host "Found .env file, checking encoding..." -ForegroundColor Yellow
    
    # Read file as bytes to check encoding
    $bytes = [System.IO.File]::ReadAllBytes($envPath)
    
    # Check for UTF-16 BOM (0xFF 0xFE)
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
        Write-Host "⚠️  Detected UTF-16 LE encoding (with BOM)" -ForegroundColor Red
        Write-Host "Converting to UTF-8..." -ForegroundColor Yellow
        
        # Read as UTF-16 and write as UTF-8
        $content = [System.IO.File]::ReadAllText($envPath, [System.Text.Encoding]::Unicode)
        [System.IO.File]::WriteAllText($envPath, $content, [System.Text.Encoding]::UTF8)
        
        Write-Host "✅ Converted to UTF-8" -ForegroundColor Green
    }
    elseif ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) {
        Write-Host "⚠️  Detected UTF-16 BE encoding (with BOM)" -ForegroundColor Red
        Write-Host "Converting to UTF-8..." -ForegroundColor Yellow
        
        # Read as UTF-16 BE and write as UTF-8
        $content = [System.IO.File]::ReadAllText($envPath, [System.Text.Encoding]::BigEndianUnicode)
        [System.IO.File]::WriteAllText($envPath, $content, [System.Text.Encoding]::UTF8)
        
        Write-Host "✅ Converted to UTF-8" -ForegroundColor Green
    }
    else {
        Write-Host "✅ File appears to be UTF-8 or ASCII" -ForegroundColor Green
    }
    
    # Verify it can be read as UTF-8
    try {
        $test = [System.IO.File]::ReadAllText($envPath, [System.Text.Encoding]::UTF8)
        Write-Host "✅ File can be read as UTF-8" -ForegroundColor Green
    }
    catch {
        Write-Host "❌ File still has encoding issues. Recreating..." -ForegroundColor Red
        
        # Backup old file
        $backupPath = "$envPath.backup"
        Copy-Item $envPath $backupPath
        Write-Host "Backed up to: $backupPath" -ForegroundColor Yellow
        
        # Create new UTF-8 file from example
        $examplePath = Join-Path $PSScriptRoot ".env.example"
        if (Test-Path $examplePath) {
            $content = [System.IO.File]::ReadAllText($examplePath, [System.Text.Encoding]::UTF8)
            [System.IO.File]::WriteAllText($envPath, $content, [System.Text.Encoding]::UTF8)
            Write-Host "✅ Created new .env from .env.example" -ForegroundColor Green
            Write-Host "⚠️  Please update EDON_API_TOKEN in .env" -ForegroundColor Yellow
        }
        else {
            # Create minimal .env
            $minimal = @"
EDON_AUTH_ENABLED=true
EDON_API_TOKEN=your-secret-token-change-me
EDON_DATABASE_PATH=edon_gateway.db
"@
            [System.IO.File]::WriteAllText($envPath, $minimal, [System.Text.Encoding]::UTF8)
            Write-Host "✅ Created minimal .env file" -ForegroundColor Green
            Write-Host "⚠️  Please update EDON_API_TOKEN" -ForegroundColor Yellow
        }
    }
}
else {
    Write-Host "⚠️  .env file not found" -ForegroundColor Yellow
    Write-Host "Creating from .env.example..." -ForegroundColor Yellow
    
    $examplePath = Join-Path $PSScriptRoot ".env.example"
    if (Test-Path $examplePath) {
        $content = [System.IO.File]::ReadAllText($examplePath, [System.Text.Encoding]::UTF8)
        [System.IO.File]::WriteAllText($envPath, $content, [System.Text.Encoding]::UTF8)
        Write-Host "✅ Created .env from .env.example" -ForegroundColor Green
    }
    else {
        Write-Host "❌ .env.example not found. Creating minimal .env..." -ForegroundColor Yellow
        $minimal = @"
EDON_AUTH_ENABLED=true
EDON_API_TOKEN=your-secret-token-change-me
EDON_DATABASE_PATH=edon_gateway.db
"@
        [System.IO.File]::WriteAllText($envPath, $minimal, [System.Text.Encoding]::UTF8)
        Write-Host "✅ Created minimal .env file" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Done! You can now start the gateway:" -ForegroundColor Green
Write-Host "  python -m edon_gateway.main" -ForegroundColor Cyan
