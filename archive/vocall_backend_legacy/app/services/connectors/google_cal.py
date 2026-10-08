import asyncio
from datetime import datetime, time, timedelta
import json
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check available free 30-minute slots on a specific date for a Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "credentials_json": {
                        "type": "string",
                        "description": "JSON string of Google service account or OAuth2 credentials.",
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Google Calendar ID (e.g., 'primary' or user email address).",
                    },
                    "date_str": {
                        "type": "string",
                        "description": "Date to check availability for in YYYY-MM-DD format (e.g. '2026-07-22').",
                    },
                    "timezone": {
                        "type": "string",
                        "description": "Target timezone string (e.g., 'Asia/Kolkata', 'America/New_York'). Default is 'Asia/Kolkata'.",
                    },
                },
                "required": ["credentials_json", "calendar_id", "date_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a new event/appointment in Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "credentials_json": {
                        "type": "string",
                        "description": "JSON string of Google service account or OAuth2 credentials.",
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Google Calendar ID (e.g., 'primary' or user email address).",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start datetime in ISO format (e.g., '2026-07-22T10:00:00+05:30').",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End datetime in ISO format (e.g., '2026-07-22T10:30:00+05:30').",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Title or summary of the appointment.",
                    },
                    "attendee_email": {
                        "type": "string",
                        "description": "Optional email address of the attendee.",
                    },
                    "timezone": {
                        "type": "string",
                        "description": "Timezone string for the event (e.g. 'Asia/Kolkata'). Default is 'Asia/Kolkata'.",
                    },
                },
                "required": [
                    "credentials_json",
                    "calendar_id",
                    "start_time",
                    "end_time",
                    "summary",
                ],
            },
        },
    },
]


def _get_calendar_service(credentials_json: str):
    info = json.loads(credentials_json)
    if info.get("type") == "service_account":
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
    else:
        credentials = Credentials(
            token=info.get("token"),
            refresh_token=info.get("refresh_token"),
            token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=info.get("client_id"),
            client_secret=info.get("client_secret"),
            scopes=SCOPES,
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())

    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _check_availability_sync(
    credentials_json: str,
    calendar_id: str,
    date_str: str,
    timezone: str = "Asia/Kolkata",
) -> List[Dict[str, str]]:
    try:
        service = _get_calendar_service(credentials_json)
        try:
            tz = ZoneInfo(timezone)
        except Exception:
            tz = ZoneInfo("UTC")

        if "T" in date_str:
            base_dt = datetime.fromisoformat(date_str)
            date_obj = base_dt.date()
        else:
            date_obj = datetime.strptime(date_str[:10], "%Y-%m-%d").date()

        day_start = datetime.combine(date_obj, time(9, 0), tzinfo=tz)
        day_end = datetime.combine(date_obj, time(17, 0), tzinfo=tz)

        body = {
            "timeMin": day_start.isoformat(),
            "timeMax": day_end.isoformat(),
            "timeZone": timezone,
            "items": [{"id": calendar_id}],
        }
        res = service.freebusy().query(body=body).execute()
        busy_list = res.get("calendars", {}).get(calendar_id, {}).get("busy", [])

        busy_ranges = []
        for b in busy_list:
            b_start = datetime.fromisoformat(b["start"])
            b_end = datetime.fromisoformat(b["end"])
            busy_ranges.append((b_start, b_end))

        free_slots = []
        current = day_start
        while current + timedelta(minutes=30) <= day_end:
            slot_start = current
            slot_end = current + timedelta(minutes=30)
            is_busy = False
            for b_start, b_end in busy_ranges:
                if max(slot_start, b_start) < min(slot_end, b_end):
                    is_busy = True
                    break
            if not is_busy:
                free_slots.append(
                    {
                        "start": slot_start.isoformat(),
                        "end": slot_end.isoformat(),
                    }
                )
            current += timedelta(minutes=30)

        return free_slots
    except Exception:
        return []


def _book_appointment_sync(
    credentials_json: str,
    calendar_id: str,
    start_time: str,
    end_time: str,
    summary: str,
    attendee_email: Optional[str] = None,
    timezone: str = "Asia/Kolkata",
) -> Dict[str, Any]:
    try:
        service = _get_calendar_service(credentials_json)

        event_body = {
            "summary": summary,
            "start": {"dateTime": start_time, "timeZone": timezone},
            "end": {"dateTime": end_time, "timeZone": timezone},
        }
        if attendee_email:
            event_body["attendees"] = [{"email": attendee_email}]

        event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        return {
            "success": True,
            "event_id": event.get("id"),
            "html_link": event.get("htmlLink"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def check_availability(
    credentials_json: str,
    calendar_id: str,
    date_str: str,
    timezone: str = "Asia/Kolkata",
) -> List[Dict[str, str]]:
    """
    Returns a list of free 30-minute slots on the given date as [{"start": "...", "end": "..."}].
    If no slots found or error occurs, returns [].
    """
    try:
        return await asyncio.to_thread(
            _check_availability_sync, credentials_json, calendar_id, date_str, timezone
        )
    except Exception:
        return []


async def book_appointment(
    credentials_json: str,
    calendar_id: str,
    start_time: str,
    end_time: str,
    summary: str,
    attendee_email: Optional[str] = None,
    timezone: str = "Asia/Kolkata",
) -> Dict[str, Any]:
    """
    Creates a calendar event.
    Returns {"success": True, "event_id": "...", "html_link": "..."} or {"success": False, "error": "..."}.
    """
    try:
        return await asyncio.to_thread(
            _book_appointment_sync,
            credentials_json,
            calendar_id,
            start_time,
            end_time,
            summary,
            attendee_email,
            timezone,
        )
    except Exception as e:
        return {"success": False, "error": str(e)}
