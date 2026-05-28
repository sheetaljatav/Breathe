"""
Per-source parsers.

Each parser exposes one entry point:
    parse(bytes) -> ParseResult

ParseResult holds three lists:
    records   — raw payloads to be inserted as SourceRecord rows
    drafts    — ActivityRecord drafts (one per record-that-parsed-clean)
    errors    — ParseError shapes for rows that couldn't be normalized

The Celery task `ingestion.tasks.parse_batch` orchestrates: it instantiates
the right parser, calls parse(), and writes everything in a single
transaction so a partial-failure leaves the batch in a consistent state.
"""

from .base import (
    PARSER_VERSION,
    ActivityDraft,
    ParseErrorShape,
    Parser,
    ParseResult,
    SourceRecordShape,
    get_parser,
)

__all__ = (
    "PARSER_VERSION",
    "ActivityDraft",
    "ParseErrorShape",
    "Parser",
    "ParseResult",
    "SourceRecordShape",
    "get_parser",
)
