#!/bin/bash
# Setup script for EDON Console UI integration

set -e

echo "Setting up EDON Console UI..."

# Navigate to UI directory
cd "$(dirname "$0")"

# Clone the UI repository if it doesn't exist
if [ ! -d "console-ui" ]; then
    echo "Cloning edon-console-ui repository..."
    git clone https://github.com/GHOSTCODERRRRAHAHA/edon-console-ui.git console-ui
else
    echo "console-ui directory already exists, pulling latest changes..."
    cd console-ui
    git pull
    cd ..
fi

# Navigate to console-ui
cd console-ui

# Install dependencies
if [ ! -d "node_modules" ]; then
    echo "Installing npm dependencies..."
    npm install
else
    echo "Dependencies already installed"
fi

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cat > .env << EOF
VITE_EDON_GATEWAY_URL=http://localhost:8000
VITE_EDON_GATEWAY_TOKEN=
EOF
    echo ".env file created. Please update VITE_EDON_GATEWAY_TOKEN if needed."
else
    echo ".env file already exists"
fi

echo ""
echo "Setup complete!"
echo ""
echo "To start the development server:"
echo "  cd edon_gateway/ui/console-ui"
echo "  npm run dev"
echo ""
echo "To build for production:"
echo "  cd edon_gateway/ui/console-ui"
echo "  npm run build"
echo ""
