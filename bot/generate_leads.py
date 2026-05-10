"""
Script standalone para generar PDFs de leads usando todas las integraciones:
- Parser LLM (OpenRouter)
- Apify Scraping
- Supabase deduplicación
- PDF Generator
"""
import asyncio
from datetime import datetime
from pathlib import Path

from scraper import scrape_businesses
from database import filter_new, save, count_sent
from pdf_generator import generate_pdf
from config import PDF_OUTPUT_DIR


def generate_leads_for_zone(business_type: str, zone: str, quantity: int, phone_prefix: str) -> str:
    """Genera PDF de leads para una zona específica."""
    print(f"\n{'='*60}")
    print(f"Generando {quantity} {business_type} en {zone}")
    print(f"{'='*60}")
    
    # 1. Parse (simulado - usamos valores directos para evitar LLM)
    print("1. Parseando solicitud...")
    req = {
        "quantity": quantity,
        "business_type": business_type,
        "zone": zone,
        "phone_prefix": phone_prefix,
            "cold_call_guide": [
             ["Hora ideal", "Dom–Jue de 10:00–12:00 o 15:00–17:00 (hora local). Prioriza franjas con menos saturación de recepción."],
             ["Apertura", '"Hola, soy [nombre]. Te llamo porque trabajamos con clínicas estéticas que quieren responder más rápido y no perder leads."'],
             ["Pitch 15 seg", '"Ayudamos a clínicas estéticas a automatizar WhatsApp, seguimiento y atención al cliente con agentes IA que responden 24/7, recuperan leads perdidos y ayudan a cerrar más citas sin sumar personal."'],
             ["Objeción común", '"Ya tenemos recepción / ya tenemos CRM" → "Perfecto, justo ahí aportamos valor: automatizamos el seguimiento, reducimos tiempos de respuesta y evitamos que entren leads fríos o se pierdan reservas."'],
             ["Cierre", 'Objetivo: agendar una demo breve. "¿Te va bien una llamada de 15 minutos esta semana para enseñarte cómo lo automatizaríamos en tu clínica?"'],
             ["CRM", 'Registra: contacto, interés, sistema actual, dolor principal, siguiente paso y fecha de seguimiento.'],
        ]
    }
    print(f"   ✓ Quantity: {req['quantity']}")
    print(f"   ✓ Type: {req['business_type']}")
    print(f"   ✓ Zone: {req['zone']}")
    
    # 2. Scrape
    print(f"\n2. Scraping con Apify...")
    candidates = scrape_businesses(
        business_type=req["business_type"],
        zone=req["zone"],
        max_results=req["quantity"] + 30,
        phone_prefix=req["phone_prefix"],
    )
    print(f"   ✓ Encontrados: {len(candidates)} candidatos")
    
    # 3. Deduplicación
    print(f"\n3. Filtrando duplicados en Supabase...")
    new_businesses = filter_new(candidates)
    already_count = count_sent(zone, business_type)
    print(f"   ✓ Nuevos: {len(new_businesses)}")
    print(f"   ✓ Ya enviados anteriormente: {already_count}")
    
    if len(new_businesses) == 0:
        print(f"\n✗ Ya se enviaron todos los {business_type} en {zone}")
        return None
    
    to_send = new_businesses[:req["quantity"]]
    if len(to_send) < req["quantity"]:
        print(f"   ⚠ Solo {len(to_send)} disponibles (se pidieron {req['quantity']})")
    
    # 4. Guardar en Supabase
    print(f"\n4. Guardando en Supabase...")
    save(to_send)
    print(f"   ✓ Guardados: {len(to_send)} negocios")
    
    # 5. Generar PDF
    print(f"\n5. Generando PDF...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_zone = zone.replace(" ", "_").replace("/", "-")
    safe_type = business_type.replace(" ", "_").replace("/", "-")
    pdf_path = PDF_OUTPUT_DIR / f"leads_{safe_zone}_{safe_type}_{timestamp}.pdf"
    
    generate_pdf(
        businesses=to_send,
        business_type=req["business_type"],
        zone=req["zone"],
        cold_call_guide=req["cold_call_guide"],
        output_path=pdf_path,
    )
    print(f"   ✓ PDF generado: {pdf_path}")
    
    return str(pdf_path)


def main():
    print("\n" + "="*60)
    print("  GENERADOR DE LEADS - AUTOMATIZACIÓN COMPLETA")
    print("="*60)
    
    PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generar Dubai
    dubai_pdf = generate_leads_for_zone(
        business_type="aesthetic clinics",
        zone="Dubai",
        quantity=50,
        phone_prefix="+971"
    )
    
    # Generar Argentina (Buenos Aires como principal ciudad)
    argentina_pdf = generate_leads_for_zone(
        business_type="aesthetic clinics",
        zone="Buenos Aires",
        quantity=50,
        phone_prefix="+54"
    )
    
    print(f"\n{'='*60}")
    print("  RESUMEN")
    print(f"{'='*60}")
    if dubai_pdf:
        print(f"✓ Dubai: {dubai_pdf}")
    if argentina_pdf:
        print(f"✓ Argentina: {argentina_pdf}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
