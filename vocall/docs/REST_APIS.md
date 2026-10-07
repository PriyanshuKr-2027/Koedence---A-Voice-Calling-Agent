# VoCall REST API Specification & OpenAPI Reference

**Document Version:** 2.0  
**Base URL:** `http://localhost:8000/api/v1`  
**Authentication:** Bearer JWT Token (`Authorization: Bearer <token>`) or `X-API-Key: <key>`  
**Related Components:** `app/routers/`, `app/models/schemas.py`

---

## 1. Authentication & Users (`/auth`)

| Method | Endpoint | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/auth/login` | Log in user with email & password | `{"email": "...", "password": "..."}` | `{"access_token": "...", "token_type": "bearer"}` |
| `GET` | `/auth/me` | Retrieve authenticated user profile | None | `{"id": "...", "email": "...", "org_id": "..."}` |

---

## 2. Agent Management (`/agents`)

| Method | Endpoint | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/agents` | List all agents for the authenticated org | None | `[AgentResponse]` |
| `POST` | `/agents` | Create a new voice agent | `AgentCreate` | `AgentResponse` |
| `GET` | `/agents/{id}` | Retrieve agent configuration | None | `AgentResponse` |
| `PATCH` | `/agents/{id}` | Update agent prompt, voice, or memory settings | `AgentUpdate` | `AgentResponse` |
| `DELETE` | `/agents/{id}` | Delete voice agent | None | `{"success": true}` |
| `POST` | `/agents/{id}/enhance-prompt` | AI Prompt Enhancer via Groq LLaMA 3.3 70B | `{"prompt": "..."}` | `{"enhanced_prompt": "..."}` |

---

## 3. Calls & LiveKit Sessions (`/calls`)

| Method | Endpoint | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/calls` | List call history with filters (direction, status) | Query params | `[CallResponse]` |
| `POST` | `/calls` | Initiate an outbound call or create session | `CallCreate` | `CallResponse` |
| `GET` | `/calls/{id}` | Retrieve call details, transcript, and emotion score | None | `CallResponse` |
| `POST` | `/calls/token` | Mint LiveKit WebRTC AccessToken for WebCall | `{"agent_id": "...", "contact_name": "..."}` | `{"token": "...", "room_name": "...", "call_id": "..."}` |
| `DELETE` | `/calls/webcall/{id}` | Terminate active WebCall pipeline | None | `{"success": true}` |

---

## 4. 4-Tier Memory Subsystem (`/memory`)

| Method | Endpoint | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/memory/long-term` | Retrieve top-k semantic facts for contact | `?contact_id=...&query=...` | `[FactResponse]` |
| `POST` | `/memory/long-term` | Store a new persistent fact | `{"contact_id": "...", "fact": "..."}` | `{"id": "...", "status": "stored"}` |
| `GET` | `/memory/episodic` | Retrieve past call summaries for contact | `?contact_id=...&limit=3` | `[EpisodeResponse]` |
| `GET` | `/memory/graph` | Retrieve FalkorDB Cypher knowledge graph context | `?contact_id=...` | `{"entities": [...], "topics": [...], "frustrations": [...]}` |

---

## 5. Emotion Engine (`/emotion`)

| Method | Endpoint | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/emotion/events` | Retrieve real-time emotion events for a call | `?call_id=...` | `{"events": [...], "source": "redis"}` |
| `POST` | `/emotion/record` | Record an acoustic/text emotion turn event | `{"call_id": "...", "valence": 0.2, "frustration": 0.1}` | `{"success": true}` |

---

## 6. VA-ICECoT Intent Engine (`/intent`)

| Method | Endpoint | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/intent/detect` | Classify intent and extract slot tokens | `{"text": "...", "call_id": "..."}` | `{"intent": "...", "confidence": 0.95, "slots": {...}}` |
| `GET` | `/intent/events` | Retrieve all intent events for a call | `?call_id=...` | `[IntentEventResponse]` |
| `GET` | `/intent/slots` | Retrieve carried-forward slots in Redis | `?call_id=...` | `{"slots": {...}}` |

---

## 7. Action Connectors (`/connectors`)

| Method | Endpoint | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/connectors` | List configured third-party connectors | None | `[ConnectorConfigResponse]` |
| `POST` | `/connectors` | Create & encrypt a connector configuration | `ConnectorConfigCreate` | `ConnectorConfigResponse` |
| `GET` | `/connectors/{id}` | Retrieve connector metadata (credentials masked) | None | `ConnectorConfigResponse` |
| `PATCH` | `/connectors/{id}` | Update connector trigger and settings | `ConnectorConfigUpdate` | `ConnectorConfigResponse` |
| `DELETE` | `/connectors/{id}` | Delete connector | None | `{"success": true}` |
| `POST` | `/connectors/{id}/test` | Trigger test invocation of connector | `{"mock_payload": {...}}` | `{"status": "success", "result": {...}}` |

---

## 8. Contacts & DPDP "Forget Me" (`/contacts`)

| Method | Endpoint | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/contacts` | List contacts with search & pagination | `?query=...&limit=20` | `[ContactResponse]` |
| `POST` | `/contacts` | Create a new contact | `ContactCreate` | `ContactResponse` |
| `GET` | `/contacts/{id}` | Retrieve contact details & call stats | None | `ContactResponse` |
| `PATCH` | `/contacts/{id}` | Update contact name, phone, tags | `ContactUpdate` | `ContactResponse` |
| `DELETE` | `/contacts/{id}` | Delete contact record | None | `{"success": true}` |
| `DELETE` | `/contacts/{id}/memory` | **DPDP Act Cascading Erasure** across Redis, pgvector, Postgres, and FalkorDB | None | `{"success": true, "records_deleted": 42}` |

---

## 9. Telephony & Phone Numbers (`/phone-numbers`)

| Method | Endpoint | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/phone-numbers` | List provisioned phone numbers | None | `[PhoneNumberResponse]` |
| `POST` | `/phone-numbers` | Provision / assign a phone number | `PhoneNumberCreate` | `PhoneNumberResponse` |
| `DELETE` | `/phone-numbers/{id}` | Release phone number | None | `{"success": true}` |

---

## 10. Webhooks & Ingest (`/webhooks`)

| Method | Endpoint | Description | Payload | Response |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/webhooks/twilio/inbound` | Inbound Twilio PSTN voice call webhook | Twilio Form URL-Encoded | TwiML XML Response |
| `POST` | `/webhooks/twilio/status` | Twilio call status update callback | Twilio Form URL-Encoded | `{"status": "received"}` |
| `POST` | `/webhooks/livekit` | LiveKit Cloud WebRTC room event webhook | LiveKit JWT Payload | `{"status": "processed"}` |

---

Approved by VoCall Technical Architecture Team.
