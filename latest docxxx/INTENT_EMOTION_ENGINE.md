# VoCall VA-ICECoT Intent & Dual-Signal Emotion Engine

**Document Version:** 2.0  
**Status:** Authoritative Scientific & Engineering Specification  
**Architecture Layer:** Multimodal Affective Computing & Intention Chain-of-Thought Planning  
**Related Components:** `app/services/emotion/`, `app/services/intent/`, `app/routers/emotion.py`, `app/routers/intent.py`

---

## 1. Executive Summary & Research Grounding

Empathy and intention recognition represent the dual cornerstones of human-grade voice interaction. Conventional voice bots treat user utterances as disembodied text, ignoring vocal tone, emotional nuance, and latent conversational goals.

VoCall bridges this fundamental gap by combining:
1. **Dual-Signal Multimodal Emotion Fusion:** Fusing acoustic voice prosody with linguistic text semantics into continuous emotional state vectors ($V, A, D$).
2. **VA-ICECoT Intent Engine:** Voice Agent Intention-Centric Chain-of-Thought planning that reasons over the caller's psychological state, context, and explicit goals to modulate agent behavior in real-time.

```text
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                           VOCALL AFFECTIVE & INTENT PIPELINE                              │
└─────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                              │
                     ┌────────────────────────┴────────────────────────┐
                     │                                                 │
            ┌────────▼────────┐                               ┌────────▼────────┐
            │ Acoustic Audio  │                               │ Text Transcript │
            │ Prosody Signal  │                               │ Semantic Signal │
            │ (Hume AI EVI)   │                               │ (Groq LLaMA 3.3)│
            └────────┬────────┘                               └────────┬────────┘
                     │                                                 │
                     └────────────────────────┬────────────────────────┘
                                              │
                                              ▼
                             ┌──────────────────────────────────┐
                             │ DUAL-SIGNAL EMOTION FUSION       │
                             │ E_fused = α·E_audio + (1-α)·E_nlp│
                             └────────────────┬─────────────────┘
                                              │
                                              ▼
                             ┌──────────────────────────────────┐
                             │ 4-ASPECT EMOTION STATE ANALYSIS  │
                             │ (State, Intensity, Cause, Action)│
                             └────────────────┬─────────────────┘
                                              │
                                              ▼
                             ┌──────────────────────────────────┐
                             │ VA-ICECoT INTENT REASONING       │
                             │ (Meta-Thought Chain of Thought)  │
                             └────────────────┬─────────────────┘
                                              │
                                              ▼
                             ┌──────────────────────────────────┐
                             │ DYNAMIC AGENT RESPONSE SYNTHESIS │
                             │ (Prompt Modifier + TTS Tone Mod) │
                             └──────────────────────────────────┘
```

---

## 2. Research Paper Grounding & Scientific Foundations

VoCall's intent and emotion architecture is grounded in five seminal peer-reviewed research papers:

### 2.1 IntentionESC: Intention-Centered Emotional Support (Zhang et al., Findings of ACL 2025)
- **Contribution:** Demonstrates that modeling conversational intention explicitly improves emotional support quality.
- **VoCall Adoption:** Implements the **ICECoT (Intention-Centric Chain-of-Thought)** reasoning protocol across 4 structured dimensions:
  1. *Observed Emotional Expression*
  2. *Inferred Underlying Cause*
  3. *Caller Intent Category*
  4. *Target Agent Conversational Goal*

### 2.2 JX4MEI: Joint Multimodal Emotion-Intent Explanation (Huang et al., Findings of ACL 2026)
- **Contribution:** Introduces joint multimodal feature extraction via Language-Query Former (LQ-Former) on the 15,461-sample XMEI dataset.
- **VoCall Adoption:** Uses bidirectional cross-attention representations where acoustic emotion modulates linguistic intent interpretation and vice versa.

### 2.3 SWI: Speaking with Intent in LLMs (Yin et al., INLG 2025)
- **Contribution:** Introduces **Meta-Thought Planning**, forcing the model to generate structured intention plans before generating verbal surface text.
- **VoCall Adoption:** The LLM prompt pipeline executes hidden intention reasoning before streaming spoken audio tokens.

### 2.4 MC-EIU: Multimodal Conversational Emotion & Intent Benchmark (Liu et al., 2024, arXiv:2407.02751)
- **Contribution:** Benchmarks conversational emotion-intent dependencies using the Emotion-Intent Interaction Network (EI2).
- **VoCall Adoption:** Validates VoCall's emotion-intent transition matrix and evaluation dataset.

### 2.5 AffectMind: Affective Multimodal Agent (Yu et al., 2025, arXiv:2511.21728)
- **Contribution:** Proposes Proactive Knowledge Grounding Network (PKGN) and Emotion-Intent Alignment Model (EIAM).
- **VoCall Adoption:** Aligns knowledge retrieval (4-Tier Memory RAG) directly with the caller's active affective state.

---

## 3. Dual-Signal Emotion Fusion Mathematical Formulation

### 3.1 Mathematical Fusion Equation

Let $E_{\text{audio}} \in [0, 1]^K$ represent the normalized acoustic emotion probability vector from Hume AI (capturing pitch variability, vocal tension, jitter, and energy).  
Let $E_{\text{text}} \in [0, 1]^K$ represent the linguistic sentiment probability vector extracted from the turn transcript via Groq LLaMA 3.3 70B.

The unified fused emotion vector $E_{\text{fused}}$ is computed as:

$$E_{\text{fused}} = \alpha \cdot E_{\text{audio}} + (1 - \alpha) \cdot E_{\text{text}}$$

Where the dynamic blending weight $\alpha \in [0.4, 0.8]$ is parameterized by audio signal-to-noise ratio ($\text{SNR}$) and prosodic confidence score $C_{\text{audio}}$:

$$\alpha = \sigma\left(\beta_0 + \beta_1 \cdot \text{SNR} + \beta_2 \cdot C_{\text{audio}}\right)$$

### 3.2 Frustration Escalation & Dynamic Tone Modulation

A scalar Frustration Index $F \in [0, 1]$ is computed per turn:

$$F = w_1 \cdot E_{\text{fused}}[\text{anger}] + w_2 \cdot E_{\text{fused}}[\text{annoyance}] + w_3 \cdot E_{\text{fused}}[\text{distress}]$$

- **Threshold $F \ge 0.75$:** 
  1. Triggers real-time prompt modification via `app/services/emotion/tone_adapter.py`.
  2. Adjusts TTS synthesis pace (Cartesia / Sarvam) to $0.9\times$ and modulates pitch contour.
  3. Dispatches asynchronous high-frustration alert to Slack (`send_frustration_alert`).
  4. Writes a frustration edge `(:Episode)-[:EXPERIENCED_FRUSTRATION]->(:FrustrationEvent)` to FalkorDB.

---

## 4. VA-ICECoT Intent Engine Architecture

### 4.1 Step 1: Per-Turn Intent Classification (`app/services/intent/detector.py`)

Every caller utterance is classified into structured intent taxonomies:
- `inquiry` (e.g., pricing, policy, operating hours)
- `complaint` (e.g., billing error, delayed shipment, rude behavior)
- `transaction` (e.g., book appointment, process refund, update address)
- `clarification` (e.g., asking agent to repeat, rephrase, or explain)
- `chitchat` (e.g., greetings, pleasantries)
- `escalation` (e.g., asking for human supervisor)

### 4.2 Step 2: Slot Carry-Forward Manager (`app/services/intent/slot_manager.py`)

Maintains entity slots in Redis across multi-turn dialogs (e.g., `slot:appointment_date = "2026-08-30"`, `slot:service_type = "cardiology"`). Template tokens (`{{slot_name}}`) are automatically resolved and substituted prior to connector execution.

### 4.3 Step 3: Intent Resolution & Decision Matrix (`app/services/intent/resolver.py` & `combined_rules.py`)

Evaluates the joint **Emotion $\times$ Intent Matrix** to decide the immediate conversational strategy:

| Intent Category | Low Frustration ($F < 0.4$) | Moderate Frustration ($0.4 \le F < 0.75$) | High Frustration ($F \ge 0.75$) |
| --- | --- | --- | --- |
| **Complaint** | Standard diagnostic flow | Empathetic validation + fast-track solution | Immediate formal apology + manager escalation offer |
| **Transaction** | Direct execution | Confirm details with extra reassurance | High-priority execution with instant SMS/WhatsApp receipt |
| **Escalation** | Offer self-service alternative | Explain transfer wait times | Immediate warm transfer / PSTN bypass |

### 4.4 Step 4: Real-Time Voice Loop Integration (`app/services/voice/va_icecot.py`)

Directly integrates the IntentionESC and JX4MEI chain-of-thought methodologies into the real-time audio loop. During each conversation turn, `va_icecot.py`:
1. Ingests current turn transcript and preceding memory context.
2. Injects a meta-thought prompt guiding the LLM to output explicit `<meta_thought>` intention tokens before generating customer-facing speech.
3. Coordinates with `slot_manager.py` to preserve and carry forward critical slot entities across user barge-ins and interruptions.
4. Triggers automatic connector execution via `resolver.py` when 100% of required slots are filled.

---

## 5. REST API Endpoints

| Method | Endpoint | Description | Query / Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/emotion/events/{call_id}` | Retrieve real-time emotion events for a call | Path: `call_id` | `{"call_id": "...", "events": [...], "source": "redis"}` |
| `POST` | `/api/v1/emotion/events` | Record turn emotion event from pipeline | Body: `EmotionEventCreate` | `{"status": "recorded", "event_id": "..."}` |
| `POST` | `/api/v1/intent/detect` | Zero-shot intent classification & slot extraction | Body: `{"text": "...", "call_id": "..."}` | `{"intent": "...", "confidence": 0.95, "slots": {...}}` |
| `GET` | `/api/v1/intent/calls/{call_id}/events` | Retrieve intent transition log for a call | Path: `call_id` | `[IntentEventResponse]` |
| `GET` | `/api/v1/intent/calls/{call_id}/slots` | Retrieve accumulated slot values in Redis | Path: `call_id` | `{"call_id": "...", "slots": {...}}` |

---

## 6. Evaluation Benchmarks & Metrics (JRBM)

VoCall evaluates emotion and intent recognition accuracy using the **Joint Recognition Balance Metric (JRBM)** (M56 evaluation script in `evaluate_jrbm.py`):

$$JRBM = \frac{2 \cdot \text{Micro-F1}_{\text{emotion}} \cdot \text{Micro-F1}_{\text{intent}}}{\text{Micro-F1}_{\text{emotion}} + \text{Micro-F1}_{\text{intent}}}$$

Automated evaluation datasets are synthesized via `generate_eval_dataset.py` implementing 3-stage LLM generation:
- **Stage 1:** Objective transcript description.
- **Stage 2:** Disentangled emotion and intent chain-of-thought analysis.
- **Stage 3:** Ground-truth joint label verification.
