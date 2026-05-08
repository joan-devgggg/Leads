"""
Punto de entrada del bot de Telegram para generación de leads.
Ejecutar: python main.py
"""
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from config import TELEGRAM_BOT_TOKEN
from bot import handle_message, handle_help

logging.basicConfig(
    format="%(asctime)s  %(levelname)s  %(name)s — %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", handle_help))
    app.add_handler(CommandHandler("help",  handle_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot de leads iniciado. Ctrl+C para detener.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
