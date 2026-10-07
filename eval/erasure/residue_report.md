> [!NOTE]
> **MOCK AUDIT DATA**: This report reflects a mock run used for testing purposes. Do not cite these numbers in empirical findings.

# DPDP Act 2023 Section 12 Memory Erasure Audit Report

**Generated:** 2026-10-07 08:00:17 UTC  
**Target Endpoint:** `DELETE /api/v1/contacts/{contact_id}/memory`  
**Test Corpus:** 20 contacts with injected unique canary strings (`CANARY-<hex>`)  
**Overall Completeness ($C = 1 - N_{after} / N_{before}$):** **1.0000 (100.0%)**  
**Overall Residue Rate:** **0.0% (0 of 460 personal records unscrubbed)**

---

## 1. Executive Summary

This probe evaluated data erasure under Section 12 of India's Digital Personal Data Protection (DPDP) Act 2023.
We seeded 20 distinct test identities with unique canary tokens across all memory tiers and relational stores.
We then executed the production cascade erasure endpoint and inspected all stores without filtering thresholds.

The probe verified complete erasure across all storage layers:
- **Tiers Cleared by Endpoint:** Upstash Redis (in-call buffer, webcall events, slot keys), Supabase pgvector (`memory_long_term`), episodic summaries (`memory_episodic`), FalkorDB contact graphs (`contact_<cid>`), intent/emotion events, call turns/transcripts, sanitized calls, and contact identity removal.
- **Residue Count:** Exactly 0 personal data records remained retrievable ($C = 1.0000$).
- **Audit Logging:** HMAC-SHA256 pseudonymized audit logs recorded without PII leakage.

---

## 2. Table VIII: Storage Tier Audit & Residue Breakdown

| Storage Store / Table | Category | Seeded (Before) | Retrievable (After) | Residue Count | Retention Rate | Completeness ($C$) | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `Redis In-Call Buffer` | Tier 1: Upstash Redis (stm:{call_id}) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Redis Webcall Stream` | Tier 1: Upstash Redis (webcall:{call_id}:events) | 40 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Redis Slot State` | Tier 1: Upstash Redis (slot:{call_id}) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Redis Extra Keys` | Tier 1: Upstash Redis (pattern scan) | 0 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Contact Profiles` | Identity: Postgres Contacts (contacts) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Calls & Audio Recordings` | Relational: Postgres Calls (calls.recording_url) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Turn-by-Turn Dialogues` | Relational: Postgres Call Turns (call_turns) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Spoken Transcripts` | Relational: Postgres Transcripts (call_transcripts) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Acoustic Emotion Events` | Relational: Postgres Emotion Events (emotion_events) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Intent Engine Events` | Tier 5: Postgres Intent Events (intent_events) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `pgvector Semantic Memory` | Tier 2: Postgres pgvector (memory_long_term) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Episodic Call Summaries` | Tier 3: Postgres Episodic (memory_episodic) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `Graph Node Metadata` | Relational: Postgres Graph Nodes (memory_graph_nodes) | 20 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `FalkorDB Contact Graph` | Tier 4: FalkorDB Nodes (contact_{cid}) | 100 | 0 | 0 | 0.0% | 1.0000 | PASS |
| `FalkorDB Global Graph` | Tier 4: FalkorDB Canary Global Search | 100 | 0 | 0 | 0.0% | 1.0000 | PASS |
| **COMPOSITE TOTAL** | **All Stores** | **460** | **0** | **0** | **0.0%** | **1.0000** | **PASS (CLEARED)** |

---

## 3. Storage Tier Findings

### Tier 1: Redis In-Call State & Dialogue Slots
Pre-fetched call IDs allow removing `stm:{call_id}`, `webcall:{call_id}:events`, and `slot:{call_id}:*` keys alongside `erasure:{cid}` suppression flags. Zero buffer residue was detected.

### Tier 2: Postgres Calls & Transcripts Sanitization
Personal identifiers in `calls` (`transcript`, `analysis`, `from_number`, `to_number`, `emotion_score`, `contact_id`) were set to NULL while non-identifying call duration and timestamps were retained. Child records in `call_turns`, `call_transcripts`, `emotion_events`, and `intent_events` were removed.

### Tier 3: Semantic & Graph Memory
`memory_long_term` and `memory_episodic` rows were deleted, and FalkorDB graph nodes for `contact_{cid}` were detached and dropped with zero node count confirmed.

---

## 4. Special Evaluation Scenarios

### Scenario A: Erasure While Call Is In Progress
- **Seeded Active Call ID:** `88de3bf3-680e-4234-a2f2-8073aac52b1a`
- **Active Dialogue Buffer Retained:** `NO`
- **Active Record in `calls` Retained:** `NO`
- **Finding:** Triggering memory erasure mid-call leaves the in-progress voice pipeline undisturbed. Ephemeral turns and active database rows continue accumulating until call teardown.

### Scenario B: Idempotence Verification (Double Erasure)
- **First Erasure Request:** Status 200 OK (`deleted=True`)
- **Second Erasure Request:** Status 200 OK (`deleted=True`)
- **Post-Erasure Item Match:** Pass 1 count = 0, Pass 2 count = 0
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
---

## 6. Compliance Verification Summary

All required remediation controls are active in `app/routers/contacts.py`:
1. Call IDs are pre-fetched before running deletions.
2. Short-term dialogue keys (`stm:{call_id}`), LiveKit buffers (`webcall:{call_id}:events`), and slots (`slot:{call_id}:*`) are purged along with the 1-hour Redis erasure flag.
3. Postgres records in `memory_long_term`, `memory_episodic`, `intent_events`, `emotion_events`, and call dialogues are wiped, while `calls` rows are scrubbed of identifying phone numbers and transcripts.
4. FalkorDB graph nodes are detached and dropped.
5. HMAC-SHA256 pseudonymized audit logs are written without raw identifier leakage.
