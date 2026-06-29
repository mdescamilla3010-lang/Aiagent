"""
Define las etapas del pipeline inmobiliario en GHL y las transiciones válidas.

Las etapas se configuran en GHL como un Pipeline personalizado.
Los IDs reales se obtienen de: GET /pipelines en la API de GHL
y se setean en el .env.
"""
from enum import Enum
from config import GHL_PIPELINE_STAGES


class Stage(str, Enum):
    NUEVO_LEAD       = "nuevo_lead"        # Llega el lead (cualquier canal)
    CONTACTADO       = "contactado"        # Agente IA inició conversación
    CALIFICADO       = "calificado"        # Se capturó nombre, interés, presupuesto
    CITA_PROPUESTA   = "cita_propuesta"    # Agente propuso fecha/hora
    CITA_CONFIRMADA  = "cita_confirmada"   # Lead confirmó la cita
    VISITA_REALIZADA = "visita_realizada"  # Asesor marcó como visitado (manual)
    NEGOCIACION      = "negociacion"       # En proceso de cierre
    CERRADO_GANADO   = "cerrado_ganado"    # Venta concretada
    CERRADO_PERDIDO  = "cerrado_perdido"   # No cerró


# Transiciones válidas (de → posibles destinos)
TRANSITIONS: dict[Stage, list[Stage]] = {
    Stage.NUEVO_LEAD:       [Stage.CONTACTADO, Stage.CERRADO_PERDIDO],
    Stage.CONTACTADO:       [Stage.CALIFICADO, Stage.CERRADO_PERDIDO],
    Stage.CALIFICADO:       [Stage.CITA_PROPUESTA, Stage.CERRADO_PERDIDO],
    Stage.CITA_PROPUESTA:   [Stage.CITA_CONFIRMADA, Stage.CALIFICADO, Stage.CERRADO_PERDIDO],
    Stage.CITA_CONFIRMADA:  [Stage.VISITA_REALIZADA, Stage.CITA_PROPUESTA, Stage.CERRADO_PERDIDO],
    Stage.VISITA_REALIZADA: [Stage.NEGOCIACION, Stage.CERRADO_PERDIDO],
    Stage.NEGOCIACION:      [Stage.CERRADO_GANADO, Stage.CERRADO_PERDIDO],
    Stage.CERRADO_GANADO:   [],
    Stage.CERRADO_PERDIDO:  [Stage.CONTACTADO],  # Reactivación
}

# Etiquetas legibles para notas y logs
STAGE_LABELS: dict[Stage, str] = {
    Stage.NUEVO_LEAD:       "🆕 Nuevo Lead",
    Stage.CONTACTADO:       "📲 Contactado",
    Stage.CALIFICADO:       "✅ Calificado",
    Stage.CITA_PROPUESTA:   "📅 Cita Propuesta",
    Stage.CITA_CONFIRMADA:  "🗓️ Cita Confirmada",
    Stage.VISITA_REALIZADA: "🏠 Visita Realizada",
    Stage.NEGOCIACION:      "🤝 En Negociación",
    Stage.CERRADO_GANADO:   "🎉 Cerrado Ganado",
    Stage.CERRADO_PERDIDO:  "❌ Cerrado Perdido",
}

# Mapeo Stage → GHL Stage ID (configurado en .env)
def get_ghl_stage_id(stage: Stage) -> str:
    return GHL_PIPELINE_STAGES.get(stage.value, "")


def can_transition(current: Stage, target: Stage) -> bool:
    return target in TRANSITIONS.get(current, [])
