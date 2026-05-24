"""
Punto de entrada del bot de Telegram para generación de leads.
Ejecutar: python main.py
"""
import logging
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

_CONFLICT_RETRY_SECS = 15
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
    return app


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)

    print("Bot de leads iniciado. Ctrl+C para detener.")
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

    logger.info("Bot detenido.")


if __name__ == "__main__":
    main()
