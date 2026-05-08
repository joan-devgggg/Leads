import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise RuntimeError(f"Variable de entorno requerida no configurada: {key}")
    return val

TELEGRAM_BOT_TOKEN  = _require("TELEGRAM_BOT_TOKEN")
SUPABASE_URL        = _require("SUPABASE_URL")
SUPABASE_KEY        = _require("SUPABASE_KEY")
APIFY_API_TOKEN     = _require("APIFY_API_TOKEN")
OPENROUTER_API_KEY  = _require("OPENROUTER_API_KEY")
OPENROUTER_MODEL    = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")

APIFY_ACTOR_ID     = "compass~crawler-google-places"
APIFY_TIMEOUT_SECS = int(os.getenv("APIFY_TIMEOUT_SECS", "480"))
PDF_OUTPUT_DIR     = BASE_DIR / "output"
