# VoCall — Comprehensive Feature Matrix & Specifications

**Document Version:** 2.0  
**Last Updated:** July 2026  
**Status:** Complete  
**Related Documents:** [PRD.md](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/vocall/docs/PRD.md), [TRD.md](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/vocall/docs/TRD.md)

---

## 1. Agent Studio & Builder Suite

### 1.1 Prompt-First Agent Creation
- **Capability:** Free-text system instruction box serving as the primary agent configuration interface.
- **Provider & Implementation:** Supabase Postgres (`agents.system_prompt`).
- **Rationale:** Reduces onboarding friction compared to rigid multi-step wizard forms.

### 1.2 AI Prompt Enhancer
- **Capability:** One-click enhancement that restructures and optimizes rough prompt drafts into high-performing voice agent prompts.
- **Provider & Implementation:** Groq LPU (`llama-3.3-70b-versatile`) via endpoint `POST /api/v1/agents/{id}/enhance-prompt`.
- **Rationale:** ~400ms latency ensures instant UI response without interrupting developer flow.

### 1.3 Pre-Built Use Case Templates
- **Capability:** One-click template chips (Customer Support, Sales Qualification, Appointment Booking, Healthcare Triage, Debt Recovery, HR Screening).
- **Provider & Implementation:** Frontend preset registry appending domain-specific guidelines into prompt.

### 1.4 Dual UI / Code View Editor
- **Capability:** Toggle between structured visual form controls and a syntax-highlighted raw JSON config editor (`agents.config`).
- **Provider & Implementation:** Next.js frontend state renderer + Monaco/JSON syntax view.

### 1.5 Web Domain Metadata Scraper
- **Capability:** Paste company website URL to automatically extract business name, service description, and brand voice guidelines.
- **Provider & Implementation:** FastAPI Scraper (`/api/v1/import-domain`) parsing OpenGraph and meta tags.

---

## 2. Voice Catalog, STT & TTS Routing

### 2.1 Speech-to-Text (STT) Routing

| Language Target | Provider | Model | Latency | Key Rationale |
| --- | --- | --- | --- | --- |
| **English** | Groq | Whisper Large-v3 | ~150ms | Ultra-fast LPU inference, high word accuracy rate |
| **Hindi / Hinglish** | Sarvam AI | Saarika v2 | ~200ms | Native code-switching training; handles natural mixed Hindi-English speech |

### 2.2 Text-to-Speech (TTS) Routing

| Mode / Language | Provider | Model | TTFAB Latency | Key Rationale |
| --- | --- | --- | --- | --- |
| **English (Standard)** | Cartesia | Sonic-2 | ~80ms | Lowest latency English synthesis available |
| **Hindi / Hinglish** | Sarvam AI | Bulbul v2 | ~150ms | Natural Indian accent & language cadence |
| **Emotion-Conditioned** | Hume AI | Octave 2 | ~75ms | Modulates pitch, warmth, and speed based on caller emotion score |

---

## 3. Dual-Signal Emotion Engine

### 3.1 Acoustic Emotion Signal (Audio)
- **Capability:** Extracts paralinguistic tone features (pitch, cadence, stress, tension) from raw speech audio.
- **Provider:** Hume AI Expression Measurement API.

### 3.2 NLP Emotion Signal (Text)
- **Capability:** Real-time sentiment and intent analysis on caller speech transcripts per turn.
- **Provider:** Groq LLaMA 3.3 70B (JSON Mode).

### 3.3 Multimodal Emotion Fusion
- **Capability:** Computes unified valence and arousal state ($E_{fused} = \alpha \cdot E_{audio} + (1-\alpha) \cdot E_{text}$).
- **Provider:** Custom FastAPI Fusion Engine (`app/services/emotion/fusion.py`).

### 3.4 Adaptive Voice & Prompt Behaviors
- **Empathetic Prompt Injection:** Automatically injects tone-softening guidelines into the system prompt when caller frustration $\ge 0.75$ (`tone_adapter.py`).
- **Voice Pitch Adaptation:** Modulates TTS voice warmth and speed based on caller emotion.
- **Automated Escalation Triggers:** Fires connectors (Slack alert or priority webhook) when frustration score exceeds configured threshold.

---

## 4. 4-Tier Hybrid Memory Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                4-TIER HYBRID MEMORY MATRIX                              │
├─────────────────┬───────────────────┬───────────────────┬───────────────────────────────┤
│ Tier            │ Storage Engine    │ Scope             │ Primary Function              │
├─────────────────┼───────────────────┼───────────────────┼───────────────────────────────┤
│ 1. Short-Term   │ Upstash Redis     │ Active Call       │ Live transcript & turn buffer │
│ 2. Long-Term    │ Supabase pgvector │ Contact Semantic  │ Top-5 vector fact retrieval   │
│ 3. Episodic     │ Supabase Postgres │ Contact History   │ Last 3 post-call summaries    │
│ 4. Knowledge    │ FalkorDB          │ Contact Relational│ Cypher entity relationship    │
└─────────────────┴───────────────────┴───────────────────┴───────────────────────────────┘
```

- **DPDP Act Compliance ("Forget Me"):** Single API call `DELETE /api/v1/contacts/{id}/memory` cascades deletion across Redis, pgvector, Postgres, and FalkorDB graph.

---

## 5. VA-ICECoT Intent Engine & Decision Matrix

- **Step 1 (Classification):** Turn-by-turn intent detection (`detector.py`) classifying into `inquiry`, `complaint`, `transaction`, `clarification`, `chitchat`, `escalation`.
- **Step 2 (Slot Carry-Forward):** Redis-backed slot manager (`slot_manager.py`) carrying forward extracted parameters across turns.
- **Step 3 (Emotion × Intent Matrix):** Multi-condition rule evaluator (`combined_rules.py` & `resolver.py`) triggering automated resolution actions.

---

## 6. Action Connectors & Integration Suite

VoCall provides 8 pre-built action connectors managed through a central dispatcher (`app/services/connectors/dispatcher.py`) with AES-256-GCM BYOK credential encryption:

1. **WhatsApp Connector:** Post-call summaries and appointment reminders via Twilio Content API.
2. **Google Calendar Connector:** Live free/busy availability query (`check_availability`) and calendar event creation (`book_appointment`).
3. **HubSpot CRM Connector:** Mid-call lead generation (`log_lead`) and post-call engagement synchronization (`sync_call_summary`).
4. **Salesforce CRM Connector:** OAuth2 token refresh and post-call Task logging (`sync_call_result`).
5. **Slack Connector:** Block Kit post-call summary cards and real-time High-Frustration alert broadcasts (`send_frustration_alert`).
6. **Custom Webhooks:** Async HMAC-SHA256 signed HTTP POST requests with mustache token replacement.
7. **Postgres / Supabase SQL Connector:** Parameterized read-only SQL queries executed mid-call to fetch account status.
8. **Tone Adapter Connector:** Dynamic prompt and TTS parameter modifiers triggered by caller emotional state.

---

## 7. Web Call Testing Studio (Ananya UI / `WebCallModal`)

- **4-Phase Lifecycle:** `idle` $\rightarrow$ `connecting` $\rightarrow$ `active` $\rightarrow$ `ended`.
- **Dynamic Voice Orb:** Visual state feedback (purple ping pulse when agent speaks, emerald pulse when user speaks, violet glow when thinking).
- **Live Stream View:** Auto-scrolling transcript window with speaker tags and duration counter.
- **Post-Call Decision Card:** Option to "Save & View Analysis" (triggers Trigger.dev pipeline) or "Discard Test Record".

---

Approved by VoCall Product & Engineering Team.
