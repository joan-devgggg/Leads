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
            ["Hora ideal", "Dom–Jue de 10:00–12:00 o 15:00–17:00 (hora local). Evita fines de semana según el país."],
            ["Apertura", '"Good morning, may I speak with the clinic manager or owner?" — siempre pide al decision-maker directamente.'],
            ["Pitch 15 seg", '"We help aesthetic clinics attract high-value clients through targeted social media advertising. We\'re currently onboarding 2 clinics in [zona]. Is this a good time for 2 minutes?"'],
            ["Objeción común", '"We already have marketing" → "That\'s great! Are you happy with the ROI? We typically double the bookings in 60 days — I can show you a case study."'],
            ["Cierre", 'Objetivo: agendar una videollamada de 20 min. "Can we jump on a quick Zoom this week? Thursday at 11 AM local time?"'],
            ["CRM", 'Apunta: contestó / no contestó / interesado / no interesado / callback. Llama 3 veces antes de descartar.'],
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
