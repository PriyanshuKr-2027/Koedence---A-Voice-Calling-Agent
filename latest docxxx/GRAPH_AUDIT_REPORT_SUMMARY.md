# VoCall Graphify Knowledge Graph Audit & Architectural Synthesis

**Audit Date:** August 2026  
**Tool:** Graphify Knowledge Graph Engine  
**Corpus Analyzed:** 273 files · ~162,438 words  
**Graph Metrics:** 2,106 Nodes · 3,409 Edges · 192 Community Clusters · 0 Import Cycles  
**Confidence Distribution:** 98% Extracted (Deterministic AST) · 2% Inferred (Semantic LLM) · 0% Ambiguous

---

## 1. Executive Summary

A comprehensive graph extraction was executed across the VoCall codebase and documentation suite, producing an interactive topological graph (`graphify-out/graph.html`), a graph dataset (`graphify-out/graph.json`), and an exhaustive audit report (`graphify-out/GRAPH_REPORT.md`).

The graph analysis reveals a robust, decoupled microservice architecture centered around a low-latency real-time voice loop, multi-tier asynchronous workflows, and high-cohesion functional clusters.

```text
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                           TOPOLOGICAL GOD NODES & CORE HUBS                               │
└─────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                              │
         ┌──────────────────┬─────────────────┼─────────────────┬──────────────────┐
         │                  │                 │                 │                  │
┌────────▼────────┐ ┌───────▼────────┐┌───────▼────────┐┌───────▼────────┐ ┌───────▼────────┐
│ LiveKitService  │ │ fire_connector ││post_call_pipe  ││synthesize_speec│ │ createClient   │
│ (23 edges)      │ │ (19 edges)     ││(25 edges)      ││(17 edges)      │ │ (27 edges)     │
├─────────────────┤ ├────────────────┤├────────────────┤├────────────────┤ ├────────────────┤
│ WebRTC Sessions │ │ 8 Third-Party  ││Async Memory &  ││Hinglish STT/TTS│ │ Supabase DDL,   │
│ & Audio Token   │ │ Action Plugins ││CRM Extraction  ││Provider Router │ │ pgvector & Auth│
└─────────────────┘ └────────────────┘└────────────────┘└────────────────┘ └────────────────┘
```

---

## 2. Top God Nodes (Core Architectural Abstractions)

The graph identified the 10 most connected entities in the repository, representing the foundation of the platform:

| Rank | Node Identifier | Degree | Architectural Role | Source File |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `react` | 46 | Frontend component reactive state engine | `package.json` |
| 2 | `createClient()` | 27 | Supabase PostgREST & pgvector client factory | `app/services/supabase_client.py` |
| 3 | `post_call_pipeline()` | 25 | Trigger.dev async background analysis engine | `trigger/post_call_pipeline.py` |
| 4 | `LiveKitService` | 23 | WebRTC audio room token minting & room manager | `app/services/livekit_service.py` |
| 5 | `post_call_pipeline()` | 22 | FastAPI router async task dispatch handler | `app/routers/calls.py` |
| 6 | `Button` | 20 | Shadcn / Tailwind core UI primitive | `src/components/ui/button.tsx` |
| 7 | `fire_connector()` | 19 | Central Action Connector dispatcher | `app/services/connectors/dispatcher.py` |
| 8 | `TelephonyService` | 18 | Twilio PSTN REST client & SIP trunking | `app/services/telephony.py` |
| 9 | `compilerOptions` | 18 | TypeScript configuration root | `tsconfig.json` |
| 10 | `synthesize_speech()` | 17 | Multi-provider TTS router (Cartesia / Sarvam) | `app/services/tts.py` |

---

## 3. High-Impact Surprising Connections

The semantic graph extraction discovered key cross-cutting relationships bridging engineering skills and architectural design specifications:

1. **`VoCall SWE Principles Skill` $\leftrightarrow$ `SWEBOK-Based Software Engineering Principles`**  
   Direct functional alignment between agent instructions and the monorepo's architectural design document (`latest docxxx/SWE-PRINCIPLE.md`), establishing formal limits on cyclomatic complexity and file sizing.
2. **`Sub-500ms Voice Loop Latency Optimization` $\leftrightarrow$ `Sub-500ms End-to-End Voice Latency Budget`**  
   Verifies that the code optimizer skill enforces the exact TRD latency budget breakdown (150ms STT + 150ms LLM + 80ms TTS + 40ms WebRTC).
3. **`AES-256 BYOK & DPDP Act Compliance` $\leftrightarrow$ `DPDP Act 2023 Forget Me Cascading Erasure`**  
   Connects encryption utilities in `app/utils/encryption.py` with privacy compliance specifications in `latest docxxx/PRD.md`.
4. **`fire_connector()` as a Universal Bridge**  
   Has the highest betweenness centrality (0.043) in the backend, linking 8 separate third-party integrations into a single unified interface.

---

## 4. Key Community Clusters & Cohesion Scores

The Louvain clustering algorithm partitioned the codebase into 192 modular communities:

- **Connectors & WhatsApp Subsystem (Community 0):** Cohesion 0.052 · 81 nodes (Pydantic configs, dispatcher, Twilio WhatsApp templates).
- **Webhooks & Contacts Subsystem (Community 1):** Cohesion 0.053 · 57 nodes (Inbound PSTN webhook routing, contact lifecycle).
- **Resolver & Slot Manager (Community 2):** Cohesion 0.055 · 54 nodes (VA-ICECoT intent engine state tracking).
- **Test Suites (Communities 3, 6, 7, 11, 28, 44):** High-density test clusters validating API endpoints, telephony, encryption, and connectors.
- **Episodic & Long-Term Memory (Communities 9 & 22):** 4-tier memory management, pgvector cosine search, and structured summarization.
- **Pipecat Voice Pipeline (Communities 41 & 42):** Real-time media streaming, tool execution, and turn buffers.

---

## 5. Architectural Health & Decoupling Recommendations

1. **Connector Dispatcher Decoupling:** `fire_connector()` currently imports all 8 connectors directly. Recommend maintaining lazy loading or a registry pattern to keep connector dependencies isolated.
2. **Memory Service Isolation:** The 4 memory tiers are cleanly separated across `short_term.py`, `long_term.py`, `episodic.py`, and `graph.py`, unified through the `retriever.py` facade.
3. **Zero Circular Imports:** The graph verified that the Python backend and TypeScript frontend contain 0 import cycles.
