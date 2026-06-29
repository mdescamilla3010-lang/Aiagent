import asyncio
import logging
from datetime import datetime, timedelta
from prompts import REMINDER_TEMPLATES

logger = logging.getLogger(__name__)

# Tareas activas: sender_id -> list[asyncio.Task]
_active_reminders: dict[str, list[asyncio.Task]] = {}


async def start_nurture_sequence(
    channel: str, sender_id: str, phone: str, lead_name: str, desarrollo: str
) -> None:
    """Inicia secuencia de nurturing para un lead sin cita agendada."""
    cancel_reminders(sender_id)

    configs = [
        (3 * 3600,    "sin_respuesta_3d"),
        (7 * 24 * 3600, "sin_respuesta_7d"),
    ]

    tasks = [
        asyncio.create_task(
            _send_delayed(
                channel=channel,
                sender_id=sender_id,
                phone=phone,
                delay_seconds=delay,
                template_key=key,
                context={"nombre": lead_name or "amigo/a", "desarrollo": desarrollo},
            )
        )
        for delay, key in configs
    ]

    _active_reminders[sender_id] = tasks
    logger.info(f"Secuencia nurturing iniciada para {sender_id} ({channel})")


async def schedule_appointment_reminders(
    channel: str,
    sender_id: str,
    phone: str,
    lead_name: str,
    desarrollo: str,
    appointment_dt: datetime,
) -> None:
    """Programa recordatorios para una cita confirmada."""
    cancel_reminders(sender_id)

    hora_str = appointment_dt.strftime("%H:%M")
    now = datetime.now()

    configs = [
        ("24h",      appointment_dt - timedelta(hours=24)),
        ("pre_cita", appointment_dt - timedelta(hours=2)),
    ]

    tasks = []
    for key, send_time in configs:
        delay = (send_time - now).total_seconds()
        if delay <= 0:
            continue
        tasks.append(
            asyncio.create_task(
                _send_delayed(
                    channel=channel,
                    sender_id=sender_id,
                    phone=phone,
                    delay_seconds=delay,
                    template_key=key,
                    context={
                        "nombre": lead_name or "amigo/a",
                        "desarrollo": desarrollo,
                        "hora": hora_str,
                    },
                )
            )
        )

    _active_reminders[sender_id] = tasks
    logger.info(f"Recordatorios de cita programados para {sender_id}: {len(tasks)}")


def cancel_reminders(sender_id: str) -> None:
    for task in _active_reminders.pop(sender_id, []):
        if not task.done():
            task.cancel()


async def _send_delayed(
    channel: str,
    sender_id: str,
    phone: str,
    delay_seconds: float,
    template_key: str,
    context: dict,
) -> None:
    from channels import send_message, IncomingMessage

    try:
        await asyncio.sleep(delay_seconds)

        text = REMINDER_TEMPLATES.get(template_key, "").format(**context)

        # Construimos un IncomingMessage mínimo para reutilizar el router de canales
        dummy = IncomingMessage(
            channel=channel,
            sender_id=sender_id,
            phone=phone,
            name=context.get("nombre", ""),
            text="",
            message_id="",
        )
        success = await send_message(dummy, text)

        if success:
            logger.info(f"Recordatorio '{template_key}' enviado a {sender_id} ({channel})")
        else:
            logger.error(f"Fallo recordatorio '{template_key}' a {sender_id}")

    except asyncio.CancelledError:
        logger.info(f"Recordatorio '{template_key}' cancelado para {sender_id}")
    except Exception as e:
        logger.error(f"Error en recordatorio para {sender_id}: {e}")
