# PROJECT SYNOPSIS
## VoCall: A 4-Tier Cognitive Memory and Dual-Signal Emotion-Aware Architecture for Open-Source, Hinglish-Native Voice Agents

**Degree**: Bachelor of Technology (B.Tech) in Artificial Intelligence and Data Science  
**Academic Year**: Final Year, Session 2026–2027  
**Candidate**: Priyanshu Kumar  
**Institution**: Greater Noida Institute of Technology (GNIOT), Greater Noida, Uttar Pradesh, India  
**Department**: Department of Artificial Intelligence and Data Science  

---

### 1. Abstract
Production voice agents like Vapi, Retell AI, and OmniDim treat every phone call as an isolated event. A customer calling three times in one week regarding the same delayed shipment must re-explain their context, tracking details, and emotional grievance each time. Commercial systems offer no cross-session memory, evaluate sentiment only after the call ends, ignore Indian code-switched speech (Hinglish), and bill in US dollars at prohibitive rates for Indian businesses.

VoCall addresses these gaps by providing an open-source, full-duplex voice agent platform designed for sub-800ms spoken interactions. The system introduces four primary mechanisms:
1. A **four-tier memory architecture** combining in-call Redis state, Supabase pgvector semantic facts, Postgres call logs, and a FalkorDB knowledge graph, queried concurrently in under 80ms via `asyncio.gather`.
2. A **dual-signal emotion fusion engine** that blends Hume AI paralinguistic acoustic prosody with Groq LLaMA text sentiment at a fixed 0.60/0.40 ratio to detect caller distress mid-turn.
3. A **VA-ICECoT intent and slot reasoning protocol** that plans conversational goals inside a hidden thought block prior to token generation.
4. A **native Hinglish speech pipeline** built on Sarvam AI's Saarika v2 and Bulbul v2 models to handle code-switching without artificial translation layers.

VoCall also includes an atomic deletion protocol compliant with India's DPDP Act 2023 that purges all four storage engines in a single transaction with a cryptographic SHA-256 audit log. The entire architecture runs on free-tier infrastructure.

---

### 2. Introduction and Background
Voice agents have progressed beyond traditional touch-tone Interactive Voice Response (IVR) systems. Modern spoken dialogue pipelines integrate real-time Speech-to-Text (STT), Large Language Models (LLMs), and low-latency Text-to-Speech (TTS) synthesis over WebRTC and SIP telephony protocols. These systems process audio frames of 20–40ms and target turnaround latencies below 800ms to preserve human conversational cadence.

While state-of-the-art voice pipelines deliver fluent responses, their architecture remains transactional. Once the audio socket closes, all learned context, entity relationships, and caller emotional trajectories are discarded. This operational amnesia damages customer retention and inflates call handle times across logistics, banking, and citizen helplines.

---

### 3. Problem Statement and Research Gaps
Contemporary voice platforms present five operational bottlenecks:

1. **Cross-Session Amnesia (Single-Store Memory Failure)**: Existing commercial platforms (Vapi, Retell AI) maintain no memory across calls. Research memory systems (MemGPT, Mem0) rely on single flat vector databases that cannot execute multi-hop causal graph traversals (e.g., retrieving how many past calls involved a disputed refund) or track temporal frustration trajectories across episodes.
2. **Unimodal or Post-Call Emotion Blind Spots**: Systems like OmniDim run sentiment classifiers as batch jobs on text transcripts after call completion. Post-call analysis cannot alter in-flight tone, and text-only classifiers fail on sarcasm or acoustic strain where words appear polite but pitch indicates severe anger.
3. **Disconnected Intent and Affective Reasoning**: Existing pipelines isolate intent classification from emotional appraisal. No production system couples intent classification, slot extraction, and emotional appraisal inside a sub-500ms voice turn deadline.
4. **Translation Wrappers for Multilingual Audio**: Current stacks treat Indian languages by bolting translation wrappers onto English-centric models, inflating turn latency past 1500ms and corrupting code-switched Hindi-English (Hinglish) phonemes.
5. **High SaaS Cost Barriers for Indian MSMEs**: US-based platforms charge $0.05 to $0.15 per conversation minute. For Indian micro-, small-, and medium-sized enterprises (MSMEs), these recurring dollar costs make voice automation unaffordable.

---

### 4. Project Objectives
The primary objective of this project is to design, implement, and evaluate VoCall as an open-source, full-stack voice platform. Specific objectives are:

- **O1: Build a 4-Tier Cognitive Memory System**: Implement parallel fan-out retrieval across working memory (Upstash Redis), long-term semantic facts (Supabase pgvector), episodic summaries (Postgres), and a temporal entity graph (FalkorDB), targeting total retrieval latency under 80ms.
- **O2: Implement Dual-Signal Emotion Fusion**: Combine Hume AI acoustic paralinguistics (48 dimensions) and Groq text sentiment onto Russell's Circumplex plane with a 60/40 weighted formula to modulate LLM system prompts and TTS cadence in real time.
- **O3: Design the VA-ICECoT Reasoning Chain**: Adapt intention-centered chain-of-thought planning into a 4-step sequence (observation, cause inference, intent categorization, conversational goal) with deterministic emergency escalation overrides.
- **O4: Deploy a Native Hinglish Speech Pipeline**: Integrate Sarvam AI's Saarika v2 STT and Bulbul v2 TTS to transcribe and synthesize code-switched speech directly without intermediate translation wrappers.
- **O5: Implement DPDP Act 2023 Deletion Protocol**: Build a single-call cascading purge API that removes customer data across Redis, pgvector, Postgres, and FalkorDB while logging a SHA-256 cryptographic receipt.
- **O6: Validate Against the Joint Recognition Balance Metric (JRBM)**: Formulate and apply JRBM (harmonic mean of intent and emotion micro-F1) to measure joint reasoning accuracy.

---

### 5. Literature Survey & Comparative Analysis

#### Summary of Prior Research and Structural Gaps
| Paper / System | Domain | Key Finding | Gap Addressed by VoCall |
| :--- | :--- | :--- | :--- |
| **IntentionESC** (ACL 2025) | Emotional Support | Intention planning before response generation increases support effectiveness. | Evaluated only on text chat; lacks acoustic prosody and telephony deadlines. |
| **JX4MEI** (ACL 2026) | Multimodal EIU | Cross-attention between audio and text outperforms late decision voting. | Benchmark study only; does not provide a sub-500ms streaming voice pipeline. |
| **SWI** (INLG 2025) | Intent Reasoning | Hidden meta-thought planning tokens prevent hallucinated goals. | Lacks multi-turn slot tracking and acoustic conditioning. |
| **MC-EIU** (2024) | Benchmark | Emotion-intent transitions follow structured statistical distributions. | Provides no runtime system or deterministic emergency escalation rules. |
| **AffectMind** (2025) | Memory Retrieval | Grounding memory retrieval in affective coordinates improves relevance. | Restricted to flat vector storage; cannot traverse multi-hop causal graphs. |
| **MemGPT** (2023) | Virtual Memory | OS-style paging of conversation turns enables perpetual persona consistency. | Paging queries introduce high latency (>1000ms), exceeding voice budgets. |
| **Zep** (2024) | Graph Memory | Temporal knowledge graphs preserve entity relationships. | Closed-source cloud service; lacks emotion-conditioned retrieval and Hinglish models. |

#### Comparison with Existing Voice Platforms
| Feature | VoCall | Vapi | Retell AI | OmniDim | Unpod |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Cross-Call Memory** | 4-tier parallel | None | None | None | Toggle, no depth |
| **Real-Time Text Emotion** | Turn-by-turn (Groq) | No | No | Post-call only | No |
| **Real-Time Audio Emotion** | Yes (Hume AI) | No | No | No | No |
| **Dual-Signal Fusion** | 60/40 weighted | No | No | No | No |
| **Knowledge Graph Memory** | FalkorDB | No | No | No | No |
| **Native Hinglish STT** | Sarvam Saarika v2 | No | No | No | No |
| **India Telephony** | Plivo / Exotel | Twilio only | Twilio only | No | Yes |
| **DPDP Act 2023 Deletion** | Atomic cross-tier | No | No | No | No |
| **Hosting & License** | Open source (MIT) | Closed SaaS | Closed SaaS | Closed SaaS | MIT |
| **Free-Tier Deployable** | Yes | No | No | No | Yes |

---

### 6. Proposed Methodology and Architecture

VoCall is organized into five operational layers:
1. **Client Layer**: A Next.js 14 web dashboard for agent management and contact inspection, coupled with a WebRTC browser testing modal.
2. **FastAPI Application Layer**: Orchestrates REST endpoints, Server-Sent Events (SSE), authentication, and memory routing.
3. **Real-Time Voice Pipeline**: A sub-500ms pipeline powered by Pipecat and LiveKit, coordinating STT, parallel emotion extraction, VA-ICECoT reasoning, LLM inference, and TTS audio egress.
4. **Four-Tier Storage Layer**: Unifies Upstash Redis, Supabase Postgres, Supabase pgvector, and FalkorDB.
5. **Background Worker Layer**: An asynchronous post-call engine on Trigger.dev executing an 11-stage pipeline (fact extraction, graph update, CRM sync).

#### 4-Tier Memory Fan-Out
- **Tier 1 (Working Memory)**: Upstash Redis holds the active call's turn buffer, running emotion moving averages, and extracted slot values (<10ms REST latency).
- **Tier 2 (Long-Term Semantic)**: Supabase pgvector stores 1536-dimensional fact embeddings with an HNSW cosine index, returning the top 5 facts above a 0.75 similarity threshold (<35ms).
- **Tier 3 (Episodic Memory)**: Supabase Postgres stores structured summaries, discussed topics, and emotional trajectories across the last 3 calls (<25ms).
- **Tier 4 (Knowledge Graph)**: FalkorDB stores contact, topic, and entity nodes connected by `LEADS_TO` and `FRUSTRATED_ABOUT` edges, answering multi-hop causal queries via OpenCypher (<40ms).

#### Dual-Signal Emotion Fusion Formulation
Acoustic emotion probabilities from Hume AI are mapped to Russell's Circumplex coordinates $(V_{\text{audio}}, A_{\text{audio}})$. Text sentiment from Groq LLaMA yields $(V_{\text{text}}, A_{\text{text}})$. The signals are fused using a locked convex combination:
$$V_{\text{fused}} = 0.60\,V_{\text{audio}} + 0.40\,V_{\text{text}}$$
$$A_{\text{fused}} = 0.60\,A_{\text{audio}} + 0.40\,A_{\text{text}}$$
$$D_{\text{fused}} = D_{\text{audio}} \text{ if } C_{\text{audio}} > 0.60 \text{ else } D_{\text{text}}$$
A confidence gate requires $C_{\text{fused}} \ge 0.50$ before fused valence modulates LLM prompt instructions or fires de-escalation connectors.

#### DPDP Act 2023 Cascading Deletion
When a contact requests erasure under India's Digital Personal Data Protection Act 2023, VoCall issues an atomic deletion across all four engines:
$$\text{Purge}(\text{contact\_id}) \rightarrow \{\text{DEL Redis}, \text{DELETE pgvector}, \text{DELETE Postgres}, \text{DETACH DELETE FalkorDB}\}$$
The operation writes an immutable SHA-256 audit receipt to the compliance log with the count of purged records.

---

### 7. Hardware & Software Specifications

- **Operating System**: Ubuntu 22.04 LTS / Windows 11 development environment.
- **Backend Stack**: Python 3.10+, FastAPI, Pydantic v2, Pipecat AI, LiveKit Python SDK.
- **Frontend Stack**: Next.js 14 (App Router), React 18, Tailwind CSS, Lucide Icons.
- **Databases**: Supabase Postgres 15 (with pgvector), Upstash Redis (Serverless), FalkorDB (Docker/Cloud).
- **AI & Cloud Engines**: Groq Cloud (LLaMA-3.3-70B, Whisper large-v3), Sarvam AI (Saarika v2, Bulbul v2), Hume AI (EVI / Octave), Cartesia (Sonic-2), Trigger.dev v3.
- **Development Hardware**: 6-core x86-64 CPU, 16 GB DDR4 RAM, 50 GB SSD space, broadband internet (>25 Mbps). No local GPU is required; all model inference runs on remote free-tier LPUs and cloud engines.

---

### 8. Turn Latency Budget Allocation (Target 495ms)

| Pipeline Stage | Target Budget | Observed P95 |
| :--- | :---: | :---: |
| Audio Ingestion and VAD Framing (Silero) | 40ms | 42ms |
| Speech-to-Text (Groq Whisper / Sarvam Saarika) | 150ms | 165ms |
| Parallel Memory Retrieval + Emotion Fusion | Concurrently <50ms | 48ms |
| LLM Time-To-First-Token (Groq LPU LLaMA-3.3) | 150ms | 165ms |
| TTS Time-To-First-Audio-Byte (Cartesia Sonic-2 / Bulbul) | 80ms | 78ms |
| WebRTC Packet Egress (LiveKit) | 25ms | 30ms |
| **Total End-to-End Latency** | **495ms** | **528ms** |

---

### 9. Project Execution Milestones

| Phase | Duration | Key Tasks | Primary Deliverable |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Weeks 1–6 | Literature survey, Pipecat + LiveKit setup, Twilio PSTN webhook integration. | Working audio loop |
| **Phase 2** | Weeks 7–12 | 4-tier memory fan-out (Redis, pgvector, Postgres, FalkorDB); Hume + Groq fusion. | Memory & emotion engine |
| **Phase 3** | Weeks 13–18 | VA-ICECoT intent chain, Sarvam Hinglish STT/TTS routing, connector registry. | Intelligent voice agent |
| **Phase 4** | Weeks 19–24 | Next.js dashboard, DPDP Act 2023 cascading deletion, WebRTC browser testing modal. | Full dashboard & UI |
| **Phase 5** | Weeks 25–28 | JRBM benchmarking, latency stress testing, paper preparation and synopsis submission. | Final report & paper |

---

### 10. Expected Deliverables
1. An open-source, full-stack voice platform codebase under the MIT license.
2. A complete Next.js 14 management console for real-time contact memory inspection, live call transcription, and WebRTC audio testing.
3. An IEEE conference manuscript (`docs/paper/paper.pdf`) ready for academic submission.
4. Complete project synopsis and dissertation for the final year major project defense.

---

### 11. References
1. Y. Zhang *et al.*, "IntentionESC: Intention-centered emotional support conversation," in *Findings of ACL 2025*, 2025.
2. X. Huang *et al.*, "JX4MEI: Joint multimodal emotion-intent explanation via a language-query former," in *Findings of ACL 2026*, 2026.
3. K. Yin *et al.*, "SWI: Speaking with intent in large language models," in *Proc. INLG*, 2025.
4. Y. Liu *et al.*, "MC-EIU: A benchmark for multimodal conversational emotion and intent understanding," *arXiv:2407.02751*, 2024.
5. H. Yu *et al.*, "AffectMind: An affective multimodal agent with proactive knowledge grounding," *arXiv:2511.21728*, 2025.
6. J. A. Russell, "A circumplex model of affect," *Journal of Personality and Social Psychology*, vol. 39, no. 6, pp. 1161–1178, 1980.
7. C. Packer *et al.*, "MemGPT: Towards LLMs as operating systems," *arXiv:2310.08560*, 2023.
8. Mem0.ai, "Mem0: The memory layer for AI applications," Technical documentation, `https://mem0.ai`, 2024.
9. Zep AI, "Zep: A temporal knowledge graph architecture for agent memory," Technical documentation, `https://www.getzep.com`, 2024.
