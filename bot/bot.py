"""
Handlers del bot de Telegram.
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from config import PDF_OUTPUT_DIR
from parser import parse_request
from scraper import scrape_businesses
from database import filter_new, save, count_sent
from pdf_generator import generate_pdf

logger = logging.getLogger(__name__)

_HELP = (
    "Envíame un mensaje indicando cuántos negocios quieres y de qué zona.\n\n"
    "Ejemplos:\n"
    "• Dame 50 clínicas estéticas de Dubai\n"
    "• Envíame 20 restaurantes en Barcelona\n"
    "• Quiero 30 peluquerías en París\n\n"
    "Recibirás un PDF con guía comercial de automatización e IA + listado + hoja de seguimiento."
)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    if not text:
        return

    # ── 1. Parse ──────────────────────────────────────────────────────────────
    await update.message.reply_text("Procesando tu solicitud...")

    try:
        req = await asyncio.to_thread(parse_request, text)
    except ValueError as e:
        await update.message.reply_text(
            f"No entendí tu solicitud: {e}\n\n{_HELP}"
        )
        return
    except Exception as e:
        logger.error("Error en parser: %s", e)
        await update.message.reply_text("Error al interpretar tu mensaje. Inténtalo de nuevo.")
        return

    quantity      = req["quantity"]
    business_type = req["business_type"]
    zone          = req["zone"]
    phone_prefix  = req["phone_prefix"]
    cold_call_guide = req["cold_call_guide"]

    # ── 2. Scrape ─────────────────────────────────────────────────────────────
    await update.message.reply_text(
        f"Buscando {quantity} {business_type} en {zone}...\n"
        "Esto puede tardar 2–3 minutos, espera."
    )

    try:
        candidates = await asyncio.to_thread(
            scrape_businesses,
            business_type=business_type,
            zone=zone,
            max_results=quantity + 30,
            phone_prefix=phone_prefix,
        )
    except Exception as e:
        logger.error("Error en scraper: %s", e)
        await update.message.reply_text(f"Error al buscar negocios en Google Maps: {e}")
        return

    # ── 3. Deduplicación ──────────────────────────────────────────────────────
    try:
        new_businesses = await asyncio.to_thread(filter_new, candidates)
    except Exception as e:
        logger.error("Error en filter_new: %s", e)
        await update.message.reply_text(f"Error al consultar la base de datos: {e}")
        return

    try:
        already_count = await asyncio.to_thread(count_sent, zone, business_type)
    except Exception as e:
        logger.error("Error en count_sent: %s", e)
        already_count = 0

    if len(new_businesses) == 0:
        msg = (
            f"Ya hemos enviado todos los {business_type} disponibles en {zone}.\n"
            f"Total enviado anteriormente: {already_count}.\n\n"
            "Prueba con una zona diferente o un tipo de negocio distinto."
        )
        await update.message.reply_text(msg)
        return

    to_send = new_businesses[:quantity]

    if len(to_send) < quantity:
        await update.message.reply_text(
            f"Solo encontré {len(to_send)} nuevos {business_type} en {zone} "
            f"(ya habías recibido {already_count} anteriormente).\n"
            "Generando el PDF con los disponibles..."
        )

    # ── 4. Guardar en Supabase ────────────────────────────────────────────────
    try:
        await asyncio.to_thread(save, to_send)
    except Exception as e:
        logger.error("Error guardando en Supabase: %s", e)
        # No interrumpimos: generamos el PDF igualmente

    # ── 5. Generar PDF ────────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_zone = zone.replace(" ", "_").replace("/", "-")
    safe_type = business_type.replace(" ", "_").replace("/", "-")
    pdf_path  = PDF_OUTPUT_DIR / f"leads_{safe_zone}_{safe_type}_{timestamp}.pdf"

    try:
        await asyncio.to_thread(
            generate_pdf,
            businesses=to_send,
            business_type=business_type,
            zone=zone,
            cold_call_guide=cold_call_guide,
            output_path=pdf_path,
        )
    except Exception as e:
        logger.error("Error generando PDF: %s", e)
        await update.message.reply_text(f"Error al generar el PDF: {e}")
        return

    # ── 6. Enviar PDF ─────────────────────────────────────────────────────────
    caption = (
        f"{len(to_send)} {business_type} en {zone} — "
        f"{datetime.now().strftime('%d/%m/%Y')}"
    )
    try:
        with open(pdf_path, "rb") as f:
            await context.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=pdf_path.name,
                caption=caption,
            )
    except Exception as e:
        logger.error("Error enviando PDF: %s", e)
        await update.message.reply_text(f"PDF generado pero error al enviarlo: {e}")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_HELP)
