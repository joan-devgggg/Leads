"""
Punto de entrada del bot de Telegram para generación de leads.
Ejecutar: python main.py
"""
import logging
import os
import signal
import threading

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


def _run_webhook(app) -> None:
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    port = int(os.environ.get("PORT", "8080"))
    webhook_url = f"https://{railway_domain}/webhook"
    logger.info("Modo webhook — %s (puerto %d)", webhook_url, port)
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="/webhook",
        webhook_url=webhook_url,
        drop_pending_updates=True,
    )


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
        _run_webhook(_build_app())
    else:
        _run_polling()

    logger.info("Bot detenido.")


if __name__ == "__main__":
    main()
