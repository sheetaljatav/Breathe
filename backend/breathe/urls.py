"""Root URL configuration."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt


def healthz(_request):
    """Process is up."""
    return JsonResponse({"status": "ok"})


def readyz(_request):
    """DB + Redis reachable. Render's healthCheckPath uses /healthz instead so a
    DB blip doesn't kill the web service; /readyz is for explicit checks."""
    from django.db import connection
    from breathe.celery import app as celery_app

    db_ok = False
    redis_ok = False
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            db_ok = cur.fetchone() == (1,)
    except Exception:  # noqa: BLE001
        db_ok = False
    try:
        celery_app.connection().ensure_connection(max_retries=1, timeout=1)
        redis_ok = True
    except Exception:  # noqa: BLE001
        redis_ok = False

    payload = {"db": db_ok, "redis": redis_ok}
    status = 200 if db_ok and redis_ok else 503
    return JsonResponse(payload, status=status)


@csrf_exempt
def sentry_test(_request):
    """
    Deliberately raise so the Sentry integration can be verified end-to-end
    on a deployed environment. Gated to authenticated superuser in prod via
    Django admin auth — we use csrf_exempt and rely on the view itself
    checking request.user.is_superuser.
    """
    if not _request.user.is_superuser:
        return JsonResponse({"detail": "Superuser only."}, status=403)
    raise RuntimeError("sentry-test: this exception is intentional")


urlpatterns = [
    path("healthz", healthz),
    path("readyz", readyz),
    path("admin/", admin.site.urls),
    path("api/_internal/sentry-test", sentry_test),
    path("api/auth/", include("core.urls_auth")),
    path("api/", include("core.urls")),
    path("api/", include("ingestion.urls")),
    path("api/", include("emissions.urls")),
]
