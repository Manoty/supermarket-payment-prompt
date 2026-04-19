# backend/gunicorn.conf.py

import multiprocessing

# Server socket
bind = "0.0.0.0:8000"

# Workers — 2-4 x number of CPUs
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = "-"       # stdout
errorlog = "-"        # stdout
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s'

# Process naming
proc_name = "supermarket_payments"

# Restart workers after this many requests (prevents memory leaks)
max_requests = 1000
max_requests_jitter = 50