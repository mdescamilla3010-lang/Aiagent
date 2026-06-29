"""
Módulo unificado para los tres canales de Meta:
- WhatsApp Cloud API
- Facebook Messenger
- Instagram Direct Messages

Todos comparten el mismo token de la App de Meta.
"""
import httpx
import logging
from dataclasses import dataclass
from config import META_TOKEN, WHATSAPP_PHONE_NUMBER_ID

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v19.0"
HEADERS = {
    "Authorization": f"Bearer {META_TOKEN}",
    "Content-Type": "application/json",
}


@dataclass
class IncomingMessage:
    channel: str          # "whatsapp" | "facebook" | "instagram"
    sender_id: str        # ID del remitente en la plataforma
    phone: str            # Teléfono (solo disponible en WhatsApp)
    name: str             # Nombre del contacto
    text: str
    message_id: str


# ── Parsers de webhook ────────────────────────────────────────────────────────

def parse_webhook(payload: dict) -> IncomingMessage | None:
    """
    Detecta el canal por el campo 'object' del webhook de Meta y
    delega al parser correspondiente.
    Retorna None para eventos leadgen (se manejan en leadgen.py).
    """
    from leadgen import is_leadgen_event

    obj = payload.get("object", "")

    if obj == "whatsapp_business_account":
        return _parse_whatsapp(payload)
    elif obj == "page":
        if is_leadgen_event(payload):
            return None  # Manejado por el flujo de leadgen en main.py
        return _parse_facebook(payload)
    elif obj == "instagram":
        return _parse_instagram(payload)

    return None


def _parse_whatsapp(payload: dict) -> IncomingMessage | None:
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        if "messages" not in value:
            return None

        msg = value["messages"][0]
        contact = value["contacts"][0]
        phone = msg["from"]

        return IncomingMessage(
            channel="whatsapp",
            sender_id=phone,
            phone=phone,
            name=contact["profile"]["name"],
            text=msg.get("text", {}).get("body", ""),
            message_id=msg["id"],
        )
    except (KeyError, IndexError):
        return None


def _parse_facebook(payload: dict) -> IncomingMessage | None:
    try:
        entry = payload["entry"][0]
        messaging = entry["messaging"][0]

        sender_id = messaging["sender"]["id"]
        text = messaging.get("message", {}).get("text", "")
        message_id = messaging.get("message", {}).get("mid", "")

        if not text:
            return None

        return IncomingMessage(
            channel="facebook",
            sender_id=sender_id,
            phone="",
            name="",         # Se enriquece con la API de Graph si se necesita
            text=text,
            message_id=message_id,
        )
    except (KeyError, IndexError):
        return None


def _parse_instagram(payload: dict) -> IncomingMessage | None:
    try:
        entry = payload["entry"][0]
        messaging = entry["messaging"][0]

        sender_id = messaging["sender"]["id"]
        text = messaging.get("message", {}).get("text", "")
        message_id = messaging.get("message", {}).get("mid", "")

        if not text:
            return None

        return IncomingMessage(
            channel="instagram",
            sender_id=sender_id,
            phone="",
            name="",
            text=text,
            message_id=message_id,
        )
    except (KeyError, IndexError):
        return None


# ── Senders ───────────────────────────────────────────────────────────────────

async def send_message(msg: IncomingMessage, text: str) -> bool:
    """Enruta el envío al canal correcto."""
    if msg.channel == "whatsapp":
        return await _send_whatsapp(msg.phone, text)
    elif msg.channel in ("facebook", "instagram"):
        return await _send_messenger(msg.sender_id, text)
    return False


async def _send_whatsapp(to: str, text: str) -> bool:
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAPH_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages",
            headers=HEADERS,
            json=payload,
        )
        if resp.status_code == 200:
            return True
        logger.error(f"Error WhatsApp send: {resp.status_code} {resp.text}")
        return False


async def _send_messenger(recipient_id: str, text: str) -> bool:
    """Válido tanto para Facebook Messenger como Instagram DM."""
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAPH_BASE}/me/messages",
            headers=HEADERS,
            params={"access_token": META_TOKEN},
            json=payload,
        )
        if resp.status_code == 200:
            return True
        logger.error(f"Error Messenger/IG send: {resp.status_code} {resp.text}")
        return False


async def get_sender_name(channel: str, sender_id: str) -> str:
    """Obtiene el nombre del usuario desde la Graph API (Facebook/Instagram)."""
    if channel == "whatsapp":
        return ""

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GRAPH_BASE}/{sender_id}",
            params={"fields": "name,username", "access_token": META_TOKEN},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("name") or data.get("username") or ""
    return ""
