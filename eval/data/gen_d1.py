"""Dataset D1 Generator: Synthetic Caller Histories for Memory Evaluation.

Generates:
  - callers.jsonl: Persona sheets with 4-6 stable facts and 1 recurring complaint topic.
  - calls.jsonl: M short call transcripts (6-14 turns) with emotional arcs and mentioned facts.
  - questions.jsonl: 8 questions per caller across 5 types (fact_recall, preference,
    recurring_complaint_pattern, temporal, adversarial).

Deterministic given seed. Uses app.services.llm.llm_service (temperature 0.7) and
disk cache (eval.common.cache) to prevent repeated paid API calls.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import yaml

from app.services.llm import llm_service
from eval.common.cache import DiskCache, default_cache
from eval.common.runlog import append_jsonl

# ---------------------------------------------------------------------------
# Candidate Persona Pools
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Aarav", "Priya", "Rohit", "Ananya", "Vikram", "Sunita", "Aditya", "Neha",
    "Karan", "Ritu", "Siddharth", "Deepika", "Manish", "Meera", "Gaurav", "Pooja",
    "Arjun", "Kavita", "Sanjay", "Swati", "Nikhil", "Divya", "Rahul", "Tanvi",
    "Amit", "Sneha", "Varun", "Isha", "Rajesh", "Shreya", "Kunal", "Pallavi",
    "Alok", "Nandini", "Harsh", "Simran", "Manoj", "Preeti", "Sameer", "Geeta",
    "Pranav", "Bhavna", "Abhishek", "Juhi", "Mayank", "Archana", "Tarun", "Rashmi",
    "Chirag", "Monika", "Sachin", "Anjali", "Vivek", "Suman", "Deepak", "Aparna",
    "Rakesh", "Komal", "Vishal", "Rekha",
]

LAST_NAMES = [
    "Sharma", "Patel", "Verma", "Iyer", "Singh", "Nair", "Joshi", "Kulkarni",
    "Malhotra", "Gupta", "Rao", "Sen", "Saxena", "Menon", "Agarwal", "Deshpande",
    "Reddy", "Pillai", "Bhatia", "Mukherjee", "Chauhan", "Nambiar", "Kapoor", "Mishra",
    "Pandey", "Mehta", "Bose", "Ghosh", "Deshmukh", "Choudhury", "Bhatt", "Dubey",
    "Trivedi", "Sethi", "Venkatesh", "Chatterjee", "Subramanian", "Jain", "Bansal", "Mahajan",
]

PLANS = [
    "Fiber Pro 300 Mbps",
    "Postpaid Max 5G Unlimited",
    "Basic Broadband 50 Mbps",
    "Gigabit Enterprise 1 Gbps",
    "Student Saver 100 Mbps",
    "Family Home Pack 200 Mbps",
    "Ultra Stream 500 Mbps",
    "Starter Postpaid 30 GB",
]

BILLING_DATES = [
    "3rd of every month",
    "5th of every month",
    "10th of every month",
    "15th of every month",
    "18th of every month",
    "22nd of every month",
    "28th of every month",
]

AREAS = [
    "Koramangala 4th Block, Bengaluru",
    "Sector 62, Noida",
    "Andheri West, Mumbai",
    "Indiranagar, Bengaluru",
    "Banjara Hills, Hyderabad",
    "Salt Lake Sector V, Kolkata",
    "Viman Nagar, Pune",
    "Connaught Place, New Delhi",
    "Alwarpet, Chennai",
    "Civil Lines, Jaipur",
    "Powai, Mumbai",
    "Whitefield, Bengaluru",
    "Gachibowli, Hyderabad",
    "South City 1, Gurugram",
    "Anna Nagar, Chennai",
]

CONTACT_TIMES = [
    "Weekdays after 6 PM",
    "Morning 9 AM to 11 AM",
    "Saturday mornings",
    "Afternoons between 2 PM and 4 PM",
    "Only text messages during office hours",
    "Lunch hours 1 PM to 2 PM",
    "Sundays anytime after 11 AM",
]

FAMILY_PREFERENCES = [
    "Elderly mother lives at home and needs landline backup",
    "Daughter uses internet for evening online tuition classes",
    "Spouse works remotely and needs zero daytime downtime",
    "Son plays competitive online games on weekends",
    "Two college students share connection for late-night project work",
    "Grandfather uses video calling every Sunday morning",
    "Home office setup requires reliable connection for client calls",
]

RECURRING_COMPLAINTS = [
    "Frequent evening broadband speed drops",
    "Unexpected roaming surcharge on monthly invoice",
    "Delayed technician visit for router replacement",
    "Billing deduction for unrequested value-added service",
    "Intermittent Wi-Fi signal loss in rear bedrooms",
    "Static noise and call drops on landline connection",
    "Delay in static IP allocation for home office server",
    "Auto-debit failure message despite successful bank deduction",
]

EMOTION_ARCS = [
    "calm -> calm",
    "calm -> irritated",
    "irritated -> irritated",
    "irritated -> angry",
    "irritated -> calm",
    "angry -> irritated",
]

ADVERSARIAL_ATTRIBUTES = [
    ("pet's name", "What is the name of the caller's pet?"),
    ("vehicle number", "What is the caller's registered vehicle registration number?"),
    ("passport number", "What passport number does the caller hold?"),
    ("college degree", "Which college or university degree did the caller complete?"),
    ("favorite color", "What is the caller's favorite color according to their profile?"),
    ("blood group", "What blood group is noted for this caller?"),
]

CALL_NON_COMPLAINT_TOPICS = [
    ("bill_inquiry", "Inquiring about current monthly invoice breakdown and payment due date"),
    ("plan_upgrade", "Asking about speed upgrade options and promotional pricing for fiber plans"),
    ("address_check", "Verifying installation address details and area service coverage"),
    ("autopay_setup", "Checking auto-pay bank mandate status and preferred payment card"),
    ("router_query", "Inquiring about dual-band router compatibility and password change steps"),
]


# ---------------------------------------------------------------------------
# Persona & Per-Call Builders
# ---------------------------------------------------------------------------

def generate_persona(caller_idx: int, rng: random.Random) -> Dict[str, Any]:
    """Generates a stable caller persona sheet with 4 to 6 facts and 1 recurring complaint."""
    caller_id = f"caller_{caller_idx:03d}"
    first_name = rng.choice(FIRST_NAMES)
    last_name = rng.choice(LAST_NAMES)
    name = f"{first_name} {last_name}"
    phone = f"+91 9{rng.randint(1000, 9999)} {rng.randint(10000, 99999)}"
    language_style = rng.choice(["English", "Hinglish"])

    # 4 to 6 stable facts
    facts: List[Dict[str, Any]] = [
        {
            "fact_id": f"{caller_id}_f1",
            "category": "plan_type",
            "key": "Plan Type",
            "value": rng.choice(PLANS),
        },
        {
            "fact_id": f"{caller_id}_f2",
            "category": "preferred_language",
            "key": "Preferred Language",
            "value": language_style,
        },
        {
            "fact_id": f"{caller_id}_f3",
            "category": "billing_date",
            "key": "Billing Date",
            "value": rng.choice(BILLING_DATES),
        },
        {
            "fact_id": f"{caller_id}_f4",
            "category": "address_area",
            "key": "Address Area",
            "value": rng.choice(AREAS),
        },
        {
            "fact_id": f"{caller_id}_f5",
            "category": "preferred_contact_time",
            "key": "Preferred Contact Time",
            "value": rng.choice(CONTACT_TIMES),
        },
        {
            "fact_id": f"{caller_id}_f6",
            "category": "family_preference",
            "key": "Family Preference",
            "value": rng.choice(FAMILY_PREFERENCES),
        },
    ]

    # Optionally trim to 5 or keep 6 facts
    num_facts = rng.choice([5, 6])
    selected_facts = facts[:num_facts]

    complaint_topic = rng.choice(RECURRING_COMPLAINTS)
    recurring_complaint = {
        "fact_id": f"{caller_id}_complaint",
        "category": "recurring_complaint",
        "topic": complaint_topic,
    }

    return {
        "caller_id": caller_id,
        "name": name,
        "phone": phone,
        "language_style": language_style,
        "facts": selected_facts,
        "recurring_complaint": recurring_complaint,
    }


def plan_calls_for_caller(persona: Dict[str, Any], rng: random.Random) -> List[Dict[str, Any]]:
    """
    Plans M calls (5 to 8) for a caller.
    Ensures the recurring complaint topic appears in at least 3 calls.
    """
    m_calls = rng.randint(5, 8)
    caller_id = persona["caller_id"]
    complaint_topic = persona["recurring_complaint"]["topic"]
    facts = persona["facts"]

    # Select at least 3 distinct call indices for the recurring complaint
    num_complaint_calls = rng.randint(3, min(m_calls, 4))
    complaint_indices = set(rng.sample(range(m_calls), num_complaint_calls))

    planned_calls = []
    for call_idx in range(m_calls):
        call_id = f"{caller_id}_c{call_idx + 1:02d}"
        has_complaint = call_idx in complaint_indices
        emotion_arc = rng.choice(EMOTION_ARCS)
        target_turns = rng.choice([6, 8, 10, 12])

        # Pick 1 to 3 stable facts to mention in dialogue
        sampled_facts = rng.sample(facts, k=rng.randint(1, min(3, len(facts))))
        mentioned_fact_ids = [f["fact_id"] for f in sampled_facts]

        if has_complaint:
            call_topic = f"Complaint about {complaint_topic}"
        else:
            _, desc = rng.choice(CALL_NON_COMPLAINT_TOPICS)
            call_topic = desc

        planned_calls.append({
            "caller_id": caller_id,
            "call_id": call_id,
            "call_index": call_idx + 1,
            "call_topic": call_topic,
            "emotion_arc": emotion_arc,
            "complaint_present": has_complaint,
            "complaint_topic": complaint_topic if has_complaint else None,
            "target_turns": target_turns,
            "mentioned_facts": sampled_facts,
            "mentioned_fact_ids": mentioned_fact_ids,
        })

    return planned_calls


# ---------------------------------------------------------------------------
# Dialogue Generator via LLM
# ---------------------------------------------------------------------------

def _build_llm_prompt(persona: Dict[str, Any], call_plan: Dict[str, Any]) -> Tuple[str, str]:
    """Assembles system and user prompts to generate dialogue turns."""
    sys_prompt = (
        "You are generating realistic customer service telephone transcripts between an Indian "
        "broadband/telecom customer and a professional AI voice support agent for VoCall.\n"
        "Return ONLY a valid JSON array of dialogue turn objects matching this exact structure:\n"
        '[\n  {"role": "agent", "content": "..."},\n  {"role": "caller", "content": "..."}\n]\n'
        "Rules:\n"
        "- Alternate strictly between agent and caller.\n"
        "- Reflect the caller's requested language style (English or Hinglish code-switching naturally).\n"
        "- Naturally weave in the mentioned facts.\n"
        "- Show the specified caller emotional trajectory.\n"
        "- Total turns should be between 6 and 14 turns."
    )

    facts_text = "\n".join(f"- {f['key']}: {f['value']}" for f in call_plan["mentioned_facts"])
    complaint_instruction = (
        f"- The caller explicitly complains about: '{call_plan['complaint_topic']}'"
        if call_plan["complaint_present"]
        else f"- The caller is calling regarding: '{call_plan['call_topic']}' (no mention of severe service complaints)"
    )

    user_prompt = (
        f"Generate a telephone call transcript for this scenario:\n"
        f"Customer Name: {persona['name']}\n"
        f"Language Style: {persona['language_style']}\n"
        f"Call Number: #{call_plan['call_index']}\n"
        f"Emotional Arc: {call_plan['emotion_arc']}\n"
        f"Target Turns: {call_plan['target_turns']}\n"
        f"Topic Objective:\n{complaint_instruction}\n"
        f"Facts to mention naturally:\n{facts_text}\n"
    )

    return sys_prompt, user_prompt


def _deterministic_fallback_dialogue(
    persona: Dict[str, Any],
    call_plan: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Deterministic rule-based dialogue generator used as offline fallback
    when running without live external API keys.
    """
    name = persona["name"]
    is_hinglish = persona["language_style"].lower() == "hinglish"
    facts = call_plan["mentioned_facts"]
    fact_phrases = [f"{f['key'].lower()} is {f['value']}" for f in facts]
    facts_str = ", and my ".join(fact_phrases)

    turns: List[Dict[str, str]] = []

    # Turn 1 & 2
    if is_hinglish:
        turns.append({"role": "agent", "content": "Namaste, VoCall Support me aapka swagat hai. Aaj main aapki kya madad kar sakta hoon?"})
        greeting = f"Namaste, main {name} baat kar raha hoon."
        if call_plan["complaint_present"]:
            turns.append({"role": "caller", "content": f"{greeting} Mere connection pe phir se issue aa gaya hai: {call_plan['complaint_topic']}."})
        else:
            turns.append({"role": "caller", "content": f"{greeting} Mujhe apne account ke baare me kuch details check karni thi."})
    else:
        turns.append({"role": "agent", "content": f"Hello, thank you for reaching VoCall Customer Care. How may I assist you today?"})
        greeting = f"Hello, this is {name}."
        if call_plan["complaint_present"]:
            turns.append({"role": "caller", "content": f"{greeting} I am calling because I have the same problem again: {call_plan['complaint_topic']}."})
        else:
            turns.append({"role": "caller", "content": f"{greeting} I would like to check some information regarding my account."})

    # Turn 3 & 4 (Facts mentioned)
    if is_hinglish:
        turns.append({"role": "agent", "content": "Haan ji, main check kar deta hoon. Kya aap apna registered detail confirm kar sakte hain?"})
        turns.append({"role": "caller", "content": f"Haan, my {facts_str}."})
    else:
        turns.append({"role": "agent", "content": "Certainly, let me pull up your account. Could you verify your registered account details?"})
        turns.append({"role": "caller", "content": f"Yes, my {facts_str}."})

    # Turn 5 & 6
    if call_plan["complaint_present"]:
        if "angry" in call_plan["emotion_arc"]:
            caller_msg = (
                "Yeh problem baar baar ho rahi hai! Pichli call me bhi agent ne ticket raise kiya tha but nothing happened."
                if is_hinglish else
                "This issue keeps repeating! The last agent opened a ticket but nothing was resolved."
            )
        else:
            caller_msg = (
                f"Please isko escalate karein, shaam ko kaam ruk jata hai."
                if is_hinglish else
                f"Please escalate this, it is disrupting my evening schedule."
            )
        agent_msg = (
            "Main samajh sakta hoon aapki pareshani. Maine priority ticket update kar diya hai aur technical team ko flag kiya hai."
            if is_hinglish else
            "I completely understand your concern. I have flagged this to our senior technical team on high priority."
        )
    else:
        agent_msg = (
            f"Maine aapka record check kiya hai. Aapka request note ho gaya hai: {call_plan['call_topic']}."
            if is_hinglish else
            f"I have reviewed your account records. Your request has been recorded: {call_plan['call_topic']}."
        )
        caller_msg = (
            "Theek hai, thank you. Mujhe bas yahi confirm karna tha."
            if is_hinglish else
            "All right, thank you. That is all I needed to confirm today."
        )

    turns.append({"role": "agent", "content": agent_msg})
    turns.append({"role": "caller", "content": caller_msg})

    # Turn 7 & 8
    if is_hinglish:
        turns.append({"role": "agent", "content": "Kya main aapki kisi aur cheez me sahayata kar sakta hoon?"})
        turns.append({"role": "caller", "content": "Nahi, abhi ke liye bas itna hi. Dhanyawad."})
    else:
        turns.append({"role": "agent", "content": "Is there anything else I can assist you with today?"})
        turns.append({"role": "caller", "content": "No, that will be all for now. Thank you."})

    return turns


async def generate_call_dialogue(
    persona: Dict[str, Any],
    call_plan: Dict[str, Any],
    model_name: str,
    cache: DiskCache,
) -> List[Dict[str, str]]:
    """
    Generates dialogue turns using llm_service with DiskCache.
    Falls back to deterministic rule-based dialogue if API is unavailable.
    """
    sys_prompt, user_prompt = _build_llm_prompt(persona, call_plan)
    provider = "groq"
    cache_payload = {
        "system": sys_prompt,
        "user": user_prompt,
        "temperature": 0.7,
        "model": model_name,
    }

    # Check disk cache
    cached = cache.get(provider, model_name, cache_payload)
    if cached and isinstance(cached, list) and len(cached) >= 4:
        return cached

    # Attempt LLM generation
    try:
        raw_res = await llm_service.generate(
            prompt=sys_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.7,
            max_tokens=768,
        )

        turns = _parse_dialogue_json(str(raw_res))
        if turns and len(turns) >= 4:
            cache.set(provider, model_name, cache_payload, turns)
            return turns
    except Exception:
        pass

    # Deterministic fallback
    fallback_turns = _deterministic_fallback_dialogue(persona, call_plan)
    cache.set(provider, model_name, cache_payload, fallback_turns)
    return fallback_turns


def _parse_dialogue_json(raw: str) -> List[Dict[str, str]]:
    """Parses JSON dialogue from raw LLM output."""
    cleaned = raw.strip()
    if "```json" in cleaned:
        match = re.search(r"```json\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()
    elif "```" in cleaned:
        match = re.search(r"```\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            valid_turns = []
            for item in data:
                if isinstance(item, dict) and "role" in item and "content" in item:
                    valid_turns.append({
                        "role": str(item["role"]).lower(),
                        "content": str(item["content"]).strip(),
                    })
            if len(valid_turns) >= 4:
                return valid_turns
    except Exception:
        pass

    return []


# ---------------------------------------------------------------------------
# Questions Generator (8 per caller)
# ---------------------------------------------------------------------------

def generate_questions_for_caller(
    persona: Dict[str, Any],
    calls: List[Dict[str, Any]],
    rng: random.Random,
) -> List[Dict[str, Any]]:
    """
    Generates exactly 8 questions per caller covering:
      - 2 fact_recall
      - 2 preference
      - 1 recurring_complaint_pattern
      - 1 temporal
      - 2 adversarial
    """
    caller_id = persona["caller_id"]
    name = persona["name"]
    facts = {f["category"]: f for f in persona["facts"]}
    questions: List[Dict[str, Any]] = []

    # 1. Fact Recall Question 1: plan_type
    q_idx = 1
    plan_fact = facts.get("plan_type", persona["facts"][0])
    questions.append({
        "caller_id": caller_id,
        "qid": f"{caller_id}_q{q_idx}",
        "type": "fact_recall",
        "question": f"What broadband or mobile plan type is registered for {name}?",
        "gold_answer": plan_fact["value"],
        "gold_fact_ids": [plan_fact["fact_id"]],
    })
    q_idx += 1

    # 2. Fact Recall Question 2: address_area or billing_date
    addr_fact = facts.get("address_area", persona["facts"][-1])
    questions.append({
        "caller_id": caller_id,
        "qid": f"{caller_id}_q{q_idx}",
        "type": "fact_recall",
        "question": f"Which neighborhood or address area is on record for {name}?",
        "gold_answer": addr_fact["value"],
        "gold_fact_ids": [addr_fact["fact_id"]],
    })
    q_idx += 1

    # 3. Preference Question 1: preferred_contact_time
    time_fact = facts.get("preferred_contact_time")
    if not time_fact:
        time_fact = persona["facts"][1]
    questions.append({
        "caller_id": caller_id,
        "qid": f"{caller_id}_q{q_idx}",
        "type": "preference",
        "question": f"What is {name}'s preferred contact time window?",
        "gold_answer": time_fact["value"],
        "gold_fact_ids": [time_fact["fact_id"]],
    })
    q_idx += 1

    # 4. Preference Question 2: family_preference
    family_fact = facts.get("family_preference")
    if not family_fact:
        family_fact = persona["facts"][2]
    questions.append({
        "caller_id": caller_id,
        "qid": f"{caller_id}_q{q_idx}",
        "type": "preference",
        "question": f"What family-related connectivity preference did {name} note?",
        "gold_answer": family_fact["value"],
        "gold_fact_ids": [family_fact["fact_id"]],
    })
    q_idx += 1

    # 5. Recurring Complaint Pattern Question
    complaint_fact_id = persona["recurring_complaint"]["fact_id"]
    complaint_topic = persona["recurring_complaint"]["topic"]
    questions.append({
        "caller_id": caller_id,
        "qid": f"{caller_id}_q{q_idx}",
        "type": "recurring_complaint_pattern",
        "question": f"Which topic has this caller complained about most across their calls?",
        "gold_answer": complaint_topic,
        "gold_fact_ids": [complaint_fact_id],
    })
    q_idx += 1

    # 6. Temporal Question: Most recent call
    latest_call = calls[-1]
    latest_call_topic = latest_call["call_topic"]
    questions.append({
        "caller_id": caller_id,
        "qid": f"{caller_id}_q{q_idx}",
        "type": "temporal",
        "question": f"What did the caller ask for or report in their most recent call?",
        "gold_answer": latest_call_topic,
        "gold_fact_ids": latest_call["mentioned_fact_ids"],
    })
    q_idx += 1

    # 7 & 8. Adversarial Questions (Correct answer is "unknown")
    adv_pairs = rng.sample(ADVERSARIAL_ATTRIBUTES, 2)
    for attr_name, q_text in adv_pairs:
        questions.append({
            "caller_id": caller_id,
            "qid": f"{caller_id}_q{q_idx}",
            "type": "adversarial",
            "question": q_text.replace("the caller's", f"{name}'s").replace("this caller", name),
            "gold_answer": "unknown",
            "gold_fact_ids": [],
        })
        q_idx += 1

    return questions


# ---------------------------------------------------------------------------
# Main Dataset Generation Orchestrator
# ---------------------------------------------------------------------------

async def generate_d1_dataset_async(
    config_path: Union[str, Path] = "eval/config.yaml",
    out_dir: Union[str, Path] = "eval/data/d1",
    n_callers: Optional[int] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Generates D1 synthetic caller history dataset."""
    cfg_path = Path(config_path)
    cfg: Dict[str, Any] = {}
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    # Seed selection
    if seed is None:
        configured_seeds = cfg.get("seeds")
        seed = int(configured_seeds[0]) if (configured_seeds and isinstance(configured_seeds, list)) else 42

    rng = random.Random(seed)
    n = n_callers if n_callers is not None else 60
    answer_model = cfg.get("models", {}).get("answer_model", "llama-3.3-70b-versatile")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    cache = DiskCache(cfg.get("paths", {}).get("cache_dir", ".eval_cache"))

    callers_file = out_path / "callers.jsonl"
    calls_file = out_path / "calls.jsonl"
    questions_file = out_path / "questions.jsonl"

    # Reset existing output files
    for fp in [callers_file, calls_file, questions_file]:
        if fp.exists():
            fp.unlink()

    all_callers = []
    all_calls = []
    all_questions = []

    for caller_idx in range(1, n + 1):
        persona = generate_persona(caller_idx, rng)
        append_jsonl(callers_file, persona)
        all_callers.append(persona)

        call_plans = plan_calls_for_caller(persona, rng)
        caller_calls = []

        for call_plan in call_plans:
            turns = await generate_call_dialogue(persona, call_plan, answer_model, cache)
            call_record = {
                "caller_id": persona["caller_id"],
                "call_id": call_plan["call_id"],
                "call_index": call_plan["call_index"],
                "call_topic": call_plan["call_topic"],
                "emotion_arc": call_plan["emotion_arc"],
                "complaint_present": call_plan["complaint_present"],
                "mentioned_fact_ids": call_plan["mentioned_fact_ids"],
                "turns": turns,
            }
            append_jsonl(calls_file, call_record)
            caller_calls.append(call_record)
            all_calls.append(call_record)

        questions = generate_questions_for_caller(persona, caller_calls, rng)
        for q in questions:
            append_jsonl(questions_file, q)
            all_questions.append(q)

    manifest = {
        "dataset": "D1",
        "description": "Synthetic caller histories for memory evaluation",
        "seed": seed,
        "n_callers": n,
        "total_calls": len(all_calls),
        "total_questions": len(all_questions),
        "answer_model": answer_model,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            "callers": str(callers_file),
            "calls": str(calls_file),
            "questions": str(questions_file),
        },
    }

    manifest_file = out_path / "generation_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def generate_d1_dataset(
    config_path: Union[str, Path] = "eval/config.yaml",
    out_dir: Union[str, Path] = "eval/data/d1",
    n_callers: Optional[int] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Synchronous entry point for dataset generator."""
    return asyncio.run(
        generate_d1_dataset_async(
            config_path=config_path,
            out_dir=out_dir,
            n_callers=n_callers,
            seed=seed,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Dataset D1 for VoCall Memory Evaluation")
    parser.add_argument("--config", default="eval/config.yaml", help="Path to config file")
    parser.add_argument("--out", default="eval/data/d1", help="Output directory for generated JSONL files")
    parser.add_argument("--n-callers", type=int, default=60, help="Number of callers to generate (default 60)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed override")
    args = parser.parse_args()

    manifest = generate_d1_dataset(
        config_path=args.config,
        out_dir=args.out,
        n_callers=args.n_callers,
        seed=args.seed,
    )
    print(f"Dataset D1 generated successfully!")
    print(f"Callers: {manifest['n_callers']} | Calls: {manifest['total_calls']} | Questions: {manifest['total_questions']}")
    print(f"Output files stored in {args.out}")


if __name__ == "__main__":
    main()
