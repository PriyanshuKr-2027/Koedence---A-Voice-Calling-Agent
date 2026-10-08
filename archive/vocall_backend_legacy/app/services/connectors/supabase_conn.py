from typing import Any, Dict, List, Optional
import asyncpg
import httpx

TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_supabase",
            "description": "Query a Supabase table via REST API to look up customer or database information during a call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Supabase project REST URL (e.g., 'https://xyz.supabase.co').",
                    },
                    "anon_key": {
                        "type": "string",
                        "description": "Supabase anon or service role API key.",
                    },
                    "table_name": {
                        "type": "string",
                        "description": "Name of the Supabase table to query.",
                    },
                    "query_column": {
                        "type": "string",
                        "description": "Column name to filter by (e.g., 'phone', 'email').",
                    },
                    "query_value": {
                        "type": "string",
                        "description": "Value to match against the query column.",
                    },
                },
                "required": ["url", "anon_key", "table_name", "query_column", "query_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_postgres",
            "description": "Execute a parameterized SQL query against a PostgreSQL database using caller's phone number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "connection_string": {
                        "type": "string",
                        "description": "PostgreSQL connection string (e.g. postgresql://user:pass@host:5432/dbname).",
                    },
                    "query_template": {
                        "type": "string",
                        "description": "SQL query template containing {contact_phone} or $1 placeholder.",
                    },
                    "contact_phone": {
                        "type": "string",
                        "description": "Caller's phone number to filter/substitute into the query.",
                    },
                },
                "required": ["connection_string", "query_template", "contact_phone"],
            },
        },
    },
]


def _stringify_rows(rows: List[Any]) -> List[Dict[str, str]]:
    stringified = []
    for r in rows:
        if isinstance(r, dict):
            stringified.append({str(k): (str(v) if v is not None else "") for k, v in r.items()})
        else:
            stringified.append({"result": str(r)})
    return stringified


async def query_supabase(
    url: str,
    anon_key: str,
    table_name: str,
    query_column: str,
    query_value: str,
) -> Dict[str, Any]:
    """
    Queries a Supabase table via PostgREST API during a call.
    Returns {"success": True, "rows": [...], "count": int} with rows capped at 5.
    Returns {"success": False, "error": "..."} on failure.
    """
    try:
        clean_url = url.rstrip("/")
        endpoint = f"{clean_url}/rest/v1/{table_name}?{query_column}=eq.{query_value}&limit=5"

        headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Prefer": "count=exact",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(endpoint, headers=headers)
            response.raise_for_status()

            data = response.json()
            if not isinstance(data, list):
                data = [data]

            capped_rows = data[:5]
            stringified_rows = _stringify_rows(capped_rows)

            return {
                "success": True,
                "rows": stringified_rows,
                "count": len(stringified_rows),
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def query_postgres(
    connection_string: str,
    query_template: str,
    contact_phone: str,
) -> Dict[str, Any]:
    """
    Executes a parameterized SQL query against a PostgreSQL database safely using asyncpg.
    Substitutes {contact_phone} with $1 parameter.
    Returns {"success": True, "rows": [...], "count": int} capped at 5.
    Returns {"success": False, "error": "..."} on failure.
    """
    conn = None
    try:
        # Prepare parameterized SQL query string safely
        sql = (
            query_template.replace("'{contact_phone}'", "$1")
            .replace('"{contact_phone}"', "$1")
            .replace("{contact_phone}", "$1")
        )

        conn = await asyncpg.connect(connection_string, timeout=10.0)

        if "$1" in sql:
            records = await conn.fetch(sql, contact_phone)
        else:
            records = await conn.fetch(sql)

        dict_rows = [dict(rec) for rec in records[:5]]
        stringified_rows = _stringify_rows(dict_rows)

        return {
            "success": True,
            "rows": stringified_rows,
            "count": len(stringified_rows),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if conn:
            try:
                await conn.close()
            except Exception:
                pass
