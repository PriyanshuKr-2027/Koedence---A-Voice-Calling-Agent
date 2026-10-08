#set page(
  paper: "a4",
  margin: (top: 2.54cm, bottom: 2.54cm, left: 2.54cm, right: 2.54cm),
  header: none,
  footer: context {
    if counter(page).get().first() > 3 {
      align(center, text(size: 11pt, font: "Times New Roman")[#counter(page).get().first()])
    }
  }
)

#set text(
  font: ("Times New Roman", "Liberation Serif"),
  size: 12pt,
  fill: rgb("#0f172a")
)

// 1.5 line spacing with clear blank line between paragraphs
#set par(justify: true, leading: 0.85em, spacing: 1.5em)

// -----------------------------------------------------------------------------
// TITLE PAGE (Matches Screenshot 1)
// -----------------------------------------------------------------------------
#align(left)[
  #image("gniot_logo.png", width: 72%)
]

#v(1.0cm)

#align(center)[
  #text(size: 13pt, weight: "bold")[DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING] \
  #v(2pt)
  #text(size: 12pt, weight: "bold")[(ARTIFICIAL INTELLIGENCE & DATA SCIENCE)] \
  #v(1.5cm)

  #text(size: 16pt, weight: "bold")[SYNOPSIS] \
  #v(1.5cm)

  #text(size: 14pt, weight: "bold")[VOCALL] \
  #v(4pt)
  #text(size: 12pt, weight: "bold")[(THE MEMORY AUGMENTED VOICE CALLING AGENT WITH] \
  #v(2pt)
  #text(size: 12pt, weight: "bold")[EMOTIONAL AWARENESS)] \
  #v(2.5cm)
]

#grid(
  columns: (1fr, 1.35fr),
  align: (left, left),
  gutter: 20pt,
  [
    #text(weight: "bold", size: 12pt)[Guided By:] \
    #v(0.4cm)
    #text(size: 11.5pt)[*Dr. Shiv Kant*] \
    #text(size: 11pt, style: "italic")[Assistant Professor] \
    #text(size: 10.5pt)[Department of CSE (AI & DS)]
  ],
  [
    #text(weight: "bold", size: 12pt)[Submitted By:] \
    #v(0.4cm)
    #text(size: 11pt)[*Priyanshu Kumar* (2301321630027)] \
    #v(0.2cm)
    #text(size: 11pt)[*Ananya Gupta* (2301321630007)] \
    #v(0.2cm)
    #text(size: 11pt)[*Abhishek Kumar Singh* (2301321630002)] \
    #v(0.2cm)
    #text(size: 11pt)[*Adarsh Pandey* (2301321630005)]
  ]
)

#v(2.0cm)
#align(center)[
  #text(size: 11.5pt)[Greater Noida Institute of Technology (Engg. Institute), Greater Noida] \
  #v(4pt)
  #text(size: 11.5pt)[Dr. A.P.J. Abdul Kalam Technical University, Lucknow]
]

#pagebreak()

// -----------------------------------------------------------------------------
// DECLARATION (Matches Screenshot 2)
// -----------------------------------------------------------------------------
#align(left)[
  #text(size: 14pt, weight: "bold")[DECLARATION]
]
#v(0.8cm)

We hereby declare that this project work entitled *"VoCall – The Memory Augmented Voice Calling Agent with Emotional Awareness"* has been prepared by us during the year 2025-26 under the guidance of *Dr. Shiv Kant*, Department of Computer Science and Engineering (Artificial Intelligence & Data Science), GNIOT, Greater Noida, in partial fulfilment of the B. Tech degree prescribed by the college.

We also declare that this project is the outcome of our own effort, and that it has not been submitted to any other university for the award of any degree.

#v(3.0cm)
#align(right)[
  #text(size: 11.5pt)[
    *Priyanshu Kumar* (2301321630027) \
    #v(0.2cm)
    *Ananya Gupta* (2301321630007) \
    #v(0.2cm)
    *Abhishek Kumar Singh* (2301321630002) \
    #v(0.2cm)
    *Adarsh Pandey* (2301321630005)
  ]
]

#pagebreak()

// -----------------------------------------------------------------------------
// ACKNOWLEDGEMENT
// -----------------------------------------------------------------------------
#align(left)[
  #text(size: 14pt, weight: "bold")[ACKNOWLEDGEMENT]
]
#v(0.8cm)

We have taken efforts in this project. However, it would not have been possible without the kind support and help of many individuals and organizations. We would like to extend our sincere thanks to all of them.

We are highly indebted to *Dr. Shiv Kant* for his guidance and constant supervision as well as for providing necessary information regarding the project, and also for his support in completing the project. We would like to express our gratitude towards our parents and members of GNIOT for their kind co-operation and encouragement which helped us in the completion of this project. We would also like to express our special gratitude and thanks to the faculty members of the Department of Computer Science and Engineering (AI & DS) for giving us such attention and time.

We thank and appreciate our colleagues who assisted us in developing this project and all the people who willingly helped us out with their abilities.

#pagebreak()

// -----------------------------------------------------------------------------
// TABLE OF CONTENTS (Matches media_1789052129696.png)
// -----------------------------------------------------------------------------
#align(left)[
  #text(size: 14pt, weight: "bold")[TABLE OF CONTENTS]
]
#v(0.8cm)

#outline(
  title: none,
  indent: 1.5em,
  depth: 2
)

#pagebreak()

// -----------------------------------------------------------------------------
// BODY SECTIONS (Starts at Page 6)
// -----------------------------------------------------------------------------
#counter(page).update(6)
#set heading(numbering: "1.1")

= INTRODUCTION
Voice is the most natural medium of human communication, yet current production conversational voice agents (such as Vapi, Retell AI, and OmniDim) remain fundamentally transactional, forgetful, and emotionally blind. Traditional Interactive Voice Response (IVR) setups and modern single-turn LLM voice bots treat every telephone call as an isolated event. A returning customer calling three times in a single week regarding an unresolved issue must repeat their identity, ticket details, and emotional grievance on every turn. Furthermore, existing voice agents cannot sense whether a caller is calm, confused, or furious in real time. This operational amnesia damages customer trust and inflates handle times across logistics, banking, healthcare, and citizen helplines.

VoCall resolves this breakdown by introducing an enterprise-grade, open-source, full-duplex spoken dialogue platform designed for sub-500ms turnaround latency (well within the 800ms human conversational threshold). The system combines 20–40ms audio frame processing with a 4-Tier Cognitive Memory Architecture, a Dual-Signal Multimodal Emotion Fusion Engine, an Intention-Centric Chain-of-Thought (VA-ICECoT) reasoning framework, and a native code-switched Hinglish speech pipeline. Together, these systems allow a voice agent to remember callers across sessions, perceive emotional distress mid-turn from both acoustic prosody and text sentiment, dynamically adapt conversational strategy, and trigger third-party actions — all deployable on free-tier infrastructure.

= PROBLEM STATEMENT
- *Cross-Session Amnesia (Single-Store Memory Failure):* Commercial voice platforms maintain zero memory across sessions. Research memory systems like MemGPT and Mem0 rely on flat vector stores that introduce high paging latencies (over 1000ms) and cannot execute multi-hop causal graph traversals across past call episodes.
- *Unimodal and Post-Call Emotion Blind Spots:* Platforms like OmniDim run sentiment classifiers as batch jobs after call completion. Post-call analysis cannot alter in-flight tone, while text-only sentiment classifiers fail entirely on sarcasm or acoustic strain where words appear polite but pitch indicates severe anger.
- *Disconnected Intent and Affective Reasoning:* Existing pipelines isolate intent classification from emotional appraisal. No production voice platform couples intent classification, multi-turn slot extraction, and affective appraisal inside a sub-500ms voice turn deadline.
- *Translation Wrappers for Multilingual Audio:* Current platforms handle Indian languages by bolting translation wrappers onto English models, inflating latency past 1500ms and corrupting code-switched Hindi-English (Hinglish) phonemes.
- *High SaaS Cost Barriers for Indian MSMEs:* US-based voice platforms bill at prohibitive rates of USD 0.05 to USD 0.15 per conversation minute, making automated voice deployment financially inaccessible for Indian enterprises.

= LITERATURE REVIEW / EXISTING SYSTEMS
The theoretical architecture of VoCall's intent, emotion, and memory subsystems is grounded in recent peer-reviewed research in conversational AI. IntentionESC (Zhang et al., Findings of ACL 2025) demonstrates that explicitly modeling a speaker's conversational intention prior to generating surface text significantly elevates emotional support quality — a principle VoCall formalizes in its Intention-Centric Chain-of-Thought (VA-ICECoT) protocol. JX4MEI (Huang et al., Findings of ACL 2026) proves that cross-attention between acoustic prosody and linguistic features outperforms late decision voting, directly motivating VoCall's Dual-Signal Emotion Fusion Engine.

Speaking with Intent in LLMs (Yin et al., INLG 2025) establishes that hidden meta-thought planning tokens prevent hallucinated goals during live generation. The MC-EIU benchmark (Liu et al., 2024) and AffectMind (Yu et al., 2025) validate that emotion-intent transitions follow structured distributions and that grounding memory retrieval in affective coordinates improves relevance. In memory systems, MemGPT (Packer et al., 2023) pioneered virtual memory paging for LLMs, but its paging queries introduce latencies exceeding 1000ms. Zep (2024) demonstrates temporal graph persistence for entity relationships, which VoCall extends with sub-40ms OpenCypher graph traversals on FalkorDB.

Commercially available systems (Vapi, Retell AI, OmniDim, Unpod) rely on static prompt trees, lack acoustic paralinguistics, provide no native Hinglish models, and operate as closed SaaS. VoCall differentiates itself as an open-source, full-duplex platform combining 4-tier memory fan-out, live acoustic emotion sensing, and native code-switching on free-tier infrastructure.

= OBJECTIVES OF THE PROJECT
1. To design and implement a 4-Tier Hybrid Cognitive Memory Architecture unifying working memory (Upstash Redis), semantic facts (Supabase pgvector), episodic history (Postgres), and knowledge graph (FalkorDB), queried concurrently in under 80ms via `asyncio.gather`.
2. To design a Dual-Signal Multimodal Emotion Fusion Engine combining Hume AI acoustic prosody (48 paralinguistic dimensions) and Groq text sentiment onto Russell's Circumplex plane (60/40 convex combination) to detect caller frustration mid-turn.
3. To implement a VA-ICECoT (Voice Agent Intention-Centric Chain-of-Thought) intent engine capable of 4-step reasoning (observation, cause, intent, goal) with deterministic escalation overrides when frustration exceeds 0.65.
4. To deploy a native code-switched Hinglish speech pipeline integrating Sarvam AI's Saarika v2 STT and Bulbul v2 TTS to process mixed Hindi-English speech without artificial translation wrappers.
5. To achieve a deterministic end-to-end voice turn latency budget of 495ms (observed P95 under 530ms) across speech-to-text, memory retrieval, emotion fusion, LLM inference, and audio synthesis.
6. To implement an atomic, DPDP Act 2023-compliant "Forget Me" cascading deletion protocol that purges contact records across all four storage tiers and generates a SHA-256 cryptographic compliance receipt.
7. To validate joint reasoning accuracy using the Joint Recognition Balance Metric (JRBM) and provide an in-browser WebRTC testing studio for real-time validation without physical telephony hardware.

= PROPOSED SYSTEM
VoCall proposes an integrated, five-layer voice AI platform in which a caller's speech is transcribed, understood, affectively appraised, and responded to in real time while simultaneously grounded in cross-session memory. Incoming audio frames of 20–40ms are ingested via WebRTC or PSTN telephony trunks. At call onset, the platform executes an asynchronous parallel fan-out across all four memory tiers — Redis buffer, pgvector semantic facts, Postgres episodic summaries, and the FalkorDB knowledge graph — completing memory retrieval within an 80ms budget.

On every conversational turn, the caller's audio is concurrently analyzed for paralinguistic acoustic cues via Hume AI and transcribed into text for sentiment analysis. The two signals are fused into a continuous Valence-Arousal coordinate on Russell's Circumplex plane. This fused emotional state, along with the VA-ICECoT intent classification and slot values, is dynamically injected into the system prompt sent to Groq LPU's LLaMA-3.3-70B model. When caller frustration crosses 0.65, the agent automatically modulates its speech cadence, softens phrasing, or triggers deterministic supervisor escalation.

Post-call, an asynchronous 11-stage background worker on Trigger.dev extracts new facts, updates the FalkorDB entity graph, records emotional trajectories, and dispatches external connectors (WhatsApp confirmation, CRM logging) — ensuring that newly learned context is immediately available for subsequent calls.

= SYSTEM ARCHITECTURE
VoCall is structured into five decoupled operational layers to ensure deterministic latency, high availability, and modular scalability:

== Tier 1 — Client and Presentation Layer
Comprises the interactive Vite 8 and React 19 testing application and the enterprise Next.js 14 (App Router) dashboard. It provides developers with agent configuration panels, contact inspection views, post-call analytics, and the in-browser WebCallModal for real-time testing.

== Tier 2 — API Gateway and Routing Layer
A FastAPI-based ASGI backend exposes REST endpoints for authentication, contact management, memory routing, and telephony webhooks, coupled with a Server-Sent Events (SSE) telemetry stream. It includes an AES-256-GCM vault for Bring-Your-Own-Key (BYOK) credential encryption.

== Tier 3 — Real-Time Conversational Media Pipeline
A Pipecat-orchestrated audio engine manages streaming audio ingestion, Silero Voice Activity Detection (VAD), parallel STT and emotion extraction, VA-ICECoT reasoning, and TTS streaming egress over LiveKit WebRTC or Twilio/Exotel/Plivo telephony SIP trunks.

== Tier 4 — Multi-Tier Cognitive Memory and Storage Layer
Four distinct storage engines operate concurrently: Upstash Redis for ephemeral in-call state, Supabase Postgres 15 for relational data, Supabase pgvector with HNSW cosine indexing for semantic facts, and FalkorDB for the associative entity knowledge graph.

== Tier 5 — Asynchronous Worker Layer
An asynchronous Trigger.dev v3 background worker executes the 11-stage post-call pipeline, handling conversation summarization, semantic fact embedding, OpenCypher graph updates, and third-party connector dispatch without blocking audio paths.

= TECHNOLOGY STACK
- *Interactive Frontend:* Vite 8, React 19, Tailwind CSS, Lucide Icons, Framer Motion 12, Recharts
- *Enterprise Dashboard:* Next.js 14 (App Router), React 18, Radix UI, Trigger.dev SDK
- *Backend API:* Python 3.10+, FastAPI, Uvicorn, Pydantic v2, Asyncio
- *Real-Time Media Engine:* Pipecat AI Framework, LiveKit Cloud WebRTC Server, Silero VAD
- *LLM Engine:* Groq LPU (LLaMA-3.3-70B-Versatile, 14,400 req/day free tier), Cerebras AI fallback
- *Speech-to-Text:* Groq Whisper Large-v3 (English), Sarvam AI Saarika v2 (Hindi / Hinglish)
- *Text-to-Speech:* Cartesia Sonic-2 (ultra-low latency), Sarvam Bulbul v2, Hume AI Octave 2
- *Emotion Engine:* Hume AI Expression Measurement API (48 audio prosody dims) & Groq NLP
- *Databases:* Supabase Postgres 15 with pgvector (500 MB free), Upstash Redis, FalkorDB
- *Action Connectors:* WhatsApp Cloud API, Google Calendar, HubSpot, Salesforce, Slack, SQL
- *Security & Compliance:* AES-256-GCM BYOK credential encryption, DPDP Act 2023 cascading purge
- *Telephony Providers:* Twilio, Exotel, Plivo (Bring-Your-Own-Key SIP trunking)

= CORE MODULES AND FUNCTIONAL DESCRIPTION

== 4-Tier Hybrid Cognitive Memory Engine
The memory engine unifies four distinct storage layers to resolve conversational amnesia within an 80ms parallel budget:
- *Tier 1 — Working Memory (Upstash Redis):* Holds the active call's turn buffer, rolling emotion moving averages, and carried-forward slot values (under 10ms REST latency).
- *Tier 2 — Long-Term Semantic Memory (pgvector):* Stores 1536-dimensional fact embeddings per contact, returning the top-5 facts above a 0.75 cosine similarity threshold using an HNSW index (under 35ms).
- *Tier 3 — Episodic Memory (Supabase Postgres):* Stores structured summaries, key topics, outcome states, and emotional trajectories across the contact's last 3 calls (under 25ms).
- *Tier 4 — Associative Knowledge Graph (FalkorDB):* Models contacts, episodes, entities, and grievances connected by `Contact -HAD_EPISODE-> Episode`, `LEADS_TO`, and `FRUSTRATED_ABOUT` edges, answering multi-hop causal queries via OpenCypher (under 40ms).

All four tiers execute in parallel using `asyncio.gather`. The combined results are synthesized into a compact memory context block injected directly into the LLM system prompt prior to generation.

== Dual-Signal Emotion Fusion Engine
Acoustic prosody features extracted via Hume AI (48 dimensions including pitch variance, energy, and vocal tension) are mapped to Russell's Circumplex plane $(V_"audio", A_"audio")$. Linguistic sentiment extracted via Groq LLaMA yields $(V_"text", A_"text")$. The signals are fused using a locked 60/40 convex combination: $V_"fused" = 0.60 dot V_"audio" + 0.40 dot V_"text"$, and $A_"fused" = 0.60 dot A_"audio" + 0.40 dot A_"text"$. A confidence gate requires $C_"fused" >= 0.50$ before the fused state modulates LLM instructions or alters TTS synthesis cadence.

== VA-ICECoT Intent Engine
Every caller utterance triggers a 4-step intention-centric chain-of-thought: (1) Observation of fused affective state, (2) Inferred Cause from turn context, (3) Intent Categorization (inquiry, complaint, transaction, clarification, chitchat, escalation), and (4) Conversational Goal. Multi-turn slot values (dates, service types) are preserved across turns. When the computed frustration index crosses 0.65, the system executes a deterministic emergency escalation override, routing the call to a human supervisor and bypassing automated tool execution.

== Action Connector Framework
A central dispatcher orchestrates live and post-call actions across eight modular connectors: WhatsApp, Google Calendar, HubSpot, Salesforce, Slack, HMAC-signed custom webhooks, and parameterized read-only SQL queries. All third-party API credentials are encrypted at rest using AES-256-GCM authenticated encryption with unique cryptographic nonces.

== Web Call Testing Studio
An in-browser WebRTC testing modal manages a 4-phase call lifecycle (idle, connecting, active, ended). It features a dynamic 3-state voice orb, an auto-scrolling live transcript stream delivered via Server-Sent Events (SSE), and a post-call decision screen allowing developers to save or discard call telemetry.

== DPDP Act 2023 “Forget Me” Erasure Protocol
In compliance with India's Digital Personal Data Protection Act 2023, a single API call initiates an atomic cascading deletion across all storage engines: `Purge(contact_id)` -> `{DEL Redis, DELETE pgvector, DELETE Postgres, DETACH DELETE FalkorDB}`. The operation writes an immutable SHA-256 audit record logging the timestamp and record counts without storing identifiable personal data.

= METHODOLOGY
1. *Phase 1 (Weeks 1–6):* Architectural design, Pipecat and LiveKit audio loop configuration, and Twilio/Exotel PSTN webhook integration.
2. *Phase 2 (Weeks 7–12):* Implementation of 4-tier parallel memory fan-out (Redis, pgvector, Postgres, FalkorDB) and Hume + Groq 60/40 emotion fusion.
3. *Phase 3 (Weeks 13–18):* VA-ICECoT intent reasoning protocol, Sarvam AI native Hinglish STT/TTS routing, and action connector dispatcher.
4. *Phase 4 (Weeks 19–24):* Next.js dashboard development, DPDP Act 2023 cascading deletion engine, and in-browser WebRTC testing studio.
5. *Phase 5 (Weeks 25–28):* End-to-end turn latency benchmarking, JRBM joint evaluation, IEEE conference paper preparation, and synopsis submission.

= MATHEMATICAL FORMULATION
Dual-Signal Emotion Fusion on Russell's Circumplex plane combines acoustic prosody and textual sentiment:
$ V_"fused" = 0.60 dot V_"audio" + 0.40 dot V_"text", quad A_"fused" = 0.60 dot A_"audio" + 0.40 dot A_"text" $

Dominance is selected based on acoustic confidence: $D_"fused" = D_"audio"$ if $C_"audio" > 0.60$, else $D_"text"$. A confidence gate enforces $C_"fused" >= 0.50$ before modulating prompt instructions.

The scalar Frustration Index $F$ triggering adaptive tone softening and supervisor escalation is computed as:
$ F = w_1 dot E_"fused"["anger"] + w_2 dot E_"fused"["annoyance"] + w_3 dot E_"fused"["distress"], quad "Threshold": F >= 0.65 $

Semantic fact retrieval from pgvector uses cosine similarity between query embedding $q$ and fact embedding $f in RR^1536$ with an HNSW index:
$ "similarity"(q, f) = (q dot f) / (||q|| dot ||f||) >= 0.75 $

Joint accuracy is validated using the Joint Recognition Balance Metric (harmonic mean of intent and emotion micro-$F_1$):
$ "JRBM" = (2 dot F_(1, "intent") dot F_(1, "emotion")) / (F_(1, "intent") + F_(1, "emotion")) $

= TOOLS AND SOFTWARE REQUIREMENTS

== Hardware Requirements
- *Development Processor:* 6-core x86-64 CPU (Intel Core i5 11th Gen / AMD Ryzen 5 5600H minimum)
- *System Memory (RAM):* 16 GB DDR4 minimum (to support concurrent Docker engines and dev servers)
- *Disk Storage:* 50 GB free SSD space
- *Network Bandwidth:* Broadband connection (over 25 Mbps, under 30ms jitter) for live WebRTC audio streams
- *GPU Requirement:* None; all model inference executes remotely on Groq LPUs and cloud AI endpoints

== Software Requirements
- *Operating System:* Ubuntu 22.04 LTS / Windows 11 development environment
- *Backend Runtime:* Python 3.10+, FastAPI, Uvicorn, Pydantic v2, Pipecat AI, LiveKit Python SDK
- *Frontend Runtime:* Node.js 18+, Vite 8, React 19, Next.js 14 (App Router), Tailwind CSS
- *Databases:* Supabase Postgres 15 (with pgvector), Upstash Redis (Serverless), FalkorDB
- *Cloud AI & Speech:* Groq Cloud (LLaMA-3.3-70B, Whisper large-v3), Sarvam AI, Hume AI, Cartesia
- *Free-Tier Economics:* Groq (14.4k req/day), Supabase (500MB), Upstash (10k cmd/day), LiveKit (50GB)

= EXPECTED OUTCOME
At project completion, VoCall will deliver a fully functional, open-source voice AI platform under the MIT license. Key outcomes include:
- *Sub-500ms Turn Latency:* Observed P95 turnaround latency under 530ms (target 495ms budget: VAD 40ms, STT 150ms, Memory/Emotion under 50ms, LLM TTFT 150ms, TTS TTFAB 80ms, WebRTC 25ms).
- *Cross-Session Contextual Continuity:* Contact-specific facts, past call episodes, and entity relationships recalled in under 80ms across multiple sessions.
- *Real-Time Affective Adaptation:* In-flight tone modulation and supervisor escalation when frustration crosses 0.65.
- *Native Hinglish Preservation:* Fluent code-switched Hindi-English speech without translation wrapper distortion.
- *Academic Deliverables:* A complete B.Tech dissertation and an IEEE conference manuscript (`paper.pdf`) submitted for peer review.

= APPLICATIONS
- *Enterprise Customer Support:* Automated helpdesk routing with cross-call contextual memory, reducing handle times.
- *Healthcare Appointment & Triage:* Patient appointment scheduling and empathetic triage assistance.
- *Empathetic Debt Collection:* Compliance-aware recovery conversations with real-time tone softening.
- *Inbound Sales Qualification:* High-volume lead qualification with instant CRM synchronization.
- *Multilingual Citizen Helplines:* Public grievance redressal in native Hindi and code-switched Hinglish.

= FUTURE SCOPE
Future extensions include: (1) Expanding native acoustic models to additional Indian regional languages (Tamil, Telugu, Bengali, Marathi); (2) Enhancing FalkorDB with automated causal-chain discovery across recurring customer complaints; (3) Edge-deployed emotion inference using lightweight quantized models to further reduce network latency; and (4) Deep bidirectional connectors for enterprise ERP platforms (SAP, Oracle) and IT ticketing suites.

= CONCLUSION
VoCall addresses the fundamental shortcomings of contemporary voice AI platforms — high latency, cross-session amnesia, and emotional blindness — through a unified architecture integrating a 4-tier cognitive memory fan-out, a dual-signal emotion fusion engine, and intention-centric reasoning. Grounded in peer-reviewed research (ACL 2025/2026) and paired with free-tier production infrastructure, VoCall proves that an enterprise-grade voice agent can be ultra-fast, emotionally empathetic, and capable of perpetual memory, bringing conversational voice AI significantly closer to natural human interaction.

= REFERENCES
+ Y. Zhang et al., "IntentionESC: Intention-Centered Emotional Support Conversation," in _Findings of the Association for Computational Linguistics (ACL)_, 2025.
+ X. Huang et al., "JX4MEI: Joint Multimodal Emotion-Intent Explanation via Language-Query Former," in _Findings of the Association for Computational Linguistics (ACL)_, 2026.
+ K. Yin et al., "SWI: Speaking with Intent in Large Language Models," in _Proceedings of the International Natural Language Generation Conference (INLG)_, 2025.
+ Y. Liu et al., "MC-EIU: A Multimodal Conversational Emotion and Intent Benchmark," _arXiv:2407.02751_, 2024.
+ H. Yu et al., "AffectMind: An Affective Multimodal Agent with Proactive Knowledge Grounding," _arXiv:2511.21728_, 2025.
+ J. A. Russell, "A Circumplex Model of Affect," _Journal of Personality and Social Psychology_, vol. 39, no. 6, pp. 1161-1178, 1980.
+ C. Packer et al., "MemGPT: Towards LLMs as Operating Systems," _arXiv:2310.08560_, 2023.
+ Digital Personal Data Protection Act, 2023, Government of India, Gazette of India, 2023.
