# VoCall REST API Specification & OpenAPI Reference

**Document Version:** 2.1  
**Base URL:** `http://localhost:8000/api/v1` (Note: Connectors router is mounted at `http://localhost:8000/api/connectors`)  
**Authentication:** Bearer JWT Token (`Authorization: Bearer <token>`) or `X-API-Key: <key>`  
**Related Components:** `app/routers/`, `app/models/schemas.py`, `app/models/connectors.py`, `src/services/api.ts`

---

## 1. Authentication & Users (`/api/v1/auth`)

| Method | Endpoint | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login` | Log in user with email & password | `{"email": "...", "password": "..."}` | `{"access_token": "...", "token_type": "bearer", "user": {...}}` |
| `GET` | `/api/v1/auth/me` | Retrieve authenticated user profile | None | `{"status": "authenticated", "user": {"id": "...", "email": "...", "org_id": "..."}}` |

---

## 2. Agent Management (`/api/v1/agents`)

| Method | Endpoint | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/agents` | List all agents for authenticated org | Query: `?org_id=...` | `[AgentResponse]` |
| `POST` | `/api/v1/agents` | Create a new voice agent | `AgentCreate` | `AgentResponse` (HTTP 201) |
| `GET` | `/api/v1/agents/{agent_id}` | Retrieve agent configuration | None | `AgentResponse` |
| `PUT` | `/api/v1/agents/{agent_id}` | Update agent prompt, voice, or memory settings | `AgentUpdate` | `AgentResponse` |
| `DELETE` | `/api/v1/agents/{agent_id}` | Delete voice agent | None | HTTP 204 No Content |
| `POST` | `/api/v1/agents/{agent_id}/publish` | Toggle published deployment status | None | `{"message": "Agent published successfully", "agent": AgentResponse}` |
| `POST` | `/api/v1/agents/{agent_id}/enhance-prompt` | AI Prompt Enhancer via Groq LLaMA 3.3 70B | `{"system_prompt": "..."}` | `{"enhanced_prompt": "..."}` |
| `POST` | `/api/v1/agents/{agent_id}/run-analysis` | Run automated simulation test & evaluation | `{"test_audio_url": "...", "scenario": "..."}` | `{"agent_id": "...", "evaluation_score": 0.94, "insights": [...]}` |

---

## 3. Calls & LiveKit WebRTC Sessions (`/api/v1/calls`)

| Method | Endpoint | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/calls` | List call history with filters (direction, status) | Query: `?org_id=...&agent_id=...&direction=...` | `[CallResponse]` |
| `POST` | `/api/v1/calls` | Create a call session record | `CallCreate` | `CallResponse` (HTTP 201) |
| `GET` | `/api/v1/calls/{call_id}` | Retrieve call details, transcript, emotion score | None | `CallResponse` |
| `GET` | `/api/v1/calls/{call_id}/memory` | Retrieve 4-tier memory context loaded for call | Query: `?org_id=...` | `{"call_id": "...", "contact_id": "...", "memory": {...}}` |
| `POST` | `/api/v1/calls/token` | Mint LiveKit WebRTC AccessToken | `{"room_name": "...", "participant_name": "...", "agent_id": "..."}` | `{"token": "...", "room_name": "...", "livekit_url": "..."}` |
| `POST` | `/api/v1/calls/webcall/start` | Start WebCall session & initialize LiveKit room | `{"agent_id": "...", "contact_name": "...", "contact_phone": "..."}` | `{"call_id": "...", "room_name": "...", "token": "...", "livekit_url": "...", "agent": {...}}` |
| `GET` | `/api/v1/calls/webcall/{call_id}/events` | **Server-Sent Events (SSE)** real-time stream | None | `text/event-stream` (emotion, transcript, intent, tools) |
| `DELETE` | `/api/v1/calls/webcall/{call_id}/end` | Terminate active WebCall pipeline & run post-call | None | `{"status": "ended", "call_id": "...", "duration_seconds": 124}` |
| `POST` | `/api/v1/calls/outbound` | Initiate outbound telephony call via Twilio/Plivo | `{"agent_id": "...", "to_number": "...", "from_number": "..."}` | `{"status": "initiated", "call_sid": "..."}` (HTTP 202) |

---

## 4. 4-Tier Memory Subsystem (`/api/v1/memory`)

| Method | Endpoint | Description | Request Body / Query | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/memory/long-term` | Retrieve top-k semantic facts for contact | `?contact_id=...&query=...&limit=5` | `[FactResponse]` |
| `POST` | `/api/v1/memory/long-term` | Store a new persistent semantic fact | `{"contact_id": "...", "fact": "...", "metadata": {...}}` | `{"id": "...", "status": "stored"}` (HTTP 201) |
| `GET` | `/api/v1/memory/episodic` | Retrieve past call episodic summaries | `?contact_id=...&limit=3` | `[EpisodeResponse]` |

*Note: Contact-specific FalkorDB Knowledge Graph traversal and DPDP clearance are managed via `/api/v1/contacts/{contact_id}/memory/graph` and `/api/v1/contacts/{contact_id}/memory`.*

---

## 5. Emotion Engine (`/api/v1/emotion`)

| Method | Endpoint | Description | Request Body / Path | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/emotion/events/{call_id}` | Retrieve real-time emotion turn events | Path: `call_id` | `{"call_id": "...", "events": [...], "source": "redis"}` |
| `POST` | `/api/v1/emotion/events` | Record multimodal emotion turn event | `{"call_id": "...", "valence": 0.2, "arousal": 0.4, "frustration": 0.1, "turn_index": 3}` | `{"status": "recorded", "event_id": "..."}` (HTTP 201) |

---

## 6. VA-ICECoT Intent Engine (`/api/v1/intent`)

| Method | Endpoint | Description | Request Body / Path | Response |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/intent/detect` | Classify intent & extract slot tokens | `{"text": "...", "call_id": "...", "context": {...}}` | `{"intent": "book_appointment", "confidence": 0.96, "slots": {"date": "tomorrow", "time": "3pm"}}` |
| `GET` | `/api/v1/intent/calls/{call_id}/events` | Retrieve all intent events for call | Path: `call_id` | `[IntentEventResponse]` |
| `GET` | `/api/v1/intent/calls/{call_id}/slots` | Retrieve carried-forward slot parameters | Path: `call_id` | `{"call_id": "...", "slots": {...}, "filled_ratio": 1.0}` |

---

## 7. Action Connectors Framework (`/api/connectors`)

*Mounted directly at `/api/connectors`.*

| Method | Endpoint | Description | Request Body / Path | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/connectors` | List configured third-party connectors | Query: `?org_id=...&agent_id=...` | `[ConnectorConfigResponse]` (Credentials masked) |
| `GET` | `/api/connectors/{connector_type}` | Retrieve connector configuration by type | Path: `connector_type` (`whatsapp`, `google_calendar`, `hubspot`, `salesforce`, `slack`, `supabase`, `webhook`) | `ConnectorConfigResponse` |
| `POST` | `/api/connectors/{connector_type}` | Create/Update encrypted connector config | `ConnectorConfigCreate` (AES-256-GCM encrypted) | `ConnectorConfigResponse` |
| `DELETE` | `/api/connectors/{connector_type}` | Delete connector configuration | Path: `connector_type` | `{"status": "deleted", "connector_type": "..."}` |
| `POST` | `/api/connectors/{connector_type}/test` | Test third-party connector live connectivity | `{"config": {...}, "test_payload": {...}}` | `{"success": true, "result": {...}}` |

---

## 8. Contacts & DPDP "Forget Me" Cascade (`/api/v1/contacts`)

| Method | Endpoint | Description | Request Body / Path | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/contacts` | List contacts with query search | Query: `?org_id=...&query=...` | `[ContactResponse]` |
| `POST` | `/api/v1/contacts` | Create a new contact record | `ContactCreate` | `ContactResponse` (HTTP 201) |
| `GET` | `/api/v1/contacts/{contact_id}` | Retrieve contact details & call stats | Path: `contact_id` | `ContactResponse` |
| `PUT` / `PATCH` | `/api/v1/contacts/{contact_id}` | Update contact name, phone, email, tags | `ContactUpdate` | `ContactResponse` |
| `DELETE` | `/api/v1/contacts/{contact_id}` | Delete contact record | Path: `contact_id` | HTTP 204 No Content |
| `GET` | `/api/v1/contacts/{contact_id}/memory/graph` | Retrieve FalkorDB knowledge graph for contact | Path: `contact_id` | `{"nodes": [...], "edges": [...], "frustrations": [...]}` |
| `DELETE` | `/api/v1/contacts/{contact_id}/memory/graph` | Purge FalkorDB graph sub-tree for contact | Path: `contact_id` | `{"success": true, "message": "Graph wiped"}` |
| `DELETE` | `/api/v1/contacts/{contact_id}/memory` | **DPDP Act 2023 "Forget Me" Complete Erasure** | Path: `contact_id` | `{"success": true, "deleted": {"redis": 1, "pgvector": 12, "episodic": 4, "falkordb": 18}}` |

---

## 9. Telephony & Phone Numbers (`/api/v1/phone-numbers`)

| Method | Endpoint | Description | Request Body / Path | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/phone-numbers` | List provisioned telephony numbers | Query: `?org_id=...` | `[PhoneNumberResponse]` |
| `POST` | `/api/v1/phone-numbers` | Provision / assign phone number to agent | `PhoneNumberCreate` | `PhoneNumberResponse` (HTTP 201) |
| `GET` | `/api/v1/phone-numbers/{phone_id}` | Retrieve phone number details & agent mapping | Path: `phone_id` | `PhoneNumberResponse` |
| `POST` | `/api/v1/phone-numbers/{phone_id}/kyc` | Submit KYC compliance documentation | Multipart form: `document_type`, `file` | `PhoneNumberResponse` (`kyc_status`: "under_review") |
| `DELETE` | `/api/v1/phone-numbers/{phone_id}` | Release / unassign telephony number | Path: `phone_id` | HTTP 204 No Content |

---

## 10. BYOK Encrypted API Keys (`/api/v1/api-keys`)

| Method | Endpoint | Description | Request Body / Path | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/api-keys` | List active BYOK keys (masked: `sk-...xxxx`) | Query: `?org_id=...` | `[APIKeyResponse]` |
| `POST` | `/api/v1/api-keys` | Register / encrypt provider API key (AES-256-GCM) | `{"provider": "groq", "api_key": "gsk_..."}` | `APIKeyResponse` (HTTP 201) |
| `DELETE` | `/api/v1/api-keys/{key_id}` | Remove registered provider key | Path: `key_id` | HTTP 204 No Content |

---

## 11. Inbound Webhooks & Telephony Ingest (`/api/v1/webhooks`)

| Method | Endpoint | Description | Payload | Response |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/webhooks/twilio/inbound` | Inbound Twilio PSTN voice call handler | Twilio Form URL-Encoded (`CallSid`, `From`, `To`) | TwiML XML Response (`<Connect><Stream>`) |
| `POST` | `/api/v1/webhooks/twilio/events` | Twilio call lifecycle status events callback | Twilio Form URL-Encoded | `{"status": "received"}` |
| `POST` | `/api/v1/webhooks/livekit` | LiveKit Cloud WebRTC room webhook | LiveKit JWT Payload (`room_started`, `participant_left`) | `{"status": "processed"}` |

---

*Verified against `app/routers/` and `src/services/api.ts`.*
