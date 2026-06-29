"""
Procesador de leads desde Facebook Lead Ads (Leadgen).

Flujo:
1. Meta envía webhook con objeto 'page' y field 'leadgen'
2. Se obtienen los datos del formulario via Graph API
3. Se crea el contacto en GHL en etapa NUEVO_LEAD
4. Se inicia contacto proactivo por WhatsApp (si hay teléfono) o se marca para seguimiento
5. Se arranca la secuencia de nurturing
"""
import httpx
import logging
from dataclasses import dataclass, field
from typing import Optional
from config import META_TOKEN, DEVELOPMENTS

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v19.0"
HEADERS = {"Authorization": f"Bearer {META_TOKEN}"}

# Mapeo de nombres de campo del formulario a claves internas
FIELD_MAP = {
    # Campos estándar de Meta Lead Ads
    "full_name":        "nombre",
    "first_name":       "nombre",
    "last_name":        "apellido",
    "email":            "email",
    "phone_number":     "telefono",
    "phone":            "telefono",
    # Preguntas personalizadas frecuentes en inmobiliario
    "presupuesto":      "presupuesto",
    "budget":           "presupuesto",
    "desarrollo":       "interes",
    "proyecto":         "interes",
    "tipo_inmueble":    "tipo_inmueble",
    "inversion_o_uso":  "tipo_compra",
    "ciudad":           "ciudad",
    "como_nos_conocio": "fuente",
}


@dataclass
class LeadFormData:
    lead_id: str
    page_id: str
    ad_id: str = ""
    form_id: str = ""
    nombre: str = ""
    apellido: str = ""
    email: str = ""
    telefono: str = ""
    presupuesto: str = ""
    interes: str = ""         # desarrollo_a | desarrollo_b | ambos
    tipo_compra: str = ""
    ciudad: str = ""
    fuente: str = "Facebook Lead Ad"
    raw_fields: dict = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        if self.apellido:
            return f"{self.nombre} {self.apellido}".strip()
        return self.nombre

    @property
    def phone_normalized(self) -> str:
        """Normaliza el teléfono al formato internacional (MX por defecto)."""
        t = self.telefono.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if t and not t.startswith("+"):
            if t.startswith("52"):
                return f"+{t}"
            return f"+52{t}"
        return t


def is_leadgen_event(payload: dict) -> bool:
    """Detecta si el webhook es un evento de Lead Ads."""
    try:
        changes = payload["entry"][0]["changes"]
        return any(c.get("field") == "leadgen" for c in changes)
    except (KeyError, IndexError):
        return False


async def extract_leadgen_data(payload: dict) -> Optional[LeadFormData]:
    """Extrae y enriquece los datos del webhook de Lead Ads."""
    try:
        entry = payload["entry"][0]
        page_id = entry["id"]
        change = next(c for c in entry["changes"] if c.get("field") == "leadgen")
        value = change["value"]

        lead_id = value["leadgen_id"]
        ad_id = value.get("ad_id", "")
        form_id = value.get("form_id", "")

        lead_data = await _fetch_lead_details(lead_id)
        if not lead_data:
            return None

        result = LeadFormData(
            lead_id=lead_id,
            page_id=page_id,
            ad_id=ad_id,
            form_id=form_id,
        )

        for field_item in lead_data.get("field_data", []):
            raw_name = field_item["name"].lower().replace(" ", "_")
            value_str = field_item.get("values", [""])[0]
            mapped = FIELD_MAP.get(raw_name)
            if mapped and hasattr(result, mapped):
                setattr(result, mapped, value_str)
            result.raw_fields[raw_name] = value_str

        # Inferir desarrollo por el nombre del anuncio si no vino en el formulario
        if not result.interes and ad_id:
            result.interes = await _infer_desarrollo_from_ad(ad_id)

        logger.info(f"Lead Ads procesado: {lead_id} — {result.full_name} {result.phone_normalized}")
        return result

    except (KeyError, IndexError, StopIteration) as e:
        logger.error(f"Error parseando leadgen payload: {e}")
        return None


async def _fetch_lead_details(lead_id: str) -> Optional[dict]:
    """Consulta la Graph API para obtener los datos del formulario."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GRAPH_BASE}/{lead_id}",
            headers=HEADERS,
            params={"fields": "field_data,ad_id,form_id,created_time"},
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error(f"Error al obtener lead {lead_id}: {resp.status_code} {resp.text}")
        return None


async def _infer_desarrollo_from_ad(ad_id: str) -> str:
    """Intenta inferir el desarrollo de interés a partir del nombre del anuncio."""
    from config import DEVELOPMENTS
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GRAPH_BASE}/{ad_id}",
            headers=HEADERS,
            params={"fields": "name"},
        )
        if resp.status_code == 200:
            ad_name = resp.json().get("name", "").lower()
            for dev_key, dev_info in DEVELOPMENTS.items():
                dev_name = dev_info["nombre"].lower()
                if any(word in ad_name for word in dev_name.split()):
                    return dev_key
    return ""


async def build_welcome_message(lead: LeadFormData) -> str:
    """Genera el mensaje de bienvenida personalizado para el lead."""
    from config import DEVELOPMENTS

    nombre = lead.nombre or "amigo/a"
    dev_info = DEVELOPMENTS.get(lead.interes, {})
    dev_name = dev_info.get("nombre", "") if dev_info else ""

    if dev_name:
        return (
            f"¡Hola {nombre}! 👋 Gracias por tu interés en *{dev_name}*.\n\n"
            f"Soy el asistente virtual del proyecto y estoy aquí para resolver todas tus dudas.\n\n"
            f"¿Qué te gustaría saber primero: precios, ubicación, amenidades o financiamiento?"
        )
    return (
        f"¡Hola {nombre}! 👋 Recibimos tu solicitud de información sobre nuestros desarrollos.\n\n"
        f"Soy el asistente virtual y estoy aquí para ayudarte. "
        f"Tenemos dos proyectos disponibles. ¿Buscas casa o departamento?"
    )
