"""
Punto de entrada del bot de Telegram para generación de leads.
Ejecutar: python main.py
"""
import asyncio
import logging
import os
import signal
import threading

from aiohttp import web
from telegram import Update
from telegram.error import Conflict
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CONNECT_TIMEOUT_SECS,
    TELEGRAM_READ_TIMEOUT_SECS,
    TELEGRAM_WRITE_TIMEOUT_SECS,
    TELEGRAM_POOL_TIMEOUT_SECS,
)
from bot import handle_message, handle_help

logging.basicConfig(
    format="%(asctime)s  %(levelname)s  %(name)s — %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

_CONFLICT_RETRY_SECS = 30
_stop_event = threading.Event()

# URL fija de producción; se puede sobreescribir con RAILWAY_PUBLIC_DOMAIN
_PRODUCTION_WEBHOOK = "https://leads-production-9c61.up.railway.app/webhook"


def _handle_sigterm(signum, frame):
    logger.info("SIGTERM recibido, deteniendo bot...")
    _stop_event.set()


def _build_app():
    request = HTTPXRequest(
        connect_timeout=TELEGRAM_CONNECT_TIMEOUT_SECS,
        read_timeout=TELEGRAM_READ_TIMEOUT_SECS,
        write_timeout=TELEGRAM_WRITE_TIMEOUT_SECS,
        pool_timeout=TELEGRAM_POOL_TIMEOUT_SECS,
    )
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", handle_help))
    app.add_handler(CommandHandler("help",  handle_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(_error_handler)
    return app


async def _error_handler(update, context):
    if isinstance(context.error, Conflict):
        logger.warning("Conflicto Telegram (múltiples instancias detectadas): %s", context.error)
        return
    logger.exception("Error no controlado en el bot", exc_info=context.error)
    if update and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Error inesperado. Inténtalo de nuevo en unos segundos.",
            )
        except Exception:
            pass


async def _run_webhook_async() -> None:
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    webhook_url = (
        f"https://{railway_domain}/webhook" if railway_domain else _PRODUCTION_WEBHOOK
    )
    port = int(os.environ.get("PORT", "8080"))
    logger.info("Modo webhook — %s (puerto %d)", webhook_url, port)

    ptb_app = _build_app()
    await ptb_app.initialize()
    await ptb_app.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    logger.info("Webhook registrado con Telegram: %s", webhook_url)
    await ptb_app.start()

    aio_app = web.Application()

    async def healthcheck(request):
        return web.Response(text="OK", status=200)

    async def webhook_handler(request):
        try:
            data = await request.json()
            update = Update.de_json(data, ptb_app.bot)
            await ptb_app.process_update(update)
        except Exception:
            logger.exception("Error procesando update de Telegram")
        return web.Response(status=200)

    async def webhook_healthcheck(request):
        return web.Response(text="OK", status=200)

    aio_app.router.add_get("/", healthcheck)
    aio_app.router.add_get("/webhook", webhook_healthcheck)
    aio_app.router.add_post("/webhook", webhook_handler)

    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Servidor HTTP escuchando en 0.0.0.0:%d", port)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)
    loop.add_signal_handler(signal.SIGINT, stop_event.set)

    await stop_event.wait()

    logger.info("Apagando bot...")
    await ptb_app.stop()
    await ptb_app.shutdown()
    await runner.cleanup()
    logger.info("Bot detenido.")


def _run_polling() -> None:
    while not _stop_event.is_set():
        app = _build_app()
        try:
            app.run_polling(drop_pending_updates=True)
            break
        except Conflict:
            logger.warning(
                "Conflicto: otra instancia del bot está activa. "
                "Reintentando en %ds...", _CONFLICT_RETRY_SECS
            )
            _stop_event.wait(timeout=_CONFLICT_RETRY_SECS)


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)
    print("Bot de leads iniciado. Ctrl+C para detener.")

    if os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip():
        asyncio.run(_run_webhook_async())
    else:
        _run_polling()

    logger.info("Bot detenido.")


if __name__ == "__main__":
    main()
