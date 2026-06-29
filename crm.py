import httpx
import logging
from typing import Optional
from config import GHL_API_KEY, GHL_LOCATION_ID, GHL_PIPELINE_ID

logger = logging.getLogger(__name__)

GHL_BASE = "https://rest.gohighlevel.com/v1"
HEADERS = {
    "Authorization": f"Bearer {GHL_API_KEY}",
    "Content-Type": "application/json",
}


# ── Contactos ─────────────────────────────────────────────────────────────────

async def upsert_contact(identifier: str, data: dict, channel: str = "whatsapp") -> Optional[str]:
    """
    Crea o actualiza contacto en GHL.
    identifier: teléfono normalizado (WhatsApp) o sender_id (Facebook/Instagram).
    """
    is_phone = identifier.startswith("+") or identifier.isdigit()
    contact_id = await _find_contact(identifier if is_phone else "", data)

    props = _build_contact_props(identifier if is_phone else "", data, channel)

    if contact_id:
        await _update_contact(contact_id, props)
        logger.info(f"Contacto actualizado en GHL: {contact_id}")
    else:
        contact_id = await _create_contact(props)
        logger.info(f"Contacto creado en GHL: {contact_id}")

    return contact_id


async def add_note(contact_id: str, note: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GHL_BASE}/contacts/{contact_id}/notes",
            headers=HEADERS,
            json={"body": note},
        )
        if resp.status_code not in (200, 201):
            logger.error(f"Error al agregar nota GHL: {resp.text}")


async def add_tag(contact_id: str, *tags: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GHL_BASE}/contacts/{contact_id}/tags",
            headers=HEADERS,
            json={"tags": list(tags)},
        )
        if resp.status_code not in (200, 201):
            logger.error(f"Error al agregar tags GHL: {resp.text}")


# ── Pipeline / Oportunidades ──────────────────────────────────────────────────

async def create_opportunity(
    contact_id: str,
    desarrollo: str,
    stage: "Stage",  # noqa: F821 — importado en runtime para evitar circular
    source: str = "IA Agent",
) -> Optional[str]:
    """Crea una oportunidad en el pipeline de GHL."""
    from config import DEVELOPMENTS
    from pipeline import get_ghl_stage_id, STAGE_LABELS

    dev_name = DEVELOPMENTS.get(desarrollo, {}).get("nombre", desarrollo)
    stage_id = get_ghl_stage_id(stage)

    async with httpx.AsyncClient() as client:
        payload = {
            "title": f"Lead - {dev_name}",
            "status": "open",
            "stageId": stage_id,
            "pipelineId": GHL_PIPELINE_ID,
            "contactId": contact_id,
            "locationId": GHL_LOCATION_ID,
            "source": source,
        }
        resp = await client.post(
            f"{GHL_BASE}/pipelines/opportunities",
            headers=HEADERS,
            json={k: v for k, v in payload.items() if v},
        )
        if resp.status_code in (200, 201):
            opp_id = resp.json().get("opportunity", {}).get("id")
            logger.info(f"Oportunidad creada GHL: {opp_id} — {STAGE_LABELS[stage]}")
            return opp_id
        logger.error(f"Error al crear oportunidad GHL: {resp.text}")
        return None


async def advance_stage(
    opportunity_id: str,
    contact_id: str,
    current_stage: "Stage",
    target_stage: "Stage",
) -> bool:
    """
    Mueve la oportunidad a la siguiente etapa si la transición es válida.
    Retorna True si se realizó el cambio.
    """
    from pipeline import can_transition, get_ghl_stage_id, STAGE_LABELS

    if not can_transition(current_stage, target_stage):
        logger.warning(
            f"Transición inválida: {current_stage} → {target_stage}"
        )
        return False

    stage_id = get_ghl_stage_id(target_stage)
    if not stage_id:
        logger.warning(f"Stage ID no configurado para {target_stage}")
        return False

    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{GHL_BASE}/pipelines/opportunities/{opportunity_id}",
            headers=HEADERS,
            json={"stageId": stage_id},
        )
        if resp.status_code in (200, 201):
            label = STAGE_LABELS[target_stage]
            logger.info(f"Pipeline avanzado → {label} (opp: {opportunity_id})")
            await add_note(contact_id, f"Etapa actualizada: {label}")
            return True
        logger.error(f"Error al actualizar stage GHL: {resp.text}")
        return False


# ── Búsqueda interna ──────────────────────────────────────────────────────────

async def _find_contact(phone: str, data: dict) -> Optional[str]:
    async with httpx.AsyncClient() as client:
        for query in filter(None, [phone, data.get("email")]):
            resp = await client.get(
                f"{GHL_BASE}/contacts/",
                headers=HEADERS,
                params={"locationId": GHL_LOCATION_ID, "query": query},
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


def _build_contact_props(phone: str, data: dict, channel: str) -> dict:
    nombre = data.get("nombre", "")
    parts = nombre.split(" ", 1) if nombre else []

    props: dict = {
        "locationId": GHL_LOCATION_ID,
        "source": f"IA - {channel.capitalize()}",
        "tags": [channel, "ia-agente"],
        "customField": [
            {"key": "desarrollo_interes", "value": data.get("interes", "")},
            {"key": "tipo_compra",        "value": data.get("tipo_compra", "")},
            {"key": "canal_entrada",      "value": channel},
            {"key": "presupuesto",        "value": data.get("presupuesto", "")},
        ],
    }

    if phone:
        props["phone"] = phone
    if parts:
        props["firstName"] = parts[0]
        if len(parts) > 1:
            props["lastName"] = parts[1]
    if data.get("email"):
        props["email"] = data["email"]

    # Limpiar campos vacíos en customField
    props["customField"] = [f for f in props["customField"] if f["value"]]
    if not props["customField"]:
        del props["customField"]

    return {k: v for k, v in props.items() if v}
