import logging
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse

from config import META_VERIFY_TOKEN, PORT, DEVELOPMENTS
from agent import process_message
from crm import upsert_contact, add_note, create_opportunity, add_tag
from calendar_service import schedule_appointment
from reminders import start_nurture_sequence, schedule_appointment_reminders, cancel_reminders
from channels import parse_webhook, send_message, get_sender_name
from prompts import APPOINTMENT_CONFIRMATION_TEMPLATE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Real Estate AI Agent")

# Estado por sesión: sender_id -> dict
# En producción: Redis o base de datos
_lead_state: dict[str, dict] = {}


# ── Webhook Meta (WhatsApp + Facebook + Instagram comparten endpoint) ─────────

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Verificación del webhook de Meta (funciona para los 3 canales)."""
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == META_VERIFY_TOKEN
    ):
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="Token inválido")


@app.post("/webhook")
async def receive_message(request: Request):
    """
    Recibe mensajes de WhatsApp, Facebook Messenger e Instagram DM.
    Meta envía todos al mismo webhook; el campo 'object' diferencia el canal.
    """
    payload = await request.json()
    incoming = parse_webhook(payload)

    if not incoming or not incoming.text:
        return {"status": "ok"}

    channel = incoming.channel
    sender_id = incoming.sender_id

    logger.info(f"[{channel.upper()}] {sender_id}: {incoming.text[:80]}")

    # Enriquecer nombre si es Facebook/Instagram (llamada a Graph API)
    if not incoming.name and channel in ("facebook", "instagram"):
        incoming.name = await get_sender_name(channel, sender_id)

    state = _lead_state.setdefault(
        sender_id,
        {
            "channel": channel,
            "nombre": incoming.name,
            "phone": incoming.phone,
            "contact_id": None,
            "opportunity_id": None,
            "is_new": True,
        },
    )

    # Procesar con el agente IA
    reply_text, action = await process_message(sender_id, incoming.text)

    # Ejecutar acción si el agente la determinó
    if action:
        await _handle_action(sender_id, action, state)

    # Iniciar secuencia de nurturing en el primer mensaje
    if state.pop("is_new", False):
        await start_nurture_sequence(
            channel=channel,
            sender_id=sender_id,
            phone=state["phone"],
            lead_name=state["nombre"],
            desarrollo=state.get("desarrollo", ""),
        )

    await send_message(incoming, reply_text)
    return {"status": "ok"}


async def _handle_action(sender_id: str, action: dict, state: dict) -> None:
    action_type = action.get("action")
    data = action.get("data", {})
    channel = state["channel"]
    phone = state["phone"]

    if action_type == "update_lead":
        if data.get("nombre"):
            state["nombre"] = data["nombre"]
        if data.get("interes"):
            state["desarrollo"] = data["interes"]

        contact_id = await upsert_contact(phone or sender_id, data, channel)

        if contact_id:
            state["contact_id"] = contact_id
            await add_tag(contact_id, f"canal-{channel}")

            if not state.get("opportunity_id"):
                opp_id = await create_opportunity(contact_id, data.get("interes", ""))
                state["opportunity_id"] = opp_id

        logger.info(f"Lead actualizado en GHL para {sender_id} ({channel})")

    elif action_type == "schedule_appointment":
        fecha = data.get("fecha")
        hora = data.get("hora")
        desarrollo = data.get("desarrollo", "desarrollo_a")

        event = await schedule_appointment(
            fecha=fecha,
            hora=hora,
            desarrollo=desarrollo,
            lead_name=state.get("nombre", "Prospecto"),
            lead_phone=phone or sender_id,
            notas=data.get("notas", f"Canal: {channel}"),
        )

        if event:
            cancel_reminders(sender_id)
            appointment_dt = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")

            await schedule_appointment_reminders(
                channel=channel,
                sender_id=sender_id,
                phone=phone,
                lead_name=state.get("nombre", "Prospecto"),
                desarrollo=event["desarrollo"],
                appointment_dt=appointment_dt,
            )

            if state.get("contact_id"):
                await add_note(
                    state["contact_id"],
                    f"Cita agendada via {channel}: {fecha} {hora} — {event['desarrollo']}",
                )
                await add_tag(state["contact_id"], "cita-agendada")

            state["appointment"] = event
            logger.info(f"Cita agendada para {sender_id}: {fecha} {hora}")

            dev_name = DEVELOPMENTS.get(desarrollo, {}).get("nombre", desarrollo)
            confirmation = APPOINTMENT_CONFIRMATION_TEMPLATE.format(
                fecha=fecha, hora=hora, desarrollo=dev_name
            )
            # Importamos la clase para el envío de confirmación
            from channels import IncomingMessage, send_message as _send
            dummy = IncomingMessage(
                channel=channel,
                sender_id=sender_id,
                phone=phone,
                name=state.get("nombre", ""),
                text="",
                message_id="",
            )
            await _send(dummy, confirmation)


@app.get("/health")
async def health():
    return {"status": "ok", "channels": ["whatsapp", "facebook", "instagram"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
