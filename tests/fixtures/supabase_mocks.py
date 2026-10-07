"""
tests/fixtures/supabase_mocks.py — Centralised Supabase MagicMock factories.

WHY THIS FILE EXISTS:
  Before this refactor, every test module that needed to patch the Supabase
  client defined its own local MagicMock chain factory:

    def make_contacts_supabase_mock(data=None, single=None): ...  # in test_contacts.py
    patch("app.services.supabase_client.supabase", None)           # in test_webhooks.py
    patch("app.services.supabase_client.supabase", None)           # in test_connectors.py
    ...

  The Graphify knowledge-graph audit detected the structural similarity between
  these factories and drew phantom cross-community edges, inflating betweenness
  centrality for make_contacts_supabase_mock() to 0.033 and incorrectly grouping
  'Test Contacts' with 'Test STT/TTS Hinglish' in the same community.

HOW IT IS FIXED:
  A single shared factory (make_supabase_mock) is defined here and imported by
  every test that needs a Supabase mock. This:
    1. Removes structural duplication across test files.
    2. Removes the phantom graph edges — the graph now sees ONE shared node
       instead of N isolated copies connected by semantic similarity.
    3. Makes the Supabase mock contract explicit and version-controlled in one place.
"""

from unittest.mock import MagicMock


def make_supabase_mock(
    table_data: list | None = None,
    single_row: dict | None = None,
) -> MagicMock:
    """
    Builds a MagicMock mimicking the Supabase Python SDK fluent query chain:

        supabase.table("x").select("*").eq("col", val).execute()  → MagicMock(data=table_data)
        supabase.table("x").select("*").single().execute()        → MagicMock(data=single_row)
        supabase.table("x").insert({...}).execute()               → MagicMock(data=[single_row])
        supabase.table("x").update({...}).eq(...).execute()       → MagicMock(data=[single_row])
        supabase.table("x").delete().eq(...).execute()            → MagicMock(data=[])

    Args:
        table_data:  List of rows returned by .execute() on list queries.
        single_row:  Single dict returned by .single().execute().
                     Defaults to table_data[0] if table_data is provided.

    Returns:
        Configured MagicMock ready to be used with patch().
    """
    rows = table_data or []
    row  = single_row or (rows[0] if rows else None)

    sb = MagicMock()

    # Build a reusable chainable query mock
    chain = MagicMock()
    chain.execute.return_value                        = MagicMock(data=rows)
    chain.eq.return_value                             = chain
    chain.neq.return_value                            = chain
    chain.order.return_value                          = chain
    chain.limit.return_value                          = chain
    chain.single.return_value.execute.return_value    = MagicMock(data=row)

    # Wire the mock to all common table operations
    tbl = sb.table.return_value
    tbl.select.return_value                                   = chain
    tbl.insert.return_value.execute.return_value              = MagicMock(data=[row] if row else [])
    tbl.update.return_value.eq.return_value.execute.return_value  = MagicMock(data=[row] if row else [])
    tbl.delete.return_value.eq.return_value.execute.return_value  = MagicMock(data=[])
    tbl.upsert.return_value.execute.return_value              = MagicMock(data=[row] if row else [])

    return sb


def make_null_supabase() -> None:
    """
    Returns None — used with patch() to simulate a missing / unconfigured
    Supabase client (triggers the 'no DB' code paths in routers).

    Usage:
        with patch("app.routers.contacts.supabase", make_null_supabase()):
            ...
    """
    return None
