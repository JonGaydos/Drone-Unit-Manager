#!/bin/bash
set -e

echo "========================================="
echo "  Drone Unit Manager"
echo "  Starting up..."
echo "========================================="

# Ensure data directories exist
mkdir -p /app/data/uploads/documents /app/data/media_cache

# Generate secret key if not provided
if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "change-me-in-production" ]; then
    if [ ! -f /app/data/.secret_key ]; then
        python -c "import secrets; print(secrets.token_hex(32))" > /app/data/.secret_key
        echo "Generated new secret key"
    fi
    export SECRET_KEY=$(cat /app/data/.secret_key)
fi

echo "Data directory: $DATA_DIR"
echo "Database: $DATABASE_URL"
echo "========================================="

# Run the application
exec "$@"
