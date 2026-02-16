#!/bin/bash
# Copyright 2025
#
# Setup script for incident response RAG pipeline

set -e

echo "🚀 Setting up Incident Response RAG Pipeline..."
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
else
    echo "✅ uv already installed"
fi

# Install dependencies
echo ""
echo "📦 Installing Python dependencies..."
uv sync

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Set up GCP credentials:"
echo "     export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json"
echo ""
echo "  2. Compile the pipeline:"
echo "     make compile"
echo ""
echo "  3. Submit the pipeline:"
echo "     make submit PROJECT_ID=your-project DRIVE_FOLDER_ID=folder-id IMPERSONATION_USER=user@domain.com"
echo ""
echo "For more information, see README.md"
