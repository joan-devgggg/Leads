"""
Handlers del bot de Telegram.
"""
import asyncio
import logging
import time
from datetime import datetime

from telegram import Update
from telegram.error import TimedOut
from telegram.ext import ContextTypes

from config import PDF_OUTPUT_DIR
from parser import parse_request
from scraper import scrape_businesses
from database import filter_new, save, count_sent
from pdf_generator import generate_pdf

logger = logging.getLogger(__name__)


def _mark(stage: str, started: float) -> None:
    logger.info("stage=%s elapsed=%.2fs", stage, time.perf_counter() - started)


async def _safe_send_message(chat_id: int, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except TimedOut:
        logger.warning("TimedOut enviando mensaje chat_id=%s", chat_id)


async def _safe_send_document(chat_id: int, context: ContextTypes.DEFAULT_TYPE, **kwargs) -> None:
    try:
        await context.bot.send_document(chat_id=chat_id, **kwargs)
    except TimedOut:
        logger.warning("TimedOut enviando documento chat_id=%s", chat_id)

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

    await _safe_send_message(chat_id, context, "Procesando tu solicitud...")

    async def _background_job() -> None:
        flow_started = time.perf_counter()
        try:
            parse_started = time.perf_counter()
            req = await asyncio.to_thread(parse_request, text)
            _mark("parse", parse_started)
        except ValueError as e:
            await _safe_send_message(chat_id, context, f"No entendí tu solicitud: {e}\n\n{_HELP}")
            return
        except Exception as e:
            logger.exception("Error en parser")
            await _safe_send_message(chat_id, context, "Error al interpretar tu mensaje. Inténtalo de nuevo.")
            return

        quantity = req["quantity"]
        business_type = req["business_type"]
        zone = req["zone"]
        phone_prefix = req["phone_prefix"]
        cold_call_guide = req["cold_call_guide"]

        await _safe_send_message(chat_id, context, f"Buscando {quantity} {business_type} en {zone}...")

        scrape_started = time.perf_counter()
        try:
            candidates = await asyncio.to_thread(
                scrape_businesses,
                business_type=business_type,
                zone=zone,
                max_results=quantity + 30,
                phone_prefix=phone_prefix,
            )
            _mark("scrape", scrape_started)
        except Exception as e:
            logger.exception("Error en scraper")
            await _safe_send_message(chat_id, context, f"Error al buscar negocios en Google Maps: {e}")
            return

        dedupe_started = time.perf_counter()
        try:
            new_businesses = await asyncio.to_thread(filter_new, candidates)
            already_count = await asyncio.to_thread(count_sent, zone, business_type)
            _mark("dedupe", dedupe_started)
        except Exception as e:
            logger.exception("Error en dedupe")
            await _safe_send_message(chat_id, context, f"Error al consultar la base de datos: {e}")
            return

        if len(new_businesses) == 0:
            await _safe_send_message(
                chat_id,
                context,
                f"Ya hemos enviado todos los {business_type} disponibles en {zone}.\n"
                f"Total enviado anteriormente: {already_count}.\n\n"
                "Prueba con una zona diferente o un tipo de negocio distinto.",
            )
            return

        to_send = new_businesses[:quantity]
        if len(to_send) < quantity:
            await _safe_send_message(
                chat_id,
                context,
                f"Solo encontré {len(to_send)} nuevos {business_type} en {zone} "
                f"(ya habías recibido {already_count} anteriormente).\n"
                "Generando el PDF con los disponibles...",
            )

        save_started = time.perf_counter()
        try:
            await asyncio.to_thread(save, to_send)
            _mark("save", save_started)
        except Exception:
            logger.exception("Error guardando en Supabase")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_zone = zone.replace(" ", "_").replace("/", "-")
        safe_type = business_type.replace(" ", "_").replace("/", "-")
        pdf_path = PDF_OUTPUT_DIR / f"leads_{safe_zone}_{safe_type}_{timestamp}.pdf"

        pdf_started = time.perf_counter()
        try:
            await asyncio.to_thread(
                generate_pdf,
                businesses=to_send,
                business_type=business_type,
                zone=zone,
                cold_call_guide=cold_call_guide,
                output_path=pdf_path,
            )
            _mark("pdf", pdf_started)
        except Exception as e:
            logger.exception("Error generando PDF")
            await _safe_send_message(chat_id, context, f"Error al generar el PDF: {e}")
            return

        send_started = time.perf_counter()
        caption = f"{len(to_send)} {business_type} en {zone} — {datetime.now().strftime('%d/%m/%Y')}"
        try:
            with open(pdf_path, "rb") as f:
                await _safe_send_document(
                    chat_id,
                    context,
                    document=f,
                    filename=pdf_path.name,
                    caption=caption,
                )
            _mark("upload_send", send_started)
        except Exception:
            logger.exception("Error enviando PDF")
            await _safe_send_message(chat_id, context, "PDF generado pero hubo un error al enviarlo.")
            return

        logger.info("flow_completed elapsed=%.2fs", time.perf_counter() - flow_started)

    context.application.create_task(_background_job())


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_HELP)
