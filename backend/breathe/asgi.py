"""ASGI entry point (unused; gunicorn WSGI is the prod server)."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "breathe.settings.prod")

application = get_asgi_application()
