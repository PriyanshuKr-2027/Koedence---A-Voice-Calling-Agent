"""
VoCall Email Service (Resend API).

Sends post-call summary reports and system notifications.
"""

from datetime import datetime, timezone
import logging
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_post_call_email(
    agent: Dict[str, Any],
    call_id: str,
    analysis: Dict[str, Any],
    recipient_email: Optional[str] = None,
) -> bool:
    """
    Sends a post-call summary report email using Resend API.
    Guarded by calls.post_steps to prevent duplicate dispatch.
    """
    if call_id:
        try:
            from app.services.supabase_client import supabase
            if supabase:
                call_res = supabase.table("calls").select("post_steps").eq("id", str(call_id)).limit(1).execute()
                if call_res.data and len(call_res.data) > 0:
                    steps = call_res.data[0].get("post_steps") or {}
                    if isinstance(steps, dict) and steps.get("email"):
                        logger.info("Email already sent for call_id=%s; skipping duplicate send", call_id)
                        return True
        except Exception as exc:
            logger.warning("Failed checking email step marker for call %s: %s", call_id, exc)

    resend_key = settings.RESEND_API_KEY
    if not resend_key:
        logger.warning("RESEND_API_KEY not configured — skipping post-call email")
        return False

    agent_name = agent.get("name", "VoCall AI Agent")
    recipient = recipient_email or agent.get("notification_email") or agent.get("owner_email")
    if not recipient:
        logger.info("No notification email specified for agent %s — skipping email", agent.get("id"))
        return False

    summary = analysis.get("summary", "No summary available.")
    sentiment = analysis.get("sentiment", "Neutral")
    action_items = analysis.get("action_items", [])
    user_intent = analysis.get("user_intent", "General inquiry")

    action_items_html = (
        "".join([f"<li>{item}</li>" for item in action_items])
        if action_items
        else "<li>None</li>"
    )

    html_content = f"""
    <h2>Call Analysis Report — Call #{call_id[:8]}</h2>
    <p><strong>Agent:</strong> {agent_name}</p>
    <p><strong>Summary:</strong> {summary}</p>
    <p><strong>Sentiment:</strong> {sentiment}</p>
    <p><strong>User Intent:</strong> {user_intent}</p>
    <h3>Action Items:</h3>
    <ul>
      {action_items_html}
    </ul>
    <hr/>
    <p><small>Sent automatically by VoCall Voice Engine</small></p>
    """

    try:
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {resend_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": "VoCall <notifications@vocall.ai>",
            "to": [recipient],
            "subject": f"Post-Call Summary Report — #{call_id[:8]} ({agent_name})",
            "html": html_content,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info("Sent post-call summary email for call %s to %s", call_id, recipient)
            if call_id:
                try:
                    from app.services.supabase_client import supabase
                    if supabase:
                        call_res = supabase.table("calls").select("post_steps").eq("id", str(call_id)).limit(1).execute()
                        c_steps = {}
                        if call_res.data and len(call_res.data) > 0:
                            c_steps = call_res.data[0].get("post_steps") or {}
                            if not isinstance(c_steps, dict):
                                c_steps = {}
                        c_steps["email"] = datetime.now(timezone.utc).isoformat()
                        supabase.table("calls").update({"post_steps": c_steps}).eq("id", str(call_id)).execute()
                except Exception as exc:
                    logger.warning("Failed recording email step marker for call %s: %s", call_id, exc)
            return True

    except Exception as exc:
        logger.error("Failed to send post-call email for call %s: %s", call_id, exc)
        return False
