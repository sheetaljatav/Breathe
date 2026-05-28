from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Organization
from .serializers import OrganizationSerializer
from .utils import current_org


class OrgListView(APIView):
    """All orgs the current user is a member of (for the org switcher)."""

    def get(self, request):
        orgs = Organization.objects.filter(memberships__user=request.user).distinct()
        return Response(OrganizationSerializer(orgs, many=True).data)


class CurrentOrgView(APIView):
    """The org currently scoping this request (from X-Org-ID or membership default)."""

    def get(self, request):
        org = current_org(request)
        if org is None:
            return Response({"detail": "No org context."}, status=status.HTTP_404_NOT_FOUND)
        return Response(OrganizationSerializer(org).data)
