"""
Handlers del bot de Telegram.
"""
import asyncio
import logging
import time
from datetime import datetime
from uuid import uuid4

from telegram import Update
from telegram.error import TelegramError, TimedOut
from telegram.ext import ContextTypes

from parser import parse_request
from scraper import scrape_businesses
from database import filter_new, save, count_sent, is_authorized
from pdf_generator import generate_pdf_bytes

logger = logging.getLogger(__name__)


def _mark(job_id: str, stage: str, started: float) -> None:
    logger.info("job_id=%s stage=%s elapsed=%.2fs", job_id, stage, time.perf_counter() - started)


async def _safe_send_message(chat_id: int, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except TimedOut:
        logger.warning("TimedOut enviando mensaje chat_id=%s text=%r", chat_id, text)
    except TelegramError:
        logger.exception("TelegramError enviando mensaje chat_id=%s text=%r", chat_id, text)
    except Exception:
        logger.exception("Error inesperado enviando mensaje chat_id=%s text=%r", chat_id, text)



def _log_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        logger.warning("Background task cancelada")
    except Exception:
        logger.exception("Background task falló")

_HELP = (
    "Envíame un mensaje indicando cuántos negocios quieres y de qué zona.\n\n"
    "Ejemplos:\n"
    "• Dame 50 clínicas estéticas de Dubai\n"
    "• Envíame 20 restaurantes en Valencia\n"
    "• Quiero 30 peluquerías en California\n\n"
    "Recibirás un PDF con guía comercial de automatización e IA + listado + hoja de seguimiento."
)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id if update.effective_user else None
    job_id = uuid4().hex[:8]

    if not text:
        return

    try:
        authorized = user_id and await asyncio.to_thread(is_authorized, user_id)
    except Exception:
        logger.exception("Error comprobando autorización para user_id=%s", user_id)
        await _safe_send_message(chat_id, context, "Error interno al verificar acceso. Inténtalo de nuevo.")
        return

    if not authorized:
        logger.warning("Acceso denegado para user_id=%s", user_id)
        await _safe_send_message(chat_id, context, "No tienes acceso a este bot.")
        return

    await _safe_send_message(chat_id, context, f"Procesando tu solicitud... [#{job_id}]")

    async def _background_job() -> None:
        flow_started = time.perf_counter()
        try:
            parse_started = time.perf_counter()
            req = await asyncio.to_thread(parse_request, text)
            _mark(job_id, "parse", parse_started)
        except ValueError as e:
            await _safe_send_message(chat_id, context, f"No entendí tu solicitud: {e}\n\n{_HELP}")
            return
        except Exception as e:
            logger.exception("Error en parser")
            await _safe_send_message(chat_id, context, "Error al interpretar tu mensaje. Inténtalo de nuevo.")
            return

        quantity = req["quantity"]
        business_type = req["business_type"]
        business_queries = req.get("business_queries") or [business_type]
        zone = req["zone"]
        phone_prefix = req["phone_prefix"]
        try:
            await _safe_send_message(chat_id, context, f"Buscando {quantity} {business_type} en {zone}... [#{job_id}]")
        except Exception:
            logger.exception("Error enviando mensaje intermedio job_id=%s", job_id)

        scrape_started = time.perf_counter()
        try:
            all_candidates_map: dict[str, dict] = {}
            has_scrape_warning = False
            for query in business_queries:
                logger.info("job_id=%s scraping query=%r zone=%r", job_id, query, zone)
                query_results, query_warning = await asyncio.to_thread(
                    scrape_businesses,
                    business_type=query,
                    zone=zone,
                    requested_count=quantity,
                    phone_prefix=phone_prefix,
                )
                if query_warning:
                    has_scrape_warning = True
                for item in query_results:
                    pid = item.get("place_id") or ""
                    if pid not in all_candidates_map:
                        item["business_type"] = business_type
                        all_candidates_map[pid] = item
            candidates = list(all_candidates_map.values())
            scrape_warning = (
                f"⚠️ Solo encontré {len(candidates)} negocios nuevos de los {quantity} pedidos. "
                "Google Maps no tiene más resultados disponibles para esta búsqueda en esta zona."
            ) if has_scrape_warning and len(candidates) < quantity else ""
            logger.info("job_id=%s queries=%s total_candidates=%s", job_id, len(business_queries), len(candidates))
            _mark(job_id, "scrape", scrape_started)
        except Exception as e:
            logger.exception("Error en scraper")
            await _safe_send_message(chat_id, context, f"Error al buscar negocios en Google Maps: {e}")
            return

        dedupe_started = time.perf_counter()
        try:
            new_businesses = await asyncio.to_thread(filter_new, candidates)
            already_count = await asyncio.to_thread(count_sent, zone, business_type)
            _mark(job_id, "dedupe", dedupe_started)
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
            _mark(job_id, "save", save_started)
        except Exception:
            logger.exception("Error guardando en Supabase")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_zone = zone.replace(" ", "_").replace("/", "-")
        safe_type = business_type.replace(" ", "_").replace("/", "-")
        pdf_filename = f"leads_{safe_zone}_{safe_type}_{timestamp}.pdf"

        pdf_started = time.perf_counter()
        try:
            pdf_buf = await asyncio.to_thread(
                generate_pdf_bytes,
                businesses=to_send,
                business_type=business_type,
                zone=zone,
            )
            _mark(job_id, "pdf", pdf_started)
        except Exception as e:
            logger.exception("Error generando PDF")
            await _safe_send_message(chat_id, context, f"Error al generar el PDF: {e}")
            return

        if scrape_warning:
            await _safe_send_message(chat_id, context, scrape_warning)

        await _safe_send_message(chat_id, context, "PDF generado, enviando...")

        send_started = time.perf_counter()
        caption = f"{len(to_send)} {business_type} en {zone} — {datetime.now().strftime('%d/%m/%Y')}"
        try:
            await context.bot.send_document(
                chat_id=chat_id,
                document=pdf_buf,
                filename=pdf_filename,
                caption=caption,
                write_timeout=120,
                read_timeout=60,
            )
            _mark(job_id, "upload_send", send_started)
        except TimedOut:
            logger.warning("TimedOut enviando documento chat_id=%s", chat_id)
            await _safe_send_message(chat_id, context, "El PDF se generó pero el envío tardó demasiado. Inténtalo de nuevo.")
        except TelegramError:
            logger.exception("TelegramError enviando documento chat_id=%s", chat_id)
            await _safe_send_message(chat_id, context, "Error de Telegram al enviar el PDF. Inténtalo de nuevo.")
        except Exception:
            logger.exception("Error inesperado enviando documento chat_id=%s", chat_id)
            await _safe_send_message(chat_id, context, "PDF generado pero hubo un error al enviarlo.")

        logger.info("job_id=%s flow_completed elapsed=%.2fs", job_id, time.perf_counter() - flow_started)

    task = context.application.create_task(_background_job())
    task.add_done_callback(_log_task_result)


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not await asyncio.to_thread(is_authorized, user_id):
        await update.message.reply_text("No tienes acceso a este bot.")
        return
    await update.message.reply_text(_HELP)
