"""
Parsea el mensaje del usuario con el LLM y devuelve la solicitud estructurada
junto con una guía comercial enfocada en automatización e IA para clínicas estéticas.
"""
import json
import re
import requests
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_TIMEOUT_SECS

SYSTEM_PROMPT = """
Eres un asistente que extrae información de solicitudes de leads y genera una guía comercial premium.

El usuario envía un mensaje pidiendo un listado de negocios. Debes extraer:
- quantity: número entero de negocios solicitados (entre 1 y 200)
- business_queries: lista de búsquedas para Google Maps en el IDIOMA LOCAL de la zona pedida. NUNCA traduzcas al inglés si la zona está en España u otro país hispanohablante. Minúsculas. Máximo 8 queries, mínimo 3 si el sector lo permite.
  * Zona en España o país hispanohablante (México, Argentina, Colombia…) → queries en ESPAÑOL
  * Zona en Francia → queries en francés
  * Zona en país angloparlante (UK, USA, Australia…) → queries en inglés
  * Zona en otro país → usa el idioma oficial local
- business_type: etiqueta corta en el idioma local de la zona para mostrar al usuario (ej: España → "clínicas estéticas", UK → "aesthetic clinics")
- zone: cualquier ubicación global (ciudad, región, país, estado o área)
- phone_prefix: prefijo telefónico internacional del país (ej: "+34" para España)

EXPANSIÓN DE QUERIES — ejemplos obligatorios (respeta el idioma de la zona):
- Si piden "clínicas estéticas en España" → business_queries: ["clínicas estéticas", "cirugía plástica", "medicina estética", "dermatología estética", "centros de estética", "depilación láser", "antiaging", "tratamientos faciales"]
- Si piden "administradores de fincas en Madrid" → business_queries: ["administrador de fincas", "administración de comunidades de propietarios", "gestión de comunidades", "administración de fincas urbanas"]
- Si piden "restaurantes en Valencia" → business_queries: ["restaurantes", "bares de tapas", "gastrobares", "tabernas", "marisquerías", "asadores"]
- Si piden "abogados en Barcelona" → business_queries: ["abogados", "despacho de abogados", "asesoría jurídica", "bufete de abogados", "notarías"]
- Si piden "dentistas en Sevilla" → business_queries: ["clínicas dentales", "dentistas", "ortodoncia", "implantes dentales", "odontología pediátrica"]
- Si piden "restaurants in London" → business_queries: ["restaurants", "bistros", "gastrobars", "brasseries", "diners", "taverns"]
- Si piden "lawyers in New York" → business_queries: ["law firms", "lawyers office", "legal advisors", "attorneys", "notary offices"]
- Para cualquier otro sector: desglosa en todos los subtipos y sinónimos relevantes en Google Maps, SIEMPRE en el idioma local de la zona.

Además, genera una guía comercial adaptada específicamente a ese tipo de negocio y zona, con exactamente 6 puntos:
1. Hora ideal (con horario local y días laborables del país)
2. Apertura (cómo iniciar la llamada de forma directa y moderna)
3. Pitch 15 seg (enfoque en automatización, IA, ahorro de tiempo y más citas)
4. Objeción común y cómo manejarla (la más frecuente para ese sector)
5. Cierre (cómo avanzar hacia una demo o reunión breve)
6. CRM (cómo registrar el resultado y el siguiente paso)

Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta:
{
  "quantity": <int>,
  "business_type": "<string>",
  "business_queries": ["<query1>", "<query2>", "..."],
  "zone": "<string>",
  "phone_prefix": "<string>",
  "cold_call_guide": [
    ["Hora ideal", "<texto>"],
    ["Apertura", "<texto>"],
    ["Pitch 15 seg", "<texto>"],
    ["Objeción común", "<texto>"],
    ["Cierre", "<texto>"],
    ["CRM", "<texto>"]
  ]
}

Si no puedes extraer quantity, business_type o zone del mensaje, devuelve:
{"error": "<explicación en español de qué falta>"}

Mensaje del usuario: "{message}"
"""


def parse_request(user_message: str) -> dict:
    """
    Devuelve dict con: quantity, business_type, business_queries, zone, phone_prefix, cold_call_guide.
    Lanza ValueError si el mensaje no puede parsearse.
    """
    prompt = SYSTEM_PROMPT.replace("{message}", user_message.replace('"', "'"))

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=OPENROUTER_TIMEOUT_SECS,
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"].strip()

    # Extraer JSON de la respuesta (por si el LLM añade texto extra)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No entendí tu solicitud. Prueba con: 'Dame 15 clínicas estéticas en Barcelona'")

    data = json.loads(match.group())

    if "error" in data:
        raise ValueError(data["error"])

    # Validaciones básicas
    quantity = int(data.get("quantity", 0))
    if quantity < 1:
        raise ValueError("Especifica cuántos negocios quieres (ej: 'Dame 20 restaurantes en Madrid')")
    if quantity > 200:
        quantity = 200

    if not data.get("business_type") or not data.get("zone"):
        raise ValueError("Especifica el tipo de negocio y la zona (ej: 'Dame 15 clínicas en Barcelona')")

    business_queries = data.get("business_queries") or []
    if not isinstance(business_queries, list) or not business_queries:
        business_queries = [data["business_type"].lower().strip()]

    zone = data["zone"].strip()
    return {
        "quantity": quantity,
        "business_type": data["business_type"].lower().strip(),
        "business_queries": [q.lower().strip() for q in business_queries if q],
        "zone": zone,
        "phone_prefix": data.get("phone_prefix", ""),
        "cold_call_guide": data.get("cold_call_guide", []),
    }
