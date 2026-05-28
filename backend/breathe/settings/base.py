"""
Base settings shared by dev and prod.

Two principles drive the layout here:
  1. Read from environment, validate at startup. No silent defaults for security-
     sensitive values (SECRET_KEY, ALLOWED_HOSTS, DATABASE_URL in prod).
  2. AUTHENTICATION_BACKENDS is the seam for SAML/OIDC. We ship the session
     backend; production deployments slot a SAML backend in front of it without
     touching app code.
"""

from __future__ import annotations

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(key: str, default: str | None = None, *, required: bool = False) -> str:
    val = os.environ.get(key, default)
    if required and not val:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val or ""


SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-do-not-use-in-prod")
DEBUG = env("DJANGO_DEBUG", default="false").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", default="").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",     # ops debugging — superuser-only, no demo users have staff=True
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    # Local
    "core",
    "ingestion",
    "emissions",
]

MIDDLEWARE = [
    # request_id must run first so every downstream log line carries it.
    "breathe.middleware.RequestIdMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # RLS context must run AFTER auth so we know the user's org.
    "breathe.middleware.TenantRLSMiddleware",
]

ROOT_URLCONF = "breathe.urls"
WSGI_APPLICATION = "breathe.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", default="postgres://breathe:breathe@localhost:5432/breathe"),
        conn_max_age=60,         # connection pooling — no per-request thrash
        conn_health_checks=True,
    )
}

# Use BigAutoField everywhere; bigserial PKs are the only sensible default
# for tables that may grow into the tens of millions (SourceRecord, AuditLog).
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Pluggable auth: session for v1; SAML/OIDC backends prepend here in production.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"        # all storage is UTC; UI handles local display
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"      # uploaded source files (deleted post-parse)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# CORS — explicit allowlist, never wildcards.
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in env("DJANGO_CORS_ALLOWED_ORIGINS", default="").split(",") if o.strip()
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept", "accept-encoding", "authorization", "content-type", "dnt", "origin",
    "user-agent", "x-csrftoken", "x-requested-with",
    # Our custom headers:
    "x-org-id", "if-match",
]
CORS_EXPOSE_HEADERS = ["x-request-id"]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "breathe.pagination.DefaultCursorPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# Celery
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_ACKS_LATE = True          # don't lose tasks on worker crash mid-run
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 600          # hard 10-min cap; parsers should finish well under
CELERY_TASK_SOFT_TIME_LIMIT = 540
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # one task at a time per worker, fairer scheduling

# Sessions: keep server-side; lighter cookie payload + supports invalidation.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False           # frontend reads csrftoken to set the X-CSRFToken header
CSRF_COOKIE_SAMESITE = "Lax"

# RLS: name of the Postgres GUC that middleware sets per request.
# Used by RLS policies in the migration.
RLS_ORG_GUC = "app.current_org_id"
RLS_USER_GUC = "app.current_user_id"

# Apply structured logging immediately.
from .. import logging as _logging  # noqa: E402
_logging.configure_structlog()
LOGGING = _logging.LOGGING_CONFIG
