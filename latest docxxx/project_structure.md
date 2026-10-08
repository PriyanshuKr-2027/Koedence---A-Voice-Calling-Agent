# VoCall — Comprehensive Project Structure & Directory Reference

**Document Version:** 2.1  
**Last Updated:** September 2026  
**Status:** Complete & Authoritative  
**Related Documents:** [PRD.md](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/latest%20docxxx/PRD.md), [TRD.md](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/latest%20docxxx/TRD.md), [architecture.md](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/latest%20docxxx/architecture.md), [components.md](file:///c:/Users/10pri/Downloads/VOCALL%2019%20JULY/latest%20docxxx/components.md)

---

## 1. Monorepo Overview

VoCall is structured as an enterprise-grade monorepo combining real-time audio pipelines, multi-tier cognitive memory services, intent/emotion engines, a high-fidelity Vite + React 19 interactive frontend, an enterprise Next.js 14 dashboard, and Supabase database migrations:

```text
VOCALL 19 JULY/
├── app/                      # Primary Active FastAPI Backend Service (Python 3.10+)
├── src/                      # High-Performance Interactive Frontend (Vite 8 + React 19 + Tailwind)
├── archive/                  # Archived Legacy Artifacts
│   └── vocall_backend_legacy/# Legacy FastApi backend package (archived)
├── vocall/                   # Monorepo Sub-Package
│   ├── frontend/             # Next.js 14 App Router Dashboard & Agent Studio (TypeScript)
│   └── docs/                 # Authoritative System & UI Specifications
├── supabase/                 # Supabase SQL Migrations & 15-Table Database Setup Queries
├── trigger/                  # Trigger.dev Asynchronous Background Job Pipelines
├── tests/                    # Backend Pytest Test Suite
├── latest docxxx/            # System Architecture, PRD, TRD, Feature Specs & Deep-Dives
├── graphify-out/             # Knowledge Graph Artifacts (graph.html, graph.json, GRAPH_REPORT.md)
└── docker-compose.yml        # Docker Multi-Container Local Stack Orchestration
```

---

## 2. Exhaustive Directory & File Tree

```text
.
├── app/                                      # Main FastAPI Backend Application
│   ├── core/
│   │   └── config.py                         # Environment variables, Pydantic settings, API keys
│   ├── models/                               # SQLModel / Pydantic data models & request/response schemas
│   │   ├── connectors.py                     # Connector configuration schemas & enums
│   │   └── schemas.py                        # Comprehensive Pydantic v2 domain schemas
│   ├── routers/                              # API Route Handlers
│   │   ├── agents.py                         # Agent CRUD, prompt enhancer (/enhance-prompt), analysis (/run-analysis), publish
│   │   ├── api_keys.py                       # Encrypted BYOK API key management (AES-256-GCM)
│   │   ├── auth.py                           # Supabase JWT validation & auth endpoints (/login, /me)
│   │   ├── calls.py                          # Call sessions, LiveKit token (/token), WebCall (/webcall/start, /events SSE, /end)
│   │   ├── connectors.py                     # Pluggable action connectors (/api/connectors) & live testing
│   │   ├── contacts.py                       # Contact CRUD, FalkorDB graph retrieval & DPDP "Forget Me" cascade clearance
│   │   ├── emotion.py                        # Real-time emotion turn events (/events/{call_id}) & recording
│   │   ├── intent.py                         # Zero-shot intent detection (/detect), call events & slot states
│   │   ├── memory.py                         # Direct memory queries across Redis, pgvector & FalkorDB
│   │   ├── phone_numbers.py                  # Telephony number purchasing, KYC document upload & agent assignment
│   │   └── webhooks.py                       # Twilio PSTN voice, status callbacks & LiveKit room events
│   ├── services/                             # Core Business Logic & Engine Services
│   │   ├── connectors/                       # 8 Action Connector Implementations
│   │   │   ├── dispatcher.py                 # Central connector dispatcher (`fire_connector()`)
│   │   │   ├── google_cal.py                 # Google Calendar availability & appointment booking
│   │   │   ├── hubspot.py                    # HubSpot CRM contact & deal sync
│   │   │   ├── salesforce.py                 # Salesforce OAuth2 token refresh & task sync
│   │   │   ├── slack.py                      # Slack Block Kit call summary & frustration alerts
│   │   │   ├── supabase_conn.py              # Parameterized read-only SQL query runner
│   │   │   ├── webhook.py                    # Async HMAC-SHA256 templated HTTP webhooks
│   │   │   └── whatsapp.py                   # Twilio WhatsApp Content API templates
│   │   ├── emotion/                          # Dual-Signal Emotion Fusion Engine
│   │   │   ├── audio_signal.py               # Hume EVI paralinguistic tone score processing
│   │   │   ├── text_signal.py                # Groq Llama-3.3-70b NLP turn sentiment analyzer
│   │   │   ├── fusion.py                     # Fused valence/arousal state calculator (α*Audio + (1-α)*Text)
│   │   │   └── tone_adapter.py               # System prompt modifier & TTS tone adapter
│   │   ├── intent/                           # Intent Engine & VA-ICECoT Framework
│   │   │   ├── detector.py                   # Zero-shot intent classifier
│   │   │   ├── slot_manager.py               # Dynamic slot parameter tracker & prompt builder
│   │   │   ├── resolver.py                   # 100% slot resolution connector trigger engine
│   │   │   └── combined_rules.py             # Emotion × Intent combined escalation rule matrix
│   │   ├── memory/                           # 4-Tier Hybrid Memory Architecture
│   │   │   ├── short_term.py                 # Tier 1: Upstash Redis live turn & transcript buffer
│   │   │   ├── long_term.py                  # Tier 2: Supabase pgvector semantic fact embeddings
│   │   │   ├── episodic.py                   # Tier 3: Supabase Postgres post-call summaries
│   │   │   ├── graph.py                      # Tier 4: FalkorDB OpenCypher knowledge graph manager
│   │   │   └── retriever.py                  # Parallel fanout memory retrieval engine (`retrieve_all_memory`)
│   │   ├── voice/                            # Real-Time Voice Reasoning Engines
│   │   │   └── va_icecot.py                  # IntentionESC + JX4MEI chain-of-thought engine in voice loop
│   │   ├── email.py                          # Resend API post-call email reporting
│   │   ├── livekit_service.py                # LiveKit server SDK room & token lifecycle manager
│   │   ├── llm.py                            # Groq & Cerebras LLM completion wrappers
│   │   ├── post_call.py                      # Post-call analysis & memory creation trigger
│   │   ├── redis_client.py                   # Upstash Redis REST connection client
│   │   ├── stt.py                            # Groq (Whisper) & Sarvam AI (Saarika) STT router
│   │   ├── supabase_client.py                # Supabase service-role client helper
│   │   ├── telephony.py                      # Twilio, Exotel, & Plivo telephony adapters
│   │   ├── tts.py                            # Cartesia (Sonic-2), Sarvam (Bulbul), Hume TTS router
│   │   ├── voice_pipeline.py                 # Main Pipecat real-time telephony audio pipeline builder
│   │   └── webcall_pipeline.py               # In-browser LiveKit WebRTC audio pipeline & SSE streamer
│   ├── utils/
│   │   └── encryption.py                     # AES-256-GCM BYOK credential encryption/decryption
│   └── main.py                               # FastAPI application entry point, CORS & router mounting
│
├── src/                                      # Interactive Frontend Application (Vite 8 + React 19)
│   ├── App.tsx                               # Master application container, view router & global state
│   ├── index.css                             # Tailwind CSS v4 & custom design tokens
│   ├── types/
│   │   └── index.ts                          # TypeScript interfaces (Agent, Call, Contact, Memory, Emotion)
│   ├── services/
│   │   └── api.ts                            # Fully-typed API client service (Auth, Agents, Calls, Contacts, Connectors)
│   └── components/                           # High-Fidelity UI Components
│       ├── WebCallModal.tsx                  # Full-featured LiveKit WebRTC testing modal (Waveform, SSE telemetry)
│       ├── AgentBuilder.tsx                  # 10-Tab Agent Builder (Identity, Persona, Voice, Memory, Emotion, etc.)
│       ├── DashboardShell.tsx                # 3-Panel application shell with workspace switcher & navigation
│       ├── DashboardHome.tsx                 # Metrics dashboard, call volume charts, recent activity widgets
│       ├── ContactsManager.tsx               # Contact directory + 4-Tier Memory Drawer + DPDP "Forget Me" button
│       ├── CallsManager.tsx                  # Call history, audio player, sentiment arc graphs & transcript viewer
│       ├── SettingsManager.tsx               # BYOK API Keys (AES-256-GCM), Telephony numbers, KYC upload
│       ├── LandingPage.tsx                   # Interactive landing page with live audio simulator & feature grid
│       ├── AnalyticsPanel.tsx                # Deep analytics breakdown (Sentiment distribution, latency percentiles)
│       ├── AuthPages.tsx                     # Sign in, sign up, and password recovery interfaces
│       └── agent/                            # Modular Agent Builder Sub-Tabs
│           ├── AgentPromptTab.tsx            # System prompt editor with AI Prompt Enhancer
│           ├── AgentVoiceTab.tsx             # Voice catalog preview, speed/temperature controls
│           ├── AgentTelephonyTab.tsx         # Telephony provider & assigned phone number routing
│           └── AgentMemoryTab.tsx            # 4-Tier Memory toggles & similarity thresholds
│
├── vocall/                                   # Monorepo Sub-Package
│   ├── frontend/                             # Enterprise Dashboard (Next.js 14 App Router)
│   │   ├── src/app/                          # Next.js 14 App Router pages (/dashboard, /agents, /calls)
│   │   ├── src/components/                   # Radix UI primitives, force graph components
│   │   ├── tailwind.config.js                # Tailwind configuration
│   │   └── package.json                      # Next.js, Radix UI, Lucide, LiveKit Client dependencies
│   ├── backend/                              # Co-located FastAPI Backend Reference
│   └── docs/                                 # Architectural specifications & system contracts
│
├── trigger/                                  # Trigger.dev Asynchronous Background Job Pipelines
│   └── post_call_pipeline.py                 # 8-Stage post-call workflow (LLM summary, graph, connectors)
│
├── tests/                                    # Backend Pytest Test Suite
│   ├── conftest.py                           # Pytest fixtures & module mocks
│   ├── test_agents.py                        # Agent router test suite
│   ├── test_auth.py                          # Authentication endpoint tests
│   ├── test_calls.py                         # Call session & token issuance tests
│   ├── test_config.py                        # Environment settings validation
│   ├── test_connectors.py                    # 8 Action connectors & dispatcher tests
│   ├── test_contacts.py                      # Contact CRUD & DPDP wipe tests
│   ├── test_emotion.py                       # Emotion scoring & fusion tests
│   ├── test_encryption.py                    # AES-256-GCM encryption round-trip tests
│   ├── test_graph_memory.py                  # FalkorDB OpenCypher graph tests
│   ├── test_health.py                        # Health-check endpoint tests
│   ├── test_memory.py                        # 4-Tier memory retrieval tests
│   ├── test_phone_numbers.py                 # Telephony number management tests
│   ├── test_post_call_pipeline.py            # 8-Stage post-call worker tests
│   ├── test_stt_tts_hinglish.py              # Multilingual STT/TTS routing tests
│   ├── test_telephony.py                     # Twilio PSTN adapter tests
│   └── test_webhooks.py                      # Inbound telephony & LiveKit webhook tests
│
├── supabase/                                 # Database Schema & Migrations
│   └── queries/
│       ├── 01_initial_schema.sql             # 15-Table Complete Supabase DDL & pgvector Setup
│       └── 02_seed_data.sql                  # Seed data for agents, contacts, and configurations
│
└── latest docxxx/                            # Authoritative Documentation Suite
    ├── PRD.md                                # Product Requirements Document
    ├── TRD.md                                # Technical Requirements Document
    ├── architecture.md                       # 5-Tier System Architecture Specification
    ├── system_design.md                      # High-Level & Low-Level Design Document
    ├── components.md                         # Technical Component Specification & Taxonomy
    ├── features.md                           # Feature Matrix & Functional Capabilities
    ├── design.md                             # UI & Design System Specifications (v2.0)
    ├── changesui.md                          # WebCallModal Lifecycle & Interaction Specs
    ├── project_structure.md                  # Comprehensive Project Structure (this file)
    ├── requirement.md                        # Environment Variables & Setup Guide
    ├── apis.md                               # API Keys & Environment Configuration
    ├── REST_APIS.md                          # REST API Specification & OpenAPI Reference
    ├── CONNECTORS.md                         # 8 Action Connectors Technical Deep-Dive
    ├── MEMORY_GRAPH_RAG.md                   # 4-Tier Memory & OpenCypher Deep-Dive
    ├── INTENT_EMOTION_ENGINE.md              # VA-ICECoT & Dual Emotion Mathematical Deep-Dive
    ├── GRAPH_AUDIT_REPORT_SUMMARY.md         # Graphify Knowledge Graph Audit Findings
    ├── SWE-PRINCIPLE.md                      # SWEBOK Engineering Guidelines & Limits
    └── VoCall_Research_Diagrams.md           # Research Tables & Comparative Architecture
```

---

Approved by VoCall Technical Architecture Team.
