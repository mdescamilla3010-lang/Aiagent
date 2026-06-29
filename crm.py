import httpx
import logging
from typing import Optional
from config import GHL_API_KEY, GHL_LOCATION_ID

logger = logging.getLogger(__name__)

GHL_BASE = "https://rest.gohighlevel.com/v1"
HEADERS = {
    "Authorization": f"Bearer {GHL_API_KEY}",
    "Content-Type": "application/json",
}


async def upsert_contact(phone: str, data: dict, channel: str = "whatsapp") -> Optional[str]:
    """Crea o actualiza un contacto en GHL. Retorna el contact ID."""
    contact_id = await _find_contact(phone, data)

    props = _build_properties(phone, data, channel)

    if contact_id:
        await _update_contact(contact_id, props)
        logger.info(f"Contacto actualizado en GHL: {contact_id}")
    else:
        contact_id = await _create_contact(props)
        logger.info(f"Contacto creado en GHL: {contact_id}")

    return contact_id


async def add_note(contact_id: str, note: str) -> None:
    """Agrega una nota al contacto en GHL."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GHL_BASE}/contacts/{contact_id}/notes",
            headers=HEADERS,
            json={"body": note},
        )
        if resp.status_code not in (200, 201):
            logger.error(f"Error al agregar nota GHL: {resp.text}")


async def create_opportunity(contact_id: str, desarrollo: str, stage: str = "nuevo lead") -> Optional[str]:
    """Crea una oportunidad (pipeline) en GHL asociada al contacto."""
    from config import DEVELOPMENTS
    dev_name = DEVELOPMENTS.get(desarrollo, {}).get("nombre", desarrollo)

    async with httpx.AsyncClient() as client:
        payload = {
            "title": f"Lead - {dev_name}",
            "status": "open",
            "stageId": stage,
            "contactId": contact_id,
            "locationId": GHL_LOCATION_ID,
        }
        resp = await client.post(
            f"{GHL_BASE}/pipelines/opportunities",
            headers=HEADERS,
            json=payload,
        )
        if resp.status_code in (200, 201):
            opp_id = resp.json().get("opportunity", {}).get("id")
            logger.info(f"Oportunidad creada en GHL: {opp_id}")
            return opp_id
        logger.error(f"Error al crear oportunidad GHL: {resp.text}")
        return None


async def update_opportunity_stage(opportunity_id: str, stage: str) -> None:
    """Actualiza el stage de una oportunidad en GHL."""
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{GHL_BASE}/pipelines/opportunities/{opportunity_id}",
            headers=HEADERS,
            json={"stageId": stage},
        )
        if resp.status_code not in (200, 201):
            logger.error(f"Error al actualizar oportunidad GHL: {resp.text}")


async def add_tag(contact_id: str, tag: str) -> None:
    """Agrega un tag al contacto en GHL."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GHL_BASE}/contacts/{contact_id}/tags",
            headers=HEADERS,
            json={"tags": [tag]},
        )
        if resp.status_code not in (200, 201):
            logger.error(f"Error al agregar tag GHL: {resp.text}")


async def _find_contact(phone: str, data: dict) -> Optional[str]:
    """Busca contacto por teléfono o email."""
    async with httpx.AsyncClient() as client:
        # Buscar por teléfono
        resp = await client.get(
            f"{GHL_BASE}/contacts/",
            headers=HEADERS,
            params={"locationId": GHL_LOCATION_ID, "query": phone},
        )
        if resp.status_code == 200:
            contacts = resp.json().get("contacts", [])
            if contacts:
                return contacts[0]["id"]

        # Buscar por email si está disponible
        email = data.get("email")
        if email:
            resp = await client.get(
                f"{GHL_BASE}/contacts/",
                headers=HEADERS,
                params={"locationId": GHL_LOCATION_ID, "query": email},
            )
            if resp.status_code == 200:
                contacts = resp.json().get("contacts", [])
                if contacts:
                    return contacts[0]["id"]

    return None


async def _create_contact(props: dict) -> Optional[str]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GHL_BASE}/contacts/",
            headers=HEADERS,
            json=props,
        )
        if resp.status_code in (200, 201):
            return resp.json().get("contact", {}).get("id")
        logger.error(f"Error al crear contacto GHL: {resp.text}")
        return None


async def _update_contact(contact_id: str, props: dict) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{GHL_BASE}/contacts/{contact_id}",
            headers=HEADERS,
            json=props,
        )
        if resp.status_code not in (200, 201):
            logger.error(f"Error al actualizar contacto GHL: {resp.text}")


def _build_properties(phone: str, data: dict, channel: str) -> dict:
    nombre = data.get("nombre", "")
    parts = nombre.split(" ", 1) if nombre else []

    props = {
        "locationId": GHL_LOCATION_ID,
        "phone": phone,
        "source": f"IA - {channel.capitalize()}",
        "tags": [channel, "ia-agente"],
        "customField": [
            {"key": "desarrollo_interes", "value": data.get("interes", "")},
            {"key": "tipo_compra", "value": data.get("tipo_compra", "")},
            {"key": "canal_entrada", "value": channel},
        ],
    }

    if parts:
        props["firstName"] = parts[0]
        if len(parts) > 1:
            props["lastName"] = parts[1]
    if data.get("email"):
        props["email"] = data["email"]

    return {k: v for k, v in props.items() if v}
