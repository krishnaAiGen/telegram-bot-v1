# Deployment Guide

## Server Configuration

### Environment Variables
Create a `.env` file in the project root with the following variables:

```bash
# Server Configuration
PORT=9000
HOST=0.0.0.0

# Application Settings
ENVIRONMENT=development
DEBUG=True

# Add your API keys and other environment variables here
```

## Running the Server

### Development Mode (with auto-reload)
```bash
# For macOS (recommended)
./start_macos.sh

# For other systems
./start_server.sh

# Or directly with gunicorn
gunicorn backend.main:app --config gunicorn.conf.py --reload
```

### Production Mode
```bash
# Using the production script
./start_prod.sh

# Or directly with gunicorn
gunicorn backend.main:app \
    --bind 0.0.0.0:9000 \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 60 \
    --keep-alive 10 \
    --max-requests 1000 \
    --preload
```

### Quick Commands

**Development:**
```bash
gunicorn backend.main:app --config gunicorn.conf.py --reload
```

**Production:**
```bash
# For macOS
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES gunicorn backend.main:app --bind 0.0.0.0:9000 --workers 1 --worker-class uvicorn.workers.UvicornWorker

# For other systems
gunicorn backend.main:app --bind 0.0.0.0:9000 --workers 2 --worker-class uvicorn.workers.UvicornWorker
```

## Migration from Uvicorn

If you were previously using:
```bash
uvicorn backend.main:app --reload --port 9000
```

You can now use:
```bash
gunicorn backend.main:app --config gunicorn.conf.py --reload
```

## Configuration Files

- `gunicorn.conf.py` - Main gunicorn configuration
- `start_server.sh` - Development startup script
- `start_prod.sh` - Production startup script
- `.env` - Environment variables (create this file)

## Benefits of Gunicorn

- Better production performance
- Process management and monitoring
- Graceful worker restarts
- Built-in logging configuration
- Better memory management
- Production-ready settings

## Troubleshooting

### macOS Fork Safety Issues

If you see errors like:
```
objc[xxxxx]: +[__NSCFConstantString initialize] may have been in progress in another thread when fork() was called.
```

**Solution 1:** Use the macOS-specific startup script:
```bash
./start_macos.sh
```

**Solution 2:** Set the environment variable manually:
```bash
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
gunicorn backend.main:app --config gunicorn.conf.py --reload
```

**Solution 3:** Use single worker mode:
```bash
gunicorn backend.main:app --bind 0.0.0.0:9000 --workers 1 --worker-class uvicorn.workers.UvicornWorker
```

### Performance Notes

- **macOS Development**: Use 1 worker for stability
- **Linux Production**: Can use multiple workers (2-4 workers recommended)
- **Memory Usage**: Single worker uses less memory but handles fewer concurrent requests
