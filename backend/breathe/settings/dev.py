"""Local development settings."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# CORS for Vite dev server
CORS_ALLOWED_ORIGINS = [
    *[o for o in env("DJANGO_CORS_ALLOWED_ORIGINS", default="").split(",") if o],
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Loosen CSRF for cross-origin Vite during dev
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# Run Celery tasks synchronously in-process so local dev requires no broker or
# worker. parse_batch runs immediately on upload; the queue is populated before
# the browser's first poll fires.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
