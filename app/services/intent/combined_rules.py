"""
Combined Rules Engine (M40)
Emotion × Intent simultaneous signal evaluation engine.
"""

import logging
from typing import Any, Dict, List, Optional

from app.services.emotion.mapping import map_to_canonical_emotion

logger = logging.getLogger(__name__)

SYSTEM_COMBINED_RULES: List[Dict[str, Any]] = [
    {
        "id": "refund_frustrated",
        "intent": "request_refund",
        "emotion_condition": {"valence_lt": -0.5},
        "action": "human_handoff",
        "instruction": """This caller is requesting a refund AND is highly frustrated. 
Escalate immediately. Do not attempt to resolve yourself. 
Acknowledge both the frustration and the refund request before transferring.""",
        "skip_llm_response": False,
    },
    {
        "id": "speak_to_human_angry",
        "intent": "speak_to_human",
        "emotion_condition": {"dominant_in": ["angry", "frustrated"]},
        "action": "human_handoff",
        "instruction": "Transfer immediately to a human agent without attempting to resolve.",
        "skip_llm_response": True,
    },
    {
        "id": "appointment_positive",
        "intent": "book_appointment",
        "emotion_condition": {"valence_gt": 0.4},
        "action": "none",
        "instruction": """Caller is in a positive mood and ready to commit. 
Confirm the appointment details confidently and move to booking immediately.""",
        "skip_llm_response": False,
    },
]


def evaluate(
    emotion_state: Dict[str, Any],
    intent_state: Dict[str, Any],
    agent_combined_rules: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Check all combined rules (system + agent-defined) against current turn state.
    Returns the first matching rule's action dict, or None if no rule matches.
    """
    if not intent_state or not intent_state.get("intent"):
        return None

    all_rules = SYSTEM_COMBINED_RULES + (agent_combined_rules or [])

    detected_intent = intent_state.get("intent")
    confidence = float(intent_state.get("confidence", 0.0))

    for rule in all_rules:
        if not isinstance(rule, dict):
            continue

        rule_intent = rule.get("intent")
        if rule_intent and rule_intent != detected_intent:
            continue

        # Check confidence threshold
        min_confidence = float(rule.get("min_confidence", 0.65))
        if confidence < min_confidence:
            continue

        emotion_cond = rule.get("emotion_condition", {})
        if not check_emotion_condition(emotion_state, emotion_cond):
            continue

        return {
            "rule_matched": rule.get("id", "custom_rule"),
            "intent": detected_intent,
            "action": rule.get("action", "none"),
            "instruction": rule.get("instruction", ""),
            "skip_llm_response": bool(rule.get("skip_llm_response", False)),
        }

    return None


def check_emotion_condition(emotion_state: Dict[str, Any], condition: Dict[str, Any]) -> bool:
    """
    Evaluates emotion condition rules:
    - valence_lt: float
    - valence_gt: float
    - arousal_gt: float
    - arousal_lt: float
    - dominant_in: list of strings
    """
    if not condition:
        return True

    if not emotion_state:
        return False

    valence = float(
        emotion_state.get("valence_fused")
        if "valence_fused" in emotion_state
        else emotion_state.get("valence", 0.0)
    )
    arousal = float(
        emotion_state.get("arousal_fused")
        if "arousal_fused" in emotion_state
        else emotion_state.get("arousal", 0.5)
    )
    dominant = map_to_canonical_emotion(
        str(
            emotion_state.get("dominant_fused")
            if "dominant_fused" in emotion_state
            else emotion_state.get("dominant", "neutral")
        )
    )

    if "valence_lt" in condition and valence >= float(condition["valence_lt"]):
        return False

    if "valence_gt" in condition and valence <= float(condition["valence_gt"]):
        return False

    if "arousal_gt" in condition and arousal <= float(condition["arousal_gt"]):
        return False

    if "arousal_lt" in condition and arousal >= float(condition["arousal_lt"]):
        return False

    if "dominant_in" in condition:
        allowed = [map_to_canonical_emotion(str(d)) for d in condition["dominant_in"]]
        if dominant not in allowed:
            return False

    return True
