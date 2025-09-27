#!/bin/bash
# Environment setup script for different configurations

set -e

ENV=${1:-local}

echo "🔧 Setting up environment: $ENV"

# Copy the appropriate environment file
if [ -f "env.$ENV.example" ]; then
    cp "env.$ENV.example" ".env"
    echo "✅ Copied env.$ENV.example to .env"
else
    echo "❌ Environment file env.$ENV.example not found"
    echo "Available environments:"
    ls env.*.example 2>/dev/null || echo "No environment files found"
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

echo "🔧 Environment variables loaded:"
echo "  ENVIRONMENT: $ENVIRONMENT"
echo "  DB_HOST: $DB_HOST"
echo "  DB_USER: $DB_USER"
echo "  GITHUB_USER: $GITHUB_USER"
echo "  GITHUB_BRANCH: $GITHUB_BRANCH"

echo ""
echo "🚀 Ready to run generator with $ENV environment"
echo "Run: python generate_site.py"
