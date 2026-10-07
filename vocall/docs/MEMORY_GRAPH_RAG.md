# VoCall 4-Tier Hybrid Cognitive Memory & Graph RAG Engine

**Document Version:** 2.0  
**Status:** Authoritative Specification  
**Architecture Layer:** Multi-Tier Cognitive Memory & Graph Knowledge Retrieval  
**Related Components:** `app/services/memory/`, `app/routers/memory.py`, `trigger/post_call_pipeline.py`, `app/services/redis_client.py`

---

## 1. Executive Summary & Architecture Overview

Traditional conversational voice agents suffer from severe amnesia: they treat every call session in complete isolation, forcing returning callers to re-explain their background, preferences, and prior unresolved issues. 

VoCall resolves this foundational challenge with a **4-Tier Hybrid Cognitive Memory Architecture** that unifies:
1. **Ultra-Low Latency Ephemeral Session Buffer (Redis)** for turn-by-turn state tracking.
2. **Dense Vector Semantic Search (Supabase pgvector)** for fact retrieval.
3. **Structured Relational Episodes (PostgreSQL)** for past call context.
4. **Causal Entity-Relationship Knowledge Graph (FalkorDB OpenCypher)** for associative multi-hop reasoning.

```text
                               ┌──────────────────────────────────────────────┐
                               │         INCOMING VOICE CALL SESSION          │
                               │        (Contact Identified via CLI/PSTN)     │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │    MULTI-TIER PARALLEL       │
                                       │    MEMORY RETRIEVER          │
                                       │    `retrieve_all_memory()`   │
                                       │    (asyncio.gather <80ms)    │
                                       └──────────────┬───────────────┘
                                                      │
         ┌─────────────────────┬──────────────────────┼──────────────────────┐
         │                     │                      │                      │
┌────────▼──────────┐ ┌────────▼──────────┐  ┌────────▼──────────┐  ┌────────▼──────────┐
│ TIER 1: WORKING   │ │ TIER 2: LONG-TERM │  │ TIER 3: EPISODIC  │  │ TIER 4: GRAPH     │
│ Short-Term Memory │ │ Semantic Vectors  │  │ Call Summaries    │  │ Knowledge Graph   │
├───────────────────┤ ├───────────────────┤  ├───────────────────┤  ├───────────────────┤
│ Upstash Redis     │ │ Supabase pgvector │  │ Postgres Table    │  │ FalkorDB (Cypher) │
│ `stm:{call_id}`   │ │ 1536-dim OpenAI   │  │ Structured JSON   │  │ Multi-hop Nodes & │
│ Active turns &    │ │ Fact embeddings & │  │ Past call arcs &  │  │ Frustration link  │
│ current emotion   │ │ cosine similarity │  │ action items      │  │ relationships     │
└───────────────────┘ └───────────────────┘  └───────────────────┘  └───────────────────┘
         │                     │                      │                      │
         └─────────────────────┴──────────────────────┼──────────────────────┘
                                                      │
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │    STRUCTURED SYSTEM PROMPT  │
                                       │    INJECTION SECTION         │
                                       │    `build_memory_prompt()`   │
                                       └──────────────────────────────┘
```

---

## 2. Deep-Dive Specification of the 4 Memory Tiers

### 2.1 Tier 1: Working & Short-Term Memory (Upstash Redis)

- **Implementation:** `app/services/memory/short_term.py` & `app/services/redis_client.py`
- **Key Pattern:** `stm:{call_id}` (Redis List & Hash with 24-hour TTL)
- **Data Maintained:**
  - Complete sliding window of turn transcripts: `[{"role": "user"|"assistant", "content": "...", "timestamp": "..."}]`
  - Running acoustic/text emotion signals and valence/arousal averages.
  - Active intent and carried-over slot key-values (VA-ICECoT slot manager).
  - Mid-call connector execution results (e.g. appointment times fetched).
- **Latency Budget:** $< 10\text{ms}$ REST / $< 2\text{ms}$ socket round-trip.

---

### 2.2 Tier 2: Long-Term Semantic Memory (Supabase pgvector)

- **Implementation:** `app/services/memory/long_term.py`
- **Database Table:** `memory_long_term`
- **Vector Embeddings:** 1536-dimensional embeddings generated via OpenAI `text-embedding-3-small`.
- **Indexing:** HNSW (Hierarchical Navigable Small World) index with cosine distance operator (`<=>`):
  ```sql
  CREATE INDEX idx_memory_long_term_embedding 
  ON memory_long_term USING hnsw (embedding vector_cosine_ops);
  ```
- **Semantic Retrieval (`retrieve_relevant_facts`):**
  Executes cosine similarity query retrieving top-$k$ ($k=5$) facts with match threshold $\ge 0.75$:
  ```sql
  SELECT id, fact, category, 1 - (embedding <=> query_embedding) AS similarity
  FROM memory_long_term
  WHERE contact_id = $1 AND (1 - (embedding <=> query_embedding)) > 0.75
  ORDER BY similarity DESC
  LIMIT 5;
  ```

---

### 2.3 Tier 3: Episodic Memory (Supabase PostgreSQL)

- **Implementation:** `app/services/memory/episodic.py`
- **Database Table:** `memory_episodic`
- **Content Stored:**
  - Comprehensive call summary synthesized via Groq LLaMA 3.3 70B in JSON mode.
  - Key topics discussed (`["billing_dispute", "refund_request"]`).
  - Extracted named entities (`{"agent_promised_refund": 500, "currency": "INR"}`).
  - Identified customer intent and final call outcome status (`"resolved"`, `"escalated"`, `"follow_up_needed"`).
  - Emotional progression trajectory (e.g. `frustrated -> neutral -> satisfied`).
  - Chronological link to the preceding call episode (`previous_episode_id`).

---

### 2.4 Tier 4: Associative Knowledge Graph (FalkorDB OpenCypher)

- **Implementation:** `app/services/memory/graph.py`
- **Graph Engine:** FalkorDB (RedisGraph successor leveraging Redis module architecture for sub-millisecond Cypher query execution).
- **Node Labels & Entity Types:**
  - `(:Contact {id, name, phone, email})`
  - `(:Episode {id, call_id, date, duration, outcome, summary})`
  - `(:Entity {name, type})` (e.g., Products, Policies, Support Agents, Promises)
  - `(:Topic {name})` (e.g., NetworkOutage, KYCVerification, PaymentFailure)
  - `(:FrustrationEvent {intensity, timestamp, trigger_phrase})`
- **Relationship Schema:**
  - `(:Contact)-[:HAD_EPISODE]->(:Episode)`
  - `(:Episode)-[:MENTIONED_ENTITY]->(:Entity)`
  - `(:Episode)-[:DISCUSSED_TOPIC]->(:Topic)`
  - `(:Episode)-[:EXPERIENCED_FRUSTRATION]->(:FrustrationEvent)`
  - `(:Episode)-[:TRANSITIONED_TO]->(:Episode)` (Temporal chain)

```cypher
// Retrieve comprehensive graph context for an active caller
MATCH (c:Contact {id: $contact_id})-[:HAD_EPISODE]->(e:Episode)
OPTIONAL MATCH (e)-[:MENTIONED_ENTITY]->(ent:Entity)
OPTIONAL MATCH (e)-[:DISCUSSED_TOPIC]->(t:Topic)
OPTIONAL MATCH (e)-[:EXPERIENCED_FRUSTRATION]->(f:FrustrationEvent)
RETURN e.date AS call_date, 
       e.summary AS summary, 
       collect(DISTINCT ent.name) AS entities,
       collect(DISTINCT t.name) AS topics,
       collect(DISTINCT f.trigger_phrase) AS frustration_triggers
ORDER BY e.date DESC
LIMIT 3;
```

---

## 3. Parallel Retrieval & System Prompt Injection

### 3.1 Parallel Fanout (`app/services/memory/retriever.py`)

When an incoming call is established, `retrieve_all_memory()` executes asynchronous parallel queries across all memory tiers using `asyncio.gather()`:

```python
async def retrieve_all_memory(contact_id: str, current_query: str) -> dict:
    """Parallel fanout across all 4 cognitive memory tiers (<80ms budget)."""
    t1_task = get_short_term_memory(contact_id)
    t2_task = retrieve_relevant_facts(contact_id, current_query)
    t3_task = get_recent_episodes(contact_id, limit=3)
    t4_task = get_contact_graph_context(contact_id)
    
    stm, long_term, episodes, graph_ctx = await asyncio.gather(
        t1_task, t2_task, t3_task, t4_task, return_exceptions=True
    )
    
    return {
        "short_term": stm if not isinstance(stm, Exception) else {},
        "long_term_facts": long_term if not isinstance(long_term, Exception) else [],
        "recent_episodes": episodes if not isinstance(episodes, Exception) else [],
        "graph_context": graph_ctx if not isinstance(graph_ctx, Exception) else {}
    }
```

### 3.2 Dynamic Prompt Injection (`build_memory_prompt`)

The aggregated memory dictionary is rendered into a formatted markdown context block injected into the LLM system instructions:

```text
=== CALLER MEMORY & CONTEXT ===
[Caller Identification]: Rahul Sharma (+91 98765 43210)
[Known Long-Term Facts]:
- Subscribed to Enterprise Voice AI Tier (since March 2025)
- Preferred communication language: Hinglish
- Billing cycle: 1st of every month

[Recent Call Episodes]:
- 2026-08-15: Discussed webhook latency issues. Agent promised follow-up on custom payload format. (Outcome: follow_up_needed)
- 2026-08-01: Inquired about DPDP compliance data retention guidelines. (Outcome: resolved)

[Knowledge Graph Entities & Frustrations]:
- Frequently discussed topics: WebhookLatency, BillingInvoice
- Previous Frustration Triggers: "Delayed invoice delivery"
===============================
```

---

## 4. DPDP Act 2023 "Forget Me" Cascading Erasure Protocol

In compliance with India's **Digital Personal Data Protection (DPDP) Act 2023** and **GDPR Article 17 (Right to Erasure)**, VoCall implements an atomic cascading data deletion protocol across all 4 memory tiers when a contact requests erasure (`DELETE /api/v1/contacts/{id}/memory`):

1. **Tier 1 Purge:** Deletes all active Redis keys (`stm:*` and session tokens) for the contact.
2. **Tier 2 Purge:** Executes SQL `DELETE FROM memory_long_term WHERE contact_id = $1` (purging dense vector embeddings).
3. **Tier 3 Purge:** Executes SQL `DELETE FROM memory_episodic WHERE contact_id = $1` (purging transcripts and structured summaries).
4. **Tier 4 Purge:** Executes FalkorDB OpenCypher deletion:
   ```cypher
   MATCH (c:Contact {id: $contact_id})
   OPTIONAL MATCH (c)-[:HAD_EPISODE]->(e:Episode)
   OPTIONAL MATCH (e)-[:EXPERIENCED_FRUSTRATION]->(f:FrustrationEvent)
   DETACH DELETE c, e, f;
   ```
5. **Audit Logging:** Emits an anonymized SHA-256 compliance record in `audit_logs` confirming timestamp and total records erased.
