# Bot de Leads — CLAUDE.md

## Qué hace este proyecto

Bot de Telegram que acepta mensajes en lenguaje natural pidiendo leads de negocios y devuelve un PDF listo para ventas consultivas de automatización e IA para clínicas estéticas.

**Flujo completo:**
1. Usuario escribe en Telegram: *"Dame 50 clínicas estéticas en Valencia"*
2. `parser.py` extrae `quantity`, `business_type`, `zone` y genera una guía comercial enfocada en automatización e IA (vía LLM → OpenRouter)
3. `scraper.py` busca en Google Maps vía Apify (`compass~crawler-google-places`)
4. `database.py` filtra duplicados contra Supabase y guarda los nuevos
5. `pdf_generator.py` genera el PDF y el bot lo envía por Telegram

## Estructura de archivos

```
bot/
├── main.py          # Entry point: python main.py
├── bot.py           # Handlers de Telegram (handle_message, handle_help)
├── parser.py        # Parsea NL con LLM → dict estructurado + guía comercial IA
├── scraper.py       # Wrapper Apify → lista normalizada de negocios
├── database.py      # Supabase: filter_new(), save(), count_sent()
├── pdf_generator.py # ReportLab: cover + guía comercial + listado + tracking sheet
├── config.py        # Carga .env, expone constantes
├── requirements.txt
├── setup.sql        # DDL tabla `negocios` (ejecutar una vez en Supabase)
└── output/          # PDFs generados (ignorar en git)
```

## Stack

| Componente | Tecnología |
|---|---|
| Bot | python-telegram-bot 20.7 |
| Parser NL | OpenRouter → `anthropic/claude-3.5-sonnet` (configurable) |
| Scraping | Apify actor `compass~crawler-google-places` |
| Deduplicación | Supabase (tabla `negocios`, índice único en `place_id`) |
| PDF | ReportLab 4.1 |

## Variables de entorno (`bot/.env`)

```
TELEGRAM_BOT_TOKEN=
SUPABASE_URL=
SUPABASE_KEY=
APIFY_API_TOKEN=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet   # opcional
APIFY_TIMEOUT_SECS=480                          # opcional
```

## PDF generado

Nombre: `leads_{zone}_{type}_{timestamp}.pdf` en `bot/output/`

Estructura (3 secciones):
1. **Portada** — título, tipo·zona, fecha, conteo
2. **Guía comercial** — 6 puntos generados por LLM (hora ideal, apertura, pitch IA, objeción, cierre, CRM)
3. **Listado de negocios** — tabla con #, nombre, teléfono, rating, web/dirección
4. **Hoja de seguimiento** — tabla imprimible con columnas: estado, notas, fecha callback

## Schema Supabase

```sql
CREATE TABLE negocios (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    place_id      TEXT NOT NULL,   -- Google Maps place ID (único)
    name          TEXT NOT NULL,
    phone         TEXT,
    address       TEXT,
    zone          TEXT NOT NULL,
    business_type TEXT NOT NULL,
    website       TEXT,
    rating        REAL,
    reviews_count INTEGER DEFAULT 0,
    sent_at       TIMESTAMPTZ DEFAULT NOW()
);
```

## Cómo ejecutar

```bash
cd bot
pip install -r requirements.txt
python main.py
```

## Límites y comportamiento

- Máximo 200 negocios por petición (se recorta automáticamente)
- Si todos los leads de esa zona+tipo ya fueron enviados → avisa al usuario
- Si hay menos nuevos de los pedidos → envía los disponibles e informa
- Apify busca con dos queries: `"{type} {zone}"` y `"best {type} in {zone}"`
- Teléfonos con prefijo `0` (no `00`) se normalizan con el prefijo internacional del país

## Posicionamiento comercial

- Automatización de WhatsApp, llamadas, CRM y seguimiento
- Agentes IA para responder 24/7 y recuperar leads perdidos
- Automatización de reservas, pipelines y atención al cliente
- Enfoque premium, directo y orientado a negocio
