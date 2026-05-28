"""
Parser ABC + shared shapes.

Design notes:
  * Parsers are PURE: bytes in, dataclasses out. No DB access. This makes them
    trivial to unit-test (golden-file style) and lets us re-run them offline
    against historical raw payloads when we fix bugs.
  * Errors are STRUCTURED. `ParseErrorShape` always has `error_code` from the
    same enum used in `ParseError` — the UI groups by it and shows a fix
    affordance per code.
  * Drafts (proto-ActivityRecord) reference the line number that produced
    them, so the orchestrating task can link FKs after inserts.

Version bumping: PARSER_VERSION is a project-wide semver string. The orchestrator
stamps `IngestionBatch.parser_version` with this value. When parser logic
changes meaningfully (different field mapping, new conversion path), bump it.
That gives us a clean way to identify which parser produced which row when
we re-parse historical batches.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable


PARSER_VERSION = "0.1.0"


# ----- shared shapes -------------------------------------------------------


@dataclass
class SourceRecordShape:
    line_number: int
    raw_payload: dict


@dataclass
class ActivityDraft:
    """
    A pre-DB ActivityRecord. References its source by line_number, which the
    orchestrator resolves into a SourceRecord FK after insert.
    """

    line_number: int
    category_code: str
    activity_date: date
    value: Decimal
    canonical_unit_code: str
    facility_code: str = ""
    period_start: date | None = None
    period_end: date | None = None
    notes: str = ""


@dataclass
class ParseErrorShape:
    line_number: int
    error_code: str
    message: str
    field_path: str = ""
    raw_excerpt: dict | None = None


@dataclass
class ParseResult:
    records: list[SourceRecordShape] = field(default_factory=list)
    drafts: list[ActivityDraft] = field(default_factory=list)
    errors: list[ParseErrorShape] = field(default_factory=list)


# ----- parser ABC ----------------------------------------------------------


class Parser(ABC):
    source_type: str           # one of ingestion.models.SourceType.values
    parser_version: str = PARSER_VERSION

    @abstractmethod
    def parse(self, data: bytes, *, context: dict | None = None) -> ParseResult:
        """
        Parse raw input bytes into a ParseResult.

        `context` carries per-org reference data that the parser may need
        (e.g. PlantCode mapping for SAP). The orchestrator builds it from
        the org's current state before calling parse().
        """


# ----- registry ------------------------------------------------------------


_REGISTRY: dict[str, type[Parser]] = {}


def register(parser_cls: type[Parser]) -> type[Parser]:
    _REGISTRY[parser_cls.source_type] = parser_cls
    return parser_cls


def get_parser(source_type: str, *, file_name: str = "") -> Parser:
    """
    Resolve the parser for a source_type. The utility source has two file
    formats (CSV and PDF); we disambiguate by file extension.
    """
    if source_type == "utility":
        if file_name.lower().endswith(".pdf"):
            from . import utility_pdf  # noqa: F401  – register on import
            return _REGISTRY["utility_pdf"]()
        from . import utility_csv     # noqa: F401
        return _REGISTRY["utility_csv"]()
    if source_type not in _REGISTRY:
        # Trigger registration via import.
        if source_type == "sap":
            from . import sap  # noqa: F401
        elif source_type == "travel":
            from . import travel  # noqa: F401
    return _REGISTRY[source_type]()


# ----- shared utilities used by multiple parsers ---------------------------


def parse_german_decimal(text: str) -> Decimal:
    """
    Convert a German-formatted decimal ("1.234,56") to Decimal.

    Rules:
      * dots are thousand separators → strip
      * comma is the decimal mark    → replace with dot
      * leading/trailing whitespace stripped
    Raises ValueError on garbage.
    """
    if text is None:
        raise ValueError("empty value")
    cleaned = text.strip().replace(".", "").replace(",", ".")
    if not cleaned:
        raise ValueError("empty value")
    return Decimal(cleaned)


def parse_german_date(text: str) -> date:
    """DD.MM.YYYY → date. SAP date format from SE16N exports."""
    parts = text.strip().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"not a DD.MM.YYYY date: {text!r}")
    d, m, y = (int(p) for p in parts)
    return date(y, m, d)
