import logging
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse

from config import WHATSAPP_VERIFY_TOKEN, PORT
from agent import process_message
from crm import upsert_contact, log_note, update_deal_stage
from calendar_service import schedule_appointment
from reminders import start_nurture_sequence, schedule_appointment_reminders, cancel_reminders
from whatsapp import parse_incoming, send_text
from prompts import APPOINTMENT_CONFIRMATION_TEMPLATE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Real Estate AI Agent")

# Estado del lead en memoria (producción: Redis/DB)
_lead_state: dict[str, dict] = {}


@app.get("/webhook")
async def verify_webhook(request: Request):
    """Verificación del webhook de Meta."""
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN
    ):
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="Token inválido")


@app.post("/webhook")
async def receive_message(request: Request):
    """Recibe y procesa mensajes entrantes de WhatsApp."""
    payload = await request.json()
    incoming = parse_incoming(payload)

    if not incoming or not incoming["text"]:
        return {"status": "ok"}

    phone = incoming["phone"]
    user_text = incoming["text"]
    contact_name = incoming["name"]

    logger.info(f"Mensaje de {phone} ({contact_name}): {user_text[:80]}")

    # Inicializar estado del lead
    state = _lead_state.setdefault(phone, {"nombre": contact_name, "contact_id": None})

    # Procesar con el agente IA
    reply_text, action = await process_message(phone, user_text)

    # Ejecutar acción si el agente la determinó
    if action:
        await _handle_action(phone, action, state)

    # Iniciar secuencia de nurturing si es el primer mensaje y no hay cita
    if state.get("is_new_lead") is None:
        state["is_new_lead"] = True
        await start_nurture_sequence(phone, state["nombre"], state.get("desarrollo", ""))

    await send_text(phone, reply_text)
    return {"status": "ok"}


async def _handle_action(phone: str, action: dict, state: dict) -> None:
    action_type = action.get("action")
    data = action.get("data", {})

    if action_type == "update_lead":
        # Actualizar nombre si vino del agente
        if data.get("nombre"):
            state["nombre"] = data["nombre"]
        if data.get("interes"):
            state["desarrollo"] = data["interes"]

        # Guardar/actualizar en HubSpot
        contact_id = await upsert_contact(phone, data)
        if contact_id:
            state["contact_id"] = contact_id
            await update_deal_stage(contact_id, "appointmentscheduled", data.get("interes", ""))

        logger.info(f"Lead actualizado en CRM para {phone}")

    elif action_type == "schedule_appointment":
        fecha = data.get("fecha")
        hora = data.get("hora")
        desarrollo = data.get("desarrollo", "desarrollo_a")

        event = await schedule_appointment(
            fecha=fecha,
            hora=hora,
            desarrollo=desarrollo,
            lead_name=state.get("nombre", "Prospecto"),
            lead_phone=phone,
            notas=data.get("notas", ""),
        )

        if event:
            # Cancelar secuencia de nurturing y activar recordatorios de cita
            cancel_reminders(phone)
            appointment_dt = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
            await schedule_appointment_reminders(
                phone=phone,
                lead_name=state.get("nombre", "Prospecto"),
                desarrollo=event["desarrollo"],
                appointment_dt=appointment_dt,
            )

            # Registrar en CRM
            if state.get("contact_id"):
                await log_note(
                    state["contact_id"],
                    f"Cita agendada: {fecha} {hora} - {event['desarrollo']}",
                )
                await update_deal_stage(state["contact_id"], "closedwon", desarrollo)

            state["appointment"] = event
            logger.info(f"Cita agendada para {phone}: {fecha} {hora}")

            # Enviar confirmación
            from config import DEVELOPMENTS
            dev_name = DEVELOPMENTS.get(desarrollo, {}).get("nombre", desarrollo)
            confirmation = APPOINTMENT_CONFIRMATION_TEMPLATE.format(
                fecha=fecha, hora=hora, desarrollo=dev_name
            )
            await send_text(phone, confirmation)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "real-estate-ai-agent"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
