import os
from typing import Any, Dict
import httpx

SLACK_API_BASE = "https://slack.com/api"


def _get_vocall_base_url() -> str:
    return os.environ.get("VOCALL_BASE_URL", "https://app.vocall.ai").rstrip("/")


async def send_frustration_alert(
    bot_token: str,
    channel_id: str,
    agent_name: str,
    contact_name: str,
    contact_phone: str,
    call_id: str,
    frustration_score: float,
    last_transcript_line: str,
) -> Dict[str, Any]:
    """
    Posts a rich Slack Block Kit high frustration alert message during a call.
    Returns {"success": True, "ts": "..."} or {"success": False, "error": "..."}.
    """
    try:
        vocall_base_url = _get_vocall_base_url()
        call_url = f"{vocall_base_url}/dashboard/calls/{call_id}"
        score_pct = f"{int(frustration_score * 100)}%" if frustration_score <= 1.0 else f"{int(frustration_score)}%"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🔴 High Frustration Alert — {agent_name}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Contact:*\n{contact_name}"},
                    {"type": "mrkdwn", "text": f"*Phone:*\n{contact_phone}"},
                    {"type": "mrkdwn", "text": f"*Frustration Score:*\n{score_pct}"},
                    {"type": "mrkdwn", "text": f"*Call ID:*\n`{call_id}`"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f">*Last Caller Speech:*\n> \"{last_transcript_line}\"",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Call Details"},
                        "url": call_url,
                        "style": "danger",
                    }
                ],
            },
        ]

        payload = {
            "channel": channel_id,
            "text": f"🔴 High Frustration Alert for call {call_id} ({score_pct})",
            "blocks": blocks,
        }

        headers = {
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"{SLACK_API_BASE}/chat.postMessage", json=payload, headers=headers
            )
            res.raise_for_status()
            data = res.json()

            if data.get("ok"):
                return {"success": True, "ts": data.get("ts")}
            else:
                return {
                    "success": False,
                    "error": data.get("error", "Unknown Slack API error"),
                }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def send_call_summary(
    bot_token: str,
    channel_id: str,
    agent_name: str,
    contact_name: str,
    call_summary: str,
    emotion_score: float,
    duration_seconds: int,
    call_id: str,
) -> Dict[str, Any]:
    """
    Posts a post-call summary Slack Block Kit message.
    Includes: agent, contact, duration, emotion score (colored emoji), summary, link to call detail.
    Returns {"success": True, "ts": "..."} or {"success": False, "error": "..."}.
    """
    try:
        vocall_base_url = _get_vocall_base_url()
        call_url = f"{vocall_base_url}/dashboard/calls/{call_id}"
        emotion_emoji = "🟢" if emotion_score >= 0 else "🔴"

        minutes = duration_seconds // 60
        seconds = duration_seconds % 60
        duration_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📞 Call Summary — {agent_name}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Agent:*\n{agent_name}"},
                    {"type": "mrkdwn", "text": f"*Contact:*\n{contact_name}"},
                    {"type": "mrkdwn", "text": f"*Duration:*\n{duration_str}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Emotion Score:*\n{emotion_emoji} {emotion_score:+.2f}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Call Summary:*\n{call_summary}",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Call Details"},
                        "url": call_url,
                    }
                ],
            },
        ]

        payload = {
            "channel": channel_id,
            "text": f"📞 Call Summary — {agent_name} with {contact_name}",
            "blocks": blocks,
        }

        headers = {
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"{SLACK_API_BASE}/chat.postMessage", json=payload, headers=headers
            )
            res.raise_for_status()
            data = res.json()

            if data.get("ok"):
                return {"success": True, "ts": data.get("ts")}
            else:
                return {
                    "success": False,
                    "error": data.get("error", "Unknown Slack API error"),
                }

    except Exception as e:
        return {"success": False, "error": str(e)}
