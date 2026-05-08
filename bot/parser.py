"""
Parsea el mensaje del usuario con el LLM y devuelve la solicitud estructurada
junto con la guía de cold call adaptada al tipo de negocio y zona.
"""
import json
import re
import requests
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL

PROMPT = """Eres un asistente que extrae información de solicitudes de leads y genera guías de llamada en frío.

El usuario envía un mensaje pidiendo un listado de negocios. Debes extraer:
- quantity: número entero de negocios solicitados (entre 1 y 200)
- business_type: tipo de negocio en inglés, plural, minúsculas (ej: "aesthetic clinics", "restaurants", "plumbers")
- zone: ciudad/zona en inglés, con mayúscula inicial (ej: "Barcelona", "Dubai", "Paris")
- phone_prefix: prefijo telefónico internacional del país (ej: "+971" para UAE, "+34" para España, "+33" para Francia)

Además, genera una guía de llamada en frío adaptada específicamente a ese tipo de negocio y zona, con exactamente 6 puntos:
1. Hora ideal (con horario local y días laborables del país)
2. Apertura (cómo iniciar la llamada)
3. Pitch 15 seg (propuesta de valor adaptada al tipo de negocio)
4. Objeción común y cómo manejarla (la más frecuente para ese sector)
5. Cierre (cómo agendar una videollamada)
6. CRM (cómo registrar el resultado)

Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta:
{
  "quantity": <int>,
  "business_type": "<string>",
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
    Devuelve dict con: quantity, business_type, zone, phone_prefix, cold_call_guide.
    Lanza ValueError si el mensaje no puede parsearse.
    """
    prompt = PROMPT.replace("{message}", user_message.replace('"', "'"))

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
        timeout=60,
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

    return {
        "quantity": quantity,
        "business_type": data["business_type"].lower().strip(),
        "zone": data["zone"].strip(),
        "phone_prefix": data.get("phone_prefix", ""),
        "cold_call_guide": data.get("cold_call_guide", []),
    }
