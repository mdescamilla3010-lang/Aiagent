import httpx
import logging
from typing import Optional
from config import HUBSPOT_API_KEY

logger = logging.getLogger(__name__)

HUBSPOT_BASE = "https://api.hubapi.com"
HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_API_KEY}",
    "Content-Type": "application/json",
}


async def upsert_contact(phone: str, data: dict) -> Optional[str]:
    """Crea o actualiza un contacto en HubSpot. Retorna el contact ID."""
    contact_id = await _find_contact_by_phone(phone)

    properties = _build_properties(phone, data)

    if contact_id:
        await _update_contact(contact_id, properties)
        logger.info(f"Contacto actualizado en HubSpot: {contact_id}")
        return contact_id
    else:
        contact_id = await _create_contact(properties)
        logger.info(f"Contacto creado en HubSpot: {contact_id}")
        return contact_id


async def log_note(contact_id: str, note: str) -> None:
    """Registra una nota/actividad en el contacto."""
    async with httpx.AsyncClient() as client:
        payload = {
            "engagement": {"active": True, "type": "NOTE"},
            "associations": {"contactIds": [int(contact_id)]},
            "metadata": {"body": note},
        }
        resp = await client.post(
            f"{HUBSPOT_BASE}/engagements/v1/engagements",
            headers=HEADERS,
            json=payload,
        )
        if resp.status_code not in (200, 201):
            logger.error(f"Error al registrar nota HubSpot: {resp.text}")


async def update_deal_stage(contact_id: str, stage: str, desarrollo: str) -> None:
    """Crea o actualiza un deal asociado al contacto."""
    from config import DEVELOPMENTS
    dev_name = DEVELOPMENTS.get(desarrollo, {}).get("nombre", desarrollo)

    async with httpx.AsyncClient() as client:
        payload = {
            "properties": {
                "dealname": f"Lead - {dev_name}",
                "dealstage": stage,
                "pipeline": "default",
            },
            "associations": [
                {
                    "to": {"id": contact_id},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}],
                }
            ],
        }
        resp = await client.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/deals",
            headers=HEADERS,
            json=payload,
        )
        if resp.status_code not in (200, 201):
            logger.error(f"Error al crear deal HubSpot: {resp.text}")


async def _find_contact_by_phone(phone: str) -> Optional[str]:
    async with httpx.AsyncClient() as client:
        payload = {
            "filterGroups": [
                {"filters": [{"propertyName": "phone", "operator": "EQ", "value": phone}]}
            ],
            "properties": ["id"],
        }
        resp = await client.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts/search",
            headers=HEADERS,
            json=payload,
        )
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                return results[0]["id"]
    return None


async def _create_contact(properties: dict) -> Optional[str]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
            headers=HEADERS,
            json={"properties": properties},
        )
        if resp.status_code in (200, 201):
            return resp.json()["id"]
        logger.error(f"Error al crear contacto HubSpot: {resp.text}")
        return None


async def _update_contact(contact_id: str, properties: dict) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts/{contact_id}",
            headers=HEADERS,
            json={"properties": properties},
        )
        if resp.status_code not in (200, 201):
            logger.error(f"Error al actualizar contacto HubSpot: {resp.text}")


def _build_properties(phone: str, data: dict) -> dict:
    props = {"phone": phone, "hs_lead_status": "IN_PROGRESS"}

    mapping = {
        "nombre": "firstname",
        "email": "email",
        "presupuesto": "budget__c",
        "tipo_compra": "tipo_compra__c",
        "interes": "desarrollo_interes__c",
    }
    for key, hs_key in mapping.items():
        if data.get(key):
            if key == "nombre":
                parts = data[key].split(" ", 1)
                props["firstname"] = parts[0]
                if len(parts) > 1:
                    props["lastname"] = parts[1]
            else:
                props[hs_key] = data[key]

    return props
