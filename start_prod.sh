#!/bin/bash

# Production startup script for Telegram Bot Backend
# This script starts the server with production-ready settings

# Load environment variables
if [ -f .env ]; then
    source .env
fi

# Set default values
PORT=${PORT:-9000}
HOST=${HOST:-0.0.0.0}
WORKERS=${WORKERS:-1}  # Use 1 worker to avoid macOS fork issues

echo "Starting Telegram Bot Backend in Production Mode..."
echo "Host: $HOST"
echo "Port: $PORT"
echo "Workers: $WORKERS"

# Start with production settings
exec gunicorn backend.main:app \
    --bind $HOST:$PORT \
    --workers $WORKERS \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 60 \
    --keep-alive 10 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
