# VoCall — Comprehensive UI & Design System Specifications (`design.md`)

**Document Version:** 2.1  
**Last Updated:** September 2026  
**Status:** Approved & Production Implemented  
**Primary Target Implementations:** `src/components/` (Vite 8 + React 19 + Framer Motion 12 + Tailwind) & `vocall/frontend/` (Next.js 14 App Router + Tailwind)  
**Brand Design Tokens:** Purple Accent `#7C3AED`, Sage Emerald `#4F7A65`, Dark Slate Surface `#0F172A` / `#1E293B`, Neutral Warm Gray `#F6F5F2`

---

## 0. Global Layout & App Shell

Applies to the dashboard container across all authenticated routes.

### 0.1 3-Panel Responsive Layout (`DashboardShell.tsx`)

#### 1. Left Primary Sidebar (64px, Icon-Only Rail)
- **Top Brand Logo**: VoCall soundwave icon with glowing purple pulse.
- **Navigation Icons** (Tooltips on hover):
  - Dashboard (`LayoutGrid`)
  - Agents (`Bot`)
  - Contacts & Memory (`Users`)
  - Calls & History (`PhoneCall`)
  - Analytics (`BarChart3`)
  - Action Connectors (`Plug`)
  - Telephony & KYC (`PhoneForwarded`)
  - API Keys BYOK (`KeyRound`)
- **Bottom User Avatar**: Org switcher, user profile badge, and sign out dropdown.

#### 2. Secondary Contextual Sidebar (260px)
- Current workspace/space name with switcher dropdown.
- Search input with keyboard shortcut (`⌘K` / `Ctrl+K`).
- Primary `+ New` button contextual to active route (e.g. `+ New Agent`, `+ Add Contact`).
- Filtered item list with status indicators (e.g. agent published badge, contact last call time).

#### 3. Main Dynamic Content Canvas
- Full viewport minus sidebar widths, with high-performance Framer Motion view transitions.

---

## 1. Web Call Modal (`WebCallModal.tsx`) Architecture & Lifecycle

The **WebCallModal** provides a real-time, browser-native WebRTC sandbox for testing voice agents end-to-end without PSTN telephony hardware.

### 1.1 Header Trigger (`AgentBuilder.tsx`)
- **Button Component**: `"Talk To Agent"`
- **Visuals**: Primary violet pill outline with `PhoneCall` icon (`border-[#7C3AED]/50 text-[#A78BFA] hover:bg-[#7C3AED]/20`).
- **Behavior**: Opens the full-viewport frosted glass modal overlay `WebCallModal`.

### 1.2 Modal Overlay & Container
- **Backdrop**: Dark frosted glass overlay (`bg-black/75 backdrop-blur-md`).
- **Container**: Elevated dark slate card (`bg-slate-900/95 border border-slate-700/80 rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden`).

### 1.3 The 4-Phase Lifecycle State Machine

```
+----------------+      Mic Granted       +----------------+
|     IDLE       | ---------------------> |   CONNECTING   |
| (Name + Mic)   |      & Start Click     | (LiveKit Room) |
+----------------+                        +----------------+
                                                   |
                                                   | Token Minted
                                                   v
+----------------+      User Ends         +----------------+
|     ENDED      | <--------------------- |     ACTIVE     |
| (Save/Discard) |      or Pipeline Stop  | (Audio + SSE)  |
+----------------+                        +----------------+
```

#### Phase 1: Pre-Call Setup (`idle` / `requesting_mic`)
- **Customer Contact Identifier Input**:
  - Input field with `User` icon prefix: `"Your Name or Contact ID"`.
  - **Engineering Role**: Identifies contact in Supabase `contacts` table to trigger parallel 4-tier memory fanout lookup (`stm`, `pgvector`, episodic, FalkorDB graph) upon session start.
- **Voice Orb (Idle State)**:
  - 96px neutral slate orb with subtle breathing border and static `PhoneCall` icon.
- **Microphone Permission Sentinel**:
  - Live browser permission badge displaying mic device status and prompt to grant hardware access.
- **Primary CTA**: `"Start Web Call"` pill button (`bg-[#7C3AED] hover:bg-[#6D28D9] text-white shadow-lg shadow-purple-500/20`).

#### Phase 2: Connecting (`connecting`)
- **Pulsing Orb**: 96px orb with multi-ring expanding glow (`animate-pulse border-2 border-[#7C3AED] bg-[#7C3AED]/20`).
- **Loading Indicator**: Rotating `Loader2` spinner.
- **Telemetry Subtext**: Monospace status message: `"Connecting to LiveKit room… initializing memory buffers"`.

#### Phase 3: Active Call (`active`)
- **Header Bar**:
  - Live indicator: Blinking red pulse dot + `LIVE` monospace tag (`text-red-400 font-mono text-xs`).
  - Session Timer: Real-time monospace call timer formatted `M:SS`.
  - Quick End Button: Top-right `X` button.
- **Split-View Canvas**:
  - **Left Column: Dynamic 3-State Voice Orb & Controls (Width 300px)**:
    - **State A: Agent Speaking**: 112px enlarged violet orb (`bg-[#7C3AED]`) with dual expanding radar rings (`animate-ping opacity-30`) and waveform bars.
    - **State B: User Speaking**: 104px emerald orb (`bg-emerald-500`) with green acoustic pulse ring (`bg-emerald-500/20`).
    - **State C: Listening/Idle**: 96px soft glowing orb with subtle ripple.
    - **Live Acoustic Prosody Meter**: Visual meter indicating Hume AI valence/arousal score.
    - **Audio Controls**: Mute Mic (`Mic` / `MicOff`) and Mute Speaker (`Volume2` / `VolumeX`).
    - **End Call CTA**: Red pill button with `PhoneOff` icon (`bg-red-600/20 border border-red-500/40 text-red-400 hover:bg-red-600/30`).
  - **Right Column: Live Transcript & Real-Time Intelligence**:
    - **Auto-Scrolling Transcript Window**: Live message stream updated via Server-Sent Events (SSE) from `/api/v1/calls/webcall/{call_id}/events`.
      - **Agent Turns**: Left-aligned dark slate cards with `Bot` badge (`bg-slate-800 text-slate-100`).
      - **User Turns**: Right-aligned purple-tinted cards with `User` badge (`bg-[#7C3AED]/20 border border-[#7C3AED]/30 text-white`).
    - **Real-Time Intelligence Drawer**:
      - **VA-ICECoT Intent Badge**: Displays detected intention (e.g. `schedule_demo`, 96% confidence).
      - **Dynamic Slot Tracker**: Shows filled slots (e.g. `date: "tomorrow"`, `time: "2pm"`).
      - **During-Call Action Feedback**: Pill showing connector firing (e.g. `Google Calendar: Slot Available`).

#### Phase 4: Post-Call Decision & Retention (`ended`)
- **Completion Header**: Glowing green `CheckCircle2` badge with session total duration.
- **Summary Preview**: Compact turn count, extracted facts, and overall call emotion score.
- **Decision Actions**:
  - **Action 1 — Discard**: `Trash2` icon button (`border-slate-600 text-slate-400 hover:bg-slate-800`). Drops ephemeral records.
  - **Action 2 — Save & Review**: Primary violet button with `ExternalLink` icon. Commits call session, runs Trigger.dev post-call pipeline, and navigates directly to `/dashboard/calls/[call_id]`.

---

## 2. Agent Studio & Builder Suite (`AgentBuilder.tsx`)

### Persistent Top Header
- Editable agent name with status pill (`Draft` / `Published`).
- Quick Actions: `Talk To Agent` (WebCall), `Voice Sandbox`, `Save Configuration`, `Publish Agent`.

### 10 Structured Builder Tabs

```text
Identity ──► Persona ──► Voice ──► Telephony ──► Memory ──► Emotion ──► Advanced ──► Analysis ──► Connectors ──► Recent Calls
```

#### 2.1 Identity Tab
- Agent Name, Public Description, Agent Persona Avatar.
- **Website Metadata Importer**: URL input with `Import` button to auto-scrape company brand tone, service offerings, and FAQs.

#### 2.2 Persona & System Prompt Tab (`AgentPromptTab.tsx`)
- **System Prompt Canvas**: Multi-line syntax-aware instruction editor.
- **AI Prompt Enhancer**: One-click prompt optimizer calling Groq Llama 3.3 70B via `POST /api/v1/agents/{id}/enhance-prompt`.
- **Pre-Built Use Case Chips**: Quick-insert templates for Customer Support, Inbound Sales, Medical Triage, Debt Collection, and Appointment Scheduling.
- **Dual Visual / Raw JSON Editor Toggle**: Direct toggle between high-level form fields and raw JSON configuration.

#### 2.3 Voice Profile Tab (`AgentVoiceTab.tsx`)
- Multi-provider voice catalog cards (Cartesia Sonic-2, Sarvam AI Bulbul, Hume AI Octave).
- Inline audio preview player (`Play` / `Pause`) with latency and pricing metrics.
- Speech rate, temperature, and emotion-conditioning modulation sliders.

#### 2.4 Telephony & Ingress Tab (`AgentTelephonyTab.tsx`)
- Provisioned phone number selector (dropdown from `/api/v1/phone-numbers`).
- Telephony provider router (Twilio, Plivo, Exotel).
- Inbound call routing toggle and outbound CLI caller ID configuration.

#### 2.5 4-Tier Memory Configuration Tab (`AgentMemoryTab.tsx`)
- Master switch: `Enable Multi-Tier Cognitive Memory`.
- **Tier 1 (Short-Term)**: Upstash Redis turn buffer toggle (Always active by default).
- **Tier 2 (Long-Term Semantic)**: Supabase pgvector fact store with max facts slider (1–10).
- **Tier 3 (Episodic)**: Past call episode summaries with recall limit slider (1–5).
- **Tier 4 (Knowledge Graph)**: FalkorDB OpenCypher entity-relationship graph toggle.
- **Memory Injection Previewer**: Real-time simulated prompt injection box showing the exact memory context that will be injected for sample contacts.

#### 2.6 Dual-Signal Emotion & Intent Arc Tab
- Master switch: `Enable Emotion & Affective Computing`.
- Multimodal Signal Sources:
  - Text Signal: Groq NLP sentiment analysis (Always active).
  - Audio Signal: Hume AI paralinguistic tone analysis (Requires BYOK Hume key).
- Dynamic Tone Adapter toggles (e.g. de-escalate when frustration > 0.70).
- **VA-ICECoT Intent & Slot Configurator**: Define required slots per intent and configure during-call connector triggers.

#### 2.7 Advanced & Latency Tuning Tab
- Turn-taking latency sliders (barge-in sensitivity, silence threshold, speech back-off seconds).
- LLM Provider Selection: Groq LPU (Primary) with Cerebras sub-second fallback.
- Operational Calling Hours: Time-window restrictions and timezone selector.

#### 2.8 Analysis & Evaluation Tab
- Post-call summary prompt templates.
- Success evaluation rubrics (Goal Achieved, Lead Qualified, Issue Resolved, Human Escalated).
- Custom JSON extraction schema builder.

#### 2.9 Connectors & Integrations Tab
- Organization-wide and agent-specific connector card grid (WhatsApp, Google Calendar, HubSpot, Salesforce, Slack, Supabase SQL, Webhook).
- Separate sections for **During-Call Real-Time Tools** and **Post-Call Asynchronous Jobs**.

#### 2.10 Recent Calls Tab
- Filtered audit table of recent call sessions for this specific agent with emotion scores and transcript links.

---

## 3. Contacts & 4-Tier Memory Inspector (`ContactsManager.tsx`)

### 3.1 Contact Directory
- Search, filter, tag assignment, and CSV bulk import.
- Table columns: Name, Phone, Tags, Call Count, Last Call Timestamp, Average Emotion Rating.

### 3.2 4-Tier Memory Slide-Over Drawer
Clicking a contact opens a dedicated cognitive memory inspection panel displaying all 4 tiers:
1. **Short-Term Memory Buffer**: Shows active turn cache from Upstash Redis or idle status.
2. **Long-Term Semantic Facts**: Chronological card list of stored facts retrieved from Supabase pgvector with deletion actions.
3. **Episodic Call Summaries**: Past call history summaries with date, duration, and sentiment score.
4. **FalkorDB Knowledge Graph Context**: Interactive node-link graph visualization showing caller entities, topics, and frustration edges (`MENTIONED`, `FRUSTRATED_ABOUT`).

### 3.3 DPDP Act 2023 "Forget Me" Cascade Clearance
- Dedicated danger zone button: `Erase All Contact Memory (DPDP Act)`.
- Triggers `DELETE /api/v1/contacts/{id}/memory`, performing atomic cascading deletion across:
  - Redis live session keys (`stm:{call_id}`)
  - Supabase `contact_memories` pgvector embeddings
  - Supabase `call_episodes` summaries
  - FalkorDB OpenCypher contact node sub-trees

---

## 4. Calls & Audit Analytics (`CallsManager.tsx`)

### 4.1 Calls Audit Log
- Direction badges: `INBOUND` (green), `OUTBOUND` (blue), `WEBCALL` (purple).
- Status pills: `Completed`, `Failed`, `In-Progress`.
- Emotion rating indicator: Red (< -0.2), Yellow (-0.2 to +0.2), Green (> +0.2).

### 4.2 Comprehensive Call Detail View
- **Audio Replay**: Waveform audio player with playback speed and scrubbing.
- **Emotion Trajectory Arc**: Interactive Recharts time-series chart showing valence, arousal, and frustration shifts turn-by-turn.
- **Turn-by-Turn Transcript**: Full conversational dialogue with timestamps, speaker avatars, and paralinguistic tone badges.
- **VA-ICECoT & Tool Audit**: Inspection of intention classification confidence, extracted slot tokens, and connector execution logs.

---

## 5. Settings, Telephony & BYOK Credentials (`SettingsManager.tsx`)

### 5.1 Encrypted BYOK API Keys (`/api-keys`)
- Key cards for Groq, Hume AI, Cartesia, Sarvam AI, LiveKit, Upstash Redis, FalkorDB, Twilio, and Resend.
- All keys encrypted client-to-server via AES-256-GCM. Stored masked (e.g. `gsk_...3a9f`).

### 5.2 Telephony Setup & Number Provisioning
- Provider selection (Twilio, Plivo, Exotel).
- Provisioned number inventory with inbound/outbound agent mapping.

### 5.3 KYC Compliance Verification
- Document upload component supporting PDF, PNG, and JPG.
- Document types: Aadhaar, PAN, GST Certificate, Company Registration.
- Verification status badges (`Under Review`, `Approved`, `Rejected`).

---

*Approved by VoCall Frontend & UI Engineering Team.*
