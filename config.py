import os
from dotenv import load_dotenv

load_dotenv()

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-sonnet-4-6"

# WhatsApp (Meta Cloud API)
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "real_estate_verify_token")

# HubSpot CRM
HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")

# Google Calendar
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# Desarrollos inmobiliarios
DEVELOPMENTS = {
    "desarrollo_a": {
        "nombre": os.getenv("DESARROLLO_A_NOMBRE", "Residencial Los Pinos"),
        "tipo": os.getenv("DESARROLLO_A_TIPO", "casas"),
        "ubicacion": os.getenv("DESARROLLO_A_UBICACION", "Norte de la ciudad"),
        "precio_desde": os.getenv("DESARROLLO_A_PRECIO", "2,500,000 MXN"),
        "amenidades": os.getenv("DESARROLLO_A_AMENIDADES", "Alberca, gimnasio, seguridad 24/7, área verde"),
        "disponibilidad": os.getenv("DESARROLLO_A_DISPONIBILIDAD", "Entrega inmediata y preventa"),
        "contacto_asesor": os.getenv("DESARROLLO_A_ASESOR", ""),
    },
    "desarrollo_b": {
        "nombre": os.getenv("DESARROLLO_B_NOMBRE", "Torres Midtown"),
        "tipo": os.getenv("DESARROLLO_B_TIPO", "departamentos"),
        "ubicacion": os.getenv("DESARROLLO_B_UBICACION", "Centro financiero"),
        "precio_desde": os.getenv("DESARROLLO_B_PRECIO", "3,200,000 MXN"),
        "amenidades": os.getenv("DESARROLLO_B_AMENIDADES", "Rooftop, coworking, pet friendly, concierge"),
        "disponibilidad": os.getenv("DESARROLLO_B_DISPONIBILIDAD", "Preventa con entrega en 18 meses"),
        "contacto_asesor": os.getenv("DESARROLLO_B_ASESOR", ""),
    },
}

# Horarios de atención para citas
BUSINESS_HOURS = {
    "start": int(os.getenv("BUSINESS_HOURS_START", "9")),
    "end": int(os.getenv("BUSINESS_HOURS_END", "18")),
    "days": [0, 1, 2, 3, 4, 5],  # Lunes a sábado
}

# Secuencia de recordatorios (en horas)
REMINDER_SEQUENCE_HOURS = [1, 24, 72, 168]  # 1h, 1 día, 3 días, 7 días

# App
PORT = int(os.getenv("PORT", "8000"))
