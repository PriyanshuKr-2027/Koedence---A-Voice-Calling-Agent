# VoCall — System & API Setup Requirements (`requirement.md`)

**Document Version:** 2.0  
**Last Updated:** July 2026  
**Status:** Authoritative Specification  
**Related Documents:** [PRD.md](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/vocall/docs/PRD.md), [TRD.md](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/vocall/docs/TRD.md)

---

## 1. Quick Summary Table

| Service / API | Category / Purpose | Status | Where to Get Key / Setup |
| :--- | :--- | :--- | :--- |
| **FalkorDB** | **Knowledge Graph Memory Tier** (Entity & Frustration OpenCypher Graph) | **MUST HAVE (RESEARCH CORE)** | Local Docker or [falkordb.com](https://falkordb.com) |
| **Hume AI** | **Real-Time Acoustic & Prosody Emotion Detection** | **MUST HAVE (RESEARCH CORE)** | [hume.ai](https://hume.ai) |
| **Supabase** | Primary Postgres DB, Auth & Vector Fact Storage (`pgvector`) | **MUST HAVE** | [supabase.com](https://supabase.com) |
| **Groq API** | LLaMA-3.3-70b LLM Inference & Text Emotion Signal Fusion | **MUST HAVE** | [console.groq.com](https://console.groq.com) |
| **Upstash Redis** | Short-Term In-Call Memory (`stm:{id}`) & SSE Real-time Events | **MUST HAVE** | [upstash.com](https://upstash.com) |
| **LiveKit** | Real-time WebRTC Audio Infrastructure for Web Calls | **MUST HAVE** | [livekit.io](https://livekit.io) |
| **Cartesia AI** | Ultra-low Latency Neural Voice Synthesis (TTS) | **MUST HAVE** | [cartesia.ai](https://cartesia.ai) |
| **Twilio** | Inbound/Outbound Telephony Phone Numbers & SIP Media Streams | **OPTIONAL** (Phone Calls) | [twilio.com](https://twilio.com) |
| **Sarvam AI** | Hindi & Hinglish Speech-to-Text / Text-to-Speech | **OPTIONAL** (Indian Languages) | [sarvam.ai](https://sarvam.ai) |
| **Resend** | Post-Call Summary Email Dispatch | **OPTIONAL** | [resend.com](https://resend.com) |
| **Trigger.dev** | Async Background Workflow Tasks | **OPTIONAL** | [trigger.dev](https://trigger.dev) |
| **Cerebras AI** | Sub-second LLM Fallback Provider | **OPTIONAL** | [cerebras.ai](https://cerebras.ai) |

---

## 2. Core Research Pillars & Mandatory Infrastructure

### A. FalkorDB (Knowledge Graph Memory Tier) — MUST HAVE
Stores persistent entity relationship chains, causal frustration paths, and contact interaction graphs across call episodes.
- **Environment Variables**:
  ```env
  FALKORDB_HOST=127.0.0.1
  FALKORDB_PORT=6379
  ```
- **Local Docker Setup**:
  ```bash
  docker run -p 6379:6379 -d --name falkordb falkordb/falkordb:latest
  ```

### B. Hume AI (Real-Time Audio Emotion & Prosody Detection) — MUST HAVE
Analyzes acoustic speech waveforms for continuous emotional signals (valence, arousal, prosody, frustration score).
- **Environment Variable**:
  ```env
  HUME_API_KEY=your_hume_api_key_here
  ```

### C. Supabase (Database, Vector Search & Auth) — MUST HAVE
Provides PostgreSQL database storage, auth management, and `pgvector` for semantic long-term memory facts.
- **Environment Variables**:
  ```env
  NEXT_PUBLIC_SUPABASE_URL=https://<your-project-id>.supabase.co
  NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOi...
  SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...
  ```

### D. Groq API (LLM Engine & Text Emotion Analysis) — MUST HAVE
Provides high-throughput LLaMA-3.3-70b inference and text-based emotion analysis.
- **Environment Variable**:
  ```env
  GROQ_API_KEY=gsk_...
  ```

### E. Upstash Redis (Short-Term Working Memory) — MUST HAVE
- **Environment Variables**:
  ```env
  UPSTASH_REDIS_REST_URL=https://<your-db>.upstash.io
  UPSTASH_REDIS_REST_TOKEN=AX...
  ```

### F. LiveKit Cloud (WebRTC Audio Streaming) — MUST HAVE
- **Environment Variables**:
  ```env
  LIVEKIT_URL=wss://<your-subdomain>.livekit.cloud
  LIVEKIT_API_KEY=API...
  LIVEKIT_API_SECRET=secret...
  ```

### G. Cartesia AI (Sonic-2 Neural Voice TTS) — MUST HAVE
- **Environment Variable**:
  ```env
  CARTESIA_API_KEY=...
  ```

### H. Master Encryption Key (AES-256 BYOK Security) — MUST HAVE
- **Environment Variable**:
  ```env
  ENCRYPTION_KEY=32_character_hex_or_string_key_here
  ```

---

## 3. Optional & Multilingual Infrastructure

### A. Sarvam AI (Hinglish & Indic Audio Models)
- **Environment Variable**: `SARVAM_API_KEY=...`

### B. Twilio Telephony (PSTN Outbound & Inbound Calls)
- **Environment Variables**:
  ```env
  TWILIO_ACCOUNT_SID=AC...
  TWILIO_AUTH_TOKEN=...
  TWILIO_PHONE_NUMBER=+1234567890
  ```

### C. Resend Email Delivery
- **Environment Variable**: `RESEND_API_KEY=re_...`

### D. Trigger.dev Background Job Pipeline
- **Environment Variable**: `TRIGGER_API_KEY=tr_...`

---

Approved by VoCall Infrastructure Team.
