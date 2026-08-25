"""Checkpointer adapter."""

from __future__ import annotations


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> object:
    """Return a LangGraph checkpointer."""
    if kind == "none":
        return None
    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if kind == "sqlite":
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver

        db_path = database_url or "outputs/checkpoints.db"
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        return SqliteSaver(conn=conn)
    if kind == "postgres":
        if not database_url:
            raise ValueError("Postgres checkpointer requires database_url")
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore

        return PostgresSaver.from_conn_string(database_url)
    raise ValueError(f"Unknown checkpointer kind: {kind}")
