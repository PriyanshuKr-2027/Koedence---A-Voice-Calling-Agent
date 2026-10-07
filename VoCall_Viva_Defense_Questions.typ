#set page(
  paper: "a4",
  margin: (top: 2.2cm, bottom: 2.2cm, left: 2.2cm, right: 2.2cm),
  header: context {
    if counter(page).get().first() > 1 {
      text(size: 8.5pt, fill: rgb("#475569"))[
        *VoCall* — Viva Examination Q&A Defense Handbook
        #h(1fr)
        *Priyanshu* (Architecture & Memory)
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

// Custom components
#let questionbox(qnum, title, trap, answer, keymetrics: none) = {
  block(
    width: 100%,
    stroke: 1pt + rgb("#2563eb"),
    radius: 6pt,
    fill: rgb("#f8fafc"),
    inset: 11pt,
    spacing: 14pt,
    [
      #text(weight: "bold", size: 11pt, fill: rgb("#1e3a8a"))[Examiner Question #qnum: #title]
      #v(6pt)
      #block(
        width: 100%,
        stroke: 0.75pt + rgb("#dc2626"),
        radius: 4pt,
        fill: rgb("#fff1f2"),
        inset: 7pt,
        [
          #text(weight: "bold", size: 8.5pt, fill: rgb("#991b1b"))[TRAP / WHAT THE EXAMINER IS TESTING:]           #text(size: 9pt, fill: rgb("#7f1d1d"))[#trap]
        ]
      )
      #v(6pt)
      #text(weight: "bold", fill: rgb("#0f172a"))[Your Spoken Answer:]       #text(fill: rgb("#334155"))[#answer]
      #if keymetrics != none [
        #v(5pt)
        #block(
          width: 100%,
          fill: rgb("#eff6ff"),
          stroke: 0.5pt + rgb("#bfdbfe"),
          radius: 4pt,
          inset: 6pt,
          [#text(weight: "bold", size: 8.5pt, fill: rgb("#1d4ed8"))[KEY METRICS TO QUOTE: ] #text(size: 8.5pt, fill: rgb("#1e40af"))[#keymetrics]]
        )
      ]
    ]
  )
}

// Title Section
#align(center)[
  #text(size: 18pt, weight: "bold", fill: rgb("#1e3a8a"))[VoCall: Viva Defense Handbook & Technical Q&A]   #v(2pt)
  #text(size: 12pt, weight: "medium", fill: rgb("#0f766e"))[The Memory-Augmented Voice Calling Agent with Emotional Awareness]   #v(2pt)
  #text(size: 9.5pt, fill: rgb("#475569"))[*Supervised by Dr. Shivkant* (Assistant Professor)]
]

#v(8pt)
#align(center)[
  #table(
    columns: (auto, auto),
    stroke: none,
    align: (right, left),
    gutter: 3pt,
    [*Priyanshu:*], [4-Tier Hybrid Memory Architecture & Overall System Pipeline],
    [*Abhishek:*], [Dual-Signal Emotion Fusion & VA-ICECoT Reasoning Engine],
    [*Ananya:*], [Streaming Voice Pipeline (LiveKit/Pipecat) & Connectors],
    [*Adarsh:*], [Frontend Agent Studio & WebCall Browser Testing Environment],
  )
]

#line(length: 100%, stroke: 1pt + rgb("#0f766e"))
#v(6pt)

#text(size: 12pt, weight: "bold", fill: rgb("#0f766e"))[Quick Reference: Your Individual Contributions] When the panel asks *"What was your individual contribution to the project?"*, state this clearly:
- *Overall System Architecture:* Designed the layered modular architecture separating the client layer, FastAPI endpoints, real-time voice streaming workers, and asynchronous post-call job execution.
- *4-Tier Hybrid Memory Retriever (`app/services/memory/retriever.py`):* Engineered the retrieval coordinator that queries Upstash Redis (short-term), pgvector (semantic facts), PostgreSQL (episodic summaries), and FalkorDB (knowledge graph) concurrently using `asyncio.gather`, keeping memory latency under 45 ms.
- *Async Decoupling:* Designed the boundary using Trigger.dev so CPU-heavy summarization and graph insertion never starve the live voice event loop.

#pagebreak()

#text(size: 13pt, weight: "bold", fill: rgb("#1e3a8a"))[1. System Architecture & Latency Defense]
#v(4pt)

#questionbox(
  "1",
  "How do you achieve an end-to-end voice latency of under 500 ms?",
  "The examiner wants to verify whether you actually measured your pipeline stages or simply wrote a target latency on the slide.",
  [We budget our 500 ms turnaround across five pipelined streaming stages without waiting for full buffers:
  1. *Voice Activity Detection (Silero VAD):* Processes 20 ms PCM audio frames. Cuts off after 150 ms of trailing silence.
  2. *Streaming STT (Whisper / Sarvam AI):* Emits final transcript within 120 ms of speech cessation over WebSockets.
  3. *Parallel Intelligence Loop (`va_icecot.py`):* Memory retrieval, emotion fusion, and intent classification run concurrently. Groq LLaMA 3.3 outputs its first token within 120 ms.
  4. *Streaming TTS (Cartesia):* Emits synthesized audio chunks over WebSocket within 80 ms of receiving the first sentence token.
  5. *LiveKit WebRTC Transport:* Adds 15 to 25 ms of jitter buffer delay.   Summing these: $150 + 120 + 120 + 80 + 20 = 490$ ms. By streaming sentence chunks rather than waiting for complete paragraphs, the caller hears speech well before the LLM finishes generating.],
  keymetrics: "150 ms VAD cut-off, 120 ms Groq TTFT, 80 ms Cartesia first-chunk, total pipeline ~490 ms."
)

#questionbox(
  "2",
  "Why did you decouple real-time voice from post-call processing using Trigger.dev?",
  "Testing whether you understand Python event-loop blocking, server resources, and asynchronous architecture.",
  [In voice agents, database indexing and LLM summarization take 2 to 5 seconds. If we ran summarization, vector embedding generation, and graph updates inside the FastAPI call loop or standard `BackgroundTasks`:
  - The Python `asyncio` event loop becomes blocked by CPU-bound JSON serialization and embedding calls, causing audio packet jitter on active calls.
  - If the server restarts or an LLM call fails, the call summary is lost.   By pushing post-call events to Trigger.dev, we obtain isolated serverless execution, automatic retries with exponential backoff, and zero CPU load on our live voice streaming workers.]
)

#pagebreak()

#text(size: 13pt, weight: "bold", fill: rgb("#1e3a8a"))[2. Four-Tier Hybrid Memory Architecture]
#v(4pt)

#questionbox(
  "3",
  "Why 4 tiers? Why couldn't you just use a single RAG vector database for everything?",
  "This is your primary defense question as the memory lead. Examiners expect clear justification for why each tier is necessary.",
  [A single vector database fails in voice systems because conversational context has four fundamentally different access patterns:
  - *Short-Term State (Redis):* Slot values (booking time, phone number) change every turn. Querying a vector database for active state costs 50 ms and lacks atomic updates. Redis handles this in 2 ms.
  - *Semantic Memory (pgvector):* Vector similarity finds unstructured semantic facts across past calls using cosine distance. But vectors cannot navigate multi-hop relationships.
  - *Episodic Memory (PostgreSQL):* Humans recall past interactions chronologically—*what happened on Tuesday?* Vector distance cannot guarantee temporal order; relational tables with indexed timestamps do.
  - *Knowledge Graph (FalkorDB):* If a caller asks *"Can you apply the discount promised to my branch manager?"*, vector search fails because the link between Customer -> Branch -> Manager -> Discount is a graph relationship. FalkorDB resolves this in Cypher queries in under 15 ms.   In `retriever.py`, we query all four tiers concurrently using `asyncio.gather`, keeping total memory retrieval time bounded by the slowest query (~45 ms).],
  keymetrics: "Redis ~2 ms, FalkorDB Cypher ~15 ms, pgvector ~40 ms, total concurrent retrieval <45 ms."
)

#questionbox(
  "4",
  "What happens if FalkorDB or pgvector goes down during a live call?",
  "Testing system resilience, error boundaries, and graceful degradation.",
  [Our memory retriever implements strict graceful degradation. In `retriever.py`, every tier query runs inside its own isolated try/except block with timeout constraints:
  - If FalkorDB fails, `_fetch_graph_context` catches the error, logs a warning, and returns empty entity lists: `{"recent_entities": [], "frustration_topics": []}`.
  - If pgvector times out (>80 ms), the pipeline continues using Redis short-term state.
  - The live call never drops. The agent continues the conversation naturally without historical recall for that turn.]
)

#pagebreak()

#text(size: 13pt, weight: "bold", fill: rgb("#1e3a8a"))[3. Dual-Signal Emotion Fusion & VA-ICECoT]
#v(4pt)

#questionbox(
  "5",
  "Why is emotion fusion weighted 60% audio and 40% text? Why not 50/50?",
  "Testing whether the fusion weights are scientifically motivated or arbitrarily assigned.",
  [In telephone conversations, callers often speak polite words while their vocal tone betrays clear frustration—saying *"Sure, take your time"* with high pitch and clipped cadence. A 50/50 split would cause the polite text to cancel out the caller's actual agitation.
  - Acoustic prosody (pitch variance, jitter, speaking rate) from Hume AI is an involuntary physiological signal that callers cannot easily disguise. We give it 60% weight.
  - Safety check in `fusion.py`: if audio confidence falls below 0.6 (due to microphone noise or packet loss), the system falls back to text classification:   `dominant = audio if confidence_audio > 0.6 else text`.   This provides sensitivity to frustration while guarding against acoustic distortion.]
)

#questionbox(
  "6",
  "What is VA-ICECoT and how is it different from standard LangChain or ReAct agents?",
  "Testing your understanding of architectural innovation versus off-the-shelf libraries.",
  [Standard LangChain or ReAct agents use sequential *Thought -> Action -> Observation* loops. In a voice agent, that is unusable:
  1. Each reasoning step requires a distinct LLM call, driving latency to 3 to 5 seconds.
  2. The LLM can hallucinate tool parameters or get trapped in cyclic reasoning while the caller waits in silence.   *VA-ICECoT (Voice-Adapted Intent, Slot & Emotion Chain-of-Thought)* executes in a single structured turn:
  - Simultaneously extracts intent and slot parameters using Pydantic schemas.
  - Fuses the caller's emotional state.
  - Evaluates deterministic decision rules (`combined_rules.py`). If a rule matches (e.g., *Intent: Billing Dispute* + *Emotion: Frustrated*), it immediately executes an escalation action without unconstrained LLM hesitation.]
)

#pagebreak()

#text(size: 13pt, weight: "bold", fill: rgb("#1e3a8a"))[4. Streaming Voice Pipeline, Hinglish & Testing]
#v(4pt)

#questionbox(
  "7",
  "How did you implement browser testing without phone numbers or SIP trunks?",
  "Highlighting Adarsh's contribution and your development testing workflow.",
  [Adarsh built the WebCall testing studio using the *LiveKit WebRTC Client SDK* inside our Next.js frontend:
  - The browser captures microphone audio via `getUserMedia`, encodes it into Opus packets, and negotiates a WebRTC session with our LiveKit media server.
  - Our Pipecat Python worker joins the same LiveKit room as an automated participant, subscribing to the user's audio track and publishing synthesized TTS audio directly back.
  - This allowed our team to test latency, emotion detection, and memory retrieval inside the browser without incurring telephony carrier costs or buying DID phone numbers.]
)

#questionbox(
  "8",
  "How does VoCall handle Hindi-English code-switching (Hinglish)?",
  "Testing real-world feasibility for Indian multilingual callers.",
  [Standard English STT models fail when Indian callers mix languages (*"Mera payment deduct ho gaya but order confirm nahi hua"*).
  - We route audio to *Sarvam AI's Saaras STT*, which is trained on Indian accent phonetics and Hindi-English code-switching.
  - For speech synthesis, we route through Sarvam's Bulbul TTS or Cartesia's multilingual models, maintaining consistent accent and prosody without robotic pronunciation of Indian names and terms.]
)

#pagebreak()

#text(size: 13pt, weight: "bold", fill: rgb("#1e3a8a"))[5. Evaluation, Edge Cases & Limitations]
#v(4pt)

#questionbox(
  "9",
  "On Slide 11, your metrics say 'To Be Evaluated'. Did you actually test the system?",
  "Crucial defense question. Distinguish honest scientific methodology from unfinished work.",
  [Yes, our core architecture, four memory tiers, emotion fusion algorithm, and voice pipeline are fully implemented and functional in our codebase.
  We explicitly marked them as *'To Be Evaluated'* on Slide 11 because we distinguish between functional integration and formal statistical benchmarking:
  - In unit and integration runs, our internal pipeline turnaround consistently clocks between 450 ms and 520 ms on Groq and Cartesia.
  - However, publishing an academic claim of >95% intent accuracy or >90% emotion correlation requires testing across hundreds of standardized multi-speaker datasets (such as IEMOCAP or MELD) with human annotators.
  - This formal, statistically validated empirical benchmark is the exact focus of our final project evaluation phase.],
  keymetrics: "Internal integration latency: 450-520 ms. Benchmarks to target: IEMOCAP, MELD, LibriSpeech."
)

#questionbox(
  "10",
  "What are the main limitations of your system today?",
  "Examiners respect candidates who know their system's weaknesses. Never claim a system is flawless.",
  [We have identified three concrete technical limitations that we are actively addressing:
  1. *Acoustic Noise Sensitivity:* Under heavy ambient noise (traffic, low-quality cellular connections), Hume AI's acoustic emotion confidence drops, forcing fallback to text-only sentiment.
  2. *Cross-Session Entity Reconciliation:* If a customer calls from a different phone number, our system cannot automatically link them to their existing FalkorDB graph entity without explicit caller identification.
  3. *Cold Start on Vector Indexes:* In empty databases, pgvector requires sufficient call volume before semantic similarity yields high-value conversational context.]
)

#v(1cm)
#align(center)[
  #text(size: 10pt, weight: "bold", fill: rgb("#64748b"))[--- End of Viva Defense Handbook ---]
]
