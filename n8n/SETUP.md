# Setup — Agente IA Inmobiliario en n8n + GHL

## Qué necesito de ti (checklist)

### 1. Anthropic (Claude IA)
- [ ] **API Key** — console.anthropic.com → API Keys → Create Key
  - Formato: `sk-ant-api03-...`

### 2. Meta for Developers (WhatsApp + Facebook + Instagram)
- [ ] **Meta Token** — graph.facebook.com → App → Access Tokens (token permanente de página)
- [ ] **WhatsApp Phone Number ID** — Meta for Developers → WhatsApp → API Setup
- [ ] **Facebook Page ID** — Configuración de la Página → Acerca de (número de 15 dígitos)
- [ ] **Instagram Account ID** — Meta for Developers → Instagram → Configuración
- [ ] Confirmar que la App tiene permisos: `whatsapp_business_messaging`, `pages_messaging`, `instagram_manage_messages`, `leads_retrieval`

### 3. Go High Level
- [ ] **API Key** — GHL → Settings → API Keys → Create
- [ ] **Location ID** — GHL → Settings → Business Profile → Location ID
- [ ] **Pipeline ID** — Crear pipeline "Inmobiliario" con las 9 etapas (ver abajo) y enviarme el ID
- [ ] **Stage IDs** — Necesito el ID de cada etapa del pipeline (se obtiene al crearlo)

#### Etapas del pipeline a crear en GHL:
| Orden | Nombre exacto |
|-------|--------------|
| 1 | Nuevo Lead |
| 2 | Contactado |
| 3 | Calificado |
| 4 | Cita Propuesta |
| 5 | Cita Confirmada |
| 6 | Visita Realizada |
| 7 | En Negociación |
| 8 | Cerrado Ganado |
| 9 | Cerrado Perdido |

#### Custom Fields a crear en GHL (Contacts → Custom Fields):
| Campo (key) | Tipo | Descripción |
|-------------|------|-------------|
| `desarrollo_interes` | Text | desarrollo_a / desarrollo_b / ambos |
| `canal_entrada` | Text | whatsapp / facebook / instagram |
| `tipo_compra` | Text | inversion / vivienda |
| `presupuesto` | Text | Rango de presupuesto |
| `pipeline_stage` | Text | Etapa actual (auto-actualizado) |
| `chat_history` | Textarea | Historial de conversación JSON |
| `cita_fecha` | DateTime | Fecha y hora de la cita |
| `recordatorios_enviados` | Number | Contador de recordatorios |
| `ultimo_recordatorio` | DateTime | Fecha del último recordatorio |
| `opportunity_id` | Text | ID de la oportunidad en GHL |
| `facebook_sender_id` | Text | ID de sender de FB/IG |

### 4. Google Calendar
- [ ] Ir a console.cloud.google.com
- [ ] Crear proyecto → Habilitar "Google Calendar API"
- [ ] Crear cuenta de servicio (Service Account) → Descargar JSON de credenciales
- [ ] Compartir el calendario con el email de la cuenta de servicio (con permisos de edición)
- [ ] Enviarme el archivo JSON de credenciales

### 5. Datos de los desarrollos
Necesito que me llenes esto para cada desarrollo:

**Desarrollo A:**
- Nombre: ___________
- Tipo (casas/departamentos/lotes): ___________
- Ubicación: ___________
- Precio desde: ___________
- Amenidades (lista): ___________
- Disponibilidad: ___________

**Desarrollo B:**
- Nombre: ___________
- Tipo: ___________
- Ubicación: ___________
- Precio desde: ___________
- Amenidades: ___________
- Disponibilidad: ___________

### 6. n8n
- [ ] ¿Ya tienes n8n instalado? Opciones:
  - **n8n Cloud** (más fácil): app.n8n.cloud — plan Starter $20 USD/mes
  - **Self-hosted** (gratis): necesitas un servidor/VPS con Docker

---

## Cómo importar los workflows en n8n

1. Abrir n8n → Workflows → **Import from file**
2. Importar en este orden:
   - `workflow_1_leadgen.json`
   - `workflow_2_conversacion.json`
   - `workflow_3_recordatorios.json`
3. En cada workflow → Configurar las **Variables** (n8n → Settings → Variables):

| Variable n8n | Valor |
|---|---|
| `META_TOKEN` | Token de Meta |
| `WHATSAPP_PHONE_NUMBER_ID` | ID del número WA |
| `ANTHROPIC_API_KEY` | API Key de Anthropic |
| `GHL_API_KEY` | API Key de GHL |
| `GHL_LOCATION_ID` | Location ID de GHL |
| `GHL_PIPELINE_ID` | Pipeline ID |
| `GHL_STAGE_NUEVO_LEAD` | Stage ID |
| `GHL_STAGE_CONTACTADO` | Stage ID |
| `GHL_STAGE_CALIFICADO` | Stage ID |
| `GHL_STAGE_CITA_PROPUESTA` | Stage ID |
| `GHL_STAGE_CITA_CONFIRMADA` | Stage ID |
| `GHL_STAGE_VISITA_REALIZADA` | Stage ID |
| `GHL_STAGE_NEGOCIACION` | Stage ID |
| `GHL_STAGE_CERRADO_GANADO` | Stage ID |
| `GHL_STAGE_CERRADO_PERDIDO` | Stage ID |
| `DESARROLLO_A_NOMBRE` | Nombre del desarrollo A |
| `DESARROLLO_A_TIPO` | Tipo (casas/deptos) |
| `DESARROLLO_A_UBICACION` | Ubicación |
| `DESARROLLO_A_PRECIO` | Precio desde |
| `DESARROLLO_A_AMENIDADES` | Amenidades |
| `DESARROLLO_A_DISPONIBILIDAD` | Disponibilidad |
| `DESARROLLO_B_NOMBRE` | (igual para B) |
| `DESARROLLO_B_TIPO` | |
| `DESARROLLO_B_UBICACION` | |
| `DESARROLLO_B_PRECIO` | |
| `DESARROLLO_B_AMENIDADES` | |
| `DESARROLLO_B_DISPONIBILIDAD` | |

4. Configurar el webhook de Meta para que apunte a las URLs de n8n:
   - Leads: `https://tu-n8n.com/webhook/leadgen`
   - Mensajes: `https://tu-n8n.com/webhook/mensajes`

---

## Arquitectura final

```
Facebook Lead Ads
       ↓
  Workflow 1 (n8n)
  ├── Graph API: obtener datos del form
  ├── GHL: crear contacto + oportunidad (Nuevo Lead)
  └── WhatsApp: mensaje bienvenida → GHL: Contactado

WhatsApp / FB DM / IG DM
       ↓
  Workflow 2 (n8n)
  ├── Detectar canal
  ├── Recuperar historial desde GHL
  ├── Claude API: generar respuesta
  ├── Si update_lead → GHL: actualizar + Pipeline: Calificado
  ├── Si schedule_appointment → Google Calendar + Pipeline: Cita Confirmada
  └── Enviar respuesta al canal correcto

  Workflow 3 (n8n — cada hora)
  ├── Buscar leads activos en GHL
  ├── Evaluar si corresponde recordatorio (3d, 7d, pre-cita 24h, 2h)
  └── Enviar mensaje + actualizar contador en GHL
```
