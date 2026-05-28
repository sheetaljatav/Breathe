"""
Utility portal CSV parser (electricity).

Why CSV from a portal export (and not API integration):
  Facilities teams typically log into the utility's web portal monthly and
  download a billing-period CSV. The two big real-world utility platforms in
  the US (e.g., commercial portals at major utilities like Con Edison or
  Duke) expose this download. APIs exist but require per-utility integration
  contracts. See SOURCES.md.

Real-world shape:
  meter_id, service_address, rate_class,
  billing_period_start, billing_period_end,
  consumption, consumption_unit (kWh or MWh in practice),
  peak_kwh, off_peak_kwh, demand_kw, total_charges_usd

Real quirks we handle:
  * Billing periods that span calendar months ("2026-03-15" to "2026-04-14")
  * Mixed units in the same export: some rows in kWh, some in MWh
  * activity_date is the billing_period_end (the date the consumption is
    "as-of" — what's used for emission-factor year selection)

Quirks we DO NOT handle:
  * Peak / off-peak factor differentiation (we sum to total kWh; documented)
  * kVA demand charges
  * Multi-meter aggregation (one row = one meter-month)
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

from emissions.converters import UnitNotSupported, convert
from ingestion.models import ParseErrorCode

from .base import (
    ActivityDraft,
    ParseErrorShape,
    Parser,
    ParseResult,
    SourceRecordShape,
    register,
)


@register
class UtilityCSVParser(Parser):
    source_type = "utility_csv"

    def parse(self, data: bytes, *, context: dict | None = None) -> ParseResult:
        result = ParseResult()
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        required = {"meter_id", "billing_period_start", "billing_period_end",
                    "consumption", "consumption_unit"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            result.errors.append(ParseErrorShape(
                line_number=1, error_code=ParseErrorCode.MISSING_FIELD,
                field_path=",".join(sorted(missing)),
                message=f"Utility CSV missing required columns: {sorted(missing)}",
            ))
            return result

        for idx, row in enumerate(reader, start=2):
            payload = {k: (v or "").strip() for k, v in row.items()}
            result.records.append(SourceRecordShape(line_number=idx, raw_payload=payload))

            try:
                period_start = date.fromisoformat(payload["billing_period_start"])
                period_end = date.fromisoformat(payload["billing_period_end"])
            except ValueError as e:
                result.errors.append(ParseErrorShape(
                    line_number=idx, error_code=ParseErrorCode.BAD_DATE,
                    field_path="billing_period_*", message=str(e),
                    raw_excerpt={k: payload.get(k) for k in
                                 ("billing_period_start", "billing_period_end")},
                ))
                continue

            try:
                qty = Decimal(payload["consumption"])
            except Exception as e:  # noqa: BLE001
                result.errors.append(ParseErrorShape(
                    line_number=idx, error_code=ParseErrorCode.BAD_NUMBER,
                    field_path="consumption", message=str(e),
                    raw_excerpt={"consumption": payload["consumption"]},
                ))
                continue

            raw_unit = payload["consumption_unit"]
            try:
                value = convert(qty, raw_unit, "kWh")
            except UnitNotSupported as e:
                result.errors.append(ParseErrorShape(
                    line_number=idx, error_code=ParseErrorCode.UNKNOWN_UNIT,
                    field_path="consumption_unit", message=str(e),
                    raw_excerpt={"consumption_unit": raw_unit},
                ))
                continue

            result.drafts.append(ActivityDraft(
                line_number=idx,
                category_code="purchased_electricity",
                activity_date=period_end,
                period_start=period_start,
                period_end=period_end,
                value=value,
                canonical_unit_code="kWh",
                facility_code=payload["meter_id"],
                notes=f"rate_class={payload.get('rate_class', '')}, "
                      f"address={payload.get('service_address', '')}",
            ))

        return result
