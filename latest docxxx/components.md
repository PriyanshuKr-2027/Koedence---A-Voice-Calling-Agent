# VoCall Component Breakdown & Technology Stack

**System:** VoCall — Enterprise Multi-Tier Emotion-Aware Voice Agent Platform  
**Document Type:** Technical Component Specification (`components.md`)  
**Version:** 2.0 (Production Release)  
**Date:** July 2026  
**Status:** Approved & Authoritative  

---

## Table of Contents

1. [Architectural Component Taxonomy](#1-architectural-component-taxonomy)
2. [Section 1: Pre-Existing External APIs & Cloud Services](#2-section-1-pre-existing-external-apis--cloud-services)
   - [1.1 Groq Cloud LPU (LLM, STT, Embedding)](#11-groq-cloud-lpu-llm-stt-embedding)
   - [1.2 Hume AI (Acoustic Prosody & Octave 2 TTS)](#12-hume-ai-acoustic-prosody--octave-2-tts)
   - [1.3 Cartesia AI (Sonic-2 Fast TTS)](#13-cartesia-ai-sonic-2-fast-tts)
   - [1.4 Sarvam AI (Indic STT & TTS)](#14-sarvam-ai-indic-stt--tts)
   - [1.5 LiveKit Cloud (WebRTC SFU Media Transport)](#15-livekit-cloud-webrtc-sfu-media-transport)
   - [1.6 Supabase Cloud (Postgres, Auth, pgvector)](#16-supabase-cloud-postgres-auth-pgvector)
   - [1.7 Upstash Redis (Short-Term Memory REST)](#17-upstash-redis-short-term-memory-rest)
   - [1.8 FalkorDB (Graph RAG Engine)](#18-falkordb-graph-rag-engine)
   - [1.9 Twilio Voice & WhatsApp Gateway](#19-twilio-voice--whatsapp-gateway)
   - [1.10 HubSpot CRM API](#110-hubspot-crm-api)
   - [1.11 Google Calendar API](#111-google-calendar-api)
   - [1.12 Salesforce REST API](#112-salesforce-rest-api)
   - [1.13 Slack API](#113-slack-api)
   - [1.14 Cerebras AI (Fallback LLM)](#114-cerebras-ai-fallback-llm)
   - [1.15 Trigger.dev Cloud](#115-triggerdev-cloud)
   - [1.16 Resend (Email Delivery)](#116-resend-email-delivery)
3. [Section 2: Pre-Existing Open-Source Libraries & Frameworks](#3-section-2-pre-existing-open-source-libraries--frameworks)
   - [2.1 Python Backend Dependencies](#21-python-backend-dependencies)
   - [2.2 TypeScript / Frontend Dependencies](#22-typescript--frontend-dependencies)
4. [Section 3: Custom-Built Components (Our Proprietary Code)](#4-section-3-custom-built-components-our-proprietary-code)
   - [3.1 Dual-Signal Emotion Fusion Engine](#31-dual-signal-emotion-fusion-engine)
   - [3.2 44-Emotion Circumplex Mapper & Acoustic Centroid](#32-44-emotion-circumplex-mapper--acoustic-centroid)
   - [3.3 4-Tier Parallel Cognitive Memory Retriever](#33-4-tier-parallel-cognitive-memory-retriever)
   - [3.4 VA-ICECoT Intent Detection Engine](#34-va-icecot-intent-detection-engine)
   - [3.5 Emotion × Intent Combined Rules Engine](#35-emotion--intent-combined-rules-engine)
   - [3.6 Action Connector Dispatcher (Registry Model)](#36-action-connector-dispatcher-registry-model)
   - [3.7 BYOK AES-256-GCM Cryptographic Subsystem](#37-byok-aes-256-gcm-cryptographic-subsystem)
   - [3.8 LiveKit WebRTC Session & Token Manager](#38-livekit-webrtc-session--token-manager)
   - [3.9 pgvector Semantic Memory Store](#39-pgvector-semantic-memory-store)
   - [3.10 FalkorDB Knowledge Graph Service](#310-falkordb-knowledge-graph-service)
   - [3.11 Conversational Tone Adapter](#311-conversational-tone-adapter)
   - [3.12 WebCall SSE Real-Time Streamer](#312-webcall-sse-real-time-streamer)
   - [3.13 8-Stage Asynchronous Post-Call Pipeline](#313-8-stage-asynchronous-post-call-pipeline)
   - [3.14 WebCallModal & Dynamic Voice Orb (Frontend)](#314-webcallmodal--dynamic-voice-orb-frontend)
5. [Section 4: Comprehensive Mathematical Formulations](#5-section-4-comprehensive-mathematical-formulations)
6. [Section 5: Component Interaction & Dependency Matrix](#6-section-5-component-interaction--dependency-matrix)

---

## 1. Architectural Component Taxonomy

Every subsystem in the VoCall monorepo falls into one of three distinct categories:

```
+-------------------------------------------------------------------------------------------------------+
|                                      VOCALL COMPONENT TAXONOMY                                         |
+------------------------------------+----------------------------------+-------------------------------+
|  1. EXTERNAL MANAGED APIS          |  2. OPEN-SOURCE PACKAGES         |  3. PROPRIETARY CUSTOM CODE   |
|  (Called over HTTPS/REST/WebRTC)   |  (Imported in Python/Node)       |  (Built from scratch by us)   |
+------------------------------------+----------------------------------+-------------------------------+
|  * Groq LPU (LLM/STT/Embed)        |  * FastAPI / Uvicorn (ASGI)      |  * Dual Emotion Fusion Engine |
|  * Hume AI (Prosody/Octave TTS)    |  * Pydantic v2 (Validation)      |  * Circumplex Centroid Mapper |
|  * Cartesia (Sonic-2 TTS)          |  * httpx (Async HTTP Client)     |  * 4-Tier Memory Retriever    |
|  * Sarvam AI (Indic Voice)         |  * cryptography (AESGCM)         |  * VA-ICECoT Intent Engine    |
|  * LiveKit Cloud (SFU WebRTC)      |  * pipecat-ai (Turn Pipeline)    |  * Combined Rules Engine      |
|  * Supabase (Postgres/Auth)        |  * falkordb-py (Graph Client)    |  * Connector Registry Engine  |
|  * Upstash Redis (REST Memory)     |  * livekit-server-sdk (Tokens)   |  * BYOK AES-256-GCM Vault     |
|  * FalkorDB (Cypher Graph Server)  |  * Next.js 14 (App Router)       |  * Post-Call 8-Stage Worker   |
|  * Twilio (PSTN / WhatsApp)        |  * Tailwind CSS / Lucide         |  * WebCall Voice Orb & SSE    |
|  * HubSpot / Salesforce / Google   |  * Recharts / Radix UI           |  * LiveKit Singleton Manager  |
+------------------------------------+----------------------------------+-------------------------------+
```

---

## 2. Section 1: Pre-Existing External APIs & Cloud Services

### 1.1 Groq Cloud LPU (LLM, STT, Embedding)
- **Vendor:** Groq Inc. (`https://console.groq.com`)
- **Primary Roles in VoCall:**
  1. **Conversational LLM:** Ultra-low latency chat completion using `llama-3.3-70b-versatile` (Time-to-First-Token $\sim 150\text{ms}$).
  2. **Speech-to-Text (STT):** High-accuracy transcription using `whisper-large-v3`.
  3. **Vector Embeddings:** 1536-dimensional semantic representation via `nomic-embed-text-v1_5`.
- **Endpoints Used:**
  - `POST https://api.groq.com/openai/v1/chat/completions` (JSON & Streaming)
  - `POST https://api.groq.com/openai/v1/audio/transcriptions` (Multipart Form)
  - `POST https://api.groq.com/openai/v1/embeddings` (Batch JSON)
- **Authentication:** `Authorization: Bearer {GROQ_API_KEY}`
- **Config / Environment Variables:** `GROQ_API_KEY`, `GROQ_MODEL`
- **Failure Mode & Resilience:** If Groq fails, the system automatically falls back to Cerebras AI (`llama-3.3-70b`) for LLM and returns a zero-vector fallback for embeddings.

---

### 1.2 Hume AI (Acoustic Prosody & Octave 2 TTS)
- **Vendor:** Hume AI Inc. (`https://hume.ai`)
- **Primary Roles in VoCall:**
  1. **Acoustic Emotion Detection:** Analyzes raw caller audio chunks for 43 distinct paralinguistic emotions (prosody, tone, pitch, jitter).
  2. **Emotion-Conditioned TTS (Octave 2):** Generates speech modulated by runtime emotional valence and arousal.
- **Endpoints Used:**
  - `POST https://api.hume.ai/v0/batch/jobs` (Multipart WAV upload)
  - `POST https://api.hume.ai/v0/evm/models` (Fallback Expression Measurement)
  - `POST https://api.hume.ai/v0/tts` (Octave 2 synthesis with `generation_parameters`)
- **Authentication:** `X-Hume-Api-Key: {HUME_API_KEY}`
- **Config / Environment Variables:** `HUME_API_KEY`
- **Failure Mode & Resilience:** If Hume AI is unreachable or unconfigured, the system falls back to text-only sentiment and routes TTS to Cartesia Sonic-2.

---

### 1.3 Cartesia AI (Sonic-2 Fast TTS)
- **Vendor:** Cartesia AI (`https://cartesia.ai`)
- **Primary Roles in VoCall:** Default ultra-low latency English neural voice synthesis ($\text{TTFAB} < 80\text{ms}$).
- **Endpoints Used:**
  - `POST https://api.cartesia.ai/tts/bytes`
  - Payload: `{"model_id": "sonic-2", "transcript": text, "voice": {"mode": "id", "id": voice_id}, "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": 24000}}`
- **Authentication:** `X-API-Key: {CARTESIA_API_KEY}`, `Cartesia-Version: 2024-06-10`
- **Config / Environment Variables:** `CARTESIA_API_KEY`

---

### 1.4 Sarvam AI (Indic STT & TTS)
- **Vendor:** Sarvam AI (`https://sarvam.ai`)
- **Primary Roles in VoCall:** Hinglish and Indian vernacular voice processing.
  1. **STT:** `Saarika v2` (`hi-IN` mixed Hindi/English transcription).
  2. **TTS:** `Bulbul v2` (natural multilingual synthesis returning Base64 WAV).
- **Endpoints Used:**
  - `POST https://api.sarvam.ai/speech-to-text`
  - `POST https://api.sarvam.ai/text-to-speech`
- **Authentication:** `api-subscription-key: {SARVAM_API_KEY}`
- **Config / Environment Variables:** `SARVAM_API_KEY`

---

### 1.5 LiveKit Cloud (WebRTC SFU Media Transport)
- **Vendor:** LiveKit Inc. (`https://livekit.io`)
- **Primary Roles in VoCall:** Real-time WebRTC media server for browser webcalls and PSTN audio streaming.
- **Protocols:** WebRTC SRTP (Audio only), WebSockets for signaling.
- **SDKs:** `livekit-server-sdk` (Python) and `@livekit/components-react` (Browser).
- **Authentication:** HMAC signed Access Tokens minted with `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`.
- **Config / Environment Variables:** `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`

---

### 1.6 Supabase Cloud (Postgres, Auth, pgvector)
- **Vendor:** Supabase Inc. (`https://supabase.com`)
- **Primary Roles in VoCall:**
  1. **Relational Database:** 15 core tables (Orgs, Agents, Calls, Contacts, etc.).
  2. **Vector Similarity:** `pgvector` extension for 1536-dim long-term memory facts with HNSW cosine index.
  3. **User Authentication:** Supabase Auth JWT issuance and verification.
- **Endpoints Used:** PostgREST HTTP gateway and direct Postgres TCP connection on port `5432` / `6543`.
- **Authentication:** `apikey: {ANON_KEY}`, `Authorization: Bearer {SERVICE_ROLE_KEY}`
- **Config / Environment Variables:** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`

---

### 1.7 Upstash Redis (Short-Term Memory REST)
- **Vendor:** Upstash Inc. (`https://upstash.com`)
- **Primary Roles in VoCall:** Ephemeral in-call conversational buffer (`stm:{call_id}`) and Server-Sent Events (SSE) message queue (`webcall:{call_id}:events`).
- **Protocol:** HTTP REST API (connectionless, ideal for serverless and async task workers).
- **Commands Used:** `LPUSH`, `LRANGE`, `DEL`, `SET`, `GET`, `EXPIRE`.
- **Authentication:** `Authorization: Bearer {UPSTASH_REDIS_REST_TOKEN}`
- **Config / Environment Variables:** `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`

---

### 1.8 FalkorDB (Graph RAG Engine)
- **Vendor:** FalkorDB (`https://falkordb.com`)
- **Primary Roles in VoCall:** Knowledge Graph store capturing contact relationships, mentioned entities, recurring frustration topics, and episodic causal chains via OpenCypher queries.
- **Protocol:** Redis Serialization Protocol (RESP3) via `falkordb` Python library.
- **Config / Environment Variables:** `FALKORDB_HOST`, `FALKORDB_PORT`

---

### 1.9 Twilio Voice & WhatsApp Gateway
- **Vendor:** Twilio Inc. (`https://twilio.com`)
- **Primary Roles in VoCall:**
  1. **PSTN Telephony:** Inbound call routing via TwiML `<Stream>` WebSocket relay; outbound agent calling.
  2. **WhatsApp Messaging:** Post-call summaries and appointment links delivered via Twilio Content API.
- **Authentication:** HTTP Basic Auth (`TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN`).
- **Config / Environment Variables:** `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`

---

### 1.10 HubSpot CRM API
- **Vendor:** HubSpot Inc. (`https://developers.hubspot.com`)
- **Primary Roles in VoCall:** Action connector for logging qualified leads, call notes, and deal stages post-call.
- **Endpoints Used:**
  - `POST https://api.hubapi.com/crm/v3/objects/contacts`
  - `POST https://api.hubapi.com/crm/v3/objects/deals`
- **Authentication:** `Authorization: Bearer {access_token}` (stored encrypted via BYOK AES-256-GCM).

---

### 1.11 Google Calendar API
- **Vendor:** Google LLC (`https://developers.google.com/calendar`)
- **Primary Roles in VoCall:** Real-time appointment scheduling during calls.
- **Endpoints Used:** `freebusy.query` (detect openings) and `events.insert` (book confirmed slots).
- **Authentication:** OAuth2 Service Account Credentials JSON.

---

### 1.12 Salesforce REST API
- **Vendor:** Salesforce Inc. (`https://developer.salesforce.com`)
- **Primary Roles in VoCall:** Post-call contact sync and task record logging.
- **Endpoints Used:** `POST {instance_url}/services/data/v58.0/sobjects/Task/`
- **Authentication:** OAuth2 Token Refresh (`client_id`, `client_secret`, `refresh_token`).

---

### 1.13 Slack API
- **Vendor:** Slack Technologies / Salesforce (`https://api.slack.com`)
- **Primary Roles in VoCall:** Real-time operational frustration alerts ($\text{Valence} < -0.7$) and post-call summaries via Block Kit messages.
- **Endpoints Used:** `POST https://slack.com/api/chat.postMessage`
- **Authentication:** `Authorization: Bearer {bot_token}`

---

### 1.14 Cerebras AI (Fallback LLM)
- **Vendor:** Cerebras Systems (`https://cerebras.ai`)
- **Primary Roles in VoCall:** High-speed fallback inference engine when Groq experiences throttling or downtime.
- **Endpoints Used:** `POST https://api.cerebras.ai/v1/chat/completions` (`llama-3.3-70b`).
- **Authentication:** `Authorization: Bearer {CEREBRAS_API_KEY}`

---

### 1.15 Trigger.dev Cloud
- **Vendor:** Trigger.dev (`https://trigger.dev`)
- **Primary Roles in VoCall:** Serverless background workflow orchestrator executing the 8-stage post-call memory pipeline.
- **Config / Environment Variables:** `TRIGGER_API_KEY`, `TRIGGER_API_URL`

---

### 1.16 Resend (Email Delivery)
- **Vendor:** Resend Inc. (`https://resend.com`)
- **Primary Roles in VoCall:** Transactional post-call email receipts and escalation notifications.
- **Endpoints Used:** `POST https://api.resend.com/emails`
- **Authentication:** `Authorization: Bearer {RESEND_API_KEY}`

---

## 3. Section 2: Pre-Existing Open-Source Libraries & Frameworks

### 2.1 Python Backend Dependencies

| Package Name | PyPI Identifier | Exact Role in VoCall |
| :--- | :--- | :--- |
| **FastAPI** | `fastapi` | High-performance ASGI web framework, REST routing, Dependency Injection (`Depends`). |
| **Uvicorn** | `uvicorn[standard]` | Lightning-fast ASGI web server hosting the FastAPI backend on port 8000. |
| **Pydantic v2** | `pydantic`, `pydantic-settings` | Data contract validation, schema enforcement, environment settings management. |
| **httpx** | `httpx` | Asynchronous HTTP/2 client for non-blocking outbound API calls. |
| **Cryptography** | `cryptography` | Enterprise `AESGCM` primitives for AES-256-GCM BYOK credential encryption. |
| **Pipecat AI** | `pipecat-ai` | Real-time conversational audio pipeline framework managing frames across STT/LLM/TTS. |
| **LiveKit SDK** | `livekit`, `livekit-api` | Server-side WebRTC room provisioning, webhook parsing, and JWT token generation. |
| **Supabase Client** | `supabase`, `postgrest` | Python interface for querying Postgres tables, RPC vector functions, and Auth. |
| **FalkorDB Client** | `falkordb` | Python client for executing OpenCypher queries against FalkorDB graph nodes. |
| **Twilio Client** | `twilio` | Official SDK for generating TwiML responses and managing PSTN voice calls. |
| **PyJWT** | `pyjwt` | Fast JWT token decoding and payload inspection for Supabase authentication. |
| **Asyncio** | `asyncio` (stdlib) | Concurrent task fanout (`asyncio.gather`) for multi-tier memory retrieval. |

---

### 2.2 TypeScript / Frontend Dependencies

#### A. Interactive Frontend (`src/` — Vite + React 19)
| Package Name | NPM Identifier | Exact Role in VoCall |
| :--- | :--- | :--- |
| **Vite 8** | `vite` | Ultra-fast development server and modern ESM bundler. |
| **React 19** | `react`, `react-dom` | Cutting-edge declarative UI engine with concurrent rendering. |
| **Framer Motion 12** | `framer-motion` | Fluid physics-based animations, view transitions, and voice orb pulses. |
| **Recharts 3** | `recharts` | Real-time SVG chart rendering for emotion arc, turn latencies, and call metrics. |
| **Lucide React** | `lucide-react` | Scalable vector icon system across the entire application interface. |
| **Tailwind CSS** | `tailwindcss` | Utility-first styling engine with customized brand tokens and dark mode. |

#### B. Enterprise Dashboard (`vocall/frontend/` — Next.js 14)
| Package Name | NPM Identifier | Exact Role in VoCall |
| :--- | :--- | :--- |
| **Next.js 14** | `next` | React framework with App Router, React Server Components (RSC), and Server Actions. |
| **React 18** | `react`, `react-dom` | Stable production UI runtime for enterprise dashboard pages. |
| **LiveKit Client** | `livekit-client` | WebRTC protocol client for browser-native audio sessions. |
| **Radix UI** | `@radix-ui/react-*` | Accessible headless primitives (Dialog, Dropdown, Avatar, Slot). |
| **React Force Graph**| `react-force-graph-2d/3d` | 2D and 3D WebGL force-directed graph renderer for FalkorDB visualization. |
| **Trigger.dev SDK** | `@trigger.dev/sdk` | Client SDK to initiate and monitor background post-call pipelines. |

---

## 4. Section 3: Custom-Built Components (Our Proprietary Code)

### 3.1 Dual-Signal Emotion Fusion Engine
- **File:** [`app/services/emotion/fusion.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/services/emotion/fusion.py)
- **Architecture & Rationale:** Single-modality emotion detection fails in real-world voice calls (e.g., sarcasm presents positive text with negative acoustic prosody). VoCall fuses acoustic prosody ($60\%$ weight) with linguistic sentiment ($40\%$ weight).
- **Exact Code Implementation:**
```python
def fuse_emotion_signals(
    text: Optional[Dict[str, Any]],
    audio: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    now_ms = int(time.time() * 1000)

    if audio is not None and isinstance(audio, dict):
        audio_val = float(audio.get("valence", 0.0))
        audio_aro = float(audio.get("arousal", 0.5))
        audio_dom = str(audio.get("dominant", "neutral"))
        audio_conf = float(audio.get("confidence", 0.5))

        if text is not None and isinstance(text, dict):
            text_val = float(text.get("valence", 0.0))
            text_aro = float(text.get("arousal", 0.5))
            text_dom = str(text.get("dominant", "neutral"))
            text_conf = float(text.get("confidence", 0.5))

            # 60% Audio Prosody / 40% Text NLP Fusion
            valence = 0.6 * audio_val + 0.4 * text_val
            arousal = 0.6 * audio_aro + 0.4 * text_aro
            dominant = audio_dom if audio_conf > 0.6 else text_dom
            confidence = max(audio_conf, text_conf)
        else:
            valence, arousal, dominant, confidence = audio_val, audio_aro, audio_dom, audio_conf

    elif text is not None and isinstance(text, dict):
        valence = float(text.get("valence", 0.0))
        arousal = float(text.get("arousal", 0.5))
        dominant = str(text.get("dominant", "neutral"))
        confidence = float(text.get("confidence", 0.5))
    else:
        valence, arousal, dominant, confidence = 0.0, 0.5, "neutral", 0.0

    return {
        "valence": round(max(-1.0, min(1.0, valence)), 3),
        "arousal": round(max(0.0, min(1.0, arousal)), 3),
        "dominant": dominant,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "timestamp": now_ms,
    }
```

---

### 3.2 44-Emotion Circumplex Mapper & Acoustic Centroid
- **File:** [`app/services/emotion/audio_signal.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/services/emotion/audio_signal.py)
- **Architecture & Rationale:** Maps Hume AI's 43 raw emotion probability scores onto a 2D Cartesian plane $(\text{Valence} \in [-1, 1], \text{Arousal} \in [0, 1])$ using Russell's Circumplex Model of Affect.
- **Circumplex Mapping Table (Sample):**

| Emotion Identifier | Valence ($v_i$) | Arousal ($a_i$) | Emotion Identifier | Valence ($v_i$) | Arousal ($a_i$) |
| :--- | :---: | :---: | :--- | :---: | :---: |
| **anger** | $-0.8$ | $0.8$ | **joy** | $+0.9$ | $0.7$ |
| **frustration** | $-0.7$ | $0.7$ | **calmness** | $+0.7$ | $0.1$ |
| **anxiety** | $-0.7$ | $0.7$ | **enthusiasm** | $+0.8$ | $0.8$ |
| **disappointment** | $-0.6$ | $0.3$ | **gratitude** | $+0.8$ | $0.3$ |
| **distress** | $-0.8$ | $0.8$ | **amusement** | $+0.8$ | $0.7$ |
| **confusion** | $-0.2$ | $0.5$ | **neutral** | $0.0$ | $0.3$ |

- **Exact Centroid Calculation:**
```python
weighted_valence = sum(score * EMOTION_CIRCUMPLEX_MAP.get(name, (0.0, 0.5))[0] for name, score in emotions)
weighted_arousal = sum(score * EMOTION_CIRCUMPLEX_MAP.get(name, (0.0, 0.5))[1] for name, score in emotions)
total_score = sum(score for _, score in emotions)

valence = weighted_valence / total_score if total_score > 0 else 0.0
arousal = weighted_arousal / total_score if total_score > 0 else 0.5
```

---

### 3.3 4-Tier Parallel Cognitive Memory Retriever
- **File:** [`app/services/memory/retriever.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/services/memory/retriever.py)
- **Architecture & Rationale:** Avoids serial retrieval bottlenecks by fanning out across Redis, pgvector, Postgres, and FalkorDB simultaneously using Python `asyncio.gather()`.
- **Exact Code Implementation:**
```python
async def retrieve_all_memory(
    contact_id: Optional[str],
    org_id: str,
    agent_id: Optional[str] = None,
    query_text: str = "",
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    config = config or {}
    call_id = config.get("call_id")

    short_term_task = short_term.get_call_memory(call_id) if call_id else asyncio.sleep(0, result=None)
    long_term_task = long_term.retrieve_relevant_facts(contact_id, org_id, query_text) if contact_id and org_id else asyncio.sleep(0, result=[])
    episodic_task = episodic.get_recent_episodes(contact_id, org_id, limit=config.get("episodic_limit", 3)) if contact_id and org_id else asyncio.sleep(0, result=[])
    graph_task = _fetch_graph_context(contact_id) if contact_id else asyncio.sleep(0, result={})

    st_res, lt_res, ep_res, gr_res = await asyncio.gather(
        short_term_task, long_term_task, episodic_task, graph_task, return_exceptions=True
    )

    return {
        "short_term": st_res if not isinstance(st_res, Exception) else None,
        "long_term": lt_res if isinstance(lt_res, list) else [],
        "episodic": ep_res if isinstance(ep_res, list) else [],
        "graph": gr_res if isinstance(gr_res, dict) else {},
    }
```

---

### 3.4 VA-ICECoT Intent Detection Engine
- **File:** [`app/services/intent/detector.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/services/intent/detector.py)
- **Architecture & Rationale:** Implements Verbalized Intent Articulation (SWI-inspired: `"To [verb] [what]"`). Extracts slot values and primary/secondary intent in a single fast Groq JSON inference turn.
- **Exact Code Snippet:**
```python
async def detect(
    transcript_turn: str,
    emotion_state: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, str]]] = None,
    agent_intents: Optional[List[Dict[str, Any]]] = None,
    filled_slots: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    all_intents = SYSTEM_INTENTS + [i.get("slug") for i in (agent_intents or []) if isinstance(i, dict)]

    prompt = f"""You are an intent detection AI analyzing a voice call transcript turn.
The caller just said: "{transcript_turn}"
Context: Caller need: {emotion_state.get('caller_need', '')}, Slots: {json.dumps(filled_slots or {})}
Available intents: {json.dumps(all_intents)}

Return ONLY valid JSON:
{{
  "intent": "one of available intents",
  "confidence": 0.85,
  "intent_articulation": "To [verb] [what] — concise statement of intent",
  "entities": ["entity1"],
  "slot_data": {{"key": "value"}},
  "secondary_intent": null,
  "is_terminal": false
}}"""
    # Executes via llm_service with strict JSON parse fallback
```

---

### 3.5 Emotion × Intent Combined Rules Engine
- **File:** [`app/services/intent/combined_rules.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/services/intent/combined_rules.py)
- **Architecture & Rationale:** Evaluates simultaneous multidimensional conditions ($\text{Intent} \land \text{Emotion}$) to execute deterministic overrides before generating LLM text.
- **Exact Code Snippet:**
```python
def evaluate(
    emotion_state: Dict[str, Any],
    intent_state: Dict[str, Any],
    agent_combined_rules: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    if not intent_state or not intent_state.get("intent"):
        return None

    all_rules = SYSTEM_COMBINED_RULES + (agent_combined_rules or [])
    detected_intent = intent_state.get("intent")
    confidence = float(intent_state.get("confidence", 0.0))

    for rule in all_rules:
        if rule.get("intent") and rule.get("intent") != detected_intent:
            continue
        if confidence < float(rule.get("min_confidence", 0.65)):
            continue
        if not check_emotion_condition(emotion_state, rule.get("emotion_condition", {})):
            continue

        return {
            "rule_matched": rule.get("id", "custom_rule"),
            "intent": detected_intent,
            "action": rule.get("action", "none"),
            "instruction": rule.get("instruction", ""),
            "skip_llm_response": bool(rule.get("skip_llm_response", False)),
        }
    return None
```

---

### 3.6 Action Connector Dispatcher (Registry Model)
- **File:** [`app/services/connectors/dispatcher.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/services/connectors/dispatcher.py)
- **Architecture & Rationale:** Replaced monolithic $111$-line if/elif god-node with an $O(1)$ keyword-to-handler registry dict, eliminating graph betweenness coupling.
- **Exact Code Snippet:**
```python
CONNECTOR_REGISTRY: Dict[str, Callable] = {
    "google":     _handle_google_cal,
    "calendar":   _handle_google_cal,
    "hubspot":    _handle_hubspot,
    "salesforce": _handle_salesforce,
    "webhook":    _handle_webhook,
    "zapier":     _handle_webhook,
    "whatsapp":   _handle_whatsapp,
    "slack":      _handle_slack,
    "supabase":   _handle_supabase,
    "postgres":   _handle_supabase,
}

async def fire_connector(
    connector_type: str, config: Dict[str, Any], payload: Dict[str, Any]
) -> Dict[str, Any]:
    ctype = connector_type.lower()
    handler = next((fn for key, fn in CONNECTOR_REGISTRY.items() if key in ctype), None)
    if handler is None:
        return {"success": False, "error": f"Unknown connector type '{connector_type}'"}
    return await handler(config, payload)
```

---

### 3.7 BYOK AES-256-GCM Cryptographic Subsystem
- **File:** [`app/utils/encryption.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/utils/encryption.py)
- **Architecture & Rationale:** Implements authenticated symmetric encryption for all credentials at rest. Prepend a $12$-byte random nonce to ciphertext with a $16$-byte authentication tag.
- **Exact Code Snippet:**
```python
def encrypt_config(config: dict) -> str:
    plaintext = json.dumps(config).encode("utf-8")
    aesgcm = AESGCM(KEY_BYTES)
    nonce = os.urandom(12)  # 96-bit random nonce
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")

def decrypt_config(ciphertext: Any) -> dict:
    raw = base64.b64decode(ciphertext_str)
    nonce, encrypted_data = raw[:12], raw[12:]
    aesgcm = AESGCM(KEY_BYTES)
    plaintext = aesgcm.decrypt(nonce, encrypted_data, None)
    return json.loads(plaintext.decode("utf-8"))
```

---

### 3.8 LiveKit WebRTC Session & Token Manager
- **File:** [`app/services/livekit_service.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/services/livekit_service.py)
- **Architecture & Rationale:** Centralized singleton managing room creation (`empty_timeout=300s`, `departure_timeout=10s`) and issuing scoped audio-only JWT tokens.
- **Exact Code Snippet:**
```python
class LiveKitService:
    ROOM_TTL_EMPTY_TIMEOUT = 300
    ROOM_TTL_DEPARTURE_TIMEOUT = 10
    TOKEN_TTL_SECONDS = 14400  # 4 hours

    def generate_agent_token(self, room_name: str, agent_id: str) -> str:
        return self._build_token(
            room_name=room_name,
            identity=f"agent-{agent_id}",
            display_name=f"VoCall Agent {agent_id}",
            can_publish=True, can_subscribe=True, can_publish_data=True
        )
```

---

### 3.9 pgvector Semantic Memory Store
- **File:** [`app/services/memory/long_term.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/services/memory/long_term.py)
- **Architecture & Rationale:** Computes 1536-dimensional embeddings for facts and retrieves top-$k$ relevant memories via cosine similarity matching.
- **Exact Retrieval Logic:**
```python
async def retrieve_relevant_facts(contact_id: str, org_id: str, query: str, limit: int = 5):
    query_emb = await generate_embedding(query)
    # Invokes PostgreSQL match_memories RPC with HNSW index
    res = supabase.rpc("match_memories", {
        "query_embedding": query_emb,
        "match_contact_id": contact_id,
        "match_org_id": org_id,
        "match_count": limit
    }).execute()
    return res.data or []
```

---

### 3.10 FalkorDB Knowledge Graph Service
- **File:** [`app/services/memory/graph.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/services/memory/graph.py)
- **Architecture & Rationale:** Maintains an isolated graph per caller (`contact_{contact_id}`). Tracks entities, mentions, and recurring frustrations using OpenCypher queries.
- **Sample Cypher Operations:**
```cypher
MERGE (c:Contact {id: $contact_id})
MERGE (t:Topic {name: $topic})
MERGE (c)-[r:FRUSTRATED_ABOUT]->(t)
ON CREATE SET r.count = 1, r.last_seen = $timestamp
ON MATCH SET r.count = r.count + 1, r.last_seen = $timestamp;
```

---

### 3.11 Conversational Tone Adapter
- **File:** [`app/services/emotion/tone_adapter.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/services/emotion/tone_adapter.py)
- **Architecture & Rationale:** Translates fused valence/arousal into dynamic prompt steering instructions injected before LLM generation.
- **Output Sample:**
```
[TONE INSTRUCTION: Caller is experiencing high frustration (Valence: -0.82). 
Adopt a calm, highly empathetic demeanor. Acknowledge the issue immediately, 
avoid defensive phrasing, and provide a clear immediate resolution path.]
```

---

### 3.12 WebCall SSE Real-Time Streamer
- **File:** [`app/routers/calls.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/routers/calls.py)
- **Architecture & Rationale:** Provides zero-polling real-time updates of transcript turns, live emotion scores, and agent tool execution to the frontend dashboard over Server-Sent Events.
- **Endpoint:** `GET /api/v1/calls/webcall/{call_id}/events` reading from Upstash Redis `webcall:{call_id}:events`.

---

### 3.13 8-Stage Asynchronous Post-Call Pipeline
- **File:** [`trigger/post_call_pipeline.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/trigger/post_call_pipeline.py)
- **Architecture & Rationale:** Non-blocking async execution worker triggered on call termination:
  1. `LRANGE stm:{call_id}` -> 2. Groq LLaMA-3.3-70B Summarization -> 3. JSON Entity/Topic Extraction -> 4. `nomic-embed-text` 1536-dim Embedding -> 5. Insert `memory_episodic` -> 6. Upsert `memory_long_term` (pgvector) -> 7. Merge FalkorDB Graph -> 8. Connector Fanout & `DEL stm:{call_id}`.

---

### 3.14 WebCallModal & Dynamic Voice Orb (Frontend)
- **Files:** [`src/components/WebCallModal.tsx`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/src/components/WebCallModal.tsx) & [`vocall/frontend/src/components/WebCallModal.tsx`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/vocall/frontend/src/components/WebCallModal.tsx)
- **Architecture & Rationale:** Interactive WebRTC voice calling modal with a 4-phase state machine (`idle` $\to$ `connecting` $\to$ `active` $\to$ `ended`), 3-state dynamic Voice Orb reflecting agent speaking (expanding purple ping), user speaking (emerald acoustic pulse), and listening modes, accompanied by live Server-Sent Events (SSE) transcript and telemetry.

---

### 3.15 Voice Agent Intention-Centric Chain-of-Thought (VA-ICECoT) Engine
- **File:** [`app/services/voice/va_icecot.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/services/voice/va_icecot.py)
- **Architecture & Rationale:** Integrates the IntentionESC and JX4MEI chain-of-thought methodologies directly into the real-time voice loop. Generates structured `<meta_thought>` tags reasoning over caller emotional valence, latent conversational intentions, and required slot parameters prior to producing agent speech responses.

---

### 3.16 In-Browser LiveKit WebCall Audio Pipeline
- **File:** [`app/services/webcall_pipeline.py`](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/app/services/webcall_pipeline.py)
- **Architecture & Rationale:** Dedicated server-side WebRTC voice streaming pipeline for browser test sessions. Ingests raw audio frames via LiveKit rooms, manages STT transcription, coordinates dual emotion fusion and slot tracking, and streams real-time updates to Upstash Redis SSE message queues.

---

## 5. Section 4: Comprehensive Mathematical Formulations

### Formulation 1: Dual-Signal Emotion Fusion
When both acoustic prosody ($\mathbf{E}_{\text{audio}}$) and linguistic text ($\mathbf{E}_{\text{text}}$) are available:
$$\text{Valence}_{\text{fused}} = 0.6 \cdot \text{Valence}_{\text{audio}} + 0.4 \cdot \text{Valence}_{\text{text}}$$
$$\text{Arousal}_{\text{fused}} = 0.6 \cdot \text{Arousal}_{\text{audio}} + 0.4 \cdot \text{Arousal}_{\text{text}}$$
$$\text{Dominant}_{\text{fused}} = \begin{cases} \text{Dominant}_{\text{audio}}, & \text{if } \text{Confidence}_{\text{audio}} > 0.6 \\ \text{Dominant}_{\text{text}}, & \text{otherwise} \end{cases}$$
$$\text{Confidence}_{\text{fused}} = \max(\text{Confidence}_{\text{audio}}, \text{Confidence}_{\text{text}})$$

---

### Formulation 2: Acoustic Emotion Circumplex Mapping
Given $N=43$ raw emotion scores $s_i \in [0, 1]$ from Hume AI and circumplex coordinate lookup $(v_i, a_i) \in [-1, 1] \times [0, 1]$:
$$\text{Valence}_{\text{audio}} = \frac{\sum_{i=1}^{N} s_i \cdot v_i}{\sum_{i=1}^{N} s_i}, \quad \text{Arousal}_{\text{audio}} = \frac{\sum_{i=1}^{N} s_i \cdot a_i}{\sum_{i=1}^{N} s_i}$$
$$\text{Dominant}_{\text{audio}} = \arg\max_{i} (s_i), \quad \text{Confidence}_{\text{audio}} = \max_{i} (s_i)$$

---

### Formulation 3: Frustration Metric & Autonomous Trigger
$$\text{FrustrationScore} = |\text{Valence}_{\text{fused}}| \quad \text{for } \text{Valence}_{\text{fused}} < 0$$
$$\text{AlertTrigger} = \begin{cases} 1, & \text{if } \text{Valence}_{\text{fused}} < -\theta_{\text{threshold}} \quad (\text{where } \theta = 0.70) \\ 0, & \text{otherwise} \end{cases}$$

---

### Formulation 4: pgvector Cosine Similarity
Given a prompt embedding query vector $\mathbf{q} \in \mathbb{R}^{1536}$ and stored fact vector $\mathbf{f}_k \in \mathbb{R}^{1536}$:
$$\text{CosineSimilarity}(\mathbf{q}, \mathbf{f}_k) = \frac{\mathbf{q} \cdot \mathbf{f}_k}{\|\mathbf{q}\|_2 \|\mathbf{f}_k\|_2} = \frac{\sum_{j=1}^{1536} q_j f_{kj}}{\sqrt{\sum_{j=1}^{1536} q_j^2} \sqrt{\sum_{j=1}^{1536} f_{kj}^2}}$$
$$\text{CosineDistance}(\mathbf{q}, \mathbf{f}_k) = 1 - \text{CosineSimilarity}(\mathbf{q}, \mathbf{f}_k)$$

---

### Formulation 5: Authenticated AES-256-GCM Encryption Scheme
Given 256-bit key $K \in \{0, 1\}^{256}$, 96-bit random nonce $N \in \{0, 1\}^{96}$, and plaintext JSON $P$:
$$C, T = \text{AES-GCM-Encrypt}(K, N, P)$$
$$\text{StoredPayload} = \text{Base64}\Big( N \,\|\, C \,\|\, T \Big)$$
where $T \in \{0, 1\}^{128}$ is the 16-byte cryptographic authentication tag.

---

### Formulation 6: Joint Recognition Balance Metric (JRBM)
Evaluates joint intent classification and emotion recognition accuracy:
$$\text{JRBM} = 2 \cdot \frac{\text{Accuracy}_{\text{intent}} \cdot \text{Accuracy}_{\text{emotion}}}{\text{Accuracy}_{\text{intent}} + \text{Accuracy}_{\text{emotion}}}$$

---

## 6. Section 5: Component Interaction & Dependency Matrix

```
+--------------------------+-----------------------+------------------------+--------------------------+
| Source Subsystem         | Target Dependency     | Protocol / Transport   | Failure Handling         |
+--------------------------+-----------------------+------------------------+--------------------------+
| Real-Time Voice Pipeline | Groq Whisper / Sarvam | HTTPS / REST           | Logs error, empty text   |
| Real-Time Voice Pipeline | Hume AI Prosody       | HTTPS Multipart        | Fallback to text emotion |
| Real-Time Voice Pipeline | Groq LLaMA 3.3 70B    | HTTPS / SSE Streaming  | Fallback to Cerebras AI  |
| Real-Time Voice Pipeline | Cartesia / Sarvam TTS | HTTPS / Raw PCM Bytes  | Fallback to Cartesia     |
| Real-Time Voice Pipeline | Upstash Redis         | HTTPS REST             | Non-blocking log warning |
| Memory Retriever         | Supabase pgvector     | PostgREST RPC / TCP    | Returns empty list       |
| Memory Retriever         | FalkorDB Graph        | RESP3 Redis Protocol   | Returns empty dict       |
| Connector Dispatcher     | Slack / HubSpot / Cal | HTTPS REST             | Returns error dict       |
| WebCall Modal            | LiveKit Cloud         | WebRTC SRTP            | Reconnects automatically |
| Post-Call Pipeline       | Trigger.dev           | Serverless Task Event  | Auto-retries 3 times     |
+--------------------------+-----------------------+------------------------+--------------------------+
```

---

*Document Authoritative Source: `latest docxxx/components.md` — VoCall Engineering Architecture Group.*
