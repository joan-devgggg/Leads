"""
Generador de PDF, generalizado desde scrape_clinicas_dubai.py.
Misma estructura: portada+guía → listado → hoja de seguimiento.
"""
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

# Paleta idéntica al original
GOLD  = colors.HexColor("#C8A96E")
DARK  = colors.HexColor("#1A1A2E")
MID   = colors.HexColor("#2D2D4E")
LIGHT = colors.HexColor("#F5F0E8")
ROW_A = colors.HexColor("#EAE6F0")

_styles = getSampleStyleSheet()

_title  = ParagraphStyle("title",  parent=_styles["Title"],   fontSize=22, textColor=DARK,  spaceAfter=4,  leading=26)
_sub    = ParagraphStyle("sub",    parent=_styles["Normal"],  fontSize=10, textColor=colors.HexColor("#666666"), spaceAfter=2)
_h2     = ParagraphStyle("h2",     parent=_styles["Heading2"],fontSize=13, textColor=DARK,  spaceBefore=10, spaceAfter=4)
_body   = ParagraphStyle("body",   parent=_styles["Normal"],  fontSize=8.5,leading=12, textColor=colors.HexColor("#333333"))
_tip    = ParagraphStyle("tip",    parent=_styles["Normal"],  fontSize=8,  leading=11, textColor=colors.HexColor("#444444"), leftIndent=10)


def generate_pdf(
    businesses: list[dict],
    business_type: str,
    zone: str,
    cold_call_guide: list[list[str]],
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
    story.append(Paragraph("Directorio de Llamadas en Frío", _title))
    story.append(Paragraph(f"{business_type.title()} · {zone}", _sub))
    story.append(Paragraph(
        f"Generado el {datetime.now().strftime('%d/%m/%Y')} · {len(businesses)} negocios",
        _sub,
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=14))

    # ── Guía de cold call (generada por LLM, adaptada al tipo/zona) ──────────
    story.append(Paragraph("Guía rápida de llamada en frío", _h2))

    tip_data = [
        [Paragraph(f"<b>{k}</b>", _tip), Paragraph(v, _tip)]
        for k, v in cold_call_guide
    ]
    tip_table = Table(tip_data, colWidths=[2.8*cm, 13.7*cm])
    tip_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), LIGHT),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [LIGHT, colors.white]),
        ("GRID",         (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    story.append(tip_table)
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CCCCCC"), spaceAfter=10))

    # ── Listado de negocios ──────────────────────────────────────────────────
    story.append(Paragraph(f"Listado de {len(businesses)} negocios", _h2))

    COLS = [0.5*cm, 5.5*cm, 3.5*cm, 2.3*cm, 4.7*cm]
    header = [
        Paragraph("<b>#</b>",             _body),
        Paragraph("<b>Negocio</b>",        _body),
        Paragraph("<b>Teléfono</b>",       _body),
        Paragraph("<b>Rating</b>",         _body),
        Paragraph("<b>Web / Dirección</b>",_body),
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
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)

    # ── Hoja de seguimiento ──────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Hoja de Seguimiento", _h2))
    story.append(Paragraph("Imprime esta página para llevar el control de cada llamada.", _sub))
    story.append(Spacer(1, 0.3*cm))

    track_header = [
        Paragraph("<b>#</b>",    _body),
        Paragraph("<b>Negocio</b>", _body),
        Paragraph("<b>Teléfono</b>", _body),
        Paragraph("<b>Estado</b><br/><font size='6'>✓ / ✗ / CB / INT</font>", _body),
        Paragraph("<b>Notas / Próximo paso</b>", _body),
        Paragraph("<b>Fecha callback</b>", _body),
    ]
    track_rows = [track_header]
    for i, b in enumerate(businesses, 1):
        track_rows.append([
            Paragraph(str(i), _body),
            Paragraph(b["name"][:28], _body),
            Paragraph(b.get("phone") or "—", _body),
            Paragraph("", _body),
            Paragraph("", _body),
            Paragraph("", _body),
        ])

    track_tbl = Table(
        track_rows,
        colWidths=[0.5*cm, 4.5*cm, 3*cm, 1.8*cm, 5.2*cm, 2.5*cm],
        repeatRows=1,
    )
    track_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  MID),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#F9F9F9")]),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("ROWHEIGHT",     (0, 1), (-1, -1), 18),
    ]))
    story.append(track_tbl)

    doc.build(story)
    return output_path
