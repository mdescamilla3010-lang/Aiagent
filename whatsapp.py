import httpx
import logging
from config import WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID

logger = logging.getLogger(__name__)

BASE_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json",
}


async def send_text(to: str, message: str) -> bool:
    """Envía un mensaje de texto por WhatsApp."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(BASE_URL, headers=HEADERS, json=payload)
        if resp.status_code == 200:
            return True
        logger.error(f"Error WhatsApp send: {resp.status_code} {resp.text}")
        return False


async def send_template(to: str, template_name: str, components: list = None) -> bool:
    """Envía un mensaje de plantilla aprobada por Meta."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "es_MX"},
            "components": components or [],
        },
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(BASE_URL, headers=HEADERS, json=payload)
        if resp.status_code == 200:
            return True
        logger.error(f"Error WhatsApp template: {resp.status_code} {resp.text}")
        return False


def parse_incoming(payload: dict) -> dict | None:
    """Extrae mensaje entrante del webhook de Meta."""
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]["value"]

        if "messages" not in change:
            return None

        msg = change["messages"][0]
        contact = change["contacts"][0]

        return {
            "phone": msg["from"],
            "name": contact["profile"]["name"],
            "message_id": msg["id"],
            "text": msg.get("text", {}).get("body", ""),
            "type": msg["type"],
        }
    except (KeyError, IndexError):
        return None
