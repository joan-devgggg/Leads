"""
Busca 50 clínicas estéticas en Dubai con Apify (Google Maps Scraper)
y genera un PDF listo para llamadas en frío.
"""
import os
import time
import json
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# ── Config ──────────────────────────────────────────────────────────────────
_env_path = Path(__file__).parent / "bot" / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")
if not APIFY_TOKEN:
    raise RuntimeError("APIFY_API_TOKEN no configurado en bot/.env")
ACTOR_ID    = "compass~crawler-google-places"   # Google Maps Scraper oficial de Apify
BASE_URL    = "https://api.apify.com/v2"
HEADERS     = {"Authorization": f"Bearer {APIFY_TOKEN}"}
OUTPUT_DIR  = Path(__file__).parent
PDF_PATH    = OUTPUT_DIR / f"clinicas_esteticas_dubai_{datetime.now().strftime('%Y%m%d')}.pdf"
JSON_PATH   = OUTPUT_DIR / "clinicas_raw.json"

RUN_INPUT = {
    "searchStringsArray": [
        "aesthetic clinic Dubai",
        "beauty clinic Dubai",
        "skin clinic Dubai",
        "cosmetic clinic Dubai",
    ],
    "maxCrawledPlacesPerSearch": 15,   # 4 búsquedas × 15 = ~60 resultados
    "language": "en",
    "maxImages": 0,
    "maxReviews": 0,
    "exportPlaceUrls": False,
    "additionalInfo": False,
    "includeWebResults": False,
}


# ── Apify runner ─────────────────────────────────────────────────────────────
def run_actor_and_wait(actor_id: str, run_input: dict, timeout: int = 480) -> list[dict]:
    print("▶  Lanzando actor Apify Google Maps Scraper…")
    r = requests.post(
        f"{BASE_URL}/acts/{actor_id}/runs",
        headers=HEADERS,
        json=run_input,
        params={"timeout": timeout},
    )
    r.raise_for_status()
    run_id = r.json()["data"]["id"]
    print(f"   Run ID: {run_id}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        s = requests.get(f"{BASE_URL}/actor-runs/{run_id}", headers=HEADERS).json()["data"]
        status = s["status"]
        print(f"   Estado: {status}", end="\r")
        if status == "SUCCEEDED":
            print()
            dataset_id = s["defaultDatasetId"]
            print(f"   Dataset: {dataset_id}")
            items = requests.get(
                f"{BASE_URL}/datasets/{dataset_id}/items",
                headers=HEADERS,
                params={"limit": 200, "clean": "true", "format": "json"},
            ).json()
            return items
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Actor terminó con estado: {status}")
        time.sleep(8)
    raise TimeoutError("El actor no terminó a tiempo.")


# ── Limpieza y deduplicación ─────────────────────────────────────────────────
def clean_phone(raw: str) -> str:
    if not raw:
        return ""
    cleaned = raw.strip()
    # normalizar a formato internacional Dubai (+971 o 04/05)
    if cleaned.startswith("0") and not cleaned.startswith("00"):
        cleaned = "+971 " + cleaned[1:]
    return cleaned


def parse_clinics(raw: list[dict]) -> list[dict]:
    seen = set()
    clinics = []
    for p in raw:
        phone = clean_phone(p.get("phone") or "")
        name  = (p.get("title") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)

        clinics.append({
            "nombre":      name,
            "telefono":    phone,
            "direccion":   (p.get("address") or "").strip(),
            "zona":        (p.get("neighborhood") or p.get("city") or "Dubai").strip(),
            "web":         (p.get("website") or "").strip(),
            "email":       (p.get("email") or "").strip(),
            "rating":      p.get("totalScore") or "",
            "num_resenas": p.get("reviewsCount") or 0,
            "categoria":   (p.get("categoryName") or "").strip(),
            "google_maps": (p.get("url") or "").strip(),
        })
        if len(clinics) >= 50:
            break

    return clinics


# ── PDF ───────────────────────────────────────────────────────────────────────
def generate_pdf(clinics: list[dict], path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Table, TableStyle,
        Spacer, HRFlowable, PageBreak
    )

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    gold   = colors.HexColor("#C8A96E")
    dark   = colors.HexColor("#1A1A2E")
    mid    = colors.HexColor("#2D2D4E")
    light  = colors.HexColor("#F5F0E8")
    green  = colors.HexColor("#2ECC71")

    title_style = ParagraphStyle("title", parent=styles["Title"],
        fontSize=22, textColor=dark, spaceAfter=4, leading=26)
    sub_style   = ParagraphStyle("sub",   parent=styles["Normal"],
        fontSize=10, textColor=colors.HexColor("#666666"), spaceAfter=2)
    h2_style    = ParagraphStyle("h2",    parent=styles["Heading2"],
        fontSize=13, textColor=dark, spaceBefore=10, spaceAfter=4)
    body_style  = ParagraphStyle("body",  parent=styles["Normal"],
        fontSize=8.5, leading=12, textColor=colors.HexColor("#333333"))
    tip_style   = ParagraphStyle("tip",   parent=styles["Normal"],
        fontSize=8, leading=11, textColor=colors.HexColor("#444444"),
        leftIndent=10)
    clinic_name = ParagraphStyle("cname", parent=styles["Normal"],
        fontSize=10, textColor=dark, fontName="Helvetica-Bold")
    label_style = ParagraphStyle("label", parent=styles["Normal"],
        fontSize=7.5, textColor=colors.HexColor("#888888"))

    story = []

    # ── Portada ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("Directorio de Llamadas en Frío", title_style))
    story.append(Paragraph("Clínicas Estéticas · Dubai · UAE", sub_style))
    story.append(Paragraph(f"Generado el {datetime.now().strftime('%d/%m/%Y')} · {len(clinics)} clínicas", sub_style))
    story.append(HRFlowable(width="100%", thickness=2, color=gold, spaceAfter=14))

    # ── Guía rápida de cold call ─────────────────────────────────────────────
    story.append(Paragraph("Guía rápida de llamada en frío", h2_style))
    tips = [
        ("Hora ideal",       "Dom–Jue de 10:00–12:00 o 15:00–17:00 (hora UAE, UTC+4). Viernes y sábado son fin de semana en Dubai."),
        ("Apertura",         '"Good morning, may I speak with the clinic manager or owner?" — siempre pide al decision-maker directamente.'),
        ("Pitch 15 seg",     '"We help aesthetic clinics in Dubai attract high-value clients through targeted social media advertising. We\'re currently onboarding 2 clinics in [zona]. Is this a good time for 2 minutes?"'),
        ("Objeción común",   '"We already have marketing" → "That\'s great! Are you happy with the ROI? We typically double the bookings in 60 days — I can show you a case study."'),
        ("Cierre",           'Objetivo: agendar una videollamada de 20 min. "Can we jump on a quick Zoom this week? Thursday at 11 AM Dubai time?"'),
        ("CRM",              'Apunta: contestó / no contestó / interesado / no interesado / callback. Llama 3 veces antes de descartar.'),
    ]
    tip_data = [[Paragraph(f"<b>{k}</b>", tip_style), Paragraph(v, tip_style)] for k, v in tips]
    tip_table = Table(tip_data, colWidths=[2.8*cm, 13.7*cm])
    tip_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), light),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [light, colors.white]),
        ("GRID",        (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    story.append(tip_table)
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CCCCCC"), spaceAfter=10))

    # ── Listado de clínicas ──────────────────────────────────────────────────
    story.append(Paragraph(f"Listado de {len(clinics)} Clínicas", h2_style))

    COLS = [0.5*cm, 5.5*cm, 3.5*cm, 2.3*cm, 4.7*cm]  # #, Nombre, Teléfono, Rating, Web/Dirección

    header = [
        Paragraph("<b>#</b>", body_style),
        Paragraph("<b>Clínica</b>", body_style),
        Paragraph("<b>Teléfono</b>", body_style),
        Paragraph("<b>Rating</b>", body_style),
        Paragraph("<b>Web / Dirección</b>", body_style),
    ]
    rows = [header]

    for i, c in enumerate(clinics, 1):
        rating_str = f"★ {c['rating']}  ({c['num_resenas']} reviews)" if c["rating"] else "—"
        web_addr   = c["web"] or c["direccion"] or "—"
        phone_str  = c["telefono"] if c["telefono"] else "⚠ Sin teléfono"
        phone_color = "#CC0000" if not c["telefono"] else "#006600"

        rows.append([
            Paragraph(str(i), body_style),
            Paragraph(f"<b>{c['nombre']}</b><br/><font size='7' color='#888888'>{c['zona']}</font>", body_style),
            Paragraph(f"<font color='{phone_color}'>{phone_str}</font>", body_style),
            Paragraph(rating_str, body_style),
            Paragraph(web_addr[:55] + ("…" if len(web_addr) > 55 else ""), body_style),
        ])

    tbl = Table(rows, colWidths=COLS, repeatRows=1)
    row_bg = [colors.HexColor("#EAE6F0"), colors.white]
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  mid),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), row_bg),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)

    # ── Hoja de seguimiento ──────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Hoja de Seguimiento", h2_style))
    story.append(Paragraph("Imprime esta página para llevar el control de cada llamada.", sub_style))
    story.append(Spacer(1, 0.3*cm))

    track_header = [
        Paragraph("<b>#</b>", body_style),
        Paragraph("<b>Clínica</b>", body_style),
        Paragraph("<b>Teléfono</b>", body_style),
        Paragraph("<b>Estado</b><br/><font size='6'>✓ / ✗ / CB / INT</font>", body_style),
        Paragraph("<b>Notas / Próximo paso</b>", body_style),
        Paragraph("<b>Fecha callback</b>", body_style),
    ]
    track_rows = [track_header]
    for i, c in enumerate(clinics, 1):
        track_rows.append([
            Paragraph(str(i), body_style),
            Paragraph(c["nombre"][:28], body_style),
            Paragraph(c["telefono"] or "—", body_style),
            Paragraph("", body_style),
            Paragraph("", body_style),
            Paragraph("", body_style),
        ])

    track_tbl = Table(
        track_rows,
        colWidths=[0.5*cm, 4.5*cm, 3*cm, 1.8*cm, 5.2*cm, 2.5*cm],
        repeatRows=1,
    )
    track_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  mid),
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
    print(f"\n✅  PDF generado: {path}")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Clínicas Estéticas Dubai — Scraper + PDF")
    print("=" * 55)

    raw = run_actor_and_wait(ACTOR_ID, RUN_INPUT)
    print(f"\n   Resultados brutos: {len(raw)}")

    # Guardar JSON por si acaso
    JSON_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    print(f"   JSON guardado: {JSON_PATH.name}")

    clinics = parse_clinics(raw)
    print(f"   Clínicas únicas con datos: {len(clinics)}")

    with_phone = sum(1 for c in clinics if c["telefono"])
    print(f"   Con teléfono: {with_phone}/{len(clinics)}")

    generate_pdf(clinics, PDF_PATH)
    print(f"\n📄  Abre el PDF: {PDF_PATH}")


if __name__ == "__main__":
    main()
