#set page(
  paper: "a4",
  margin: (top: 2.2cm, bottom: 2.2cm, left: 2.2cm, right: 2.2cm),
  header: context {
    if counter(page).get().first() > 1 {
      text(size: 8.5pt, fill: rgb("#475569"))[
        *VoCall* — Slide-by-Slide Speaker Notes & Presentation Script
        #h(1fr)
        Priyanshu | Abhishek | Ananya
      ]
      v(-0.3cm)
      line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))
    }
  },
  footer: context {
    align(center, text(size: 9pt, fill: rgb("#64748b"))[Page #counter(page).get().first()])
  }
)

#set text(
  font: ("Segoe UI", "Arial"),
  size: 10pt,
  fill: rgb("#1e293b")
)
#set par(justify: true, leading: 0.65em)

#align(center)[
  #text(size: 18pt, weight: "bold", fill: rgb("#1e3a8a"))[VoCall: Slide-by-Slide Speaker Notes & Delivery Script]   #v(2pt)
  #text(size: 12pt, weight: "medium", fill: rgb("#0f766e"))[3-Presenter Delivery Guide: Priyanshu, Abhishek, Ananya]   #v(2pt)
  #text(size: 9.5pt, fill: rgb("#475569"))[*Supervised by Dr. Shivkant* (Assistant Professor) | *Team:* Priyanshu, Abhishek, Ananya, Adarsh]
]

#v(8pt)
#line(length: 100%, stroke: 1pt + rgb("#0f766e"))
#v(6pt)

#text(size: 12pt, weight: "bold", fill: rgb("#0f766e"))[Speaking Allocation & Timing Summary] - *Total Estimated Presentation Duration:* ~10 minutes (600 seconds).
- *Priyanshu (Opening, Problem, Architecture, Memory):* Slides 1, 4, 8, 10 (Part A). Total time: ~3.75 minutes.
- *Abhishek (Literature Review, Objectives, Emotion/VA-ICECoT, Evaluation):* Slides 5, 6, 10 (Part B), 11. Total time: ~3.5 minutes.
- *Ananya (Proposed System, Tech Stack, Conclusion, References):* Slides 7, 9, 2, 3. Total time: ~2.75 minutes.
- *Adarsh's Engineering Credit:* Frontend UI, Agent Studio, and WebCall WebRTC browser environment (detailed during viva defense).

#v(10pt)
#line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))
#v(10pt)

#let slideblock(slidenum, pptxnum, title, presenter, duration, script, handoff: none, takeaway: none) = {
  block(
    width: 100%,
    stroke: 0.75pt + rgb("#94a3b8"),
    radius: 5pt,
    fill: rgb("#f8fafc"),
    inset: 11pt,
    spacing: 12pt,
    [
      #grid(
        columns: (1fr, auto),
        [#text(weight: "bold", size: 11pt, fill: rgb("#1e3a8a"))[Slide #slidenum (PPTX Slide #pptxnum): #title]],
        [#text(size: 9pt, weight: "bold", fill: rgb("#0f766e"))[#presenter | #duration]]
      )
      #v(6pt)
      #text(weight: "bold", size: 9.5pt, fill: rgb("#0f172a"))[Spoken Script:]       #text(fill: rgb("#334155"))[#script]
      #if handoff != none [
        #v(6pt)
        #text(weight: "bold", size: 9pt, fill: rgb("#2563eb"))[Verbal Handoff Cue: ] #text(style: "italic", size: 9pt, fill: rgb("#1e40af"))[#handoff]
      ]
      #if takeaway != none [
        #v(4pt)
        #text(weight: "bold", size: 9pt, fill: rgb("#059669"))[Core Takeaway: ] #text(size: 9pt, fill: rgb("#047857"))[#takeaway]
      ]
    ]
  )
}

#slideblock(
  "1", "1", "Title Slide", "Priyanshu", "45s",
  ["Good morning, respected supervisor Dr. Shivkant sir and honorable members of the panel. Today, our team is presenting our final project: *VoCall — The Memory-Augmented Voice Calling Agent with Emotional Awareness*.

  My name is Priyanshu, and presenting with me today are Abhishek and Ananya. Our fourth teammate, Adarsh, built the frontend engineering and browser testing studio for our platform.

  VoCall addresses the trade-off between conversational speed and deep contextual understanding in voice agents. We solve this by combining a four-tier persistent memory, dual-signal emotion fusion, and a structured intent engine into a streaming voice pipeline. Abhishek will now walk you through the real-world problem and literature that motivated this system."],
  handoff: ["Over to you, Abhishek, for the problem statement and literature review."]
)

#slideblock(
  "2", "4", "Introduction — Problem Statement & Motivation", "Priyanshu", "60s",
  ["When we examine voice agents deployed in production today, we see a recurring compromise: systems either pick fast, shallow conversations, or slower, detached retrieval that breaks human speech cadence.

  Specifically, existing voice platforms suffer from three severe bottlenecks:
  1. *Contextual Amnesia:* When a user calls support on Monday and calls back on Thursday, the agent has zero recollection of their previous conversation, open tickets, or preferences.
  2. *Emotional Blindness:* Current agents parse words, but miss distress, urgency, or frustration carried in vocal pitch and cadence.
  3. *Brittle Dialogue Flow:* Basic intent classifiers either hallucinate or fail when conversational context shifts during task execution.

  VoCall's goal is to build a production voice platform where persistent caller memory, acoustic-textual emotion intelligence, and deterministic intent execution run inside a sub-500-millisecond voice loop."],
  handoff: ["Let's examine how academic literature approaches these constraints. Abhishek will present the literature review."]
)

#pagebreak()

#slideblock(
  "3", "5", "Literature Review — Problems in Existing Approaches", "Abhishek", "60s",
  ["Thank you, Priyanshu. In our survey of conversational systems, dialogue systems generally fall into two categories, both with clear bottlenecks:

  Traditional rule-based IVRs provide deterministic task routing, but are rigid and fail completely on natural phrasing. Modern LLM voice wrappers offer fluid conversational ability, but treat each call as an isolated session.

  As highlighted on the slide, the research gaps are clear:
  - *Contextual Amnesia:* Once a call disconnects, state vanishes.
  - *Limited Emotional Awareness:* Recent papers like Zhang et al. (ACL 2025) and Huang et al. (ACL 2026) emphasize joint emotion-intent understanding, but practical voice implementations rarely fuse prosodic audio cues with textual sentiment.
  - *Code-Switching Difficulty:* Most commercial engines degrade rapidly on Hindi-English (Hinglish) code-switching common across Indian speakers.
  - *Latency Constraints:* Multi-agent frameworks often introduce 2 to 3 seconds of delay, completely destroying conversational turn-taking.

  These findings established the technical foundation of what VoCall addresses."],
  takeaway: [Key references: Zhang et al. (ACL 2025 IntentionESC), Huang et al. (ACL 2026 JX4MEI).]
)

#slideblock(
  "4", "6", "Research Objectives", "Abhishek", "45s",
  ["To directly address these gaps, our project established seven concrete research objectives:
  1. *Layered Architecture:* Separate client, API, persistent storage, real-time voice streaming, and asynchronous background jobs.
  2. *Four-Tier Hybrid Memory:* Build and benchmark short-term call state, semantic long-term memory, episodic summaries, and graph relationships.
  3. *Dual-Signal Emotion Fusion:* Combine acoustic prosody from raw audio with textual sentiment from transcripts.
  4. *VA-ICECoT Engine:* Implement Voice-Adapted Intent, Slot & Emotion Chain-of-Thought for deterministic action dispatch.
  5. *Hinglish Support:* Integrate language-aware STT and TTS routing for Hindi-English code-switched dialogues.
  6. *Browser-Based WebCall Studio:* Enable zero-telephony testing directly from the browser using WebRTC.
  7. *Unified Agent Studio:* Allow developers to configure prompts, memory scopes, tools, and voice properties in one interface.

  Ananya will now present our proposed system architecture and contributions."],
  handoff: ["Ananya will now present how VoCall translates these objectives into a functioning platform."]
)

#slideblock(
  "5", "7", "Proposed System — VoCall Major Contributions", "Ananya", "60s",
  ["Thank you, Abhishek. On this slide, you see how each identified challenge maps directly to an engineering module in VoCall:
  - Where standard voice bots suffer from context loss, VoCall introduces our *Four-Tier Hybrid Memory*, balancing in-memory speed with relational knowledge.
  - Where existing systems miss emotional shifts, our *Dual-Signal Fusion Engine* tracks caller sentiment turn-by-turn.
  - Where standard LLM bots hallucinate during tool execution, our *VA-ICECoT Engine* validates required slots and executes business connectors deterministically.
  - For Indian language code-switching, we use *language-aware STT and TTS routing*, utilizing Sarvam AI alongside Whisper and Cartesia.
  - And to remove the bottleneck of costly SIP trunks and telephony carriers during development, Adarsh built our *Web Call testing studio* using direct LiveKit WebRTC audio.

  Priyanshu will now walk you through the layered system architecture that connects these components."],
  handoff: ["Priyanshu will now detail the system architecture."]
)

#pagebreak()

#slideblock(
  "6", "8", "System Architecture — Modular Platform Design", "Priyanshu", "75s",
  ["Our system architecture is structured into clean functional layers to ensure hard real-time guarantees:

  At the top, the *Client Layer* consists of the Next.js and React dashboard, where operators configure agents and test audio via WebRTC.

  The *API Layer* is built on FastAPI. It handles authentication, caller profile management, contact records, and webhook routing.

  Below this is the *Intelligence Layer*, housing our four-tier memory retriever, the dual-signal emotion fusion engine, and the VA-ICECoT intent loop.

  The core of the platform is the *Real-Time Voice Pipeline*, orchestrated using Pipecat and LiveKit. Audio chunks stream bidirectionally over WebRTC. Interruption handling (VAD) runs directly on the audio stream.

  A crucial architectural decision is the *Async Post-Call Processing layer via Trigger.dev*. Heavy operations—like calculating conversation metrics, generating episodic summaries, and extracting knowledge graph entities—are completely decoupled from the live call. The voice pipeline never waits on database writes or heavy background consolidation."],
  takeaway: [The time-sensitive voice path (under 500 ms) is decoupled from post-call processing (async workers).]
)

#slideblock(
  "7", "9", "Technology Stack", "Ananya", "60s",
  ["Our technology stack was selected to satisfy stringent latency and stability requirements:
  - *Frontend & Client:* Next.js, React, TypeScript, and Tailwind CSS, providing real-time telemetry and call monitoring.
  - *Backend:* Python and FastAPI for asynchronous I/O and clean OpenAPI service boundaries.
  - *Voice Orchestration:* Pipecat for frame-based audio pipeline construction, coupled with LiveKit for production WebRTC media transport.
  - *AI & Speech Providers:* Groq running LLaMA 3.3 for ultra-low first-token latency; Whisper and Sarvam AI for multilingual STT; Cartesia and Sarvam AI for streaming TTS synthesis; and Hume AI for voice prosody analysis.
  - *Storage Architecture:* Supabase PostgreSQL for relational data; pgvector for semantic fact search; Upstash Redis for sub-5ms active call state; and FalkorDB for low-latency graph traversals.
  - *Job Orchestration:* Trigger.dev for resilient asynchronous background tasks.

  Now, Priyanshu and Abhishek will present our core innovations: the memory architecture, emotion fusion, and VA-ICECoT."],
  handoff: ["Priyanshu will now break down our Four-Tier Memory Architecture."]
)

#pagebreak()

#slideblock(
  "8", "10", "Core Innovation — Memory, Emotion & VA-ICECoT", "Priyanshu & Abhishek", "90s",
  [*Part A: Four-Tier Hybrid Memory (Priyanshu — 45s):*   "The first core innovation is our *Four-Tier Hybrid Memory Architecture*:
  1. *Short-Term Memory (Upstash Redis):* Holds active call context, recent turns, and currently collected slots in single-digit milliseconds.
  2. *Long-Term Semantic Memory (PostgreSQL + pgvector):* Stores caller facts, profile attributes, and semantic embeddings retrieved using cosine distance over previous conversations.
  3. *Episodic Memory (PostgreSQL):* Preserves structured summaries of past calls—what was discussed, what issue was resolved, and the customer's sentiment.
  4. *Knowledge Graph (FalkorDB):* Maps relationships between entities—such as caller to company, caller to pending tickets, or products discussed.

  In our code (`app/services/memory/retriever.py`), we query these tiers concurrently using `asyncio.gather`, bounding total retrieval latency to under 45 milliseconds before prompting the LLM."

  #v(4pt)
  *Part B: Dual-Signal Emotion Fusion & VA-ICECoT (Abhishek — 45s):*   "Alongside memory, we implement *Dual-Signal Emotion Fusion*:
  Human emotion lives both in *what* is said and *how* it is said. We extract acoustic prosody from raw audio via Hume AI, and combine it with textual sentiment extracted via Groq. Our fusion algorithm weights acoustic signal at 60% and text at 40%, because acoustic prosody reliably betrays frustration before words do.

  This fused state feeds directly into *VA-ICECoT*—our Voice-Adapted Intent, Slot & Emotion Chain-of-Thought engine. Instead of handing full control to an unconstrained LLM, VA-ICECoT identifies the intent, tracks required slots, evaluates deterministic combined rules, and triggers business connectors—such as booking a Google Calendar event or updating HubSpot CRM.

  I will now present our evaluation framework and target metrics."]
)

#slideblock(
  "9", "11", "Evaluation — Proposed Metrics", "Abhishek", "60s",
  ["To evaluate VoCall rigorously, we established six empirical metrics:
  1. *End-to-End Latency:* Target is under 500 milliseconds from the moment the user stops speaking to the first audio packet returned.
  2. *Voice First-Byte Latency:* TTS streaming synthesis target is under 100 milliseconds using Cartesia's WebSocket protocol.
  3. *Emotion Fusion Accuracy:* Target is greater than 90% correlation against human-annotated sentiment benchmarks.
  4. *Intent Accuracy:* Target is greater than 95% classification accuracy across labelled task scenarios.
  5. *Memory Retrieval Precision:* Target is greater than 92% precision for relevant semantic and graph facts injected into prompt context.
  6. *Task Completion Rate:* Target is greater than 85% for end-to-end simulated calls involving slot filling and connector execution.

  We want to be explicit: the architecture, memory tiers, fusion rules, and voice pipelines are implemented. Formal large-scale statistical validation across diverse benchmark datasets is scheduled for our final project phase.

  Ananya will conclude our presentation with our summary and future roadmap."],
  handoff: ["Ananya will now present our conclusion and future roadmap."]
)

#pagebreak()

#slideblock(
  "10", "2", "Conclusion & Future Work", "Ananya", "60s",
  ["To conclude, VoCall demonstrates a practical, production-oriented approach to intelligent voice systems:
  - We unified four memory tiers to eliminate contextual amnesia between calls.
  - We fused acoustic prosody with textual sentiment to give agents genuine emotional context.
  - We built the VA-ICECoT framework to bridge emotion, intent, slot validation, and business action execution.
  - And we decoupled real-time voice streaming from heavy asynchronous database indexing.

  *Future Scope:* In upcoming phases, we plan to expand native support for additional regional Indian languages, calibrate acoustic emotion models specifically for Indian accents, implement stronger cross-session memory consolidation algorithms, and perform large-scale empirical stress testing against our proposed latency and accuracy targets.

  Thank you Dr. Shivkant sir and esteemed panel members. Abhishek, Priyanshu, and I are now ready to take your questions."],
  takeaway: [Questions will be answered by Priyanshu (architecture & memory), Abhishek (emotion & intent), and Ananya (pipeline & connectors).]
)

#slideblock(
  "11", "3", "References", "Ananya", "15s",
  ["These are the key research papers and internal engineering specifications guiding our work, including recent publications from ACL 2025 and ACL 2026 on intention-centered emotional dialogue and multimodal joint understanding. Thank you."]
)

#v(1cm)
#align(center)[
  #text(size: 10pt, weight: "bold", fill: rgb("#64748b"))[--- End of Presentation Script ---]
]
