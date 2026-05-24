"""
Generador de PDF para clínicas estéticas con enfoque en automatización e IA.
Estructura: portada + listado de negocios.
"""
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

    COLS = [0.5*cm, 5.5*cm, 3.5*cm, 2.3*cm, 4.7*cm]
    header = [
        Paragraph("#", _th),
        Paragraph("Negocio", _th),
        Paragraph("Teléfono", _th),
        Paragraph("Rating", _th),
        Paragraph("Web / Dirección", _th),
    ]
    rows = [header]

    for i, b in enumerate(businesses, 1):
        rating_str  = f"★ {b['rating']}  ({b['reviews_count']} reviews)" if b.get("rating") else "—"
        web_addr    = b.get("website") or b.get("address") or "—"
        phone_str   = b["phone"] if b.get("phone") else "⚠ Sin teléfono"
        phone_color = "#CC0000" if not b.get("phone") else "#006600"

        rows.append([
            Paragraph(str(i), _body),
            Paragraph(
                f"<b>{b['name']}</b><br/><font size='7' color='#888888'>{b['zone']}</font>",
                _body,
            ),
            Paragraph(f"<font color='{phone_color}'>{phone_str}</font>", _body),
            Paragraph(rating_str, _body),
            Paragraph(web_addr[:55] + ("…" if len(web_addr) > 55 else ""), _body),
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
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]))
    story.append(tbl)

    doc.build(story)
    return output_path
