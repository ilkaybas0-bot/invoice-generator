"""PDF rendering for invoices/proposals using ReportLab."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image as RLImage,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_LEFT

from utils.i18n import t, DOC_TYPE_KEYS

DEFAULT_ACCENT = "#2563EB"
DARK = colors.HexColor("#1E293B")
GRAY = colors.HexColor("#64748B")
LIGHT_BG = colors.HexColor("#F1F5F9")

# --- Unicode font registration -------------------------------------------
# The built-in PDF base fonts (Helvetica etc.) only support WinAnsi encoding,
# which is missing Turkish letters (ı, İ, ş, ğ) and the ₺ sign. We register a
# system TrueType font that covers them, with a base-font fallback so the app
# still runs (in degraded form) on machines without any of these fonts.
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"

_CANDIDATES = [
    # (regular, bold, italic)
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\ariali.ttf"),
    (r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\calibrib.ttf", r"C:\Windows\Fonts\calibrii.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
     "/System/Library/Fonts/Supplemental/Arial Italic.ttf"),
]

for _regular, _bold, _italic in _CANDIDATES:
    if os.path.exists(_regular):
        try:
            pdfmetrics.registerFont(TTFont("AppSans", _regular))
            FONT_REGULAR = "AppSans"
            if os.path.exists(_bold):
                pdfmetrics.registerFont(TTFont("AppSans-Bold", _bold))
                FONT_BOLD = "AppSans-Bold"
            if os.path.exists(_italic):
                pdfmetrics.registerFont(TTFont("AppSans-Italic", _italic))
                FONT_ITALIC = "AppSans-Italic"
            break
        except Exception:
            continue

THEMES = {
    "blue": "#2563EB",
    "green": "#16A34A",
    "purple": "#7C3AED",
    "navy": "#1E3A8A",
    "slate": "#334155",
}


def format_money(amount: float, currency: str, lang: str) -> str:
    """Format an amount with locale-appropriate thousands/decimal separators."""
    if lang == "tr":
        text = f"{amount:,.2f}".replace(",", "").replace(".", ",").replace("", ".")
    else:
        text = f"{amount:,.2f}"
    return f"{currency}{text}"


@dataclass
class PartyDetails:
    name: str = ""
    email: str = ""
    address: str = ""
    tax_number: str = ""
    logo_bytes: bytes | None = None
    signature_bytes: bytes | None = None


@dataclass
class ClientDetails:
    name: str = ""
    company: str = ""
    email: str = ""
    address: str = ""


@dataclass
class LineItem:
    description: str
    quantity: float
    unit_price: float

    @property
    def total(self) -> float:
        return self.quantity * self.unit_price


@dataclass
class DocumentData:
    doc_type: str  # "Invoice" or "Proposal"
    doc_number: str
    issue_date: str
    due_date: str
    sender: PartyDetails
    client: ClientDetails
    items: list[LineItem] = field(default_factory=list)
    tax_percent: float = 0.0
    discount_amount: float = 0.0
    currency: str = "$"
    notes: str = ""
    language: str = "en"
    tax_inclusive: bool = False
    accent_color: str = DEFAULT_ACCENT
    advance_paid: float = 0.0

    @property
    def _items_total(self) -> float:
        """Sum of quantity * unit_price, as entered (may already include tax)."""
        return sum(item.total for item in self.items)

    @property
    def subtotal(self) -> float:
        """Pre-tax subtotal. When prices are tax-inclusive, tax is backed out."""
        if self.tax_inclusive and self.tax_percent:
            return self._items_total / (1 + self.tax_percent / 100)
        return self._items_total

    @property
    def tax_amount(self) -> float:
        if self.tax_inclusive:
            return self._items_total - self.subtotal
        return self.subtotal * (self.tax_percent / 100)

    @property
    def grand_total(self) -> float:
        if self.tax_inclusive:
            return self._items_total - self.discount_amount
        return self.subtotal + self.tax_amount - self.discount_amount

    @property
    def balance_due(self) -> float:
        return self.grand_total - self.advance_paid


def _styles(accent: colors.Color):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="DocTitle", fontName=FONT_BOLD, fontSize=22,
        textColor=accent, alignment=TA_RIGHT, leading=26, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SmallGray", fontName=FONT_REGULAR, fontSize=9,
        textColor=GRAY, alignment=TA_RIGHT, leading=13,
    ))
    styles.add(ParagraphStyle(
        name="SectionLabel", fontName=FONT_BOLD, fontSize=9,
        textColor=accent, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Body", fontName=FONT_REGULAR, fontSize=10,
        textColor=DARK, leading=14,
    ))
    styles.add(ParagraphStyle(
        name="CompanyName", fontName=FONT_BOLD, fontSize=14,
        textColor=DARK, leading=17,
    ))
    styles.add(ParagraphStyle(
        name="NotesBody", fontName=FONT_REGULAR, fontSize=9,
        textColor=GRAY, leading=13,
    ))
    return styles


def build_pdf(data: DocumentData) -> bytes:
    """Render DocumentData into a formatted PDF and return the raw bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"{data.doc_type} {data.doc_number}",
    )
    accent = colors.HexColor(data.accent_color or DEFAULT_ACCENT)
    styles = _styles(accent)
    story = []
    lang = data.language

    # --- Header: logo/company on left, doc title + meta on right ---
    left_cell = []
    if data.sender.logo_bytes:
        try:
            img = RLImage(io.BytesIO(data.sender.logo_bytes))
            img._restrictSize(40 * mm, 20 * mm)
            left_cell.append(img)
            left_cell.append(Spacer(1, 4))
        except Exception:
            pass
    left_cell.append(Paragraph(data.sender.name or t(lang, "your_company"), styles["CompanyName"]))
    if data.sender.address:
        left_cell.append(Paragraph(data.sender.address.replace("\n", "<br/>"), styles["Body"]))
    if data.sender.email:
        left_cell.append(Paragraph(data.sender.email, styles["Body"]))
    if data.sender.tax_number:
        left_cell.append(Paragraph(f"{t(lang, 'sender_tax').split(' (')[0]}: {data.sender.tax_number}", styles["Body"]))

    doc_type_label = t(lang, DOC_TYPE_KEYS.get(data.doc_type, "invoice")).upper()
    right_cell = [
        Paragraph(doc_type_label, styles["DocTitle"]),
        Paragraph(f"<b>{t(lang, 'no_label')}:</b> {data.doc_number}", styles["SmallGray"]),
        Paragraph(f"<b>{t(lang, 'issue_date_label')}:</b> {data.issue_date}", styles["SmallGray"]),
        Paragraph(f"<b>{t(lang, 'due_date_label')}:</b> {data.due_date}", styles["SmallGray"]),
    ]

    header_table = Table(
        [[left_cell, right_cell]],
        colWidths=[100 * mm, 72 * mm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.2, color=accent))
    story.append(Spacer(1, 14))

    # --- Bill To section ---
    client_lines = [Paragraph(t(lang, "bill_to"), styles["SectionLabel"])]
    name_line = data.client.name or t(lang, "client_name_default")
    if data.client.company:
        name_line += f" — {data.client.company}"
    client_lines.append(Paragraph(f"<b>{name_line}</b>", styles["Body"]))
    if data.client.address:
        client_lines.append(Paragraph(data.client.address.replace("\n", "<br/>"), styles["Body"]))
    if data.client.email:
        client_lines.append(Paragraph(data.client.email, styles["Body"]))

    story.append(Table([[client_lines]], colWidths=[172 * mm]))
    story.append(Spacer(1, 16))

    # --- Items table ---
    header_row = [
        t(lang, "col_description"),
        t(lang, "col_quantity"),
        t(lang, "col_unit_price"),
        t(lang, "col_total"),
    ]
    rows = [header_row]
    for item in data.items:
        rows.append([
            Paragraph(item.description or "-", styles["Body"]),
            f"{item.quantity:g}",
            format_money(item.unit_price, data.currency, lang),
            format_money(item.total, data.currency, lang),
        ])

    items_table = Table(rows, colWidths=[86 * mm, 22 * mm, 32 * mm, 32 * mm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), accent),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 9.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 1), (-1, -1), 9.5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 12))

    # --- Totals summary ---
    totals_rows = [[t(lang, "subtotal"), format_money(data.subtotal, data.currency, lang)]]
    if data.tax_percent:
        tax_key = "tax_label_incl" if data.tax_inclusive else "tax_label"
        totals_rows.append([t(lang, tax_key, pct=data.tax_percent), format_money(data.tax_amount, data.currency, lang)])
    if data.discount_amount:
        totals_rows.append([t(lang, "discount_label"), f"-{format_money(data.discount_amount, data.currency, lang)}"])
    totals_rows.append([t(lang, "grand_total"), format_money(data.grand_total, data.currency, lang)])
    grand_total_row_idx = len(totals_rows) - 1

    if data.advance_paid:
        totals_rows.append([t(lang, "paid_label"), f"-{format_money(data.advance_paid, data.currency, lang)}"])
        totals_rows.append([t(lang, "balance_due_label"), format_money(data.balance_due, data.currency, lang)])

    totals_table = Table(totals_rows, colWidths=[40 * mm, 40 * mm])
    final_row_idx = len(totals_rows) - 1
    style_cmds = [
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTNAME", (0, grand_total_row_idx), (-1, grand_total_row_idx), FONT_BOLD),
        ("FONTSIZE", (0, grand_total_row_idx), (-1, grand_total_row_idx), 12),
        ("LINEABOVE", (0, grand_total_row_idx), (-1, grand_total_row_idx), 1, accent),
        ("FONTNAME", (0, final_row_idx), (-1, final_row_idx), FONT_BOLD),
        ("FONTSIZE", (0, final_row_idx), (-1, final_row_idx), 12),
        ("TEXTCOLOR", (0, final_row_idx), (-1, final_row_idx), accent),
    ]
    if final_row_idx != grand_total_row_idx:
        style_cmds.append(("LINEABOVE", (0, final_row_idx), (-1, final_row_idx), 0.5, colors.HexColor("#CBD5E1")))
    totals_table.setStyle(TableStyle(style_cmds))

    wrapper = Table([[Spacer(1, 1), totals_table]], colWidths=[92 * mm, 80 * mm])
    wrapper.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(wrapper)
    story.append(Spacer(1, 24))

    # --- Notes / payment terms ---
    if data.notes:
        story.append(Paragraph(t(lang, "notes_section"), styles["SectionLabel"]))
        story.append(Paragraph(data.notes.replace("\n", "<br/>"), styles["NotesBody"]))
        story.append(Spacer(1, 12))

    # --- Signature / stamp ---
    if data.sender.signature_bytes:
        try:
            sig_img = RLImage(io.BytesIO(data.sender.signature_bytes))
            sig_img._restrictSize(45 * mm, 25 * mm)
            sig_table = Table([[sig_img]], colWidths=[172 * mm])
            sig_table.setStyle(TableStyle([("ALIGN", (0, 0), (0, 0), "RIGHT")]))
            story.append(sig_table)
            story.append(Spacer(1, 4))
        except Exception:
            pass

    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#E2E8F0")))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        t(lang, "thank_you", sender=data.sender.name or t(lang, "your_company")),
        ParagraphStyle(name="Footer", fontName=FONT_ITALIC, fontSize=8.5, textColor=GRAY),
    ))

    doc.build(story)
    return buffer.getvalue()
