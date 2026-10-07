# VoCall — Design Document (Pages & Tabs Reference)

**Version:** 1.0 | **Date:** April 2026 | **Author:** Priyanshu Kumar

> This document lists every screen, tab, and the fields/components on it. Use this as the checklist when building UI — one section per page. Brand color: purple `#7C3AED`.

---

## 0. Global Layout

### 0.1 App Shell (3-Panel Layout)

Applies to every page under `/dashboard/*`.

#### Left Sidebar (60px, icon-only, tooltips on hover)

- Dashboard (grid icon)
- Agents (bot icon)
- Spaces (layout icon)
- Contacts (users icon)
- Calls (phone icon)
- Analytics (chart icon)
- Connectors (plug icon)
- Settings (gear icon)
- API Keys (key icon)
- User avatar at bottom → dropdown: Profile, Logout

#### Second Panel (240px)

- Current space name + switcher dropdown
- Search bar
- "+ New" button
- Contextual list (agents / contacts / calls depending on section)

#### Main Panel

Fills remaining width, renders the page content below.

---

## 1. Auth Pages

### 1.1 Signup (`/signup`)

- Email input
- Password input
- Sign Up button
- Link to Login

### 1.2 Login (`/login`)

- Email input
- Password input
- Log In button
- Forgot password link
- Link to Signup

### 1.3 Password Reset (`/reset-password`)

- Email input → sends reset link (Resend)
- New password form (from reset link)

---

## 2. Onboarding Flow (`/onboarding`)

### Step 1 — Create Organization

- Organization name (text)
- Domain URL input + "Import" button (auto-fills name + description)
- Description (textarea, auto-filled or manual)
- Logo upload (circular preview)
- Continue button

### Step 2 — Create First Space

- Space name (default: "General")
- Continue button

### Step 3 — Create First Agent

- Prompt box (free text)
- Use case chips
- Continue button

### Step 4 — Voice Profile

- Voice card picker (preview + language tags)
- Continue button

### Step 5 — Setup Telephony

- Provider choice: Twilio (default) / Plivo / Exotel
- Calling hours (optional at this stage, can skip)
- Continue button

### Step 6 — Configure Memory

- Enable Memory toggle
- Tier toggles (short/long/episodic/graph) — defaults on
- Continue button

### Step 7 — Configure Emotion

- Enable Emotion toggle
- Text signal (always on) / Audio signal toggle (requires Hume key)
- Continue button

### Step 8 — Deploy + Test

- Test mode buttons: Chat | Web Call | Phone Call
- "Go to Dashboard" button

---

## 3. Dashboard Home (`/dashboard`)

- Heading: "Welcome, {user.name}"
- **3 Quick-Action Cards** (horizontal row):
  1. Create Agent → bot icon → `/dashboard/agents/new`
  2. Setup Memory → brain icon → `/dashboard/settings/memory`
  3. Setup Telephony → phone icon → `/dashboard/settings/telephony`
- **Stats Section — "Agents Overview"** (6 cards, 2 rows):
  - Row 1: Total Calls | Avg Duration | Successful Calls
  - Row 2: Failed Calls | Avg Emotion Score (colored: green/yellow/red) | Active Agents
  - Total Cost card shown in ₹ (INR) and $ (USD)

---

## 4. Agent Builder (`/dashboard/agents/[id]`)

### Header (persistent across all tabs)

- Agent name (editable inline)
- Chat button | Voice button | Talk To Agent button (`PhoneCall` icon, opens `WebCallModal`) | Save button | Publish button (purple, primary)

### Tab bar (10 tabs, horizontal)

```text
Identity → Persona → Voice Profile → Telephony → Memory → Emotion → Advanced → Analysis → Integrations → Recent Calls
```

### 4.1 Identity Tab

- Agent Name (text input)
- Avatar (image upload, circular preview)
- Description (textarea)
- Quick Import from Website: domain URL input + Import button

### 4.2 Persona Tab

- System Prompt (large textarea, primary input)
- "Enhance Prompt" button (purple, below textarea, shows spinner while loading)
- Use case chips (clickable, append to prompt): Customer Support | Sales | Appointment Booking | HR | Collections | Healthcare | Debt Recovery | Lead Qualification
- UI / Code toggle (top right) — Code mode shows raw JSON of full agent config

### 4.3 Voice Profile Tab

- Voice card grid, each card:
  - Play button (circular, left)
  - Voice name (bold)
  - Gender badge
  - Language tags: EN / HI / MA / Hinglish (colored chips)
  - Provider badge: Cartesia / Sarvam AI / Hume AI (right-aligned)
  - Cost bar (red = expensive, green = free)
  - Latency bar
  - Click to select (purple border highlight)
- Emotion-conditioned voice toggle: "Use Hume AI Octave for emotion-adaptive tone" (only shown if Emotion tab has audio signal enabled)

### 4.4 Telephony Tab

- Provider selector: Twilio (default) | Plivo | Exotel
- Assigned phone number (dropdown of numbers from Settings → Telephony)
- Inbound enabled toggle
- Outbound caller ID
- Link to full Telephony Settings page

### 4.5 Memory Tab (VoCall-exclusive)

- Master toggle: "Enable Memory"
- **4 Tier Cards** (shown when enabled):
  1. **Short-term** — Badge: "Upstash Redis" — always on, no config
  2. **Long-term** — Badge: "Supabase pgvector" — toggle + slider "Max facts retrieved" (1–10, default 5)
  3. **Episodic** — Badge: "Supabase Postgres" — toggle + slider "Episodes to retrieve" (1–5, default 3)
  4. **Knowledge Graph** — Badge: "FalkorDB" — toggle + note "Tracks entity relationships and frustration patterns across calls"
- **Memory Injection Preview** panel (read-only code block) — shows what will be injected into the system prompt for a sample contact; "No memory yet for this contact" if none.
- **Graph Preview** (mini visual) — shows a small node-link graph for the selected sample contact, if graph tier enabled.

### 4.6 Emotion & Intent Arc Tab (VoCall-exclusive)

- Master toggle: "Enable Emotion Detection"
- **Signal Source Cards:**
  1. Text Signal — Badge: "Free • Default" — always on when emotion enabled — Groq NLP
  2. Audio Signal — Badge: "BYOK • Optional" — toggle, requires Hume AI key configured in Settings
- **Behaviors:**
  - Toggle: Tone Adaptation
  - Toggle: Emotion-Conditioned Voice (Hume Octave TTS) — requires audio signal on
  - Slider: Frustration Threshold (0–1, default 0.7)
  - Dropdown: "On Frustration Trigger" → select a connector to fire
- **Intent Arc & Connector Resolution Rules (Section 1):**
  - Displays configured intents (e.g. `book_appointment`, `file_complaint`) with required/optional slots to collect.
  - Resolution chain configuration: step-by-step connector actions triggered on success.
- **Emotion × Intent Combined Rules (Section 2):**
  - Displays multi-dimensional rules combining intent + emotion (e.g., IF Intent == `cancel_subscription` AND Emotion == `frustrated` THEN Action == `escalate_to_human`).

### 4.7 Advanced Tab

- **Stop Speaking Plan** section:
  - Slider: Number of words (0–10, default 4)
  - Slider: Voice seconds (0–0.5s, default 0.2)
  - Slider: Back off seconds (0–10s, default 1)
- **Auto Reachout** section:
  - Toggle: Enable Followup
  - Toggle: Instant Redial
  - Toggle: Notify Via SMS
  - Input: Handover Number (shown when a handoff toggle is on)
- **Calling Hours** section:
  - Day chips: Mon Tue Wed Thu Fri Sat Sun (purple = selected, all default on)
  - Time range pickers (e.g. 08:00 AM – 08:00 PM)
  - "+ Add Range" button (multiple windows)

### 4.8 Analysis Tab

- **Summary** section: Prompt textarea (default provided) + slider "Min messages to trigger" (0–10, default 2)
- **Success Evaluation** section: Prompt textarea + Rubric dropdown (Goal Achieved / Appointment Booked / Lead Qualified / Issue Resolved / Custom)
- **Structured Data** section: Prompt textarea + slider "Timeout (seconds)" (0–60, default 10) + "+ Add Property" button (Property Name + Extraction Prompt row) + note "emotion_state is always included automatically"

### 4.9 Integrations Tab

- Two labeled sections: **During Call** and **Post Call**
- Connector card grid, each card:
  - Icon + name
  - Tag: "During Call" or "Post Call" (colored)
  - Status: Configured (green) / Not configured (gray)
  - "Configure" button → opens modal with connector-specific fields
- Connectors listed: Google Calendar, HubSpot, Custom Webhook, Supabase/Postgres, WhatsApp (post-call only)

### 4.10 Recent Calls Tab

- Table for this agent only: Direction | From | To | Date | Duration | Status | Emotion Score | Test tag | View button
- Click row → opens `/dashboard/calls/[id]`

---

## 5. Contacts

### 5.1 Contacts List (`/dashboard/contacts`)

- Search bar
- "+ Add Contact" button → modal (Name, Phone, Email, Tags)
- Table: Name | Phone | Tags | Last Call | Emotion Score | Actions

### 5.2 Contact Detail (`/dashboard/contacts/[id]`)

#### Left Column (30%) — Contact Details

- Avatar (initials-based)
- Name, phone, email, tags
- "Call Now" button (purple, triggers outbound call)
- Edit button

#### Right Column (70%) — Tabbed Views

##### Tab 1 — Memory (all 4 tiers visible)

- Short-term section: Badge "Live during calls only" — shows active transcript or "No active call"
- Long-term section: list of facts with timestamp + emotion tag chip (e.g. "frustrated" in red) — "Clear long-term memory" button (confirm dialog)
- Episodic section: list of past episodes — summary + date + mini emotion-arc bar — "View full episode" expands key_facts — "Clear episodic memory" button
- **Knowledge Graph section** (new): interactive node-link graph visualization showing this contact's entities and relationships — nodes color-coded by type (Entity/Topic/Episode), edges labeled (MENTIONED, FRUSTRATED_ABOUT, LEADS_TO) — "Clear graph memory" button

##### Tab 2 — Call History

- Table: Date | Duration | Direction | Status | Emotion Score | View

##### Tab 3 — Emotion History

- Line chart (Recharts) of emotion scores across all calls with this contact over time

---

## 6. Calls

### 6.1 Calls List (`/dashboard/calls`)

- Filter bar: All | Inbound | Outbound | Test Calls | Date range picker
- Table: Direction badge (green "IN" / blue "OUT") | From | To | Date | Duration | Status badge (green=completed, red=failed, yellow=in-progress) | Emotion Score (colored number) | Test Call tag (purple) | View button

### 6.2 Call Detail (`/dashboard/calls/[id]`)

Three columns:

#### Left Column (30%) — Metadata

- Direction, From, To, Date, Duration, Status, Agent name, Contact name
- Emotion Score (large, colored)
- Test Call badge if applicable

#### Middle Column (40%) — Transcript

- Scrollable transcript, speaker labels (Agent / Caller)
- Caller lines right-aligned, Agent lines left-aligned with purple accent
- Timestamp per line

#### Right Column (30%) — Analysis & Intent Arc

- **Emotion Arc** — Recharts line chart, X=time(s), Y=valence(-1 to 1), red below 0 / green above 0
- **Intent Arc & Connector Resolution (VA-ICECoT)** — Card showing detected intent flows (e.g. `book_appointment`, 0.88 confidence), extracted slots (`date`, `time`), slot completion %, and connectors fired (`google_calendar`).
- **Call Summary** — text from `call.analysis.summary`
- **Success Evaluation** — result + rubric used
- **Structured Data** — collapsible JSON viewer
- **Memory Recalled** — shows what memory (all 4 tiers) was injected at call start
- **Graph Context Used** — shows which entities/relationships from FalkorDB were surfaced for this call

---

## 7. Analytics (`/dashboard/analytics`)

- 4 top stat cards: Total Calls | Interested Calls | Not Connected | Avg. Success Score
- "Status Breakdown" section (bar chart)
- "Call Analytics Overview" section (line chart over time)
- "Emotion Trend" section (avg emotion score over time, colored line)
- Filter: by agent, by date range

---

## 8. Connectors (`/dashboard/connectors`)

- Same card grid as the Integrations tab, but org-wide (across all agents)
- Grouped by During Call / Post Call
- Configure modal per connector type

---

## 9. Settings

### 9.1 API Keys (`/dashboard/settings/api-keys`)

Provider cards, each with: name + icon, description, masked key input, Save button, status badge (Connected/Not configured).

| Provider | Description | Required? |
| --- | --- | --- |
| Groq | LLM, STT, Emotion NLP | Required |
| Sarvam AI | Hinglish STT + TTS | Optional |
| Cartesia | English TTS | Optional |
| Hume AI | Audio Emotion + Emotional TTS (EVI) | Optional — shows usage meter: chars used / 10,000, EVI minutes used / 5 |
| Cerebras | LLM fallback | Optional |
| Twilio | Telephony (dev/demo) | Optional (2 fields: Account SID + Auth Token) |
| Plivo | India telephony | Optional (2 fields: Auth ID + Auth Token) |
| Exotel | India telephony | Optional |
| Resend | Transactional email | Optional |

### 9.2 Telephony (`/dashboard/settings/telephony`)

- 3 cards: Telephony Setup | Voice AI Integration | KYC Compliance
- Country selector (default: India)
- Phone Numbers table: Number | Provider | Agent | KYC Status | Actions
- "+ Add Number" button → modal (number, provider, assign agent)
- KYC upload: drag & drop, accepts PDF/JPG/PNG, document type selector (Aadhaar / PAN / GST / Company Registration), Submit button, status badge (Pending/Submitted/Approved)

### 9.3 Organization Settings (`/dashboard/settings`)

- Org name, domain, logo, description (editable)
- Member list + role management (owner/admin/member)
- Danger zone: delete organization

### 9.4 Spaces (`/dashboard/spaces`)

- List of spaces with agent/contact/call counts
- "+ New Space" button

---

## 10. Modals (used across the app)

- **Add Contact** — Name, Phone, Email, Tags
- **Add Phone Number** — Number, Provider, Assign Agent
- **Configure Connector** — dynamic fields per connector type
- **Confirm Delete** — used for: delete agent, clear memory tier, delete API key, delete phone number (all require typed confirmation or a second click)
- **Voice Preview** — inline audio player triggered from Voice Profile cards

---

## 11. Empty States (every list page needs one)

- Agents empty: "No agents yet. Create your first agent." + bot illustration + CTA
- Contacts empty: "No contacts yet." + users illustration + CTA
- Calls empty: "No calls yet. Publish an agent and make a test call." + CTA
- Memory (any tier) empty: "No memory yet for this contact."
- Connectors empty: "No connectors configured." + CTA

---

## 12. Loading & Error States

- Skeleton loaders on: agent list, contacts list, calls list, dashboard stats
- Spinners on: Enhance Prompt button, voice preview button, all Save buttons
- Toast notifications (sonner) on API errors
- Inline validation errors on all forms

---

## Build Order Suggestion (for a vibe coder)

1. Global 3-panel shell + auth pages
2. Dashboard home (static stats first, wire up later)
3. Agent Builder — Identity + Persona tabs (core value first)
4. Voice Profile + Telephony tabs
5. Memory tab (start with short/long/episodic, add Graph card last)
6. Emotion tab
7. Advanced + Analysis tabs
8. Integrations tab
9. Contacts (list + detail with memory viewer)
10. Calls (list + detail with transcript/emotion arc)
11. Analytics
12. Settings (API Keys, Telephony)
13. Empty states, loading states, polish pass

---

End of Design Document v1.0.
