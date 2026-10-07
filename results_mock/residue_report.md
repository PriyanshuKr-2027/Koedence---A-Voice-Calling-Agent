# DPDP Act 2023 Section 12 Memory Erasure Audit Report

**Generated:** 2026-10-05 08:26:53 UTC  
**Target Endpoint:** `DELETE /api/v1/contacts/{contact_id}/memory`  
**Test Corpus:** 20 contacts with injected unique canary strings (`CANARY-<hex>`)  
**Overall Completeness ($C = 1 - N_{after} / N_{before}$):** **0.5652 (56.5%)**  
**Overall Residue Rate:** **43.5% (200 of 460 personal records unscrubbed)**

---

## 1. Executive Summary

This probe evaluated data erasure under Section 12 of India's Digital Personal Data Protection (DPDP) Act 2023.
We seeded 20 distinct test identities with unique canary tokens across all 5 memory tiers and relational stores.
We then executed the production cascade erasure endpoint and inspected all stores without filtering thresholds.

The probe uncovered a substantial compliance gap:
- **Tiers Cleared by Endpoint:** Supabase pgvector (`memory_long_term`), episodic summaries (`memory_episodic`), FalkorDB contact graphs (`contact_<cid>`), and contact-linked intent events (`intent_events`).
- **Residue Findings (Stores Untouched by Endpoint):**
  1. **Relational Audio & Call Logs:** The `calls` table retains audio file references (`recording_url`), transcripts, and timestamps. Child tables `call_turns`, `call_transcripts`, and `emotion_events` remain completely intact.
  2. **Identity & Graph Metadata:** The `contacts` table record itself and `memory_graph_nodes` entries are never cleared.
  3. **Redis Identifier Mismatch:** In-call short-term memory keys (`stm:{call_id}`), webcall event buffers (`webcall:{call_id}:events`), and dialogue slot state (`slot:{call_id}`) survived because the router requested deletion using `contact_id` rather than active `call_id` handles.

---

## 2. Table VIII: Storage Tier Audit & Residue Breakdown

| Storage Store / Table | Category | Seeded (Before) | Retrievable (After) | Residue Count | Retention Rate | Completeness ($C$) | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `Redis In-Call Buffer` | Tier 1: Upstash Redis (stm:{call_id}) | 20 | 20 | 20 | 100.0% | 0.0000 | **RESIDUE** |
| `Redis Webcall Stream` | Tier 1: Upstash Redis (webcall:{call_id}:events) | 40 | 40 | 40 | 100.0% | 0.0000 | **RESIDUE** |
| `Redis Slot State` | Tier 1: Upstash Redis (slot:{call_id}) | 20 | 20 | 20 | 100.0% | 0.0000 | **RESIDUE** |
| `Redis Extra Keys` | Tier 1: Upstash Redis (pattern scan) | 0 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Contact Profiles` | Identity: Postgres Contacts (contacts) | 20 | 20 | 20 | 100.0% | 0.0000 | **RESIDUE** |
| `Calls & Audio Recordings` | Relational: Postgres Calls (calls.recording_url) | 20 | 20 | 20 | 100.0% | 0.0000 | **RESIDUE** |
| `Turn-by-Turn Dialogues` | Relational: Postgres Call Turns (call_turns) | 20 | 20 | 20 | 100.0% | 0.0000 | **RESIDUE** |
| `Spoken Transcripts` | Relational: Postgres Transcripts (call_transcripts) | 20 | 20 | 20 | 100.0% | 0.0000 | **RESIDUE** |
| `Acoustic Emotion Events` | Relational: Postgres Emotion Events (emotion_events) | 20 | 20 | 20 | 100.0% | 0.0000 | **RESIDUE** |
| `Intent Engine Events` | Tier 5: Postgres Intent Events (intent_events) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `pgvector Semantic Memory` | Tier 2: Postgres pgvector (memory_long_term) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Episodic Call Summaries` | Tier 3: Postgres Episodic (memory_episodic) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Graph Node Metadata` | Relational: Postgres Graph Nodes (memory_graph_nodes) | 20 | 20 | 20 | 100.0% | 0.0000 | **RESIDUE** |
| `FalkorDB Contact Graph` | Tier 4: FalkorDB Nodes (contact_{cid}) | 100 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `FalkorDB Global Graph` | Tier 4: FalkorDB Canary Global Search | 100 | 0 | 0 | 0.0% | 1.0000 | PASS |
| **COMPOSITE TOTAL** | **All Stores** | **460** | **200** | **200** | **43.48%** | **0.5652** | **DEFICIT DETECTED** |

---

## 3. Specific Storage Residue Findings

### Finding 1: S3 Audio Recording URLs and Transcripts in Postgres (`calls`, `call_turns`, `call_transcripts`)
The erasure endpoint cleans `memory_long_term` and `memory_episodic`, but leaves `calls.recording_url` and spoken turns completely untouched.
Under DPDP Section 12, raw voice audio and verbatim call turns constitute personal data.
An external auditor or data principal can reconstruct the entire spoken dialogue by reading `call_turns.transcript` or downloading audio from `calls.recording_url`.

### Finding 2: Redis Call ID vs Contact ID Mismatch
In `app/routers/contacts.py`, the router triggers:
```python
redis_task = short_term.clear_call(cid)
```
The parameter passed is `cid` (the contact UUID). Active dialogues, LiveKit audio buffers, and slot keys are keyed by `call_id` (`stm:{call_id}`, `webcall:{call_id}:events`, `slot:{call_id}`).
Consequently, calling `clear_call` with `contact_id` deletes nothing. 100% of ephemeral in-memory dialogue turns and slot values remain active until their 3600-second TTL expires.

### Finding 3: Acoustic Emotion and Intent Metadata
While `intent_events` rows matching `contact_id` were wiped, acoustic records in `emotion_events` (valence, arousal, dominant tone, confidence) were retained because they reference `call_id` without a direct contact foreign key delete cascade.

---

## 4. Special Evaluation Scenarios

### Scenario A: Erasure While Call Is In Progress
- **Seeded Active Call ID:** `daabaa78-7505-4336-9e2a-bf0b645ef9e6`
- **Active Dialogue Buffer Retained:** `YES`
- **Active Record in `calls` Retained:** `YES`
- **Finding:** Triggering memory erasure mid-call leaves the in-progress voice pipeline undisturbed. Ephemeral turns and active database rows continue accumulating until call teardown.

### Scenario B: Idempotence Verification (Double Erasure)
- **First Erasure Request:** Status 200 OK (`deleted=True`)
- **Second Erasure Request:** Status 200 OK (`deleted=True`)
- **Post-Erasure Item Match:** Pass 1 count = 10, Pass 2 count = 10
- **Finding:** The cascade deletion route is fully idempotent. Repeating the call does not crash, return 500, or modify audit states.

### Scenario C: Shared Graph Node Survival
- **Shared Entity:** `Entity-Shared-Apollo-Hospital`
- **Node Survived for Contact B:** `YES`
- **Contact B Identity Node Survived:** `YES`
- **Finding:** Because VoCall partitions FalkorDB graphs per contact (`contact_<cid>`), deleting Contact A's graph does not drop nodes in Contact B's graph.

---

## 5. Audit Log Safety Verification

- **Audit Entries Checked in `compliance_log`:** 20
- **Missing Audit Entries:** 0
- **Raw Personal Data Leaks (Names, Numbers, Emails, Canaries):** **0**
- **Safety Status:** **COMPLIANT (Zero PII Leaked)**

Audit entries record action name (`forget_me`), contact UUID, timestamps, and cleared tier tags. No raw canary tokens, phone numbers, or dialogue snippets leak into audit storage.

---

## 6. Direct Remediation Steps (For Subsequent Fix Task)

1. Add explicit deletion of parent `contacts` and child `calls` rows (with S3 object deletion for `recording_url`).
2. Cascade deletion to `call_turns`, `call_transcripts`, `emotion_events`, and `memory_graph_nodes`.
3. In `short_term.clear_call`, query all call IDs associated with `contact_id` from Postgres before deleting Redis keys, or store an index `contact_calls:{cid}`.
4. Add deletion of `webcall:{call_id}:events` and `slot:{call_id}` in Redis.
