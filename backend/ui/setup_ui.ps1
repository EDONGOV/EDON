# Setup script for EDON Console UI integration (PowerShell)

Write-Host "Setting up EDON Console UI..." -ForegroundColor Cyan

# Navigate to UI directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# Clone the UI repository if it doesn't exist
if (-not (Test-Path "console-ui")) {
    Write-Host "Cloning edon-console-ui repository..." -ForegroundColor Yellow
    git clone https://github.com/GHOSTCODERRRRAHAHA/edon-console-ui.git console-ui
} else {
    Write-Host "console-ui directory already exists, pulling latest changes..." -ForegroundColor Yellow
    Set-Location console-ui
    git pull
    Set-Location ..
}

# Navigate to console-ui
Set-Location console-ui

# Install dependencies
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing npm dependencies..." -ForegroundColor Yellow
    npm install
} else {
    Write-Host "Dependencies already installed" -ForegroundColor Green
}

# Create .env file if it doesn't exist
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env file..." -ForegroundColor Yellow
    @"
VITE_EDON_GATEWAY_URL=http://localhost:8000
VITE_EDON_GATEWAY_TOKEN=
"@ | Out-File -FilePath ".env" -Encoding utf8
    Write-Host ".env file created. Please update VITE_EDON_GATEWAY_TOKEN if needed." -ForegroundColor Yellow
} else {
    Write-Host ".env file already exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To start the development server:" -ForegroundColor Cyan
Write-Host "  cd edon_gateway\ui\console-ui"
Write-Host "  npm run dev"
Write-Host ""
Write-Host "To build for production:" -ForegroundColor Cyan
Write-Host "  cd edon_gateway\ui\console-ui"
Write-Host "  npm run build"
Write-Host ""
