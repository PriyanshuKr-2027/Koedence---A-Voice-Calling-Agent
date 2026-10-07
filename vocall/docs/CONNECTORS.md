# VoCall Action Connectors — Comprehensive Technical Specification

**Document Version:** 2.0  
**Status:** Authoritative Specification  
**Architecture Layer:** Real-Time & Asynchronous Action Integration  
**Related Components:** `app/services/connectors/`, `app/routers/connectors.py`, `app/utils/encryption.py`, `trigger/post_call_pipeline.py`

---

## 1. Executive Summary & Architecture Overview

VoCall provides a pluggable, high-performance **Action Connector Framework** enabling voice agents to interact seamlessly with third-party enterprise tools, CRMs, calendars, databases, messaging channels, and internal webhook endpoints. 

Connectors operate across two distinct runtime execution phases:
1. **During-Call Real-Time Execution:** Low-latency tool calls executed mid-conversation via LLM function calling (e.g., checking calendar availability, booking appointments, logging real-time CRM leads, firing frustration alerts).
2. **Post-Call Asynchronous Execution:** Background jobs triggered via the Trigger.dev asynchronous pipeline (`trigger/post_call_pipeline.py` / `app/trigger/post_call_pipeline.py`) upon call termination to sync structured call summaries, sentiment arcs, action items, and transcripts.

```text
                               ┌─────────────────────────────────────────┐
                               │       VOCALL AGENT RUNTIME / LLM        │
                               └────────────────────┬────────────────────┘
                                                    │ Mid-Call Tool Calling
                                                    ▼
┌──────────────────────────────┐        ┌────────────────────────────────┐
│   TRIGGER.DEV POST-CALL      ├───────►│        CENTRAL DISPATCHER      │
│   ASYNC PIPELINE WORKFLOW    │ Post-  │        `fire_connector()`      │
└──────────────────────────────┘ Call   └───────────────┬────────────────┘
                                                        │
         ┌──────────────────┬───────────────────┼───────────────────┬──────────────────┐
         │                  │                   │                   │                  │
┌────────▼────────┐ ┌───────▼────────┐  ┌───────▼────────┐  ┌───────▼────────┐ ┌───────▼────────┐
│ WhatsApp        │ │ Google Cal     │  │ HubSpot CRM    │  │ Salesforce CRM │ │ Slack Block Kit│
│ (Twilio API)    │ │ (Free/Busy/Evt)│  │ (Deals/Leads)  │  │ (OAuth2 Sync)  │ │ (Summary/Alert)│
└─────────────────┘ └────────────────┘  └────────────────┘  └────────────────┘ └────────────────┘
         │                  │                   │                   │                  │
┌────────▼────────┐ ┌───────▼────────┐  ┌───────▼────────┐          │                  │
│ Custom Webhook  │ │ Supabase / PG  │  │ Tone Adapter   │◄─────────┴──────────────────┘
│ (HMAC Templated)│ │ (SQL Query)    │  │ (Prompt Mod)   │  Mid-Call Emotion Adaptation
└─────────────────┘ └────────────────┘  └────────────────┘
```

---

## 2. AES-256-GCM BYOK Security Model

All sensitive third-party credentials (API keys, OAuth tokens, client secrets, webhook signing keys) are encrypted before storage in the Supabase PostgreSQL database (`connector_configs.config` JSONB column) using **AES-256-GCM** authenticated encryption with Bring-Your-Own-Key (BYOK) support.

### 2.1 Encryption Implementation (`app/utils/encryption.py`)

- **Algorithm:** AES-256-GCM (Galois/Counter Mode) with 128-bit authentication tag.
- **Key Derivation:** SHA-256 hash of the master encryption secret `SETTINGS.ENCRYPTION_KEY`.
- **Initialization Vector (IV):** 12-byte cryptographically secure pseudorandom nonce generated per encryption operation.
- **Payload Format:** `base64( IV [12 bytes] + Ciphertext [N bytes] + AuthTag [16 bytes] )`

```python
import os
import json
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import settings

def encrypt_config(data: dict) -> str:
    """Encrypts a dictionary to base64 AES-256-GCM string."""
    key = settings.ENCRYPTION_KEY.encode('utf-8')[:32].ljust(32, b'0')
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    plaintext = json.dumps(data).encode('utf-8')
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce + ciphertext).decode('utf-8')

def decrypt_config(encrypted_str: str) -> dict:
    """Decrypts base64 AES-256-GCM string back to dictionary."""
    raw_data = base64.b64decode(encrypted_str.encode('utf-8'))
    nonce, ciphertext = raw_data[:12], raw_data[12:]
    key = settings.ENCRYPTION_KEY.encode('utf-8')[:32].ljust(32, b'0')
    aesgcm = AESGCM(key)
    decrypted = aesgcm.decrypt(nonce, ciphertext, None)
    return json.loads(decrypted.decode('utf-8'))
```

---

## 3. Detailed Specifications for the 8 Connectors

### 3.1 WhatsApp Connector (`app/services/connectors/whatsapp.py`)

- **Purpose:** Sends post-call notifications, appointment confirmations, payment links, and call summaries to the user's WhatsApp number.
- **Transport:** Twilio Messaging REST API (`POST /2010-04-01/Accounts/{AccountSid}/Messages.json`).
- **Modes of Operation:**
  1. **Approved Twilio Content Template:** Uses pre-approved Meta WhatsApp templates with dynamic variables (`{{1}}`, `{{2}}`).
  2. **Free-Text Message Fallback:** Sends plain-text WhatsApp messages when within the active 24-hour customer care window.
- **Key Function:**
  ```python
  async def send_whatsapp_message(
      to_number: str,
      message_body: str,
      config: dict,
      content_sid: Optional[str] = None,
      content_variables: Optional[dict] = None
  ) -> dict:
      """Dispatches WhatsApp message via Twilio API with E.164 normalization."""
  ```

---

### 3.2 Google Calendar Connector (`app/services/connectors/google_cal.py`)

- **Purpose:** Real-time mid-call appointment booking and availability lookup.
- **Authentication:** Google OAuth2 Service Account or OAuth2 User Refresh Token with Calendar scopes (`https://www.googleapis.com/auth/calendar`).
- **Core Operations:**
  - `check_availability(calendar_id, date, timezone, duration_minutes=30)`: Calls Google Calendar `freeBusy.query` API to find open time windows between 09:00 and 18:00 local time.
  - `book_appointment(calendar_id, start_time, end_time, summary, description, attendee_email)`: Creates confirmed calendar event with Google Meet link integration.

---

### 3.3 HubSpot CRM Connector (`app/services/connectors/hubspot.py`)

- **Purpose:** Bidirectional customer sync, lead generation, and call logging.
- **Authentication:** HubSpot Private App Access Token (`Bearer pat-na1-...`).
- **During-Call Functionality:**
  - `log_lead(email, firstname, lastname, phone, deal_name, deal_amount)`: Creates or updates a HubSpot Contact record and immediately opens an associated Deal in the sales pipeline.
- **Post-Call Functionality:**
  - `sync_call_summary(contact_id, call_id, transcript, summary, outcome, duration_seconds)`: Creates an engagement `Call` record associated with the HubSpot Contact containing duration, recording URL, and AI-generated call notes.

---

### 3.4 Salesforce CRM Connector (`app/services/connectors/salesforce.py`)

- **Purpose:** Enterprise CRM customer lookup, lead ingestion, and activity tracking.
- **Authentication:** Salesforce OAuth2 Connected App with automatic token refresh (`/services/oauth2/token`).
- **Operations:**
  - `refresh_access_token(client_id, client_secret, refresh_token, instance_url)`: Automatically fetches fresh JWT access tokens on expiry.
  - `sync_call_result(lead_or_contact_id, call_data, summary, outcome)`: Inserts a Salesforce `Task` record with `Status='Completed'`, `Subject='VoCall AI Voice Session'`, and custom field mapping.

---

### 3.5 Slack Connector (`app/services/connectors/slack.py`)

- **Purpose:** Internal team visibility, live escalation notifications, and post-call telemetry.
- **Transport:** Slack Incoming Webhooks & Slack Web API (`chat.postMessage`).
- **Message Formats (Block Kit):**
  1. **Post-Call Summary Card:** Formatted header, caller details, duration, sentiment badge, key bullet points, action items, and link to dashboard call detail page.
  2. **High-Frustration Live Alert (`send_frustration_alert`):** Triggered immediately when caller frustration exceeds threshold ($\ge 0.75$), alerting human supervisors with a direct link to intervene.

---

### 3.6 Custom Webhook Connector (`app/services/connectors/webhook.py`)

- **Purpose:** Generic HTTP integration with internal backends, Zapier, Make, n8n, and custom microservices.
- **Security:** HMAC-SHA256 payload signature header (`X-VoCall-Signature`) for webhook verification.
- **Template Engine:** Supports mustache-style token replacement:
  - `{call_id}`, `{caller_number}`, `{agent_name}`, `{duration_seconds}`, `{sentiment}`, `{summary}`, `{transcript}`.
- **Execution:** Async `httpx.AsyncClient` with configurable timeout (default: 5.0s) and exponential backoff retry policy (3 attempts).

---

### 3.7 Postgres / Supabase SQL Connector (`app/services/connectors/supabase_conn.py`)

- **Purpose:** Execute dynamic database queries mid-call to fetch account balances, order statuses, inventory counts, or patient records.
- **Security Safeguards:**
  - Enforces strict read-only execution (`SELECT` statements only; regex blocks `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`).
  - Parameterized variable interpolation (`$1`, `$2`) to eliminate SQL injection risks.
- **Methods:**
  - `query_postgres(connection_string, sql_template, params)`: Executes via `asyncpg`.
  - `query_supabase(table, select_cols, filters)`: Executes via Supabase PostgREST API.

---

### 3.8 Tone Adapter Connector (`app/services/emotion/tone_adapter.py`)

- **Purpose:** Real-time prompt modifier dynamically injected into the active LLM context based on detected caller emotional states.
- **Mapping Matrix:**
  | Detected Emotion State | Prompt Modification Instruction | TTS Modifier |
  | --- | --- | --- |
  | **High Frustration ($\ge 0.75$)** | *"The caller is highly frustrated. Speak in a soothing, highly empathetic, apologetic tone. Do not debate or explain; acknowledge the issue directly and offer immediate resolution."* | Pace: 0.9x, Emotion: empathetic |
  | **Confusion / Hesitation** | *"The caller seems uncertain. Use simple language, break explanations into short steps, and actively check for understanding."* | Pace: 0.95x, Pitch: neutral |
  | **Satisfaction / Joy** | *"The caller is pleased and enthusiastic. Match their energy with warm, upbeat, and professional delivery."* | Pace: 1.05x, Emotion: cheerful |
  | **Neutral / Transactional** | *"Deliver crisp, concise, and professional responses without excessive conversational filler."* | Pace: 1.0x, Emotion: neutral |

---

## 4. Connector Data Models & API Contracts

### 4.1 Schema Definitions (`app/models/schemas.py`)

```python
class ConnectorType(str, Enum):
    WHATSAPP = "whatsapp"
    GOOGLE_CALENDAR = "google_calendar"
    HUBSPOT = "hubspot"
    SALESFORCE = "salesforce"
    SLACK = "slack"
    WEBHOOK = "webhook"
    POSTGRES = "postgres"
    TONE_ADAPTER = "tone_adapter"

class ConnectorTrigger(str, Enum):
    DURING_CALL = "during_call"
    POST_CALL = "post_call"
    ON_FRUSTRATION = "on_frustration"

class ConnectorConfigCreate(BaseModel):
    org_id: UUID
    agent_id: Optional[UUID] = None
    type: ConnectorType
    name: str
    is_enabled: bool = True
    trigger_event: ConnectorTrigger = ConnectorTrigger.POST_CALL
    config: Dict[str, Any]  # Plaintext in API; encrypted at rest
```

### 4.2 REST API Endpoints (`app/routers/connectors.py`)

- `GET /api/v1/connectors`: List all configured connectors for the authenticated organization.
- `POST /api/v1/connectors`: Create and encrypt a new connector configuration.
- `GET /api/v1/connectors/{id}`: Retrieve connector metadata (credentials masked).
- `PATCH /api/v1/connectors/{id}`: Update connector settings and trigger events.
- `DELETE /api/v1/connectors/{id}`: Remove connector configuration.
- `POST /api/v1/connectors/{id}/test`: Execute a test invocation of the connector with mock call payload.

---

## 5. Verification & Testing

The connectors are validated via automated tests in `tests/test_connectors.py`:
- `TC-CONNECTORS-DISPATCHER-01`: Verify `fire_connector` routes to correct handler by connector type.
- `TC-CONNECTORS-ENCRYPTION-01`: Verify round-trip AES-256-GCM encryption/decryption of auth secrets.
- `TC-CONNECTORS-TEST-01`: Execute test dispatch with mocked external HTTP clients.
