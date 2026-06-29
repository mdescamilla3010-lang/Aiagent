import logging
from datetime import datetime, timedelta
from typing import Optional
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import GOOGLE_CREDENTIALS_FILE, GOOGLE_CALENDAR_ID, DEVELOPMENTS

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service():
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds)


async def schedule_appointment(
    fecha: str,
    hora: str,
    desarrollo: str,
    lead_name: str,
    lead_phone: str,
    notas: str = "",
) -> Optional[dict]:
    """Crea un evento en Google Calendar y retorna los datos del evento."""
    try:
        service = _get_service()
        dev_info = DEVELOPMENTS.get(desarrollo, {})
        dev_name = dev_info.get("nombre", desarrollo)

        start_dt = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(hours=1)

        event = {
            "summary": f"Visita {dev_name} - {lead_name}",
            "description": (
                f"Lead: {lead_name}\n"
                f"Teléfono: {lead_phone}\n"
                f"Desarrollo: {dev_name}\n"
                f"Notas: {notas}"
            ),
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Mexico_City"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Mexico_City"},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 1440},   # 24h antes
                    {"method": "popup", "minutes": 60},      # 1h antes
                ],
            },
        }

        created = service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
        logger.info(f"Evento creado: {created.get('id')}")

        return {
            "event_id": created.get("id"),
            "fecha": fecha,
            "hora": hora,
            "desarrollo": dev_name,
            "lead_name": lead_name,
        }

    except Exception as e:
        logger.error(f"Error al crear evento en Google Calendar: {e}")
        return None


async def get_available_slots(fecha: str, desarrollo: str) -> list[str]:
    """Retorna horarios disponibles para una fecha dada."""
    from config import BUSINESS_HOURS
    try:
        service = _get_service()
        day = datetime.strptime(fecha, "%Y-%m-%d")

        time_min = day.replace(hour=BUSINESS_HOURS["start"], minute=0).isoformat() + "Z"
        time_max = day.replace(hour=BUSINESS_HOURS["end"], minute=0).isoformat() + "Z"

        events_result = (
            service.events()
            .list(
                calendarId=GOOGLE_CALENDAR_ID,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        busy_slots = set()
        for event in events_result.get("items", []):
            start = event["start"].get("dateTime", "")
            if start:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                busy_slots.add(dt.strftime("%H:%M"))

        all_slots = [
            f"{h:02d}:00" for h in range(BUSINESS_HOURS["start"], BUSINESS_HOURS["end"])
        ]
        return [s for s in all_slots if s not in busy_slots]

    except Exception as e:
        logger.error(f"Error al consultar disponibilidad: {e}")
        return ["10:00", "11:00", "12:00", "16:00", "17:00"]
