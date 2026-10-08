import json
import os
from typing import Any, Dict, Literal, Union
from uuid import UUID
import httpx

try:
    from app.services.supabase_client import get_supabase_client
except ImportError:
    try:
        from vocall.backend.app.services.supabase_client import get_supabase_client
    except ImportError:
        get_supabase_client = None


def _format_e164(phone: str) -> str:
    """Formats phone number into standard E.164 string."""
    raw = phone.replace("whatsapp:", "")
    digits = "".join(c for c in raw if c.isdigit() or c == "+")
    if not digits.startswith("+"):
        digits = "+" + digits
    return digits


async def _get_telephony_credentials(org_id: Union[str, UUID], provider: str) -> Dict[str, str]:
    """Look up telephony API credentials from connector_configs or environment variables."""
    # 1. Supabase connector_configs lookup
    if get_supabase_client:
        try:
            sb = get_supabase_client()
            res = (
                sb.table("connector_configs")
                .select("config")
                .eq("org_id", str(org_id))
                .eq("connector_type", provider)
                .execute()
            )
            if res.data and len(res.data) > 0:
                config = res.data[0].get("config", {})
                if config:
                    return config
        except Exception:
            pass

        try:
            sb = get_supabase_client()
            res = (
                sb.table("api_keys")
                .select("*")
                .eq("org_id", str(org_id))
                .eq("provider", provider)
                .execute()
            )
            if res.data and len(res.data) > 0:
                row = res.data[0]
                enc_key = row.get("encrypted_key", "")
                if enc_key.startswith("{"):
                    return json.loads(enc_key)
                else:
                    return {"auth_token": enc_key, "account_sid": enc_key}
        except Exception:
            pass

    # 2. Environment variable fallbacks
    if provider == "twilio":
        sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        if sid and token:
            return {"account_sid": sid, "auth_token": token}
    elif provider == "plivo":
        auth_id = os.environ.get("PLIVO_AUTH_ID", "")
        token = os.environ.get("PLIVO_AUTH_TOKEN", "")
        if auth_id and token:
            return {"auth_id": auth_id, "auth_token": token}

    return {}


async def send_summary(
    provider: Literal["twilio", "plivo"],
    from_number: str,
    to_number: str,
    message_template: str,
    call_summary: str,
    agent_name: str,
    contact_name: str,
    emotion_score: float,
    org_id: Union[str, UUID],
) -> Dict[str, Any]:
    """
    Post Call connector to send a WhatsApp call summary message via Twilio or Plivo.
    Returns {"success": True, "message_sid": "..."} or {"success": False, "error": "..."}.
    """
    try:
        # Compute emotion label
        if emotion_score > 0.3:
            emotion_label = "satisfied"
        elif emotion_score > -0.3:
            emotion_label = "neutral"
        else:
            emotion_label = "frustrated"

        # Substitute template placeholders
        message_body = message_template.format(
            contact_name=contact_name,
            agent_name=agent_name,
            call_summary=call_summary,
            emotion_score=f"{emotion_score:.2f}",
            emotion_label=emotion_label,
        )

        formatted_to = _format_e164(to_number)
        formatted_from = _format_e164(from_number)

        # Fetch credentials for the org
        credentials = await _get_telephony_credentials(org_id, provider)

        async with httpx.AsyncClient(timeout=15.0) as client:
            if provider == "twilio":
                account_sid = credentials.get("account_sid")
                auth_token = credentials.get("auth_token")

                if not account_sid or not auth_token:
                    return {
                        "success": False,
                        "error": f"Twilio credentials (account_sid, auth_token) not found for org {org_id}.",
                    }

                url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

                from_wa = f"whatsapp:{formatted_from}" if not formatted_from.startswith("whatsapp:") else formatted_from
                to_wa = f"whatsapp:{formatted_to}" if not formatted_to.startswith("whatsapp:") else formatted_to

                data = {
                    "From": from_wa,
                    "To": to_wa,
                    "Body": message_body,
                }

                res = await client.post(url, data=data, auth=(account_sid, auth_token))
                res_data = res.json()

                if res.status_code in (200, 201):
                    return {
                        "success": True,
                        "message_sid": res_data.get("sid", res_data.get("id")),
                    }
                else:
                    return {
                        "success": False,
                        "error": res_data.get("message", res.text),
                    }

            elif provider == "plivo":
                auth_id = credentials.get("auth_id") or credentials.get("account_sid")
                auth_token = credentials.get("auth_token")

                if not auth_id or not auth_token:
                    return {
                        "success": False,
                        "error": f"Plivo credentials (auth_id, auth_token) not found for org {org_id}.",
                    }

                url = f"https://api.plivo.com/v1/Account/{auth_id}/Message/"

                payload = {
                    "src": formatted_from,
                    "dst": formatted_to,
                    "text": message_body,
                    "type": "whatsapp",
                }

                res = await client.post(url, json=payload, auth=(auth_id, auth_token))
                res_data = res.json()

                if res.status_code in (200, 201, 202):
                    msg_uuids = res_data.get("message_uuid", [])
                    msg_sid = msg_uuids[0] if msg_uuids else res_data.get("id", "plivo_msg")
                    return {"success": True, "message_sid": msg_sid}
                else:
                    return {
                        "success": False,
                        "error": res_data.get("error", res.text),
                    }

            else:
                return {
                    "success": False,
                    "error": f"Unsupported WhatsApp provider: '{provider}'.",
                }

    except Exception as e:
        return {"success": False, "error": str(e)}
