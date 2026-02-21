"""
Standalone MCP Server - exponiert Discord-Funktionen als Tools ueber SSE/HTTP.
Auth mit API-Keys, Role-based Permissions, Rate-Limiting und Audit-Log.
"""

import asyncio
import json
import logging
import os
import sys
import time
from collections import defaultdict
from typing import Optional, List, Dict, Any

from fastmcp import FastMCP
from fastmcp.server.auth import StaticTokenVerifier
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_access_token

from audit_log import init_db, log_action

logger = logging.getLogger(__name__)


# === API KEY MANAGEMENT ===


def load_api_keys(path: str = "api_keys.json") -> dict:
    """Laedt API Keys aus JSON und konvertiert fuer StaticTokenVerifier."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.warning(f"API-Key-Datei nicht gefunden: {path} - Server startet ohne Auth")
        return {}

    tokens = {}
    for key, meta in data.get("keys", {}).items():
        if not meta.get("active", True):
            continue
        tokens[key] = {
            "client_id": meta.get("name", "unknown"),
            "scopes": _role_to_scopes(meta.get("role", "reader")),
        }

    logger.info(f"{len(tokens)} API-Keys geladen aus {path}")
    return tokens


def _role_to_scopes(role: str) -> list:
    """Rolle -> OAuth-Scopes."""
    if role == "reader":
        return ["tools:read"]
    elif role == "writer":
        return ["tools:read", "tools:write"]
    elif role == "admin":
        return ["tools:read", "tools:write", "tools:admin"]
    return []


# === SECURITY MIDDLEWARE ===


class SecurityMiddleware(Middleware):
    """Prueft Permissions, Rate-Limits und loggt in Audit-DB."""

    # Tools die bestimte Scopes brauchen
    TOOL_SCOPES = {
        "create_event": "tools:write",
        "send_message": "tools:write",
        "update_event": "tools:write",
        "delete_event_by_name": "tools:admin",
        "delete_message": "tools:admin",
        "delete_last_message": "tools:admin",
    }
    # Alles andere: reader reicht

    # Rate-Limits (max_calls, window_seconds)
    WRITE_RATE_LIMIT = (10, 60)   # 10 writes/min
    READ_RATE_LIMIT = (30, 60)    # 30 reads/min

    def __init__(self):
        super().__init__()
        # Rate-Limit Counter im Speicher
        self._rate_counters: dict = defaultdict(list)

    def _check_rate_limit(self, client_id: str, is_write: bool) -> bool:
        """True wenn noch innerhalb vom Limit."""
        now = time.time()
        max_calls, window = self.WRITE_RATE_LIMIT if is_write else self.READ_RATE_LIMIT

        # Alte Eintraege entfernen
        self._rate_counters[client_id] = [
            (ts, wt) for ts, wt in self._rate_counters[client_id]
            if now - ts < window
        ]

        # Relevante Aufrufe zaehlen
        count = sum(
            1 for _, wt in self._rate_counters[client_id]
            if wt == is_write
        )

        if count >= max_calls:
            return False

        self._rate_counters[client_id].append((now, is_write))
        return True

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Intercepted Tool-Calls fuer Auth, Rate-Limit und Audit."""
        token = get_access_token()
        tool_name = context.message.name
        args = context.message.arguments or {}

        client_id = token.client_id if token else "unknown"
        user_scopes = token.scopes if token else []

        # 1. Permsission Check
        required_scope = self.TOOL_SCOPES.get(tool_name)
        if required_scope and required_scope not in user_scopes:
            log_action(
                client_id=client_id,
                user_name=client_id,
                action=tool_name,
                params=args,
                result_summary="PERMISSION DENIED",
                success=False,
            )
            raise PermissionError(
                f"Keine Berechtigung fuer '{tool_name}'. "
                f"Benoetigter Scope: {required_scope}, "
                f"Deine Scopes: {user_scopes}"
            )

        # 2. Rate-Limiting
        is_write = required_scope is not None
        if not self._check_rate_limit(client_id, is_write):
            action_type = "Write" if is_write else "Read"
            log_action(
                client_id=client_id,
                user_name=client_id,
                action=tool_name,
                params=args,
                result_summary=f"RATE LIMIT ({action_type})",
                success=False,
            )
            raise Exception(
                f"Rate-Limit ueberschritten ({action_type}-Aktionen). Bitte warte einen Moment."
            )

        # 3. Tool ausfuehren (eigentlicher Call)
        try:
            result = await call_next(context)
            success = True
            result_summary = str(result)[:200] if result else "OK"
        except Exception as e:
            success = False
            result_summary = f"ERROR: {str(e)[:180]}"
            raise
        finally:
            # 4. Audit-Log
            log_action(
                client_id=client_id,
                user_name=client_id,
                action=tool_name,
                params=args,
                result_summary=result_summary,
                success=success,
            )

        return result


# === SERVER SETUP ===

# API Keys laden + Auth konfig
_api_keys = load_api_keys()

if _api_keys:
    _auth = StaticTokenVerifier(tokens=_api_keys)
    logger.info("Auth aktiviert (StaticTokenVerifier)")
else:
    _auth = None
    logger.warning("KEIN Auth aktiv - Server laeuft ohne Authentifizierung!")

# Audit-DB init
init_db()

# Server mit Auth und Middleware erstelen
mcp = FastMCP(
    "Discord Bot MCP Server",
    auth=_auth,
    middleware=[SecurityMiddleware()],
)

# Globale Instanzen (lazy init beim ersten Tool-Call)
_helper = None
_mcp_client = None
_llm_voice = None
_initialized = False


async def _ensure_initialized():
    """Lazy init - startet Helper beim ersten Aufruf."""
    global _helper, _mcp_client, _llm_voice, _initialized

    if _initialized:
        return _helper

    from config import Config
    from mcp_client import DiscordMCPClient
    from llm_voice import LLMVoiceInterface
    from discord_helpers import DiscordEventHelper

    logger.info("Initialisiere MCP Server Komponenten...")

    config = Config()

    # Intern immer subprocess (sonst Endlosschleife wenn MCP_MODE=remote)
    config.mcp_mode = "subprocess"
    _mcp_client = DiscordMCPClient(config)
    await _mcp_client.connect()
    logger.info("Discord MCP Client verbunden")

    # LLM fuer Zusammenfassungen (optional)
    _llm_voice = None
    if config.llm_provider and config.llm_available:
        try:
            _llm_voice = LLMVoiceInterface(config)
            logger.info("LLM Voice Interface initialisiert")
        except Exception as e:
            logger.warning(f"LLM Voice nicht verfuegbar: {e}")

    # Discord Event Helper
    _helper = DiscordEventHelper(config, _mcp_client, gemini=_llm_voice)
    await _helper.initialize()
    logger.info("Discord Helper initialisiert")

    _initialized = True
    return _helper


def _get_triggered_by() -> Optional[str]:
    """User-Name aus Auth-Token holen (fuer Attribution)."""
    token = get_access_token()
    return token.client_id if token else None


# === MCP TOOLS ===
# Kein discord_api Raw-Tool (Sicherheitsrisiko)


@mcp.tool()
async def create_event(
    name: str,
    start_time: str,
    description: str = "",
    duration_hours: float = 1.0,
    location: str = "Discord",
    event_type: str = "online",
    channel_id: Optional[str] = None,
) -> dict:
    """Erstellt ein Scheduled Event auf dem Discord Server."""
    helper = await _ensure_initialized()
    triggered_by = _get_triggered_by()
    return await helper.create_event(
        name=name,
        start_time=start_time,
        description=description,
        duration_hours=duration_hours,
        location=location,
        event_type=event_type,
        channel_id=channel_id,
        triggered_by=triggered_by,
    )


@mcp.tool()
async def list_upcoming_events(
    limit: int = 50,
    days_ahead: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    location: Optional[str] = None,
    group_by_days: bool = False,
    timeframe: Optional[str] = None,
) -> dict:
    """Listet kommende Events auf (Zeitraum-Filter moeglich)."""
    helper = await _ensure_initialized()
    return await helper.list_upcoming_events(
        limit=limit,
        days_ahead=days_ahead,
        from_date=from_date,
        to_date=to_date,
        location=location,
        group_by_days=group_by_days,
        timeframe=timeframe,
    )


@mcp.tool()
async def list_events_on_specific_day(
    from_date: str,
    to_date: Optional[str] = None,
    location: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """Events an einem bestimten Tag auflisten."""
    helper = await _ensure_initialized()
    return await helper.list_events_on_specific_day(
        from_date=from_date,
        to_date=to_date,
        location=location,
        limit=limit,
    )


@mcp.tool()
async def delete_event_by_name(event_name: str) -> dict:
    """Loescht ein Event per Name."""
    helper = await _ensure_initialized()
    triggered_by = _get_triggered_by()
    return await helper.delete_event_by_name(event_name=event_name, triggered_by=triggered_by)


@mcp.tool()
async def update_event(event_id: str, updates: dict) -> dict:
    """Aktualisiert ein bestehendes Event (name, description, start_time etc)."""
    helper = await _ensure_initialized()
    triggered_by = _get_triggered_by()
    return await helper.update_event(event_id=event_id, updates=updates, triggered_by=triggered_by)


@mcp.tool()
async def send_message(
    channel_id: str,
    content: str,
    mentions: Optional[List[str]] = None,
) -> dict:
    """Nachricht in einen Channel senden (channel_id kann auch Name sein)."""
    helper = await _ensure_initialized()
    triggered_by = _get_triggered_by()
    return await helper.send_message(
        channel_id=channel_id,
        content=content,
        mentions=mentions,
        triggered_by=triggered_by,
    )


@mcp.tool()
async def get_server_info() -> dict:
    """Server-Infos abrufen (Name, Member-Count etc)."""
    helper = await _ensure_initialized()
    return await helper.get_server_info()


@mcp.tool()
async def list_channels(channel_type: str = "all") -> dict:
    """Alle Channels auflisten (filter: all/text/voice)."""
    helper = await _ensure_initialized()
    return await helper.list_channels(channel_type=channel_type)


@mcp.tool()
async def get_online_members_count() -> dict:
    """Anzahl online Mitglieder."""
    helper = await _ensure_initialized()
    return await helper.get_online_members_count()


@mcp.tool()
async def list_online_members(limit: int = 20) -> dict:
    """Online Mitglieder mit Namen auflisten."""
    helper = await _ensure_initialized()
    return await helper.list_online_members(limit=limit)


@mcp.tool()
async def delete_message(
    channel_id: str,
    message_id: Optional[str] = None,
    content: Optional[str] = None,
) -> dict:
    """Nachricht loeschen (per ID oder Content-Suche)."""
    helper = await _ensure_initialized()
    triggered_by = _get_triggered_by()
    return await helper.delete_message(
        channel_id=channel_id,
        message_id=message_id,
        content=content,
        triggered_by=triggered_by,
    )


@mcp.tool()
async def delete_last_message(channel_id: str) -> dict:
    """Letzte Nachricht im Channel loeschen."""
    helper = await _ensure_initialized()
    triggered_by = _get_triggered_by()
    return await helper.delete_last_message(channel_id=channel_id, triggered_by=triggered_by)


@mcp.tool()
async def get_channel_messages(channel_id: str, limit: int = 5) -> dict:
    """Letzte Nachrichten aus einem Channel holen."""
    helper = await _ensure_initialized()
    return await helper.get_channel_messages(channel_id=channel_id, limit=limit)


@mcp.tool()
async def summarize_channel(channel_id: str, limit: int = 10) -> dict:
    """Channel-Nachrichten per LLM zusammnfassen."""
    helper = await _ensure_initialized()
    return await helper.summarize_channel(channel_id=channel_id, limit=limit)


# === SERVER START ===

if __name__ == "__main__":
    # Logging setup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("mcp_server.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_SERVER_PORT", "8000"))
    transport = os.getenv("MCP_TRANSPORT", "sse")

    auth_status = "AKTIV" if _api_keys else "DEAKTIVIERT"

    print("=" * 60)
    print("Discord Bot - MCP Server")
    print("=" * 60)
    print(f"Transport: {transport}")
    print(f"Host:      {host}")
    print(f"Port:      {port}")
    print(f"URL:       http://{host}:{port}/sse")
    print(f"Auth:      {auth_status} ({len(_api_keys)} Keys)")
    print(f"Audit-Log: audit_log.db")
    print("=" * 60)

    asyncio.run(
        mcp.run_http_async(
            transport=transport,
            host=host,
            port=port,
        )
    )
