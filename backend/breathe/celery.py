"""Celery app configuration.

Tasks auto-discover from `<app>/tasks.py` modules in every INSTALLED_APP.
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "breathe.settings.dev")

app = Celery("breathe")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self) -> str:
    """No-op task used by the smoke test to verify worker + broker reachability."""
    return f"ok:{self.request.id}"
