from typing import Any, Dict, Optional
import httpx

BASE_URL = "https://api.hubapi.com"

TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "log_lead",
            "description": "Create a HubSpot contact and deal for a new lead captured during a call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "access_token": {
                        "type": "string",
                        "description": "HubSpot Private App access token.",
                    },
                    "pipeline_id": {
                        "type": "string",
                        "description": "HubSpot Deal Pipeline ID.",
                    },
                    "deal_stage_id": {
                        "type": "string",
                        "description": "HubSpot Deal Stage ID.",
                    },
                    "contact_name": {
                        "type": "string",
                        "description": "Full name of the contact/lead.",
                    },
                    "contact_phone": {
                        "type": "string",
                        "description": "Phone number of the contact/lead.",
                    },
                    "contact_email": {
                        "type": "string",
                        "description": "Optional email address of the contact/lead.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notes or deal description captured from the call.",
                    },
                },
                "required": [
                    "access_token",
                    "pipeline_id",
                    "deal_stage_id",
                    "contact_name",
                    "contact_phone",
                ],
            },
        },
    }
]


async def log_lead(
    access_token: str,
    pipeline_id: str,
    deal_stage_id: str,
    contact_name: str,
    contact_phone: str,
    contact_email: Optional[str] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """
    During Call function to create a HubSpot Contact and Deal.
    Returns {"success": True, "contact_id": "...", "deal_id": "..."} or {"success": False, "error": "..."}.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Create or Find Contact
            contact_payload = {
                "properties": {
                    "firstname": contact_name,
                    "phone": contact_phone,
                }
            }
            if contact_email:
                contact_payload["properties"]["email"] = contact_email

            contact_res = await client.post(
                f"{BASE_URL}/crm/v3/objects/contacts",
                json=contact_payload,
                headers=headers,
            )

            contact_id = None
            if contact_res.status_code in (200, 201):
                contact_id = contact_res.json().get("id")
            elif contact_res.status_code == 409:
                # Contact already exists, search by phone
                search_payload = {
                    "filterGroups": [
                        {
                            "filters": [
                                {
                                    "propertyName": "phone",
                                    "operator": "EQ",
                                    "value": contact_phone,
                                }
                            ]
                        }
                    ]
                }
                search_res = await client.post(
                    f"{BASE_URL}/crm/v3/objects/contacts/search",
                    json=search_payload,
                    headers=headers,
                )

                if search_res.status_code in (200, 201):
                    results = search_res.json().get("results", [])
                    if results:
                        contact_id = results[0].get("id")

                if not contact_id and contact_email:
                    search_email_payload = {
                        "filterGroups": [
                            {
                                "filters": [
                                    {
                                        "propertyName": "email",
                                        "operator": "EQ",
                                        "value": contact_email,
                                    }
                                ]
                            }
                        ]
                    }
                    search_email_res = await client.post(
                        f"{BASE_URL}/crm/v3/objects/contacts/search",
                        json=search_email_payload,
                        headers=headers,
                    )
                    if search_email_res.status_code in (200, 201):
                        results = search_email_res.json().get("results", [])
                        if results:
                            contact_id = results[0].get("id")

            if not contact_id:
                return {
                    "success": False,
                    "error": f"Failed to create or locate contact in HubSpot: {contact_res.text}",
                }

            # 2. Create Deal
            deal_payload = {
                "properties": {
                    "dealname": f"Lead from Call - {contact_name}",
                    "pipeline": pipeline_id,
                    "dealstage": deal_stage_id,
                    "description": notes,
                },
                "associations": [
                    {
                        "to": {"id": contact_id},
                        "types": [
                            {
                                "associationCategory": "HUBSPOT_DEFINED",
                                "associationTypeId": 3,  # deal_to_contact
                            }
                        ],
                    }
                ],
            }

            deal_res = await client.post(
                f"{BASE_URL}/crm/v3/objects/deals",
                json=deal_payload,
                headers=headers,
            )

            deal_id = None
            if deal_res.status_code in (200, 201):
                deal_id = deal_res.json().get("id")
            else:
                # Fallback to unassociated deal creation and separate association
                deal_payload_simple = {
                    "properties": {
                        "dealname": f"Lead from Call - {contact_name}",
                        "pipeline": pipeline_id,
                        "dealstage": deal_stage_id,
                        "description": notes,
                    }
                }
                deal_res = await client.post(
                    f"{BASE_URL}/crm/v3/objects/deals",
                    json=deal_payload_simple,
                    headers=headers,
                )
                if deal_res.status_code in (200, 201):
                    deal_id = deal_res.json().get("id")
                    assoc_url = f"{BASE_URL}/crm/v3/objects/deals/{deal_id}/associations/contacts/{contact_id}/deal_to_contact"
                    await client.put(assoc_url, headers=headers)

            if not deal_id:
                return {
                    "success": False,
                    "error": f"Failed to create deal in HubSpot: {deal_res.text}",
                }

            return {
                "success": True,
                "contact_id": str(contact_id),
                "deal_id": str(deal_id),
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def sync_call_summary(
    access_token: str,
    contact_phone: str,
    call_summary: str,
    success_eval: str,
    emotion_score: float,
    call_duration_seconds: int,
) -> Dict[str, Any]:
    """
    Post Call function called from Trigger.dev pipeline to sync call engagement and emotion score.
    Returns {"success": True} or {"success": False, "error": "..."}.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Search contact by phone
            search_payload = {
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "phone",
                                "operator": "EQ",
                                "value": contact_phone,
                            }
                        ]
                    }
                ]
            }
            search_res = await client.post(
                f"{BASE_URL}/crm/v3/objects/contacts/search",
                json=search_payload,
                headers=headers,
            )

            contact_id = None
            if search_res.status_code in (200, 201):
                results = search_res.json().get("results", [])
                if results:
                    contact_id = results[0].get("id")

            if not contact_id:
                return {
                    "success": False,
                    "error": f"HubSpot contact with phone number '{contact_phone}' not found.",
                }

            # 2. Create Call engagement object
            call_payload = {
                "properties": {
                    "hs_call_title": "VoCall Call Summary",
                    "hs_call_body": f"Summary:\n{call_summary}\n\nSuccess Evaluation:\n{success_eval}",
                    "hs_call_duration": call_duration_seconds * 1000,
                },
                "associations": [
                    {
                        "to": {"id": contact_id},
                        "types": [
                            {
                                "associationCategory": "HUBSPOT_DEFINED",
                                "associationTypeId": 194,  # call_to_contact
                            }
                        ],
                    }
                ],
            }

            call_res = await client.post(
                f"{BASE_URL}/crm/v3/objects/calls",
                json=call_payload,
                headers=headers,
            )

            if call_res.status_code not in (200, 201):
                # Fallback to legacy engagements v1 API
                engagement_payload = {
                    "engagement": {"type": "CALL"},
                    "associations": {"contactIds": [int(contact_id)]},
                    "metadata": {
                        "body": f"Summary:\n{call_summary}\n\nSuccess Evaluation:\n{success_eval}",
                        "durationMilliseconds": call_duration_seconds * 1000,
                    },
                }
                await client.post(
                    f"{BASE_URL}/engagements/v1/engagements",
                    json=engagement_payload,
                    headers=headers,
                )

            # 3. Update contact property 'last_call_emotion_score'
            update_payload = {
                "properties": {
                    "last_call_emotion_score": str(emotion_score),
                }
            }

            update_res = await client.patch(
                f"{BASE_URL}/crm/v3/objects/contacts/{contact_id}",
                json=update_payload,
                headers=headers,
            )

            # If custom property does not exist, create it and retry
            if (
                update_res.status_code == 400
                or "PropertyDoesNotExist" in update_res.text
                or "last_call_emotion_score" in update_res.text
            ):
                create_prop_payload = {
                    "name": "last_call_emotion_score",
                    "label": "Last Call Emotion Score",
                    "type": "number",
                    "fieldType": "number",
                    "groupName": "contactinformation",
                }
                await client.post(
                    f"{BASE_URL}/crm/v3/properties/contacts",
                    json=create_prop_payload,
                    headers=headers,
                )

                # Retry contact update
                await client.patch(
                    f"{BASE_URL}/crm/v3/objects/contacts/{contact_id}",
                    json=update_payload,
                    headers=headers,
                )

            return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}
