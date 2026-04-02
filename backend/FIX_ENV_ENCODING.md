# Fix .env File Encoding Issue

## Problem

The `.env` file has invalid UTF-8 encoding (likely UTF-16 with BOM or corrupted).

Error:
```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0
```

## Solution

### Option 1: Recreate .env File (Recommended)

**Delete and recreate:**
```powershell
cd edon_gateway
Remove-Item .env -ErrorAction SilentlyContinue
Copy-Item .env.example .env
# Edit .env with your values
```

**Or create fresh:**
```powershell
cd edon_gateway
@"
EDON_AUTH_ENABLED=true
EDON_API_TOKEN=your-new-token-here
EDON_DATABASE_PATH=edon_gateway.db
"@ | Out-File -FilePath .env -Encoding UTF8
```

### Option 2: Fix Encoding

**Convert existing file:**
```powershell
cd edon_gateway
$content = Get-Content .env -Raw
$content | Out-File -FilePath .env -Encoding UTF8 -NoNewline
```

### Option 3: Use Notepad++ or VS Code

1. Open `.env` in Notepad++ or VS Code
2. Go to Encoding → Convert to UTF-8
3. Save file

## Verification

**Check file encoding:**
```powershell
cd edon_gateway
Get-Content .env -Encoding UTF8 | Select-Object -First 5
```

**Should show:**
```
EDON_AUTH_ENABLED=true
EDON_API_TOKEN=...
```

## After Fix

Restart gateway:
```powershell
python -m edon_gateway.main
```

Should start without encoding errors.
