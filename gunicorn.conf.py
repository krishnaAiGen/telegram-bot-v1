# Gunicorn configuration file
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Server socket
bind = f"{os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', '9000')}"
backlog = 2048

# Worker processes
workers = 1  # Use only 1 worker to avoid fork issues on macOS
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
timeout = 30
keepalive = 10

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "telegram-bot-backend"

# Disable preload to avoid fork issues on macOS with Firebase/Google Cloud
preload_app = False

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
