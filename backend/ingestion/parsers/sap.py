"""
SAP SE16N flat-file CSV parser.

Why SE16N CSV (and not IDoc / BAPI / OData):
  In production, ESG analysts get SE16N table extracts forwarded by the SAP BASIS
  team. IDocs require an EDI listener and per-customer message-type config;
  BAPI/OData need named SAP users with role authorization. SE16N CSV is the
  realistic shape an analyst-facing tool sees in v1. See SOURCES.md for the
  research and citations.

Real-world quirks we handle:
  * UTF-8 BOM on the first line
  * Semicolon delimiter (German config)
  * German decimal commas: "1.234,56" not "1,234.56"
  * Dates: DD.MM.YYYY
  * Column headers in German: Werk, Buchungsdatum, Material, Menge, BasisME,
    Nettowert, Waehrung
  * Material codes prefixed by category: DIESEL_*, PETROL_* → fuel;
    OFFICE_*, IT_*, SVC_* → procurement (Scope 3 spend)
  * Plant codes (Werk) require lookup; unmapped → flagged, not dropped
  * "TO" appears for metric tonne (1000 kg)

Real-world quirks we DO NOT handle (deliberately):
  * IDoc XML
  * Multi-currency normalization (we leave currency as a passthrough)
  * Tax (Steuer) lines
  * Material master enrichment from MARA
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
    parse_german_date,
    parse_german_decimal,
    register,
)


# Category resolution from material code prefix.
# Real systems use a material master mapping table; for the prototype this
# captures the realistic shape and is documented.
FUEL_PREFIXES = {
    "DIESEL_": ("mobile_fuel_diesel", "L"),
    "PETROL_": ("stationary_fuel_petrol", "L"),
    "HEATING_OIL_": ("stationary_fuel_diesel", "L"),
}
PROCUREMENT_PREFIXES = ("OFFICE_", "IT_", "SVC_", "PAPER_")


@register
class SAPParser(Parser):
    source_type = "sap"

    def parse(self, data: bytes, *, context: dict | None = None) -> ParseResult:
        result = ParseResult()
        plant_codes: set[str] = set((context or {}).get("plant_codes") or [])

        # Strip BOM, decode UTF-8.
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text), delimiter=";")

        # Header validation up-front: better error than per-row "KeyError: 'Werk'"
        required = {"Werk", "Buchungsdatum", "Material", "Menge", "BasisME", "Nettowert", "Waehrung"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            result.errors.append(ParseErrorShape(
                line_number=1,
                error_code=ParseErrorCode.MISSING_FIELD,
                field_path=",".join(sorted(missing)),
                message=f"SE16N export missing required columns: {sorted(missing)}",
                raw_excerpt={"header": reader.fieldnames},
            ))
            return result

        for idx, row in enumerate(reader, start=2):  # line 1 was header
            # Always capture the row as a SourceRecord, regardless of parse outcome.
            payload = {k: (v or "").strip() for k, v in row.items()}
            result.records.append(SourceRecordShape(line_number=idx, raw_payload=payload))

            werk = payload["Werk"]
            material = payload["Material"]

            # Plant lookup — unmapped is flagged but the row still gets a SourceRecord.
            if werk and plant_codes and werk not in plant_codes:
                result.errors.append(ParseErrorShape(
                    line_number=idx,
                    error_code=ParseErrorCode.UNMAPPED_PLANT,
                    field_path="Werk",
                    message=f"Plant code {werk!r} is not in the lookup table for this org.",
                    raw_excerpt={"Werk": werk},
                ))
                # Don't continue — we still produce a draft, the analyst can
                # set facility_code manually.

            # Resolve category + canonical unit from material prefix.
            cat_unit = self._resolve_category(material)
            if cat_unit is None:
                result.errors.append(ParseErrorShape(
                    line_number=idx,
                    error_code=ParseErrorCode.UNKNOWN_CATEGORY,
                    field_path="Material",
                    message=f"Could not resolve emission category from material {material!r}.",
                    raw_excerpt={"Material": material},
                ))
                continue
            category_code, canonical_unit = cat_unit

            # Date
            try:
                activity_date = parse_german_date(payload["Buchungsdatum"])
            except ValueError as e:
                result.errors.append(ParseErrorShape(
                    line_number=idx, error_code=ParseErrorCode.BAD_DATE,
                    field_path="Buchungsdatum", message=str(e),
                    raw_excerpt={"Buchungsdatum": payload["Buchungsdatum"]},
                ))
                continue

            # Quantity + unit
            try:
                qty = parse_german_decimal(payload["Menge"])
            except ValueError as e:
                result.errors.append(ParseErrorShape(
                    line_number=idx, error_code=ParseErrorCode.BAD_NUMBER,
                    field_path="Menge", message=str(e),
                    raw_excerpt={"Menge": payload["Menge"]},
                ))
                continue

            raw_unit = payload["BasisME"]
            if category_code == "purchased_goods_spend":
                # Procurement: use net value in currency, ignore physical UoM.
                try:
                    spend = parse_german_decimal(payload["Nettowert"])
                except ValueError as e:
                    result.errors.append(ParseErrorShape(
                        line_number=idx, error_code=ParseErrorCode.BAD_NUMBER,
                        field_path="Nettowert", message=str(e),
                    ))
                    continue
                result.drafts.append(ActivityDraft(
                    line_number=idx,
                    category_code=category_code,
                    activity_date=activity_date,
                    value=spend,
                    canonical_unit_code="usd",  # demo: treat currency as USD
                    facility_code=werk,
                    notes=f"material={material} ({payload['Waehrung']} {spend})",
                ))
                continue

            try:
                value = convert(qty, raw_unit, canonical_unit)
            except UnitNotSupported as e:
                result.errors.append(ParseErrorShape(
                    line_number=idx, error_code=ParseErrorCode.UNKNOWN_UNIT,
                    field_path="BasisME", message=str(e),
                    raw_excerpt={"BasisME": raw_unit, "Menge": payload["Menge"]},
                ))
                continue

            result.drafts.append(ActivityDraft(
                line_number=idx,
                category_code=category_code,
                activity_date=activity_date,
                value=value,
                canonical_unit_code=canonical_unit,
                facility_code=werk,
                notes=f"material={material}",
            ))

        return result

    @staticmethod
    def _resolve_category(material: str) -> tuple[str, str] | None:
        for prefix, mapping in FUEL_PREFIXES.items():
            if material.startswith(prefix):
                return mapping
        if any(material.startswith(p) for p in PROCUREMENT_PREFIXES):
            return ("purchased_goods_spend", "usd")
        return None
