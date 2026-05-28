from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import record_change
from .models import AuditAction
from .serializers import LoginSerializer, UserSerializer
from .utils import current_org


class CsrfView(APIView):
    """Issue a csrftoken cookie. Called by the SPA on app boot."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrftoken": get_token(request)})


@method_decorator(ratelimit(key="ip", rate="10/m", method="POST", block=True), name="post")
class LoginView(APIView):
    """
    Email + password → session. Rate-limited per IP.

    We resolve user by email (not username) because that's how real ESG
    enterprise SSO will eventually identify users. Username is unused
    internally and unset on creation; we treat email as the user identity.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        User = get_user_model()
        try:
            user_obj = User.objects.get(email__iexact=ser.validated_data["email"])
        except User.DoesNotExist:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        user = authenticate(request, username=user_obj.username, password=ser.validated_data["password"])
        if user is None:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        login(request, user)

        # Best-effort audit; failing the audit write should not fail login.
        org = current_org(request)
        if org is not None:
            try:
                record_change(
                    organization=org, actor=user, action=AuditAction.LOGGED_IN, target=user
                )
            except Exception:  # noqa: BLE001
                pass

        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
