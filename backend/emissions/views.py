"""
Review queue + record detail + state transitions + small read-only settings views.

State transitions are explicit endpoints (`/approve`, `/flag`, `/reject`,
`/lock`, `/unlock`) rather than PATCHing `review_state`. This gives us:
  * a single place to enforce role gating (analyst vs admin)
  * a single place to write the audit entry
  * clear API contract — the verb is in the URL, not buried in a payload

Edits go through PATCH on the detail endpoint, which requires the `If-Match`
header to carry the current `version`. Mismatch → 412 with the current state.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit import record_change
from core.models import AuditAction, MembershipRole
from core.utils import require_org, require_role
from ingestion.models import IngestionBatch

from .anomaly import compute_hints
from .calc import pin_factor_and_compute
from .models import (
    ActivityRecord,
    Airport,
    CanonicalUnit,
    EmissionCategory,
    EmissionFactor,
    PlantCode,
    ReviewState,
)
from .serializers import (
    ActivityRecordEditSerializer,
    ActivityRecordSerializer,
    AirportSerializer,
    CanonicalUnitSerializer,
    EmissionCategorySerializer,
    EmissionFactorSerializer,
    PlantCodeSerializer,
)


class QueueView(generics.ListAPIView):
    serializer_class = ActivityRecordSerializer

    def get_queryset(self):
        org = require_org(self.request)
        qs = ActivityRecord.objects.for_org(org).select_related(
            "category", "unit", "emission_factor"
        )

        state = self.request.query_params.get("state")
        if state in ReviewState.values:
            qs = qs.filter(review_state=state)
        cat = self.request.query_params.get("category")
        if cat:
            qs = qs.filter(category__code=cat)
        batch = self.request.query_params.get("batch")
        if batch and batch.isdigit():
            qs = qs.filter(source_record__batch_id=int(batch))
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(facility_code__icontains=q) | Q(notes__icontains=q)
            )
        return qs


class ActivityDetailView(APIView):
    def get(self, request, pk):
        org = require_org(request)
        record = ActivityRecord.objects.for_org(org).select_related(
            "category", "unit", "emission_factor", "source_record__batch"
        ).get(pk=pk)
        body = ActivityRecordSerializer(record).data
        body["hints"] = [h.__dict__ for h in compute_hints(record)]
        if record.source_record_id:
            body["raw_payload"] = record.source_record.raw_payload
            body["source_line"] = record.source_record.line_number
        return Response(body)

    def patch(self, request, pk):
        org = require_org(request)
        record = ActivityRecord.objects.for_org(org).select_for_update().get(pk=pk)

        if record.review_state == ReviewState.LOCKED:
            raise PermissionDenied("Record is locked for audit.")

        # Optimistic locking via If-Match
        if_match = request.headers.get("If-Match")
        if if_match is None or not if_match.isdigit() or int(if_match) != record.version:
            return Response(
                {"detail": "Version mismatch.",
                 "current_version": record.version,
                 "current": ActivityRecordSerializer(record).data},
                status=status.HTTP_412_PRECONDITION_FAILED,
            )

        ser = ActivityRecordEditSerializer(record, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)

        before = ActivityRecordSerializer(record).data
        with transaction.atomic():
            for field, value in ser.validated_data.items():
                setattr(record, field, value)
            record.version = record.version + 1
            # Re-pin factor if value/unit/date changed.
            pin_factor_and_compute(record)
            record.save()
            after = ActivityRecordSerializer(record).data
            record_change(
                organization=org, actor=request.user,
                action=AuditAction.UPDATED, target=record,
                before=before, after=after,
            )
        return Response(after)


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


class _TransitionView(APIView):
    """Base class for state-changing endpoints. Subclasses set the verb."""

    audit_action: AuditAction
    new_state: ReviewState
    require_roles: tuple[str, ...] = (MembershipRole.ANALYST, MembershipRole.ADMIN)
    forbid_if_locked: bool = True

    def post(self, request, pk):
        org = require_org(request)
        require_role(request, org, *self.require_roles)
        record = ActivityRecord.objects.for_org(org).select_for_update().get(pk=pk)
        if self.forbid_if_locked and record.review_state == ReviewState.LOCKED:
            raise PermissionDenied("Record is locked for audit.")
        reason = request.data.get("reason") or None
        if self.audit_action in (AuditAction.LOCKED, AuditAction.UNLOCKED) and not reason:
            raise ValidationError({"reason": "Required for lock/unlock."})

        before = ActivityRecordSerializer(record).data
        with transaction.atomic():
            record.review_state = self.new_state
            record.reviewed_by = request.user
            record.reviewed_at = timezone.now()
            if self.new_state == ReviewState.LOCKED:
                record.locked_at = timezone.now()
            elif self.audit_action == AuditAction.UNLOCKED:
                record.locked_at = None
                # Bypass the locked-mutation guard for this one save.
                record.save(_unlock=True)
                after = ActivityRecordSerializer(record).data
                record_change(
                    organization=org, actor=request.user,
                    action=self.audit_action, target=record,
                    before=before, after=after, reason=reason,
                )
                return Response(after)
            record.save()
            after = ActivityRecordSerializer(record).data
            record_change(
                organization=org, actor=request.user,
                action=self.audit_action, target=record,
                before=before, after=after, reason=reason,
            )
        return Response(after)


class ApproveView(_TransitionView):
    audit_action = AuditAction.APPROVED
    new_state = ReviewState.APPROVED


class FlagView(_TransitionView):
    audit_action = AuditAction.FLAGGED
    new_state = ReviewState.FLAGGED


class RejectView(_TransitionView):
    audit_action = AuditAction.REJECTED
    new_state = ReviewState.REJECTED


class LockView(_TransitionView):
    audit_action = AuditAction.LOCKED
    new_state = ReviewState.LOCKED
    require_roles = (MembershipRole.ADMIN,)


class UnlockView(_TransitionView):
    audit_action = AuditAction.UNLOCKED
    new_state = ReviewState.APPROVED
    require_roles = (MembershipRole.ADMIN,)
    forbid_if_locked = False


# ---------------------------------------------------------------------------
# Overview + settings
# ---------------------------------------------------------------------------


class OverviewView(APIView):
    def get(self, request):
        org = require_org(request)
        qs = ActivityRecord.objects.for_org(org)
        totals = qs.aggregate(
            total_kg_co2e=Sum("emissions_kg_co2e"),
            pending=Count("id", filter=Q(review_state=ReviewState.PENDING)),
            flagged=Count("id", filter=Q(review_state=ReviewState.FLAGGED)),
            approved=Count("id", filter=Q(review_state=ReviewState.APPROVED)),
            locked=Count("id", filter=Q(review_state=ReviewState.LOCKED)),
        )
        # By scope
        by_scope = (
            qs.values("category__scope")
            .annotate(kg=Sum("emissions_kg_co2e"), n=Count("id"))
            .order_by("category__scope")
        )
        last_batch = (
            IngestionBatch.objects.for_org(org)
            .order_by("-uploaded_at").first()
        )
        return Response({
            "totals": {
                "kg_co2e": float(totals["total_kg_co2e"] or 0),
                "pending": totals["pending"],
                "flagged": totals["flagged"],
                "approved": totals["approved"],
                "locked": totals["locked"],
            },
            "by_scope": [
                {"scope": row["category__scope"], "kg_co2e": float(row["kg"] or 0), "rows": row["n"]}
                for row in by_scope
            ],
            "last_batch": {
                "id": last_batch.id,
                "source_type": last_batch.source_type,
                "uploaded_at": last_batch.uploaded_at,
                "status": last_batch.status,
            } if last_batch else None,
        })


class FactorListView(generics.ListAPIView):
    serializer_class = EmissionFactorSerializer
    queryset = EmissionFactor.objects.select_related("category", "unit").all()


class LookupsView(APIView):
    def get(self, request):
        org = require_org(request)
        return Response({
            "plant_codes": PlantCodeSerializer(
                PlantCode.objects.filter(organization=org), many=True).data,
            "airports": AirportSerializer(Airport.objects.all()[:200], many=True).data,
        })


class UnitsView(generics.ListAPIView):
    serializer_class = CanonicalUnitSerializer
    queryset = CanonicalUnit.objects.all()
