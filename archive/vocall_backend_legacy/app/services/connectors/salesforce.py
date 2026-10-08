from typing import Any, Dict, Optional
import httpx


async def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    instance_url: str = "https://login.salesforce.com",
) -> str:
    """
    Uses the Salesforce OAuth2 token refresh endpoint to obtain a fresh access token.
    """
    token_url = (
        f"{instance_url.rstrip('/')}/services/oauth2/token"
        if ("login.salesforce.com" in instance_url or "test.salesforce.com" in instance_url)
        else "https://login.salesforce.com/services/oauth2/token"
    )

    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(token_url, data=data)
        res.raise_for_status()
        token_data = res.json()
        return token_data["access_token"]


async def sync_call_result(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    instance_url: str,
    contact_phone: str,
    call_summary: str,
    disposition: str,
    emotion_score: float,
) -> Dict[str, Any]:
    """
    Post Call connector function to sync call results to Salesforce.
    1. Refreshes the access token.
    2. Searches for a Contact by phone number.
    3. If found, logs a Task linked to Contact.
    4. If not found, creates a Lead and logs Task linked to Lead.
    Returns {"success": True, "record_id": "..."} or {"success": False, "error": "..."}.
    """
    try:
        instance_url_clean = instance_url.rstrip("/")
        access_token = await refresh_access_token(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            instance_url=instance_url_clean,
        )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            # Helper function for executing requests with 401 token refresh retry
            async def execute_request(method: str, url: str, **kwargs):
                nonlocal access_token, headers
                req_headers = kwargs.pop("headers", headers)
                res = await client.request(method, url, headers=req_headers, **kwargs)
                if res.status_code == 401:
                    # Token expired: refresh token and retry once
                    access_token = await refresh_access_token(
                        client_id=client_id,
                        client_secret=client_secret,
                        refresh_token=refresh_token,
                        instance_url=instance_url_clean,
                    )
                    headers["Authorization"] = f"Bearer {access_token}"
                    res = await client.request(method, url, headers=headers, **kwargs)
                return res

            # 2. SOQL query to find Contact by Phone or MobilePhone
            soql_query = f"SELECT Id FROM Contact WHERE Phone = '{contact_phone}' OR MobilePhone = '{contact_phone}'"
            query_url = f"{instance_url_clean}/services/data/v58.0/query/?q={soql_query}"

            query_res = await execute_request("GET", query_url)
            target_id = None
            target_type = None

            if query_res.status_code == 200:
                records = query_res.json().get("records", [])
                if records:
                    target_id = records[0].get("Id")
                    target_type = "Contact"

            # 3. If contact not found, create a new Lead
            if not target_id:
                lead_url = f"{instance_url_clean}/services/data/v58.0/sobjects/Lead/"
                lead_payload = {
                    "LastName": f"Call Lead {contact_phone}",
                    "Company": "VoCall Inbound Call",
                    "Phone": contact_phone,
                }
                lead_res = await execute_request("POST", lead_url, json=lead_payload)
                if lead_res.status_code in (200, 201):
                    target_id = lead_res.json().get("id")
                    target_type = "Lead"
                else:
                    return {
                        "success": False,
                        "error": f"Failed to create Lead in Salesforce: {lead_res.text}",
                    }

            # 4. Create Task record linked to target_id (WhoId)
            task_url = f"{instance_url_clean}/services/data/v58.0/sobjects/Task/"
            task_payload = {
                "Subject": "VoCall Completed",
                "Description": f"{call_summary}\n\nEmotion Score: {emotion_score}",
                "CallDisposition": disposition,
                "Emotion_Score__c": emotion_score,
                "WhoId": target_id,
                "Status": "Completed",
            }

            task_res = await execute_request("POST", task_url, json=task_payload)

            # If Emotion_Score__c custom field does not exist in Salesforce org, retry without it
            if task_res.status_code == 400 and "Emotion_Score__c" in task_res.text:
                task_payload.pop("Emotion_Score__c")
                task_res = await execute_request("POST", task_url, json=task_payload)

            if task_res.status_code in (200, 201):
                task_id = task_res.json().get("id")
                return {
                    "success": True,
                    "record_id": str(task_id),
                    "target_id": str(target_id),
                    "target_type": target_type,
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to create Task in Salesforce: {task_res.text}",
                }

    except Exception as e:
        return {"success": False, "error": str(e)}
