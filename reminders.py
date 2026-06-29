import asyncio
import logging
from datetime import datetime, timedelta
from prompts import REMINDER_TEMPLATES
from whatsapp import send_text

logger = logging.getLogger(__name__)

# Tareas activas: phone -> asyncio.Task
_active_reminders: dict[str, list[asyncio.Task]] = {}


async def start_nurture_sequence(phone: str, lead_name: str, desarrollo: str) -> None:
    """Inicia secuencia de nurturing para un lead sin cita agendada."""
    cancel_reminders(phone)

    delays_hours = [1, 24 * 3, 24 * 7]
    templates = ["sin_respuesta_3d", "sin_respuesta_3d", "sin_respuesta_7d"]

    tasks = []
    for hours, template_key in zip(delays_hours, templates):
        task = asyncio.create_task(
            _send_delayed_reminder(
                phone=phone,
                delay_seconds=hours * 3600,
                template_key=template_key,
                context={"nombre": lead_name, "desarrollo": desarrollo},
            )
        )
        tasks.append(task)

    _active_reminders[phone] = tasks
    logger.info(f"Secuencia nurturing iniciada para {phone}")


async def schedule_appointment_reminders(
    phone: str,
    lead_name: str,
    desarrollo: str,
    appointment_dt: datetime,
) -> None:
    """Programa recordatorios específicos para una cita agendada."""
    cancel_reminders(phone)

    hora_str = appointment_dt.strftime("%H:%M")
    now = datetime.now()
    tasks = []

    reminder_configs = [
        ("24h", appointment_dt - timedelta(hours=24)),
        ("pre_cita", appointment_dt - timedelta(hours=2)),
    ]

    for template_key, send_time in reminder_configs:
        delay = (send_time - now).total_seconds()
        if delay <= 0:
            continue

        task = asyncio.create_task(
            _send_delayed_reminder(
                phone=phone,
                delay_seconds=delay,
                template_key=template_key,
                context={"nombre": lead_name, "desarrollo": desarrollo, "hora": hora_str},
            )
        )
        tasks.append(task)

    _active_reminders[phone] = tasks
    logger.info(f"Recordatorios de cita programados para {phone}: {len(tasks)} recordatorio(s)")


def cancel_reminders(phone: str) -> None:
    """Cancela todos los recordatorios pendientes de un lead."""
    for task in _active_reminders.pop(phone, []):
        if not task.done():
            task.cancel()


async def _send_delayed_reminder(
    phone: str,
    delay_seconds: float,
    template_key: str,
    context: dict,
) -> None:
    try:
        await asyncio.sleep(delay_seconds)

        template = REMINDER_TEMPLATES.get(template_key, "")
        message = template.format(**context)

        success = await send_text(phone, message)
        if success:
            logger.info(f"Recordatorio '{template_key}' enviado a {phone}")
        else:
            logger.error(f"Fallo al enviar recordatorio '{template_key}' a {phone}")
    except asyncio.CancelledError:
        logger.info(f"Recordatorio '{template_key}' cancelado para {phone}")
    except Exception as e:
        logger.error(f"Error en recordatorio para {phone}: {e}")
