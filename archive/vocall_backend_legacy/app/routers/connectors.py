import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
import httpx

from app.models.connectors import (
    ConnectorConfigCreate,
    ConnectorConfigResponse,
    ConnectorConfigUpdate,
    ConnectorType,
)
from app.routers.auth import get_current_user
from app.utils.encryption import decrypt_dict, encrypt_dict

try:
    from app.services.supabase_client import get_supabase_client
except ImportError:
    try:
        from vocall.backend.app.services.supabase_client import get_supabase_client
    except ImportError:
        get_supabase_client = None

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


def _safe_get_supabase_client():
    if not get_supabase_client:
        return None
    try:
        return get_supabase_client()
    except Exception:
        return None


def _format_connector_response(row: Dict[str, Any]) -> Dict[str, Any]:
    raw_config = row.get("config") or {}
    decrypted_config = decrypt_dict(raw_config)

    created_at = row.get("created_at")
    updated_at = row.get("updated_at")

    if isinstance(created_at, str):
        created_at_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    else:
        created_at_dt = created_at or datetime.now(timezone.utc)

    if isinstance(updated_at, str):
        updated_at_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    else:
        updated_at_dt = updated_at or datetime.now(timezone.utc)

    return {
        "id": row.get("id"),
        "org_id": row.get("org_id"),
        "agent_id": row.get("agent_id"),
        "connector_type": row.get("connector_type"),
        "is_enabled": row.get("is_enabled", False),
        "config": decrypted_config,
        "created_at": created_at_dt,
        "updated_at": updated_at_dt,
    }


async def _test_connector_connectivity(
    connector_type: str, config: Dict[str, Any]
) -> Dict[str, Any]:
    try:
        if connector_type == "google_calendar":
            creds_json = config.get("credentials_json", "")
            if not creds_json:
                return {"success": False, "error": "Missing credentials_json in configuration"}
            from app.services.connectors.google_cal import _get_calendar_service

            service = await asyncio.to_thread(_get_calendar_service, creds_json)
            await asyncio.to_thread(service.calendarList().list(maxResults=1).execute)
            return {"success": True, "message": "Connected to Google Calendar API successfully"}

        elif connector_type == "hubspot":
            access_token = config.get("access_token", "")
            if not access_token:
                return {"success": False, "error": "Missing access_token in configuration"}
            headers = {"Authorization": f"Bearer {access_token}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    "https://api.hubapi.com/crm/v3/objects/contacts?limit=1", headers=headers
                )
                if res.status_code < 400:
                    return {"success": True, "message": "Connected to HubSpot API successfully"}
                else:
                    return {
                        "success": False,
                        "error": f"HubSpot API error HTTP {res.status_code}: {res.text[:200]}",
                    }

        elif connector_type == "salesforce":
            client_id = config.get("client_id", "")
            client_secret = config.get("client_secret", "")
            refresh_token = config.get("refresh_token", "")
            instance_url = config.get("instance_url", "")
            if not (client_id and client_secret and refresh_token and instance_url):
                return {
                    "success": False,
                    "error": "Missing Salesforce credentials (client_id, client_secret, refresh_token, instance_url)",
                }
            from app.services.connectors.salesforce import refresh_access_token

            access_token = await refresh_access_token(
                client_id, client_secret, refresh_token, instance_url
            )
            headers = {"Authorization": f"Bearer {access_token}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                query_url = f"{instance_url.rstrip('/')}/services/data/v58.0/query/?q=SELECT+Id+FROM+Contact+LIMIT+1"
                res = await client.get(query_url, headers=headers)
                if res.status_code < 400:
                    return {"success": True, "message": "Connected to Salesforce API successfully"}
                else:
                    return {
                        "success": False,
                        "error": f"Salesforce API error HTTP {res.status_code}: {res.text[:200]}",
                    }

        elif connector_type == "supabase":
            url = config.get("url", "")
            anon_key = config.get("anon_key", "")
            table_name = config.get("table_name", "")
            if not (url and anon_key):
                return {"success": False, "error": "Missing Supabase URL or anon_key"}
            headers = {"apikey": anon_key, "Authorization": f"Bearer {anon_key}"}
            endpoint = (
                f"{url.rstrip('/')}/rest/v1/{table_name}?limit=1"
                if table_name
                else f"{url.rstrip('/')}/rest/v1/"
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(endpoint, headers=headers)
                if res.status_code < 400:
                    return {"success": True, "message": "Connected to Supabase REST API successfully"}
                else:
                    return {
                        "success": False,
                        "error": f"Supabase API error HTTP {res.status_code}: {res.text[:200]}",
                    }

        elif connector_type == "postgres":
            conn_str = config.get("connection_string", "")
            if not conn_str:
                return {"success": False, "error": "Missing connection_string in configuration"}
            import asyncpg

            conn = await asyncpg.connect(conn_str, timeout=10.0)
            await conn.fetchval("SELECT 1")
            await conn.close()
            return {"success": True, "message": "Connected to PostgreSQL database successfully"}

        elif connector_type == "slack":
            bot_token = config.get("bot_token", "")
            if not bot_token:
                return {"success": False, "error": "Missing bot_token in configuration"}
            headers = {"Authorization": f"Bearer {bot_token}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post("https://slack.com/api/auth.test", headers=headers)
                data = res.json()
                if data.get("ok"):
                    return {
                        "success": True,
                        "message": f"Connected to Slack as bot '{data.get('user')}'",
                    }
                else:
                    return {"success": False, "error": f"Slack Auth Test failed: {data.get('error')}"}

        elif connector_type == "whatsapp":
            provider = config.get("provider", "twilio")
            from_number = config.get("from_number", "")
            if not from_number:
                return {"success": False, "error": "Missing from_number in configuration"}
            from app.services.connectors.whatsapp import _format_e164

            formatted = _format_e164(from_number)
            return {
                "success": True,
                "message": f"Validated WhatsApp configuration for provider '{provider}' and number '{formatted}'",
            }

        elif connector_type in ("zapier", "custom_webhook"):
            url = config.get("webhook_url") or config.get("url")
            if not url:
                return {"success": False, "error": "Missing webhook URL in configuration"}
            from app.services.connectors.webhook import fire_webhook

            headers = config.get("headers", {})
            res = await fire_webhook(
                url=url, method="POST", headers=headers, payload={"test": True}
            )
            if res.get("success"):
                return {
                    "success": True,
                    "message": f"Webhook test sent successfully (HTTP {res.get('status_code')})",
                }
            else:
                return {
                    "success": False,
                    "error": res.get("error", "Webhook delivery test failed"),
                }

        else:
            return {"success": False, "error": f"Unknown connector type '{connector_type}'"}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("", response_model=List[ConnectorConfigResponse])
async def list_connectors(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns all connector_configs for the current user's org.
    """
    org_id = current_user.get("org_id")
    sb = _safe_get_supabase_client()
    if not sb:
        return []

    res = sb.table("connector_configs").select("*").eq("org_id", str(org_id)).execute()

    results = []
    for row in res.data or []:
        results.append(_format_connector_response(row))
    return results


@router.get("/{connector_type}", response_model=ConnectorConfigResponse)
async def get_connector(
    connector_type: str,
    agent_id: Optional[UUID] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Returns the config for a specific connector type for current org.
    If agent_id query param is provided, returns agent-level override if exists, else falls back to org-level.
    """
    org_id = current_user.get("org_id")
    sb = _safe_get_supabase_client()
    if not sb:
        raise HTTPException(status_code=500, detail="Database client unavailable")

    # 1. Try agent-level if agent_id provided
    if agent_id:
        agent_res = (
            sb.table("connector_configs")
            .select("*")
            .eq("org_id", str(org_id))
            .eq("connector_type", connector_type)
            .eq("agent_id", str(agent_id))
            .execute()
        )
        if agent_res.data and len(agent_res.data) > 0:
            return _format_connector_response(agent_res.data[0])

    # 2. Fall back to org-level config
    org_res = (
        sb.table("connector_configs")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("connector_type", connector_type)
        .is_("agent_id", "null")
        .execute()
    )
    if org_res.data and len(org_res.data) > 0:
        return _format_connector_response(org_res.data[0])

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Connector configuration '{connector_type}' not found for org",
    )


@router.post("/{connector_type}", response_model=ConnectorConfigResponse)
async def upsert_connector(
    connector_type: str,
    payload: ConnectorConfigCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Creates or updates (upsert) the connector config for the org.
    Encrypts the `config` JSONB using AES-256 before storing.
    """
    org_id = current_user.get("org_id")
    sb = _safe_get_supabase_client()
    if not sb:
        raise HTTPException(status_code=500, detail="Database client unavailable")

    encrypted_str = encrypt_dict(payload.config)

    record = {
        "org_id": str(org_id),
        "agent_id": str(payload.agent_id) if payload.agent_id else None,
        "connector_type": connector_type,
        "is_enabled": payload.is_enabled,
        "config": {"encrypted": encrypted_str},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    res = (
        sb.table("connector_configs")
        .upsert(record, on_conflict="org_id,agent_id,connector_type")
        .execute()
    )

    if not res.data:
        # Retry with direct select/update if upsert returns empty
        query = (
            sb.table("connector_configs")
            .select("*")
            .eq("org_id", str(org_id))
            .eq("connector_type", connector_type)
        )
        if payload.agent_id:
            query = query.eq("agent_id", str(payload.agent_id))
        else:
            query = query.is_("agent_id", "null")

        existing = query.execute()
        if existing.data and len(existing.data) > 0:
            up_res = (
                sb.table("connector_configs")
                .update(record)
                .eq("id", existing.data[0]["id"])
                .execute()
            )
            data_row = up_res.data[0] if up_res.data else existing.data[0]
        else:
            ins_res = sb.table("connector_configs").insert(record).execute()
            data_row = ins_res.data[0] if ins_res.data else record
    else:
        data_row = res.data[0]

    return _format_connector_response(data_row)


@router.delete("/{connector_type}")
async def delete_connector(
    connector_type: str,
    agent_id: Optional[UUID] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Soft-deletes connector config by setting is_enabled = False and clearing config to {}.
    """
    org_id = current_user.get("org_id")
    sb = _safe_get_supabase_client()
    if not sb:
        raise HTTPException(status_code=500, detail="Database client unavailable")

    query = (
        sb.table("connector_configs")
        .update({"is_enabled": False, "config": {}})
        .eq("org_id", str(org_id))
        .eq("connector_type", connector_type)
    )

    if agent_id:
        query = query.eq("agent_id", str(agent_id))
    else:
        query = query.is_("agent_id", "null")

    res = query.execute()

    return {
        "message": f"Connector '{connector_type}' disabled and configuration cleared.",
        "connector_type": connector_type,
    }


@router.post("/{connector_type}/test")
async def test_connector(
    connector_type: str,
    agent_id: Optional[UUID] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Runs a quick connectivity test for the connector using stored config.
    Returns {"success": True, "message": "Connected"} or {"success": False, "error": "..."}.
    """
    org_id = current_user.get("org_id")
    config: Dict[str, Any] = {}

    sb = _safe_get_supabase_client()
    if sb:
        query = (
            sb.table("connector_configs")
            .select("*")
            .eq("org_id", str(org_id))
            .eq("connector_type", connector_type)
        )
        if agent_id:
            query = query.eq("agent_id", str(agent_id))

        res = query.execute()
        if res.data and len(res.data) > 0:
            config = decrypt_dict(res.data[0].get("config", {}))

    return await _test_connector_connectivity(connector_type, config)
