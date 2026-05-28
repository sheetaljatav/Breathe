"""
Corporate-travel JSON parser (Concur Reporting API v4 shape).

Why JSON paste vs real API:
  Concur OAuth onboarding requires a corporate-customer relationship with
  SAP Concur and per-tenant App Center approval — not achievable in a
  prototype. We accept the same response shape an authenticated Reporting v4
  call would return, so the parser we ship is exactly the parser a real
  integration would use. The shipping cost is the trust boundary (paste vs
  signed API call), not the data shape. See SOURCES.md.

Real-world shape — top-level: {"metadata": {...}, "trips": [...]}
Each trip has segments[], where segments[i].type ∈ {AIR, LODGING, CAR}.

Quirks handled:
  * AIR segments may have null distance_km → we look up via Airport table
    and compute great-circle. Unknown airport → UNRESOLVABLE_AIRPORT.
  * LODGING: nights × emission factor (room-nights category).
  * CAR: distance_km × ground-transport factor.

Quirks NOT handled (deliberately):
  * Rail segments (not in our category set yet)
  * Cabin class differentiation for AIR (Business is ~3× Economy; we use a
    single short-haul-economy-style factor and note this in SOURCES)
  * Hotel emission factor by chain/property
  * Multi-leg fare splits
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from ingestion.models import ParseErrorCode

from .base import (
    ActivityDraft,
    ParseErrorShape,
    Parser,
    ParseResult,
    SourceRecordShape,
    register,
)


def _great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in km. Earth radius 6371 km."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@register
class TravelParser(Parser):
    source_type = "travel"

    def parse(self, data: bytes, *, context: dict | None = None) -> ParseResult:
        result = ParseResult()
        airports = (context or {}).get("airports") or {}    # {iata: (lat, lon)}

        try:
            doc = json.loads(data.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            result.errors.append(ParseErrorShape(
                line_number=1, error_code=ParseErrorCode.BAD_NUMBER,
                field_path="<root>", message=f"Invalid JSON: {e}",
            ))
            return result

        trips: Iterable[dict] = doc.get("trips") or []
        line_no = 0
        for trip in trips:
            trip_id = trip.get("trip_id", "")
            for seg in trip.get("segments", []):
                line_no += 1
                payload = {"trip_id": trip_id, "employee_id": trip.get("employee_id", ""), **seg}
                result.records.append(SourceRecordShape(line_number=line_no, raw_payload=payload))

                seg_type = seg.get("type")
                draft_or_error = self._segment_to_draft(line_no, seg, airports)
                if isinstance(draft_or_error, ParseErrorShape):
                    result.errors.append(draft_or_error)
                elif draft_or_error is not None:
                    result.drafts.append(draft_or_error)

        return result

    # ---- per-segment ------------------------------------------------------

    def _segment_to_draft(
        self, line_no: int, seg: dict, airports: dict[str, tuple[float, float]],
    ) -> ActivityDraft | ParseErrorShape | None:
        seg_type = seg.get("type")

        if seg_type == "AIR":
            return self._air(line_no, seg, airports)
        if seg_type == "LODGING":
            return self._lodging(line_no, seg)
        if seg_type == "CAR":
            return self._car(line_no, seg)
        return ParseErrorShape(
            line_number=line_no, error_code=ParseErrorCode.UNKNOWN_CATEGORY,
            field_path="type", message=f"Unsupported segment type: {seg_type!r}",
            raw_excerpt={"type": seg_type},
        )

    def _air(self, line_no, seg, airports):
        origin = seg.get("origin_iata")
        dest = seg.get("destination_iata")
        dist = seg.get("distance_km")

        if dist is None and origin and dest:
            try:
                lat1, lon1 = airports[origin]
                lat2, lon2 = airports[dest]
            except KeyError as miss:
                return ParseErrorShape(
                    line_number=line_no, error_code=ParseErrorCode.UNRESOLVABLE_AIRPORT,
                    field_path="origin_iata/destination_iata",
                    message=f"Airport not in lookup table: {miss.args[0]!r}",
                    raw_excerpt={"origin_iata": origin, "destination_iata": dest},
                )
            dist = _great_circle_km(lat1, lon1, lat2, lon2)

        if dist is None:
            return ParseErrorShape(
                line_number=line_no, error_code=ParseErrorCode.MISSING_FIELD,
                field_path="distance_km",
                message="distance_km missing and IATA pair could not resolve it.",
            )

        try:
            activity_date = self._parse_dt(seg.get("departure_at") or seg.get("trip_at") or "")
        except ValueError as e:
            return ParseErrorShape(
                line_number=line_no, error_code=ParseErrorCode.BAD_DATE,
                field_path="departure_at", message=str(e),
            )

        return ActivityDraft(
            line_number=line_no,
            category_code="business_travel_air",
            activity_date=activity_date,
            value=Decimal(str(dist)).quantize(Decimal("0.001")),
            canonical_unit_code="passenger_km",
            notes=f"{seg.get('vendor', '')} {origin}->{dest} "
                  f"cabin={seg.get('cabin_class', 'ECONOMY')}",
        )

    def _lodging(self, line_no, seg):
        nights = seg.get("nights")
        if nights is None:
            return ParseErrorShape(
                line_number=line_no, error_code=ParseErrorCode.MISSING_FIELD,
                field_path="nights", message="Lodging segment missing `nights`.",
            )
        try:
            checkin = self._parse_dt(seg.get("checkin_date", ""))
        except ValueError as e:
            return ParseErrorShape(
                line_number=line_no, error_code=ParseErrorCode.BAD_DATE,
                field_path="checkin_date", message=str(e),
            )
        return ActivityDraft(
            line_number=line_no,
            category_code="business_travel_lodging",
            activity_date=checkin,
            value=Decimal(str(nights)),
            canonical_unit_code="room_nights",
            notes=f"{seg.get('vendor', '')} property={seg.get('property_id', '')}",
        )

    def _car(self, line_no, seg):
        dist = seg.get("distance_km")
        if dist is None:
            return ParseErrorShape(
                line_number=line_no, error_code=ParseErrorCode.MISSING_FIELD,
                field_path="distance_km", message="Car segment missing `distance_km`.",
            )
        try:
            activity_date = self._parse_dt(seg.get("trip_at") or seg.get("checkin_date") or "")
        except ValueError as e:
            return ParseErrorShape(
                line_number=line_no, error_code=ParseErrorCode.BAD_DATE,
                field_path="trip_at", message=str(e),
            )
        return ActivityDraft(
            line_number=line_no,
            category_code="business_travel_ground",
            activity_date=activity_date,
            value=Decimal(str(dist)),
            canonical_unit_code="km",
            notes=f"{seg.get('vendor', '')} category={seg.get('category', '')}",
        )

    @staticmethod
    def _parse_dt(text: str) -> date:
        if not text:
            raise ValueError("empty date/time")
        # Accept both '2026-04-12' and '2026-04-12T07:30:00Z'.
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
