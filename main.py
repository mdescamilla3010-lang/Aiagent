import logging
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse

from config import META_VERIFY_TOKEN, PORT, DEVELOPMENTS
from pipeline import Stage
from agent import process_message
from crm import upsert_contact, add_note, add_tag, create_opportunity, advance_stage
from calendar_service import schedule_appointment
from reminders import start_nurture_sequence, schedule_appointment_reminders, cancel_reminders
from channels import parse_webhook, send_message, get_sender_name, IncomingMessage
from leadgen import is_leadgen_event, extract_leadgen_data, build_welcome_message
from prompts import APPOINTMENT_CONFIRMATION_TEMPLATE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Real Estate AI Agent")

# Estado de sesión por lead: sender_id → dict
# Producción: reemplazar con Redis
_lead_state: dict[str, dict] = {}


# ── Webhook Meta ───────────────────────────────────────────────────────────────

@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == META_VERIFY_TOKEN
    ):
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="Token inválido")


@app.post("/webhook")
async def receive_event(request: Request):
    """
    Punto de entrada único para todos los eventos de Meta:
    - Mensajes: WhatsApp, Facebook Messenger, Instagram DM
    - Leads: Facebook Lead Ads (Leadgen)
    """
    payload = await request.json()

    # ── Lead Ads ────────────────────────────────────────────────────────────
    if is_leadgen_event(payload):
        lead = await extract_leadgen_data(payload)
        if lead:
            await _handle_new_leadgen(lead)
        return {"status": "ok"}

    # ── Mensajes conversacionales ────────────────────────────────────────────
    incoming = parse_webhook(payload)
    if not incoming or not incoming.text:
        return {"status": "ok"}

    await _handle_conversation(incoming)
    return {"status": "ok"}


# ── Leadgen: contacto proactivo ───────────────────────────────────────────────

async def _handle_new_leadgen(lead) -> None:
    """Procesa un lead nuevo de Facebook Lead Ads."""
    logger.info(f"[LEADGEN] {lead.full_name} | {lead.phone_normalized} | {lead.email}")

    # 1. Crear contacto en GHL en etapa NUEVO_LEAD
    lead_data = {
        "nombre":     lead.full_name,
        "email":      lead.email,
        "interes":    lead.interes,
        "presupuesto": lead.presupuesto,
        "tipo_compra": lead.tipo_compra,
    }
    contact_id = await upsert_contact(lead.phone_normalized, lead_data, channel="facebook-leadgen")

    if contact_id:
        opp_id = await create_opportunity(contact_id, lead.interes, Stage.NUEVO_LEAD, source="Facebook Lead Ad")
        await add_tag(contact_id, "lead-ad", "facebook")
        await add_note(contact_id, f"Lead Ad ID: {lead.lead_id} | Form ID: {lead.form_id} | Ad ID: {lead.ad_id}")

        # Inicializar estado de sesión para cuando responda por WhatsApp
        sender_key = lead.phone_normalized or lead.lead_id
        _lead_state[sender_key] = {
            "channel":        "whatsapp",
            "nombre":         lead.full_name,
            "phone":          lead.phone_normalized,
            "contact_id":     contact_id,
            "opportunity_id": opp_id,
            "stage":          Stage.NUEVO_LEAD,
            "desarrollo":     lead.interes,
            "is_new":         False,
        }

        # 2. Avanzar a CONTACTADO y enviar mensaje de bienvenida por WhatsApp
        if lead.phone_normalized:
            await advance_stage(opp_id, contact_id, Stage.NUEVO_LEAD, Stage.CONTACTADO)
            _lead_state[sender_key]["stage"] = Stage.CONTACTADO

            welcome = await build_welcome_message(lead)
            dummy = IncomingMessage(
                channel="whatsapp",
                sender_id=lead.phone_normalized,
                phone=lead.phone_normalized,
                name=lead.full_name,
                text="",
                message_id="",
            )
            await send_message(dummy, welcome)

            # Iniciar secuencia de nurturing
            await start_nurture_sequence(
                channel="whatsapp",
                sender_id=lead.phone_normalized,
                phone=lead.phone_normalized,
                lead_name=lead.full_name,
                desarrollo=lead.interes,
            )
        else:
            # Sin teléfono: marcar para seguimiento manual
            await add_tag(contact_id, "sin-telefono", "seguimiento-manual")
            await add_note(contact_id, "Lead sin teléfono — contactar por email o Facebook DM")
            logger.warning(f"Lead sin teléfono: {lead.lead_id} — {lead.email}")


# ── Conversación ──────────────────────────────────────────────────────────────

async def _handle_conversation(incoming: IncomingMessage) -> None:
    channel = incoming.channel
    sender_id = incoming.sender_id

    logger.info(f"[{channel.upper()}] {sender_id}: {incoming.text[:80]}")

    # Enriquecer nombre en Facebook/Instagram
    if not incoming.name and channel in ("facebook", "instagram"):
        incoming.name = await get_sender_name(channel, sender_id)

    state = _lead_state.setdefault(
        sender_id,
        {
            "channel":        channel,
            "nombre":         incoming.name,
            "phone":          incoming.phone,
            "contact_id":     None,
            "opportunity_id": None,
            "stage":          Stage.NUEVO_LEAD,
            "is_new":         True,
        },
    )

    # Procesar con el agente IA
    reply_text, action = await process_message(sender_id, incoming.text)

    # Ejecutar acción si el agente la incluyó
    if action:
        await _handle_agent_action(sender_id, action, state)

    # Primer mensaje: crear registro en GHL y arrancar nurturing
    if state.pop("is_new", False):
        contact_id = await upsert_contact(
            state["phone"] or sender_id,
            {"nombre": state["nombre"]},
            channel,
        )
        if contact_id:
            state["contact_id"] = contact_id
            opp_id = await create_opportunity(contact_id, "", Stage.NUEVO_LEAD, source=f"IA - {channel}")
            state["opportunity_id"] = opp_id
            await advance_stage(opp_id, contact_id, Stage.NUEVO_LEAD, Stage.CONTACTADO)
            state["stage"] = Stage.CONTACTADO
            await add_tag(contact_id, channel)

        await start_nurture_sequence(
            channel=channel,
            sender_id=sender_id,
            phone=state["phone"],
            lead_name=state["nombre"],
            desarrollo=state.get("desarrollo", ""),
        )

    await send_message(incoming, reply_text)


async def _handle_agent_action(sender_id: str, action: dict, state: dict) -> None:
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
                opp_id = await create_opportunity(contact_id, data.get("interes", ""), Stage.CONTACTADO, source=f"IA - {channel}")
                state["opportunity_id"] = opp_id
                state["stage"] = Stage.CONTACTADO

        # Avanzar a CALIFICADO si ya tenemos suficientes datos
        required = ["nombre", "interes"]
        if all(data.get(f) for f in required) and state.get("opportunity_id"):
            moved = await advance_stage(
                state["opportunity_id"], state["contact_id"],
                state["stage"], Stage.CALIFICADO,
            )
            if moved:
                state["stage"] = Stage.CALIFICADO

    elif action_type == "schedule_appointment":
        fecha = data.get("fecha")
        hora = data.get("hora")
        desarrollo = data.get("desarrollo", state.get("desarrollo", "desarrollo_a"))

        # Avanzar a CITA_PROPUESTA mientras se confirma
        if state.get("opportunity_id") and state.get("contact_id"):
            await advance_stage(
                state["opportunity_id"], state["contact_id"],
                state["stage"], Stage.CITA_PROPUESTA,
            )
            state["stage"] = Stage.CITA_PROPUESTA

        event = await schedule_appointment(
            fecha=fecha,
            hora=hora,
            desarrollo=desarrollo,
            lead_name=state.get("nombre", "Prospecto"),
            lead_phone=phone or sender_id,
            notas=data.get("notas", f"Canal: {channel}"),
        )

        if event:
            # Cancelar nurturing y activar recordatorios de cita
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

            # Avanzar a CITA_CONFIRMADA
            if state.get("opportunity_id") and state.get("contact_id"):
                await advance_stage(
                    state["opportunity_id"], state["contact_id"],
                    state["stage"], Stage.CITA_CONFIRMADA,
                )
                state["stage"] = Stage.CITA_CONFIRMADA
                await add_tag(state["contact_id"], "cita-confirmada")
                await add_note(
                    state["contact_id"],
                    f"Cita agendada ({channel}): {fecha} {hora} — {event['desarrollo']}",
                )

            state["appointment"] = event
            logger.info(f"Cita confirmada para {sender_id}: {fecha} {hora}")

            dev_name = DEVELOPMENTS.get(desarrollo, {}).get("nombre", desarrollo)
            dummy = IncomingMessage(
                channel=channel, sender_id=sender_id,
                phone=phone, name=state.get("nombre", ""),
                text="", message_id="",
            )
            await send_message(
                dummy,
                APPOINTMENT_CONFIRMATION_TEMPLATE.format(fecha=fecha, hora=hora, desarrollo=dev_name),
            )


@app.get("/health")
async def health():
    return {"status": "ok", "channels": ["whatsapp", "facebook", "instagram", "leadgen"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
