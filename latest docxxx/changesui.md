# UI & Design System Specifications for Web Call Testing (`changesui.md`)

**Document Version:** 2.1  
**Implementation Status:** 100% Fully Implemented in `src/components/WebCallModal.tsx` & `src/components/AgentBuilder.tsx`  
**Related Documents:** [design.md](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/latest%20docxxx/design.md), [components.md](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/latest%20docxxx/components.md)

---

## 1. Web Call Trigger & Header Integration

### Location: `/dashboard/agents/[id]` (`AgentBuilder.tsx` Top Action Bar)

- **Button Component**: `"Talk To Agent"`
  - **Style**: Secondary Outline Button with subtle violet/sage accent borders (`border-[#7C3AED]/50` / `border-[var(--accent-color)]/50`, text `#A78BFA` / `var(--accent-color)`, hover `bg-[#7C3AED]/20` / `bg-[var(--accent-light)]`).
  - **Icon**: `PhoneCall` (Lucide icon).
  - **Position**: Mounted in top-right action bar next to *Voice Catalog*, *Save*, and *Publish* buttons.
  - **Behavior**: Clicking opens the full-screen modal overlay `WebCallModal`.

---

## 2. Web Call Modal (`WebCallModal.tsx`) Component Architecture

### Overlay & Layout Specs

- **Backdrop**: Full viewport backdrop with dark frosted glass effect (`bg-black/75 backdrop-blur-md`).
- **Modal Container**:
  - Max width: `max-w-4xl` (~896px).
  - Surface: `bg-slate-900/95` / `var(--card-color)`, border `border-slate-700/80` / `var(--border-color)`, rounded `rounded-2xl`, shadow `shadow-2xl`.
  - Max height constraint: `max-h-[90vh]` with vertical flex layout for header, main body, and footer/controls.

---

## 3. Web Call Lifecycle States & UI Specifications

### Phase 1: Pre-Call Setup (`idle` / `requesting_mic`)

- **Customer Contact Input**:
  - Field label: `YOUR NAME OR CONTACT ID` (Mono, uppercase, muted).
  - Input field: Text input with `User` icon prefix. Required to start call.
  - Design Purpose: Links the test session to Supabase `contacts` table to trigger 4-tier memory retrieval (Short-term, Long-term facts, Episodic summaries, Knowledge graph).
- **Voice Orb (Idle State)**:
  - Static 96px orb with `PhoneCall` icon, neutral dark slate border.
- **Mic Permission Badge**:
  - Shows browser microphone permission status (`Mic` icon with purple text, or red warning if permission denied).
- **Primary CTA**: `"Start Web Call"`
  - Violet/Sage pill button (`bg-[#7C3AED]` / `bg-[var(--accent-color)]`, rounded-full shadow-lg).
  - Disabled state: `opacity-40` until name is entered and mic is requested.

---

### Phase 2: Connecting (`connecting`)

- **Voice Orb (Pulsing State)**:
  - 96px orb with animated pulse glow (`bg-[#7C3AED]/30 border-2 border-[#7C3AED]/60 animate-pulse`).
  - Loading spinner (`Loader2` rotating icon).
- **Status Subtext**: Monospace pulsing text: `"Connecting to [Agent Name]…"`.

---

### Phase 3: Active Call (`active`)

- **Top Header Bar**:
  - **Live Indicator**: Red blinking pulse dot + `LIVE` text (`text-red-400 font-mono text-xs`).
  - **Call Timer**: Monospace timer formatted `M:SS` (`text-slate-400 font-mono`).
  - **Close Button**: Top-right `X` icon button triggering call end.

- **Split View Body**:
  - **Left Section (Audio Visualizer & Orb — Width 300px)**:
    - **Dynamic Voice Orb**:
      - **Agent Speaking State**: Enlarged orb (112px), solid purple/sage (`bg-[#7C3AED]` / `bg-[#4F7A65]`), multi-layered expanding ping animation (`bg-[#7C3AED]/20 animate-ping`), label `"Agent speaking…"`.
      - **User Speaking State**: Green orb (104px), solid emerald `bg-emerald-600` / `var(--green-accent)`, green ping pulse (`bg-emerald-500/20`), label `"You are speaking…"`.
      - **Idle/Listening State**: Medium purple/sage orb (96px) with soft glow, label `"Listening…"`.
    - **End Call Action**: Red outline pill button (`bg-red-600/20 border-red-500/40 text-red-400 hover:bg-red-600/30`), `PhoneOff` icon.
    - **Controls**: Mic mute toggle (`Mic` / `MicOff`) and speaker mute toggle (`Volume2` / `VolumeX`).

  - **Right Section (Real-Time Live Transcript & Telemetry)**:
    - **Header**: Live transcript label with green status indicator.
    - **Scroll Container**: Flex-1 auto-scrolling container with thin custom scrollbar.
    - **Message Bubbles**:
      - **Agent Turns**: Left-aligned, dark slate bubble (`bg-slate-800 text-slate-200 rounded-2xl rounded-tl-sm`), Bot avatar badge (`bg-[#7C3AED]/30 text-[#A78BFA]`).
      - **User Turns**: Right-aligned, purple/emerald-tinted bubble (`bg-[#7C3AED]/20 border border-[#7C3AED]/30 text-slate-200 rounded-2xl rounded-tr-sm`), User avatar badge (`bg-emerald-500/20 text-emerald-400`).
    - **Real-Time Intelligence**: Live telemetry showing VA-ICECoT intent confidence, slot extraction, and tool actions.

---

### Phase 4: Post-Call Decision Prompt (`ended`)

- **Header**: `CheckCircle2` success icon inside glowing purple/sage circle.
- **Summary**: Total call duration (`Duration: M:SS`), turn count, and sentiment rating.
- **Transcript Preview Card**: Scrollable compact preview showing the dialogue turns.
- **Save vs. Discard Decision Card**:
  - Card Heading: *"Save this test call for review?"*
  - Explanation Text: *"Saved calls include the full transcript, emotion arc, and post-call analysis — viewable from your calls dashboard."*
  - **Action 1 — Discard**: Secondary outline button (`Trash2` icon, `border-slate-600 text-slate-300 hover:bg-slate-700`). Drops test record.
  - **Action 2 — Save & View**: Primary CTA button (`ExternalLink` icon, `bg-[#7C3AED] hover:bg-[#7C3AED]/90`). Saves session and navigates directly to `/dashboard/calls/[callId]`.

---

## 4. Color Palette & Design Tokens

| Token Name | Custom Hex / Variable | UI Component Mapping | Notes / Guidelines |
| --- | --- | --- | --- |
| `brand-primary` | `#7C3AED` / `#4F7A65` | Primary CTAs, active agent orb glow, active nav tabs | Purple & Sage Emerald |
| `brand-accent` | `#A78BFA` / `#EBF1EE` | Secondary highlights, agent badges, active chip fills | Light Accent Tint |
| `status-live` | `#EF4444` / `#10B981` | Live call recording indicator, pulse ring, status badges | Red Pulse / Emerald Green |
| `user-speaking` | `#10B981` (`var(--green-accent)`) | User speaking orb state, user transcript badge | Emerald Green Indicator |
| `surface-bg` | `#0F172A` / `#F6F5F2` | Fullscreen modal backdrop, page background | Dark Slate / Warm Neutral |
| `surface-card` | `#1E293B` / `#FFFFFF` | Modal inner panels, transcript container, input fields | Dark Surface & Pure White |
| `border-subtle` | `#334155` / `#E6E4DF` | Modal borders, card outlines, divider lines | Subtle Border Color |
| `text-primary` | `#F8FAFC` / `#202124` | Headings, primary button text, dialogue text | High-Contrast Typography |
| `text-muted` | `#94A3B8` / `#6B6B6B` | Call timers, status subtext labels, metadata | Muted Slate Gray |
| `font-sans` | `'Inter', 'Geist', sans-serif` | Main interface typography, headings & body text | Clean Modern Sans-Serif |
| `font-mono` | `'Geist Mono', monospace` | Timers, LIVE badges, technical telemetry | Precision Monospace |

---

## 5. Verification & Component Status

- [x] **`src/components/WebCallModal.tsx`**: Fully implemented with 4-phase lifecycle, LiveKit WebRTC audio connection, mic controls, 3-state Voice Orb, auto-scrolling transcript stream, and Save/Discard post-call card.
- [x] **`src/components/AgentBuilder.tsx`**: Header includes `"Talk To Agent"` button with `PhoneCall` icon, connected to `WebCallModal`.
- [x] **Memory & Telemetry Integration**: Contact name input propagates contact ID for 4-tier memory fanout lookup and links to `/api/v1/calls/webcall/{call_id}/events` SSE stream.

---

*Verified by VoCall Engineering Team.*
