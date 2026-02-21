"""SQLite Audit-Logger fuer den MCP Server."""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "audit_log.db"

_connection: Optional[sqlite3.Connection] = None


def _get_connection() -> sqlite3.Connection:
    """Geteilte DB-Verbindung (thread-safe)."""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
    return _connection


def init_db():
    """Erstellt Audit-Tabelle falls nciht vorhanden."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            client_id TEXT,
            user_name TEXT,
            action TEXT NOT NULL,
            params TEXT,
            result_summary TEXT,
            success INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_client ON audit_log(client_id)
    """)
    conn.commit()
    logger.info("Audit-Log DB initialisiert")


def log_action(
    client_id: str,
    user_name: str,
    action: str,
    params: Optional[dict] = None,
    result_summary: Optional[str] = None,
    success: bool = True,
):
    """Schreibt eine Aktion ins Audit-Log (params werden als JSON gespeichert)."""
    try:
        conn = _get_connection()
        conn.execute(
            """
            INSERT INTO audit_log (timestamp, client_id, user_name, action, params, result_summary, success)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(),
                client_id,
                user_name,
                action,
                json.dumps(params, ensure_ascii=False) if params else None,
                (result_summary[:200] if result_summary else None),
                1 if success else 0,
            ),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Audit-Log Fehler: {e}")


def get_recent_actions(limit: int = 50) -> list:
    """Letzte Audit-Eintraege als Liste von Dicts."""
    conn = _get_connection()
    cursor = conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [dict(row) for row in cursor.fetchall()]
