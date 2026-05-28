"""
Utility bill PDF parser (text-extractable).

Why we ship a PDF parser:
  Real production clients arrive with two utility realities — portal CSVs AND
  emailed PDF bills. Shipping only CSV is a half-product. Bills with selectable
  text (most modern utility bills, generated from a billing system) work with
  pdfplumber. Scanned PDFs (rare for utility, but real) get routed to the
  manual-entry queue with a clear error code; we do not OCR (see TRADEOFFS).

The parser is intentionally simple-minded: extract every line, then run a few
labeled regexes for the fields we need. Utility bill layouts vary across
providers, so a real production parser would have provider-specific templates.
For the demo we handle the layout produced by `samples/_generate_utility_pdf.py`
— which itself models a realistic bill layout.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime
from decimal import Decimal

import pdfplumber

from ingestion.models import ParseErrorCode

from .base import (
    ActivityDraft,
    ParseErrorShape,
    Parser,
    ParseResult,
    SourceRecordShape,
    register,
)


# Labeled regexes. Order matters — first hit wins per field.
RX = {
    "meter_id":        re.compile(r"Meter\s*(?:ID|No|Number)\s*[:#]\s*([A-Za-z0-9\-]+)", re.I),
    "service_addr":    re.compile(r"Service\s+Address\s*[:]\s*(.+)", re.I),
    "period":          re.compile(
        r"Billing\s+Period\s*[:]\s*"
        r"(\d{4}-\d{2}-\d{2})\s+(?:to|-|–)\s+(\d{4}-\d{2}-\d{2})",
        re.I,
    ),
    "consumption":     re.compile(r"Total\s+Consumption\s*[:]\s*([\d,]+(?:\.\d+)?)\s*(kWh|MWh)", re.I),
}


@register
class UtilityPDFParser(Parser):
    source_type = "utility_pdf"

    def parse(self, data: bytes, *, context: dict | None = None) -> ParseResult:
        result = ParseResult()

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text_chunks = [page.extract_text() or "" for page in pdf.pages]
        full_text = "\n".join(text_chunks)

        # If the PDF has effectively no extractable text, it's a scan.
        # Route to manual entry rather than guess with OCR (TRADEOFFS).
        if len(full_text.strip()) < 50:
            result.errors.append(ParseErrorShape(
                line_number=1, error_code=ParseErrorCode.SCANNED_PDF,
                message="PDF has no extractable text. Needs manual entry.",
            ))
            return result

        # The bill is one source row — we use line_number=1 throughout.
        payload: dict = {"text": full_text}
        for key, rx in RX.items():
            m = rx.search(full_text)
            if m:
                payload[key] = m.group(1).strip() if key != "period" else {
                    "start": m.group(1), "end": m.group(2),
                }

        result.records.append(SourceRecordShape(line_number=1, raw_payload=payload))

        # Required fields
        for f in ("meter_id", "period", "consumption"):
            if f not in payload:
                result.errors.append(ParseErrorShape(
                    line_number=1, error_code=ParseErrorCode.MISSING_FIELD,
                    field_path=f,
                    message=f"Could not locate {f!r} in the PDF text. "
                            f"Re-template the parser for this utility provider.",
                ))
                return result

        # Re-extract consumption with the captured unit (regex already separated them).
        m = RX["consumption"].search(full_text)
        assert m is not None  # we just verified
        qty = Decimal(m.group(1).replace(",", ""))
        unit_label = m.group(2)
        from emissions.converters import convert
        value = convert(qty, unit_label, "kWh")

        try:
            period_start = date.fromisoformat(payload["period"]["start"])
            period_end = date.fromisoformat(payload["period"]["end"])
        except ValueError as e:
            result.errors.append(ParseErrorShape(
                line_number=1, error_code=ParseErrorCode.BAD_DATE,
                field_path="Billing Period", message=str(e),
            ))
            return result

        result.drafts.append(ActivityDraft(
            line_number=1,
            category_code="purchased_electricity",
            activity_date=period_end,
            period_start=period_start,
            period_end=period_end,
            value=value,
            canonical_unit_code="kWh",
            facility_code=payload["meter_id"],
            notes=f"From PDF bill, address={payload.get('service_addr', '')}",
        ))

        return result
