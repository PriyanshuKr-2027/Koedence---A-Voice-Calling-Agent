# UI & Design System Specifications for `design.md` (`changes.md` / `changesui.md`)

This document outlines all UI components, interactive states, design system tokens, UX flows, and implementation status for **Web Call Testing** and **Agent Studio** in the `abhishek ui` frontend directory.

---

## 1. Web Call Trigger & Header Integration

### Location: `/dashboard/agents/[id]` (Agent Studio Top Bar)

- **Button Component**: `"Talk To Agent"`
  - **Style**: Secondary Outline Button with subtle violet/sage accent borders (`border-[#7C3AED]/50` or `border-[var(--accent-color)]/50`, text `#A78BFA` / `var(--accent-color)`, hover `bg-[#7C3AED]/20` / `bg-[var(--accent-light)]`).
  - **Icon**: `PhoneCall` (Lucide icon).
  - **Position**: Mounted in top-right action bar next to *Voice Catalog*, *Save*, and *Publish* buttons.
  - **Behavior**: Clicking opens the full-screen modal overlay `WebCallModal`.

---

## 2. Web Call Modal (`WebCallModal.tsx`) Component Architecture

### Overlay & Layout Specs

- **Backdrop**: Full viewport backdrop with dark frosted glass effect (`bg-black/70 backdrop-blur-sm`).
- **Modal Container**:
  - Max width: `max-w-3xl` (~768px).
  - Surface: `bg-slate-900` / `var(--card-color)`, border `border-slate-700` / `var(--border-color)`, rounded `rounded-2xl`, shadow `shadow-2xl`.
  - Max height constraint: `max-h-[90vh]` with vertical flex layout for header, main body, and footer/controls.

---

## 3. Web Call Lifecycle States & UI Specifications

### Phase 1: Pre-Call Setup (`idle` / `requesting_mic`)

- **Customer Contact Input**:
  - Field label: `YOUR NAME` (Mono, uppercase, muted).
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
  - **Left Section (Audio Visualizer & Orb — Width 256px)**:
    - **Dynamic Voice Orb**:
      - **Agent Speaking State**: Enlarged orb (112px), solid purple/sage (`bg-[#7C3AED]` / `bg-[#4F7A65]`), multi-layered expanding ping animation (`bg-[#7C3AED]/20 animate-ping`), label `"Agent speaking…"`.
      - **User Speaking State**: Green orb (104px), solid emerald `bg-emerald-600` / `var(--green-accent)`, green ping pulse (`bg-emerald-500/20`), label `"You are speaking…"`.
      - **Idle/Listening State**: Medium purple/sage orb (96px) with soft glow, label `"Listening…"`.
    - **End Call Action**: Red outline pill button (`bg-red-600/20 border-red-500/40 text-red-400 hover:bg-red-600/30`), `PhoneOff` icon.

  - **Right Section (Real-Time Live Transcript)**:
    - **Header**: Live transcript label with green status indicator.
    - **Scroll Container**: Flex-1 auto-scrolling container with thin custom scrollbar.
    - **Message Bubbles**:
      - **Agent Turns**: Left-aligned, dark slate bubble (`bg-slate-800 text-slate-200 rounded-2xl rounded-tl-sm`), Bot avatar badge (`bg-[#7C3AED]/30 text-[#A78BFA]`).
      - **User Turns**: Right-aligned, purple/emerald-tinted bubble (`bg-[#7C3AED]/20 border border-[#7C3AED]/30 text-slate-200 rounded-2xl rounded-tr-sm`), User avatar badge (`bg-emerald-500/20 text-emerald-400`).

---

### Phase 4: Post-Call Decision Prompt (`ended`)

- **Header**: `CheckCircle2` success icon inside glowing purple/sage circle.
- **Summary**: Total call duration (`Duration: M:SS`).
- **Transcript Preview Card**: Scrollable compact preview showing the last 4 dialogue turns.
- **Save vs. Discard Decision Card**:
  - Card Heading: *"Save this test call for review?"*
  - Explanation Text: *"Saved calls include the full transcript, emotion arc, and post-call analysis — viewable from your calls dashboard."*
  - **Action 1 — Discard**: Secondary outline button (`Trash2` icon, `border-slate-600 text-slate-300 hover:bg-slate-700`). Deletes test record.
  - **Action 2 — Save & View**: Primary CTA button (`ExternalLink` icon, `bg-[#7C3AED] hover:bg-[#7C3AED]/90`). Saves session and navigates directly to `/dashboard/calls/[callId]`.

---

## 4. Color Palette & Design Tokens (Extracted from `abhishek ui/src/index.css`)

| Token Name | Custom Hex / Variable | UI Component Mapping | Notes / Guidelines |
| --- | --- | --- | --- |
| `brand-primary` | `#4F7A65` (`var(--accent-color)`) | Primary CTAs, active agent orb glow, active nav tabs & main brand accents | Sage Emerald Green |
| `brand-accent` | `#EBF1EE` (`var(--accent-light)`) | Secondary highlights, agent badges, active chip fills, selection background | Light Sage Tint |
| `status-live` | `#C94C4C` / `#2D9D78` (`var(--red-accent)` / `var(--green-accent)`) | Live call recording indicator, pulse ring, status badges | Terracotta Red / Sage Green Pulse |
| `user-speaking` | `#2D9D78` (`var(--green-accent)`) | User speaking orb state, user transcript badge | Emerald Green Audio Indicator |
| `surface-bg` | `#F6F5F2` (`var(--bg-color)`) | Fullscreen modal backdrop, page background | Warm Neutral Ivory |
| `surface-card` | `#FFFFFF` / `#FCFBF8` (`var(--card-color)` / `var(--surface-color)`) | Modal inner panels, transcript container, input fields, elevated surfaces | Pure White & Soft Parchment |
| `border-subtle` | `#E6E4DF` (`var(--border-color)`) | Modal borders, card outlines, divider lines, custom scrollbar thumb | Soft Warm Gray |
| `text-primary` | `#202124` (`var(--text-primary)`) | Headings, primary button text, main dialogue text, dark CTA container | High-Contrast Deep Charcoal |
| `text-muted` | `#6B6B6B` (`var(--text-secondary)`) | Call timers, status subtext labels, placeholder text, secondary metadata | Muted Slate Gray |
| `font-sans` | `'Inter', 'Geist', sans-serif` | Main interface typography, headings & body text | Clean Modern Sans-Serif |
| `font-mono` | `'Geist Mono', ui-monospace, monospace` | Timers, LIVE badges, technical metadata, latency indicators | Precision Monospace |

---

## 5. `abhishek ui` Frontend Audit & Gap Analysis

An audit of the `abhishek ui` frontend directory ([abhishek ui/src](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/abhishek%20ui/src)) reveals the following implementation status:

### Implemented Components in `abhishek ui`

- **`AgentBuilder.tsx`**: Complete 10-tab Agent Studio navigation (General Info, Voice, Persona, LLM, Knowledge Base, Tools, Guardrails, Webhooks, Integrations, Call Workflow).
- **`DashboardShell.tsx`**: Sidebar navigation and layout wrapper.
- **`CallsManager.tsx`**: Detailed call logs view with emotion/sentiment arc, player, and filters.
- **`ContactsManager.tsx`**: Contact management table with memory tier detail drawer.
- **`AnalyticsPanel.tsx` & `AnalyticsShowcase.tsx`**: Analytics charts and KPI metrics.

### Identified Implementation Gaps against Specifications

1. **Missing `WebCallModal.tsx` Component**: No web call test modal currently exists under `abhishek ui/src/components/`.
2. **Generic Header CTA in `AgentBuilder.tsx`**: Header currently uses `"Live Call"` and `"Chat Sandbox"` text buttons instead of `"Talk To Agent"` with the `PhoneCall` icon.
3. **Missing Lifecycle State UI**:
   - No Pre-Call customer name input field (required for Supabase 4-tier memory lookup trigger).
   - No active split-view with dynamic 3-state Voice Orb (Agent Speaking / User Speaking / Listening) and auto-scrolling live transcript stream.
   - No Post-Call Save vs. Discard decision card.

---

## 6. Implementation Roadmap for `abhishek ui`

1. **Create `abhishek ui/src/components/WebCallModal.tsx`**:
   - Implement modal state machine: `idle` | `requesting_mic` | `connecting` | `active` | `ended`.
   - Implement Phase 1 Name input, Phase 2 Connecting pulse, Phase 3 Split View (Voice Orb + Live Transcript), Phase 4 Save/Discard decision card.
2. **Update `AgentBuilder.tsx` Top Bar**:
   - Replace generic button with `"Talk To Agent"` CTA.
   - Attach state handler to open `WebCallModal`.
3. **Connect Session Memory & Navigation**:
   - Wire customer name input to pass contact context for memory retrieval.
   - Direct Save CTA in post-call modal to `/dashboard/calls/[callId]`.
