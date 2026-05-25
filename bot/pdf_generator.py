"""
Generador de PDF para clínicas estéticas con enfoque en automatización e IA.
Estructura: portada + listado de negocios.
"""
import re
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

# Paleta idéntica al original
GOLD  = colors.HexColor("#C8A96E")
DARK  = colors.HexColor("#1A1A2E")
MID   = colors.HexColor("#243B6B")
LIGHT = colors.HexColor("#F5F0E8")
ROW_A = colors.HexColor("#F7F9FC")
GRID  = colors.HexColor("#D7DDE8")

_styles = getSampleStyleSheet()

_title  = ParagraphStyle("title",  parent=_styles["Title"],   fontSize=22, textColor=DARK,  spaceAfter=4,  leading=26)
_sub    = ParagraphStyle("sub",    parent=_styles["Normal"],  fontSize=10, textColor=colors.HexColor("#666666"), spaceAfter=2)
_h2     = ParagraphStyle("h2",     parent=_styles["Heading2"],fontSize=13, textColor=DARK,  spaceBefore=10, spaceAfter=4)
_body   = ParagraphStyle("body",   parent=_styles["Normal"],  fontSize=8.5,leading=12, textColor=colors.HexColor("#333333"))
_tip    = ParagraphStyle("tip",    parent=_styles["Normal"],  fontSize=8,  leading=11, textColor=colors.HexColor("#444444"), leftIndent=10)
_th     = ParagraphStyle(
    "table_header",
    parent=_styles["Normal"],
    fontSize=8.5,
    leading=10,
    textColor=colors.white,
    alignment=1,
    fontName="Helvetica-Bold",
)

_DAY_MAP = {
    "monday": "Lu", "tuesday": "Ma", "wednesday": "Mi",
    "thursday": "Ju", "friday": "Vi", "saturday": "Sá", "sunday": "Do",
}

def _ampm_to_24h(s: str) -> str:
    """Convert '9:00 AM – 8:00 PM' → '9:00-20:00'."""
    def _convert(m: re.Match) -> str:
        h, mins, period = int(m.group(1)), m.group(2), m.group(3).upper()
        if period == "PM" and h != 12:
            h += 12
        elif period == "AM" and h == 12:
            h = 0
        return f"{h}:{mins}"
    return re.sub(r"(\d{1,2}):(\d{2})\s*(AM|PM)", _convert, s).replace(" – ", "-").replace(" — ", "-")


def _format_opening_hours(opening_hours: list) -> str:
    if not opening_hours:
        return "—"
    lines = []
    for entry in opening_hours:
        day = _DAY_MAP.get((entry.get("day") or "").lower(), (entry.get("day") or "")[:2])
        hours = _ampm_to_24h(entry.get("hours") or "Cerrado")
        lines.append(f"<b>{day}</b>: {hours}")
    return "<br/>".join(lines)


def generate_pdf(
    businesses: list[dict],
    business_type: str,
    zone: str,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=2*cm,    bottomMargin=2*cm,
    )

    story = []

    # ── Portada ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("Directorio Comercial de Automatización e IA", _title))
    story.append(Paragraph(f"{business_type.title()} · {zone}", _sub))
    story.append(Paragraph(
        f"Generado el {datetime.now().strftime('%d/%m/%Y')} · {len(businesses)} negocios",
        _sub,
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=14))

    # ── Listado de negocios ──────────────────────────────────────────────────
    story.append(Paragraph(f"Listado de {len(businesses)} negocios", _h2))

    COLS = [0.5*cm, 4.5*cm, 3.0*cm, 1.8*cm, 3.5*cm, 4.7*cm]
    header = [
        Paragraph("#", _th),
        Paragraph("Negocio", _th),
        Paragraph("Teléfono", _th),
        Paragraph("Rating", _th),
        Paragraph("Web / Dirección", _th),
        Paragraph("Horario", _th),
    ]
    rows = [header]

    for i, b in enumerate(businesses, 1):
        rating_str  = f"★ {b['rating']}  ({b['reviews_count']} rev.)" if b.get("rating") else "—"
        web_addr    = b.get("website") or b.get("address") or "—"
        phone_str   = b["phone"] if b.get("phone") else "⚠ Sin teléfono"
        phone_color = "#CC0000" if not b.get("phone") else "#006600"
        hours_str   = _format_opening_hours(b.get("opening_hours") or [])

        rows.append([
            Paragraph(str(i), _body),
            Paragraph(
                f"<b>{b['name']}</b><br/><font size='7' color='#888888'>{b['zone']}</font>",
                _body,
            ),
            Paragraph(f"<font color='{phone_color}'>{phone_str}</font>", _body),
            Paragraph(rating_str, _body),
            Paragraph(web_addr[:40] + ("…" if len(web_addr) > 40 else ""), _body),
            Paragraph(hours_str, _body),
        ])

    tbl = Table(rows, colWidths=COLS, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  MID),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [ROW_A, colors.white]),
        ("GRID",          (0, 0), (-1, -1), 0.35, GRID),
        ("LINEBELOW",     (0, 0), (-1, 0), 1.2, GOLD),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ALIGN",         (0, 0), (0, -1),  "CENTER"),
        ("ALIGN",         (2, 1), (3, -1),  "CENTER"),
        ("FONTSIZE",      (5, 1), (5, -1),  7),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]))
    story.append(tbl)

    doc.build(story)
    return output_path
