"""
Generate a text-extractable utility-bill PDF used by the smoke test.

Run once:
    python samples/_generate_utility_pdf.py

This produces samples/utility_bill_acme_facility_03_2026.pdf. We check the
generator into the repo (not the PDF) because PDFs are binary and noisy to
diff. CI / reviewers can regenerate the file deterministically.

The layout deliberately mirrors what a real commercial-rate utility bill
looks like (header block, billing period, meter detail, charges) so the
pdfplumber-based parser in ingestion/parsers/utility_pdf.py has realistic
text to work against.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


OUT = Path(__file__).resolve().parent / "utility_bill_acme_facility_03_2026.pdf"


def build() -> None:
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Heading1"], fontSize=16, leading=20, spaceAfter=8)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=10, textColor=colors.grey)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14)
    kv = ParagraphStyle("kv", parent=styles["Normal"], fontSize=10, leading=14, leftIndent=0)

    doc = SimpleDocTemplate(str(OUT), pagesize=LETTER, leftMargin=0.6 * inch,
                            rightMargin=0.6 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch)

    story = [
        Paragraph("ConEd Commercial Services", h),
        Paragraph("Statement of Account | Customer copy", sub),
        Spacer(1, 16),

        Paragraph("Account No: 8430-2210-997", body),
        Paragraph("Bill Date: 2026-04-05", body),
        Paragraph("Due Date: 2026-04-25", body),
        Spacer(1, 12),

        Paragraph("Service Address: 500 Peachtree Atlanta GA 30308", body),
        Paragraph("Meter ID: M-AC-ATL-002", body),
        Paragraph("Rate Class: LP-3 (Large Commercial Time-of-Use)", body),
        Paragraph("Billing Period: 2026-03-15 to 2026-04-14", body),
        Spacer(1, 18),

        Paragraph("Usage Summary", h),
        Table([
            ["Total Consumption:", "92,100 kWh"],
            ["Peak (12pm – 8pm weekdays):", "56,200 kWh"],
            ["Off-Peak (all other hours):", "35,900 kWh"],
            ["Peak Demand:", "182.4 kW"],
        ], colWidths=[3.2 * inch, 2.0 * inch], style=TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ])),
        Spacer(1, 14),

        Paragraph("Charges", h),
        Table([
            ["Energy charge (peak)",       "$5,402.40"],
            ["Energy charge (off-peak)",   "$2,512.30"],
            ["Demand charge",              "$1,289.00"],
            ["Customer / service charges", "$  244.05"],
            ["Taxes & surcharges",         "$  251.00"],
            ["Total amount due",           "$9,698.75"],
        ], colWidths=[3.2 * inch, 2.0 * inch], style=TableStyle([
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.lightgrey),
            ("LINEABOVE", (0, -1), (-1, -1), 0.7, colors.black),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ])),
        Spacer(1, 20),
        Paragraph("Questions about this statement? commercial-support@coned-demo.example",
                  sub),
    ]
    doc.build(story)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
