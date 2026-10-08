import json
from typing import Any, Dict, Optional
import httpx

DURING_CALL_TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "fire_webhook",
            "description": "Trigger a custom HTTP webhook during a call with key-value payload data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Destination Webhook URL.",
                    },
                    "payload": {
                        "type": "object",
                        "description": "Key-value pairs to send in the webhook body.",
                    },
                },
                "required": ["url", "payload"],
            },
        },
    }
]


async def fire_webhook(
    url: str,
    method: str = "POST",
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes an async HTTP request to a webhook endpoint using httpx. Timeout = 10s.
    Returns {"success": True, "status_code": int, "response_body": str} or {"success": False, "error": "..."}.
    """
    try:
        http_method = (method or "POST").upper()
        req_headers = {"Content-Type": "application/json"}
        if headers:
            if isinstance(headers, str):
                try:
                    parsed = json.loads(headers)
                    req_headers.update(parsed)
                except Exception:
                    pass
            elif isinstance(headers, dict):
                req_headers.update(headers)

        async with httpx.AsyncClient(timeout=10.0) as client:
            if http_method == "GET":
                params = payload if isinstance(payload, dict) else None
                res = await client.get(url, headers=req_headers, params=params)
            elif http_method in ("POST", "PUT", "PATCH", "DELETE"):
                if isinstance(payload, str):
                    res = await client.request(
                        http_method, url, headers=req_headers, content=payload
                    )
                else:
                    res = await client.request(
                        http_method, url, headers=req_headers, json=payload
                    )
            else:
                res = await client.request(
                    http_method, url, headers=req_headers, json=payload
                )

            if res.status_code < 400:
                return {
                    "success": True,
                    "status_code": res.status_code,
                    "response_body": res.text,
                }
            else:
                return {
                    "success": False,
                    "status_code": res.status_code,
                    "response_body": res.text,
                    "error": f"HTTP {res.status_code}: {res.text[:200]}",
                }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def fire_post_call_webhook(
    url: str,
    method: str = "POST",
    headers: Optional[Dict[str, str]] = None,
    payload_template: Optional[str] = None,
    call_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Fires a post-call webhook (Zapier or Custom Webhook).
    If payload_template is provided, substitutes variables from call_data.
    If payload_template is None, sends call_data directly as JSON (respecting include_transcript/include_emotion).
    Returns {"success": True, "status_code": int} or {"success": False, "error": "..."}.
    """
    try:
        data = call_data or {}
        payload_to_send: Any = None

        if payload_template and payload_template.strip():
            template_vars = {
                "call_id": str(data.get("call_id", "")),
                "contact_phone": str(data.get("contact_phone", "")),
                "contact_name": str(data.get("contact_name", "")),
                "agent_name": str(data.get("agent_name", "")),
                "call_summary": str(data.get("call_summary", "")),
                "emotion_score": str(data.get("emotion_score", "")),
                "duration_seconds": str(data.get("duration_seconds", "")),
                "transcript": json.dumps(data.get("transcript", [])),
                "structured_data": json.dumps(data.get("structured_data", {})),
            }

            rendered_str = payload_template
            for var_key, var_val in template_vars.items():
                rendered_str = rendered_str.replace(f"{{{var_key}}}", var_val)

            try:
                payload_to_send = json.loads(rendered_str)
            except Exception:
                payload_to_send = rendered_str

        else:
            # Build payload directly from call_data
            payload_dict = dict(data)
            include_transcript = payload_dict.pop("include_transcript", True)
            include_emotion = payload_dict.pop("include_emotion", True)

            if not include_transcript and "transcript" in payload_dict:
                payload_dict.pop("transcript")
            if not include_emotion and "emotion_score" in payload_dict:
                payload_dict.pop("emotion_score")

            payload_to_send = payload_dict

        result = await fire_webhook(
            url=url, method=method, headers=headers, payload=payload_to_send
        )

        if result.get("success"):
            return {
                "success": True,
                "status_code": result.get("status_code", 200),
            }
        else:
            return {
                "success": False,
                "status_code": result.get("status_code"),
                "error": result.get("error", "Webhook delivery failed."),
            }

    except Exception as e:
        return {"success": False, "error": str(e)}
