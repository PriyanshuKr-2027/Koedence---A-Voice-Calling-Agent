const {
  Document, Packer, Paragraph, TextRun, ImageRun, HeadingLevel,
  AlignmentType, Table, TableRow, TableCell, WidthType, BorderStyle,
  PageBreak, PageNumber, Footer, Header, LevelFormat, convertInchesToTwip,
  TabStopType, TabStopPosition, ShadingType, VerticalAlign
} = require("docx");
const fs = require("fs");
const path = require("path");

const FONT = "Times New Roman";
const SIZE = 24; // 12pt * 2

// ---------- helpers ----------
function P(text, opts = {}) {
  const {
    bold = false, italic = false, size = SIZE, align = AlignmentType.JUSTIFIED,
    spacingAfter = 180, spacingBefore = 0, allCaps = false, underline = false,
    lineSpacing = 360
  } = opts;
  return new Paragraph({
    alignment: align,
    spacing: { after: spacingAfter, before: spacingBefore, line: lineSpacing, lineRule: "auto" },
    children: [
      new TextRun({
        text, bold, italics: italic, size, font: FONT, allCaps,
        underline: underline ? {} : undefined
      })
    ]
  });
}

function PMulti(runs, opts = {}) {
  const { align = AlignmentType.JUSTIFIED, spacingAfter = 180, spacingBefore = 0, lineSpacing = 360 } = opts;
  return new Paragraph({
    alignment: align,
    spacing: { after: spacingAfter, before: spacingBefore, line: lineSpacing, lineRule: "auto" },
    children: runs.map(r => new TextRun({ font: FONT, size: SIZE, ...r }))
  });
}

function heading(text, opts = {}) {
  const { size = 28, spacingBefore = 320, spacingAfter = 160 } = opts;
  return new Paragraph({
    alignment: AlignmentType.LEFT,
    spacing: { before: spacingBefore, after: spacingAfter },
    children: [new TextRun({ text, bold: true, size, font: FONT })]
  });
}

function subHeading(text, opts = {}) {
  const { size = 26, spacingBefore = 220, spacingAfter = 120 } = opts;
  return new Paragraph({
    alignment: AlignmentType.LEFT,
    spacing: { before: spacingBefore, after: spacingAfter },
    children: [new TextRun({ text, bold: true, italics: false, size, font: FONT })]
  });
}

function bullet(text, opts = {}) {
  const { bold = false } = opts;
  return new Paragraph({
    numbering: { reference: "bullet-list", level: 0 },
    alignment: AlignmentType.JUSTIFIED,
    spacing: { after: 120, line: 360, lineRule: "auto" },
    children: [new TextRun({ text, font: FONT, size: SIZE, bold })]
  });
}

function boldLabelBullet(label, rest) {
  return new Paragraph({
    numbering: { reference: "bullet-list", level: 0 },
    alignment: AlignmentType.JUSTIFIED,
    spacing: { after: 120, line: 360, lineRule: "auto" },
    children: [
      new TextRun({ text: label, bold: true, font: FONT, size: SIZE }),
      new TextRun({ text: rest, font: FONT, size: SIZE })
    ]
  });
}

function numbered(text, opts = {}, listRef = "num-list") {
  return new Paragraph({
    numbering: { reference: listRef, level: 0 },
    alignment: AlignmentType.JUSTIFIED,
    spacing: { after: 120, line: 360, lineRule: "auto" },
    children: [new TextRun({ text, font: FONT, size: SIZE, ...opts })]
  });
}

function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

function spacer(size = 200) {
  return new Paragraph({ spacing: { after: size }, children: [new TextRun({ text: "", font: FONT, size: SIZE })] });
}

// ---------- Title page ----------
const logoPath = path.join(__dirname, "gniot_logo.jpeg");
const logoBuffer = fs.readFileSync(logoPath);

const titlePage = [
  new Paragraph({
    alignment: AlignmentType.LEFT,
    spacing: { after: 0 },
    children: [
      new ImageRun({
        type: "jpg",
        data: logoBuffer,
        transformation: { width: 480, height: 123 }
      })
    ]
  }),
  spacer(180),
  P("DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING", { bold: true, align: AlignmentType.CENTER, size: 28, spacingAfter: 0, lineSpacing: 300 }),
  P("(ARTIFICIAL INTELLIGENCE & DATA SCIENCE)", { bold: true, align: AlignmentType.CENTER, size: 28, spacingAfter: 250, lineSpacing: 300 }),
  spacer(120),
  P("SYNOPSIS", { bold: true, align: AlignmentType.CENTER, size: 32, spacingAfter: 250 }),
  spacer(100),
  P("VOCALL", { bold: true, align: AlignmentType.CENTER, size: 28, spacingAfter: 0, lineSpacing: 300 }),
  P("(THE MEMORY AUGMENTED VOICE CALLING AGENT WITH EMOTIONAL AWARENESS)", { bold: true, align: AlignmentType.CENTER, size: 28, spacingAfter: 150, lineSpacing: 300 }),
  spacer(250),
  new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: {
      top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      left: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      insideHorizontal: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      insideVertical: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }
    },
    rows: [
      new TableRow({
        children: [
          new TableCell({
            width: { size: 45, type: WidthType.PERCENTAGE },
            children: [
              P("Guided By:", { bold: true, align: AlignmentType.LEFT, spacingAfter: 180 }),
              P("Dr. Shiv Kant", { align: AlignmentType.LEFT, spacingAfter: 80 }),
              P("Assistant Professor", { align: AlignmentType.LEFT, spacingAfter: 80, italic: true }),
              P("Dept. of CSE (AI & DS)", { align: AlignmentType.LEFT, spacingAfter: 80 })
            ]
          }),
          new TableCell({
            width: { size: 55, type: WidthType.PERCENTAGE },
            children: [
              P("Submitted By:", { bold: true, align: AlignmentType.LEFT, spacingAfter: 180 }),
              P("Priyanshu Kumar (2301321630027)", { align: AlignmentType.LEFT, spacingAfter: 80 }),
              P("Ananya Gupta (2301321630007)", { align: AlignmentType.LEFT, spacingAfter: 80 }),
              P("Abhishek Kumar Singh (2301321630002)", { align: AlignmentType.LEFT, spacingAfter: 80 }),
              P("Adarsh Pandey (2301321630005)", { align: AlignmentType.LEFT, spacingAfter: 80 })
            ]
          })
        ]
      })
    ]
  }),
  spacer(180),
  P("Greater Noida Institute of Technology (Engg. Institute), Greater Noida", { align: AlignmentType.CENTER, spacingAfter: 80 }),
  P("Dr. A.P.J. Abdul Kalam Technical University, Lucknow", { align: AlignmentType.CENTER, spacingAfter: 0 }),
  pageBreak()
];

// ---------- Declaration & Acknowledgement ----------
const declarationPage = [
  heading("DECLARATION", { size: 28, spacingBefore: 0 }),
  P('We hereby declare that this project work entitled "VoCall – The Memory Augmented Voice Calling Agent with Emotional Awareness" has been prepared by us during the year 2025-26 under the guidance of Dr. Shiv Kant, Department of Computer Science and Engineering (Artificial Intelligence & Data Science), GNIOT, Greater Noida, in partial fulfilment of the B. Tech degree prescribed by the college.'),
  P("We also declare that this project is the outcome of our own effort, and that it has not been submitted to any other university for the award of any degree."),
  spacer(500),
  P("Priyanshu Kumar (2301321630027)", { align: AlignmentType.RIGHT, spacingAfter: 100 }),
  P("Ananya Gupta (2301321630007)", { align: AlignmentType.RIGHT, spacingAfter: 100 }),
  P("Abhishek Kumar Singh (2301321630002)", { align: AlignmentType.RIGHT, spacingAfter: 100 }),
  P("Adarsh Pandey (2301321630005)", { align: AlignmentType.RIGHT, spacingAfter: 100 }),
  pageBreak(),
  heading("ACKNOWLEDGEMENT", { size: 28, spacingBefore: 0 }),
  P("We have taken efforts in this project. However, it would not have been possible without the kind support and help of many individuals and organizations. We would like to extend our sincere thanks to all of them."),
  P("We are highly indebted to Dr. Shiv Kant for his guidance and constant supervision as well as for providing necessary information regarding the project, and also for his support in completing the project. We would like to express our gratitude towards our parents and members of GNIOT for their kind co-operation and encouragement which helped us in the completion of this project. We would also like to express our special gratitude and thanks to the faculty members of the Department of Computer Science and Engineering (AI & DS) for giving us such attention and time."),
  P("We thank and appreciate our colleagues who assisted us in developing this project and all the people who willingly helped us out with their abilities."),
  pageBreak()
];

// ---------- Table of contents (manual matching screenshot) ----------
function tocRow(title, page) {
  return new Paragraph({
    tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX, leader: "dot" }],
    spacing: { after: 35, line: 260 },
    children: [
      new TextRun({ text: title, font: FONT, size: 22 }),
      new TextRun({ text: `\t${page}`, font: FONT, size: 22 })
    ]
  });
}

function tocSubRow(title, page) {
  return new Paragraph({
    tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX, leader: "dot" }],
    indent: { left: 400 },
    spacing: { after: 25, line: 260 },
    children: [
      new TextRun({ text: title, font: FONT, size: 22 }),
      new TextRun({ text: `\t${page}`, font: FONT, size: 22 })
    ]
  });
}

const tocPage = [
  heading("TABLE OF CONTENTS", { size: 28, spacingBefore: 0, spacingAfter: 200 }),
  tocRow("1 INTRODUCTION", 6),
  tocRow("2 PROBLEM STATEMENT", 6),
  tocRow("3 LITERATURE REVIEW / EXISTING SYSTEMS", 7),
  tocRow("4 OBJECTIVES OF THE PROJECT", 7),
  tocRow("5 PROPOSED SYSTEM", 8),
  tocRow("6 SYSTEM ARCHITECTURE", 8),
  tocSubRow("6.1 Tier 1 — Client and Presentation Layer", 8),
  tocSubRow("6.2 Tier 2 — API Gateway and Routing Layer", 9),
  tocSubRow("6.3 Tier 3 — Real-Time Conversational Media Pipeline", 9),
  tocSubRow("6.4 Tier 4 — Multi-Tier Cognitive Memory and Storage Layer", 9),
  tocSubRow("6.5 Tier 5 — Asynchronous Worker Layer", 9),
  tocRow("7 TECHNOLOGY STACK", 9),
  tocRow("8 CORE MODULES AND FUNCTIONAL DESCRIPTION", 10),
  tocSubRow("8.1 4-Tier Hybrid Cognitive Memory Engine", 10),
  tocSubRow("8.2 Dual-Signal Emotion Fusion Engine", 10),
  tocSubRow("8.3 VA-ICECoT Intent Engine", 10),
  tocSubRow("8.4 Action Connector Framework", 10),
  tocSubRow("8.5 Web Call Testing Studio", 11),
  tocSubRow("8.6 DPDP Act 2023 “Forget Me” Erasure Protocol", 11),
  tocRow("9 METHODOLOGY", 11),
  tocRow("10 MATHEMATICAL FORMULATION", 11),
  tocRow("11 TOOLS AND SOFTWARE REQUIREMENTS", 12),
  tocSubRow("11.1 Hardware Requirements", 12),
  tocSubRow("11.2 Software Requirements", 12),
  tocRow("12 EXPECTED OUTCOME", 12),
  tocRow("13 APPLICATIONS", 13),
  tocRow("14 FUTURE SCOPE", 13),
  tocRow("15 CONCLUSION", 13),
  tocRow("16 REFERENCES", 13),
  pageBreak()
];

// ---------- numbering config ----------
const numbering = {
  config: [
    {
      reference: "bullet-list",
      levels: [
        {
          level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } }
        }
      ]
    },
    {
      reference: "objectives-list",
      levels: [
        {
          level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } }
        }
      ]
    },
    {
      reference: "methodology-list",
      levels: [
        {
          level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } }
        }
      ]
    },
    {
      reference: "references-list",
      levels: [
        {
          level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } }
        }
      ]
    }
  ]
};

// ---------- Body content ----------
const body = [];

// ==========================================
// PAGE 6: 1. INTRODUCTION & 2. PROBLEM STATEMENT
// ==========================================
body.push(heading("1. INTRODUCTION"));
body.push(P("Voice is the most natural medium of human communication, yet current production conversational voice agents (such as Vapi, Retell AI, and OmniDim) remain fundamentally transactional, forgetful, and emotionally blind. Traditional Interactive Voice Response (IVR) setups and modern single-turn LLM voice bots treat every telephone call as an isolated event. A returning customer calling three times in a single week regarding an unresolved issue must repeat their identity, ticket details, and emotional grievance on every turn. Furthermore, existing voice agents cannot sense whether a caller is calm, confused, or furious in real time. This operational amnesia damages customer trust and inflates handle times across logistics, banking, healthcare, and citizen helplines."));
body.push(P("VoCall resolves this breakdown by introducing an enterprise-grade, open-source, full-duplex spoken dialogue platform designed for sub-500ms turnaround latency (well within the 800ms human conversational threshold). The system combines 20–40ms audio frame processing with a 4-Tier Cognitive Memory Architecture, a Dual-Signal Multimodal Emotion Fusion Engine, an Intention-Centric Chain-of-Thought (VA-ICECoT) reasoning framework, and a native code-switched Hinglish speech pipeline. Together, these systems allow a voice agent to remember callers across sessions, perceive emotional distress mid-turn from both acoustic prosody and text sentiment, dynamically adapt conversational strategy, and trigger third-party actions — all deployable on free-tier infrastructure."));

body.push(heading("2. PROBLEM STATEMENT"));
body.push(boldLabelBullet("Cross-Session Amnesia (Single-Store Memory Failure): ", "Commercial voice platforms maintain zero memory across sessions. Research memory systems like MemGPT and Mem0 rely on flat vector stores that introduce high paging latencies (>1000ms) and cannot execute multi-hop causal graph traversals across past call episodes."));
body.push(boldLabelBullet("Unimodal and Post-Call Emotion Blind Spots: ", "Platforms like OmniDim run sentiment classifiers as batch jobs after call completion. Post-call analysis cannot alter in-flight tone, while text-only sentiment classifiers fail entirely on sarcasm or acoustic strain where words appear polite but pitch indicates severe anger."));
body.push(boldLabelBullet("Disconnected Intent and Affective Reasoning: ", "Existing pipelines isolate intent classification from emotional appraisal. No production voice platform couples intent classification, multi-turn slot extraction, and affective appraisal inside a sub-500ms voice turn deadline."));
body.push(boldLabelBullet("Translation Wrappers for Multilingual Audio: ", "Current platforms handle Indian languages by bolting translation wrappers onto English models, inflating latency past 1500ms and corrupting code-switched Hindi-English (Hinglish) phonemes."));
body.push(boldLabelBullet("High SaaS Cost Barriers for Indian MSMEs: ", "US-based voice platforms bill at prohibitive rates of $0.05 to $0.15 per conversation minute, making automated voice deployment financially inaccessible for Indian enterprises."));

body.push(pageBreak());

// ==========================================
// PAGE 7: 3. LITERATURE REVIEW & 4. OBJECTIVES
// ==========================================
body.push(heading("3. LITERATURE REVIEW / EXISTING SYSTEMS"));
body.push(P("The theoretical architecture of VoCall's intent, emotion, and memory subsystems is grounded in recent peer-reviewed research in conversational AI. IntentionESC (Zhang et al., Findings of ACL 2025) demonstrates that explicitly modeling a speaker's conversational intention prior to generating surface text significantly elevates emotional support quality — a principle VoCall formalizes in its Intention-Centric Chain-of-Thought (VA-ICECoT) protocol. JX4MEI (Huang et al., Findings of ACL 2026) proves that cross-attention between acoustic prosody and linguistic features outperforms late decision voting, directly motivating VoCall's Dual-Signal Emotion Fusion Engine."));
body.push(P("Speaking with Intent in LLMs (Yin et al., INLG 2025) establishes that hidden meta-thought planning tokens prevent hallucinated goals during live generation. The MC-EIU benchmark (Liu et al., 2024) and AffectMind (Yu et al., 2025) validate that emotion-intent transitions follow structured distributions and that grounding memory retrieval in affective coordinates improves relevance. In memory systems, MemGPT (Packer et al., 2023) pioneered virtual memory paging for LLMs, but its paging queries introduce latencies exceeding 1000ms. Zep (2024) demonstrates temporal graph persistence for entity relationships, which VoCall extends with sub-40ms OpenCypher graph traversals on FalkorDB."));
body.push(P("Commercially available systems (Vapi, Retell AI, OmniDim, Unpod) rely on static prompt trees, lack acoustic paralinguistics, provide no native Hinglish models, and operate as closed SaaS. VoCall differentiates itself as an open-source, full-duplex platform combining 4-tier memory fan-out, live acoustic emotion sensing, and native code-switching on free-tier infrastructure."));

body.push(heading("4. OBJECTIVES OF THE PROJECT"));
body.push(numbered("To design and implement a 4-Tier Hybrid Cognitive Memory Architecture unifying working memory (Upstash Redis), semantic facts (Supabase pgvector), episodic history (Postgres), and knowledge graph (FalkorDB), queried concurrently in under 80ms via asyncio.gather.", {}, "objectives-list"));
body.push(numbered("To design a Dual-Signal Multimodal Emotion Fusion Engine combining Hume AI acoustic prosody (48 paralinguistic dimensions) and Groq text sentiment onto Russell's Circumplex plane (60/40 convex combination) to detect caller frustration mid-turn.", {}, "objectives-list"));
body.push(numbered("To implement a VA-ICECoT (Voice Agent Intention-Centric Chain-of-Thought) intent engine capable of 4-step reasoning (observation, cause, intent, goal) with deterministic escalation overrides when frustration exceeds 0.65.", {}, "objectives-list"));
body.push(numbered("To deploy a native code-switched Hinglish speech pipeline integrating Sarvam AI's Saarika v2 STT and Bulbul v2 TTS to process mixed Hindi-English speech without artificial translation wrappers.", {}, "objectives-list"));
body.push(numbered("To achieve a deterministic end-to-end voice turn latency budget of 495ms (observed P95 < 530ms) across speech-to-text, memory retrieval, emotion fusion, LLM inference, and audio synthesis.", {}, "objectives-list"));
body.push(numbered("To implement an atomic, DPDP Act 2023-compliant \"Forget Me\" cascading deletion protocol that purges contact records across all four storage tiers and generates a SHA-256 cryptographic compliance receipt.", {}, "objectives-list"));
body.push(numbered("To validate joint reasoning accuracy using the Joint Recognition Balance Metric (JRBM) and provide an in-browser WebRTC testing studio for real-time validation without physical telephony hardware.", {}, "objectives-list"));

body.push(pageBreak());

// ==========================================
// PAGE 8: 5. PROPOSED SYSTEM & 6. SYSTEM ARCHITECTURE (INTRO + 6.1)
// ==========================================
body.push(heading("5. PROPOSED SYSTEM"));
body.push(P("VoCall proposes an integrated, five-layer voice AI platform in which a caller's speech is transcribed, understood, affectively appraised, and responded to in real time while simultaneously grounded in cross-session memory. Incoming audio frames of 20–40ms are ingested via WebRTC or PSTN telephony trunks. At call onset, the platform executes an asynchronous parallel fan-out across all four memory tiers — Redis buffer, pgvector semantic facts, Postgres episodic summaries, and the FalkorDB knowledge graph — completing memory retrieval within an 80ms budget."));
body.push(P("On every conversational turn, the caller's audio is concurrently analyzed for paralinguistic acoustic cues via Hume AI and transcribed into text for sentiment analysis. The two signals are fused into a continuous Valence-Arousal coordinate on Russell's Circumplex plane. This fused emotional state, along with the VA-ICECoT intent classification and slot values, is dynamically injected into the system prompt sent to Groq LPU's LLaMA-3.3-70B model. When caller frustration crosses 0.65, the agent automatically modulates its speech cadence, softens phrasing, or triggers deterministic supervisor escalation."));
body.push(P("Post-call, an asynchronous 11-stage background worker on Trigger.dev extracts new facts, updates the FalkorDB entity graph, records emotional trajectories, and dispatches external connectors (WhatsApp confirmation, CRM logging) — ensuring that newly learned context is immediately available for subsequent calls."));

body.push(heading("6. SYSTEM ARCHITECTURE"));
body.push(P("VoCall is structured into five decoupled operational layers to ensure deterministic latency, high availability, and modular scalability:"));

body.push(subHeading("6.1 Tier 1 — Client and Presentation Layer"));
body.push(P("Comprises the interactive Vite 8 and React 19 testing application and the enterprise Next.js 14 (App Router) dashboard. It provides developers with agent configuration panels, contact inspection views, post-call analytics, and the in-browser WebCallModal for real-time testing."));

body.push(pageBreak());

// ==========================================
// PAGE 9: 6.2 - 6.5 & 7. TECHNOLOGY STACK
// ==========================================
body.push(subHeading("6.2 Tier 2 — API Gateway and Routing Layer"));
body.push(P("A FastAPI-based ASGI backend exposes REST endpoints for authentication, contact management, memory routing, and telephony webhooks, coupled with a Server-Sent Events (SSE) telemetry stream. It includes an AES-256-GCM vault for Bring-Your-Own-Key (BYOK) credential encryption."));

body.push(subHeading("6.3 Tier 3 — Real-Time Conversational Media Pipeline"));
body.push(P("A Pipecat-orchestrated audio engine manages streaming audio ingestion, Silero Voice Activity Detection (VAD), parallel STT and emotion extraction, VA-ICECoT reasoning, and TTS streaming egress over LiveKit WebRTC or Twilio/Exotel/Plivo telephony SIP trunks."));

body.push(subHeading("6.4 Tier 4 — Multi-Tier Cognitive Memory and Storage Layer"));
body.push(P("Four distinct storage engines operate concurrently: Upstash Redis for ephemeral in-call state, Supabase Postgres 15 for relational data, Supabase pgvector with HNSW cosine indexing for semantic facts, and FalkorDB for the associative entity knowledge graph."));

body.push(subHeading("6.5 Tier 5 — Asynchronous Worker Layer"));
body.push(P("An asynchronous Trigger.dev v3 background worker executes the 11-stage post-call pipeline, handling conversation summarization, semantic fact embedding, OpenCypher graph updates, and third-party connector dispatch without blocking audio paths."));

body.push(heading("7. TECHNOLOGY STACK"));
body.push(bullet("Interactive Frontend: Vite 8, React 19, Tailwind CSS, Lucide Icons, Framer Motion 12, Recharts"));
body.push(bullet("Enterprise Dashboard: Next.js 14 (App Router), React 18, Radix UI, Trigger.dev SDK"));
body.push(bullet("Backend API: Python 3.10+, FastAPI, Uvicorn, Pydantic v2, Asyncio"));
body.push(bullet("Real-Time Media Engine: Pipecat AI Framework, LiveKit Cloud WebRTC Server, Silero VAD"));
body.push(bullet("LLM Engine: Groq LPU (LLaMA-3.3-70B-Versatile, 14,400 req/day free tier), Cerebras AI fallback"));
body.push(bullet("Speech-to-Text: Groq Whisper Large-v3 (English), Sarvam AI Saarika v2 (Hindi / Hinglish)"));
body.push(bullet("Text-to-Speech: Cartesia Sonic-2 (ultra-low latency), Sarvam Bulbul v2, Hume AI Octave 2"));
body.push(bullet("Emotion Engine: Hume AI Expression Measurement API (48 audio prosody dims) & Groq NLP"));
body.push(bullet("Databases: Supabase Postgres 15 with pgvector (500 MB free), Upstash Redis, FalkorDB"));
body.push(bullet("Action Connectors: WhatsApp Cloud API, Google Calendar, HubSpot, Salesforce, Slack, SQL"));
body.push(bullet("Security & Compliance: AES-256-GCM BYOK credential encryption, DPDP Act 2023 cascading purge"));
body.push(bullet("Telephony Providers: Twilio, Exotel, Plivo (Bring-Your-Own-Key SIP trunking)"));

body.push(pageBreak());

// ==========================================
// PAGE 10: 8. CORE MODULES (8.1 to 8.4)
// ==========================================
body.push(heading("8. CORE MODULES AND FUNCTIONAL DESCRIPTION"));

body.push(subHeading("8.1 4-Tier Hybrid Cognitive Memory Engine"));
body.push(P("The memory engine unifies four distinct storage layers to resolve conversational amnesia within an 80ms parallel budget:"));
body.push(boldLabelBullet("Tier 1 — Working Memory (Upstash Redis): ", "Holds the active call's turn buffer, rolling emotion moving averages, and carried-forward slot values (<10ms REST latency)."));
body.push(boldLabelBullet("Tier 2 — Long-Term Semantic Memory (pgvector): ", "Stores 1536-dimensional fact embeddings per contact, returning the top-5 facts above a 0.75 cosine similarity threshold using an HNSW index (<35ms)."));
body.push(boldLabelBullet("Tier 3 — Episodic Memory (Supabase Postgres): ", "Stores structured summaries, key topics, outcome states, and emotional trajectories across the contact's last 3 calls (<25ms)."));
body.push(boldLabelBullet("Tier 4 — Associative Knowledge Graph (FalkorDB): ", "Models contacts, episodes, entities, and grievances connected by LEADS_TO and FRUSTRATED_ABOUT edges, answering multi-hop causal queries via OpenCypher (<40ms)."));
body.push(P("All four tiers execute in parallel using asyncio.gather. The combined results are synthesized into a compact memory context block injected directly into the LLM system prompt prior to generation."));

body.push(subHeading("8.2 Dual-Signal Emotion Fusion Engine"));
body.push(P("Acoustic prosody features extracted via Hume AI (48 dimensions including pitch variance, energy, and vocal tension) are mapped to Russell's Circumplex plane (V_audio, A_audio). Linguistic sentiment extracted via Groq LLaMA yields (V_text, A_text). The signals are fused using a locked 60/40 convex combination: V_fused = 0.60 * V_audio + 0.40 * V_text, and A_fused = 0.60 * A_audio + 0.40 * A_text. A confidence gate requires C_fused >= 0.50 before the fused state modulates LLM instructions or alters TTS synthesis cadence."));

body.push(subHeading("8.3 VA-ICECoT Intent Engine"));
body.push(P("Every caller utterance triggers a 4-step intention-centric chain-of-thought: (1) Observation of fused affective state, (2) Inferred Cause from turn context, (3) Intent Categorization (inquiry, complaint, transaction, clarification, chitchat, escalation), and (4) Conversational Goal. Multi-turn slot values (dates, service types) are preserved across turns. When the computed frustration index crosses 0.65, the system executes a deterministic emergency escalation override, routing the call to a human supervisor and bypassing automated tool execution."));

body.push(subHeading("8.4 Action Connector Framework"));
body.push(P("A central dispatcher orchestrates live and post-call actions across eight modular connectors: WhatsApp, Google Calendar, HubSpot, Salesforce, Slack, HMAC-signed custom webhooks, and parameterized read-only SQL queries. All third-party API credentials are encrypted at rest using AES-256-GCM authenticated encryption with unique cryptographic nonces."));

body.push(pageBreak());

// ==========================================
// PAGE 11: 8.5, 8.6, 9. METHODOLOGY, 10. MATH
// ==========================================
body.push(subHeading("8.5 Web Call Testing Studio"));
body.push(P("An in-browser WebRTC testing modal manages a 4-phase call lifecycle (idle, connecting, active, ended). It features a dynamic 3-state voice orb, an auto-scrolling live transcript stream delivered via Server-Sent Events (SSE), and a post-call decision screen allowing developers to save or discard call telemetry."));

body.push(subHeading("8.6 DPDP Act 2023 “Forget Me” Erasure Protocol"));
body.push(P("In compliance with India's Digital Personal Data Protection Act 2023, a single API call initiates an atomic cascading deletion across all storage engines: Purge(contact_id) -> {DEL Redis, DELETE pgvector, DELETE Postgres, DETACH DELETE FalkorDB}. The operation writes an immutable SHA-256 audit record logging the timestamp and record counts without storing identifiable personal data."));

body.push(heading("9. METHODOLOGY"));
body.push(numbered("Phase 1 (Weeks 1–6): Architectural design, Pipecat and LiveKit audio loop configuration, and Twilio/Exotel PSTN webhook integration.", {}, "methodology-list"));
body.push(numbered("Phase 2 (Weeks 7–12): Implementation of 4-tier parallel memory fan-out (Redis, pgvector, Postgres, FalkorDB) and Hume + Groq 60/40 emotion fusion.", {}, "methodology-list"));
body.push(numbered("Phase 3 (Weeks 13–18): VA-ICECoT intent reasoning protocol, Sarvam AI native Hinglish STT/TTS routing, and action connector dispatcher.", {}, "methodology-list"));
body.push(numbered("Phase 4 (Weeks 19–24): Next.js dashboard development, DPDP Act 2023 cascading deletion engine, and in-browser WebRTC testing studio.", {}, "methodology-list"));
body.push(numbered("Phase 5 (Weeks 25–28): End-to-end turn latency benchmarking, JRBM joint evaluation, IEEE conference paper preparation, and synopsis submission.", {}, "methodology-list"));

body.push(heading("10. MATHEMATICAL FORMULATION"));
body.push(P("Dual-Signal Emotion Fusion on Russell's Circumplex plane combines acoustic prosody and textual sentiment:"));
body.push(P("V_fused = 0.60 \u00B7 V_audio + 0.40 \u00B7 V_text,   A_fused = 0.60 \u00B7 A_audio + 0.40 \u00B7 A_text", { align: AlignmentType.CENTER, bold: true }));
body.push(P("Dominance is selected based on acoustic confidence: D_fused = D_audio if C_audio > 0.60, else D_text. A confidence gate enforces C_fused \u2265 0.50 before modulating prompt instructions."));
body.push(P("The scalar Frustration Index F triggering adaptive tone softening and supervisor escalation is computed as:"));
body.push(P("F = w\u2081 \u00B7 E_fused[anger] + w\u2082 \u00B7 E_fused[annoyance] + w\u2083 \u00B7 E_fused[distress],   Threshold: F \u2265 0.65", { align: AlignmentType.CENTER, bold: true }));
body.push(P("Semantic fact retrieval from pgvector uses cosine similarity between query embedding q and fact embedding f \u2208 \u211D\u00B9\u2075\u00B3\u2076 with an HNSW index:"));
body.push(P("similarity(q, f) = (q \u00B7 f) / (\u2016q\u2016 \u2016f\u2016) \u2265 0.75", { align: AlignmentType.CENTER, bold: true }));
body.push(P("Joint accuracy is validated using the Joint Recognition Balance Metric (harmonic mean of intent and emotion micro-F1):"));
body.push(P("JRBM = (2 \u00B7 F1_intent \u00B7 F1_emotion) / (F1_intent + F1_emotion)", { align: AlignmentType.CENTER, bold: true }));

body.push(pageBreak());

// ==========================================
// PAGE 12: 11. TOOLS & REQUIREMENTS, 12. EXPECTED OUTCOME
// ==========================================
body.push(heading("11. TOOLS AND SOFTWARE REQUIREMENTS"));

body.push(subHeading("11.1 Hardware Requirements"));
body.push(bullet("Development Processor: 6-core x86-64 CPU (Intel Core i5 11th Gen / AMD Ryzen 5 5600H minimum)"));
body.push(bullet("System Memory (RAM): 16 GB DDR4 minimum (to support concurrent Docker engines and dev servers)"));
body.push(bullet("Disk Storage: 50 GB free SSD space"));
body.push(bullet("Network Bandwidth: Broadband connection (>25 Mbps, <30ms jitter) for live WebRTC audio streams"));
body.push(bullet("GPU Requirement: None; all model inference executes remotely on Groq LPUs and cloud AI endpoints"));

body.push(subHeading("11.2 Software Requirements"));
body.push(bullet("Operating System: Ubuntu 22.04 LTS / Windows 11 development environment"));
body.push(bullet("Backend Runtime: Python 3.10+, FastAPI, Uvicorn, Pydantic v2, Pipecat AI, LiveKit Python SDK"));
body.push(bullet("Frontend Runtime: Node.js 18+, Vite 8, React 19, Next.js 14 (App Router), Tailwind CSS"));
body.push(bullet("Databases: Supabase Postgres 15 (with pgvector), Upstash Redis (Serverless), FalkorDB"));
body.push(bullet("Cloud AI & Speech: Groq Cloud (LLaMA-3.3-70B, Whisper large-v3), Sarvam AI, Hume AI, Cartesia"));
body.push(bullet("Free-Tier Economics: Groq (14.4k req/day), Supabase (500MB), Upstash (10k cmd/day), LiveKit (50GB)"));

body.push(heading("12. EXPECTED OUTCOME"));
body.push(P("At project completion, VoCall will deliver a fully functional, open-source voice AI platform under the MIT license. Key outcomes include:"));
body.push(bullet("Sub-500ms Turn Latency: Observed P95 turnaround latency under 530ms (target 495ms budget: VAD 40ms, STT 150ms, Memory/Emotion <50ms, LLM TTFT 150ms, TTS TTFAB 80ms, WebRTC 25ms)."));
body.push(bullet("Cross-Session Contextual Continuity: Contact-specific facts, past call episodes, and entity relationships recalled in under 80ms across multiple sessions."));
body.push(bullet("Real-Time Affective Adaptation: In-flight tone modulation and supervisor escalation when frustration crosses 0.65."));
body.push(bullet("Native Hinglish Preservation: Fluent code-switched Hindi-English speech without translation wrapper distortion."));
body.push(bullet("Academic Deliverables: A complete B.Tech dissertation and an IEEE conference manuscript (paper.pdf) submitted for peer review."));

body.push(pageBreak());

// ==========================================
// PAGE 13: 13. APPLICATIONS, 14. FUTURE SCOPE, 15. CONCLUSION, 16. REFERENCES
// ==========================================
body.push(heading("13. APPLICATIONS"));
body.push(bullet("Enterprise Customer Support: Automated helpdesk routing with cross-call contextual memory, reducing handle times."));
body.push(bullet("Healthcare Appointment & Triage: Patient appointment scheduling and empathetic triage assistance."));
body.push(bullet("Empathetic Debt Collection: Compliance-aware recovery conversations with real-time tone softening."));
body.push(bullet("Inbound Sales Qualification: High-volume lead qualification with instant CRM synchronization."));
body.push(bullet("Multilingual Citizen Helplines: Public grievance redressal in native Hindi and code-switched Hinglish."));

body.push(heading("14. FUTURE SCOPE"));
body.push(P("Future extensions include: (1) Expanding native acoustic models to additional Indian regional languages (Tamil, Telugu, Bengali, Marathi); (2) Enhancing FalkorDB with automated causal-chain discovery across recurring customer complaints; (3) Edge-deployed emotion inference using lightweight quantized models to further reduce network latency; and (4) Deep bidirectional connectors for enterprise ERP platforms (SAP, Oracle) and IT ticketing suites."));

body.push(heading("15. CONCLUSION"));
body.push(P("VoCall addresses the fundamental shortcomings of contemporary voice AI platforms — high latency, cross-session amnesia, and emotional blindness — through a unified architecture integrating a 4-tier cognitive memory fan-out, a dual-signal emotion fusion engine, and intention-centric reasoning. Grounded in peer-reviewed research (ACL 2025/2026) and paired with free-tier production infrastructure, VoCall proves that an enterprise-grade voice agent can be ultra-fast, emotionally empathetic, and capable of perpetual memory, bringing conversational voice AI significantly closer to natural human interaction."));

body.push(heading("16. REFERENCES"));
body.push(numbered("Y. Zhang et al., \"IntentionESC: Intention-Centered Emotional Support Conversation,\" in Findings of the Association for Computational Linguistics (ACL), 2025.", {}, "references-list"));
body.push(numbered("X. Huang et al., \"JX4MEI: Joint Multimodal Emotion-Intent Explanation via Language-Query Former,\" in Findings of the Association for Computational Linguistics (ACL), 2026.", {}, "references-list"));
body.push(numbered("K. Yin et al., \"SWI: Speaking with Intent in Large Language Models,\" in Proceedings of the International Natural Language Generation Conference (INLG), 2025.", {}, "references-list"));
body.push(numbered("Y. Liu et al., \"MC-EIU: A Multimodal Conversational Emotion and Intent Benchmark,\" arXiv:2407.02751, 2024.", {}, "references-list"));
body.push(numbered("H. Yu et al., \"AffectMind: An Affective Multimodal Agent with Proactive Knowledge Grounding,\" arXiv:2511.21728, 2025.", {}, "references-list"));
body.push(numbered("J. A. Russell, \"A Circumplex Model of Affect,\" Journal of Personality and Social Psychology, vol. 39, no. 6, pp. 1161-1178, 1980.", {}, "references-list"));
body.push(numbered("C. Packer et al., \"MemGPT: Towards LLMs as Operating Systems,\" arXiv:2310.08560, 2023.", {}, "references-list"));
body.push(numbered("Digital Personal Data Protection Act, 2023, Government of India, Gazette of India, 2023.", {}, "references-list"));

// ---------- assemble ----------
const doc = new Document({
  numbering,
  styles: {
    default: {
      document: {
        run: { font: FONT, size: SIZE }
      }
    }
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 }, // US Letter in DXA
          margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 }
        }
      },
      children: titlePage
    },
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 }
        }
      },
      children: declarationPage
    },
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 }
        }
      },
      children: tocPage
    },
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 },
          pageNumbers: { start: 6 }
        }
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 20 })
              ]
            })
          ]
        })
      },
      children: body
    }
  ]
});

Packer.toBuffer(doc).then(buf => {
  const filenames = [
    "VoCall_Synopsis_Final.docx",
    "VoCall_Synopsis.docx",
    "VoCall_Synopsis_Updated.docx",
    "VoCall_Synopsis_Refined.docx"
  ];
  let writtenCount = 0;
  for (const name of filenames) {
    try {
      fs.writeFileSync(path.join(__dirname, name), buf);
      console.log("Successfully generated/updated:", name);
      writtenCount++;
    } catch (e) {
      if (e.code === "EBUSY") {
        console.log(`Note: ${name} is open in Word (cannot overwrite while open)`);
      } else {
        console.error(`Error writing ${name}:`, e.message);
      }
    }
  }
  if (writtenCount === 0) {
    const timestampedName = `VoCall_Synopsis_${Date.now()}.docx`;
    fs.writeFileSync(path.join(__dirname, timestampedName), buf);
    console.log("Generated fresh unblocked file:", timestampedName);
  }
}).catch(err => {
  console.error("Error generating docx:", err);
});
