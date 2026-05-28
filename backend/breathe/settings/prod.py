"""Production settings (Render)."""

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# These three are required at boot in prod. Fail fast if absent.
SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", required=True).split(",") if h.strip()]

# Security headers
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Frontend and backend live on different *.onrender.com subdomains, so cookies
# must be SameSite=None to flow on cross-origin XHR. Secure is required when
# SameSite=None per the spec, and we already set it.
SESSION_COOKIE_SAMESITE = "None"
CSRF_COOKIE_SAMESITE = "None"
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30   # 30 days; ramp up after confidence
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False               # don't preload until we're sure
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Sentry
_dsn = env("SENTRY_DSN", default="")
if _dsn:
    sentry_sdk.init(
        dsn=_dsn,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        # Performance off for the prototype; errors only.
        traces_sample_rate=0.0,
        send_default_pii=False,
        environment="production",
    )
