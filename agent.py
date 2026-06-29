import json
import re
import logging
from anthropic import AsyncAnthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from prompts import build_system_prompt

logger = logging.getLogger(__name__)

client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# Historial en memoria: phone -> list of messages
# En producción reemplazar con Redis o base de datos
_conversation_history: dict[str, list] = {}

MAX_HISTORY = 20  # mensajes a conservar por conversación


async def process_message(phone: str, user_message: str) -> tuple[str, dict | None]:
    """
    Procesa un mensaje entrante y retorna (respuesta_texto, accion_dict | None).
    La acción puede ser 'update_lead' o 'schedule_appointment'.
    """
    history = _conversation_history.setdefault(phone, [])

    history.append({"role": "user", "content": user_message})

    # Limitar historial para no exceder tokens
    if len(history) > MAX_HISTORY:
        history[:] = history[-MAX_HISTORY:]

    response = await client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=build_system_prompt(),
        messages=history,
    )

    assistant_text = response.content[0].text
    history.append({"role": "assistant", "content": assistant_text})

    # Extraer acción JSON si está presente
    action = _extract_action(assistant_text)
    clean_text = _strip_json_block(assistant_text)

    return clean_text, action


def _extract_action(text: str) -> dict | None:
    """Busca y parsea el bloque JSON de acción al final del texto."""
    pattern = r"```json\s*(\{.*?\})\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.warning("JSON de acción malformado en respuesta del agente")
    return None


def _strip_json_block(text: str) -> str:
    """Elimina el bloque JSON de la respuesta antes de enviarla al usuario."""
    return re.sub(r"```json\s*\{.*?\}\s*```", "", text, flags=re.DOTALL).strip()


def clear_history(phone: str) -> None:
    _conversation_history.pop(phone, None)


def get_history_length(phone: str) -> int:
    return len(_conversation_history.get(phone, []))
