"""
MCP Client für Discord Raw API Server
Eigene Implementierung mit FastMCP, inspiriert durch das Raw-API-Konzept von hanweg/mcp-discord-raw
"""

import asyncio
import logging
import json
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class DiscordMCPClient:
    """Client für MCP Discord Raw API Server"""

    def __init__(self, config):
        self.config = config
        self.server_process = None
        self.client = None
        self.connected = False

    async def connect(self):
        """
        Verbindet mit dem MCP Discord Raw Server

        Startet entweder den Server als Subprocess oder verbindet
        zu einem laufenden Server
        """
        try:
            logger.info("Verbinde mit MCP Discord Server...")

            # OPTION 1: Server als subprocess starten (empfohlen für Entwicklung)
            if self.config.mcp_mode == "subprocess":
                await self._start_server_subprocess()

            # OPTION 2: Zu laufendem Server verbinden (für Produktion)
            elif self.config.mcp_mode == "remote":
                await self._connect_to_remote_server()

            else:
                raise ValueError(f"Ungültiger MCP Mode: {self.config.mcp_mode}")

            self.connected = True
            logger.info("MCP Client erfolgreich verbunden")

        except Exception as e:
            logger.error(f"Fehler beim Verbinden: {e}", exc_info=True)
            raise

    async def _start_server_subprocess(self):
        """Startet MCP Server als Subprocess"""
        try:
            from fastmcp import FastMCP
            from fastmcp.client import Client

            # Server-Konfiguration für discord-raw
            # Eigene Implementierung inspiriert durch das Raw-API-Konzept von hanweg/mcp-discord-raw
            mcp = FastMCP("Discord Raw API Server")

            # Discord API Tool registrieren
            @mcp.tool()
            async def discord_api(
                method: str,
                endpoint: str,
                data: Optional[Dict[str, Any]] = None
            ) -> Dict[str, Any]:
                """
                Raw Discord API Access

                Args:
                    method: HTTP method (GET, POST, PATCH, DELETE, PUT)
                    endpoint: API endpoint (z.B. /guilds/{guild_id}/scheduled-events)
                    data: Request body (optional)

                Returns:
                    API response as dict
                """
                import aiohttp

                base_url = "https://discord.com/api/v10"
                url = f"{base_url}{endpoint}"

                headers = {
                    'Authorization': f'Bot {self.config.discord_token}',
                    'User-Agent': 'DiscordBot (https://github.com/discord-bot) Python/3.11 aiohttp/3.9',
                    'Content-Type': 'application/json'
                }

                logger.info(f"Discord API Call: {method} {endpoint}")

                async with aiohttp.ClientSession(headers=headers) as session:
                    try:
                        result = None

                        if method.upper() == 'GET':
                            async with session.get(url) as response:
                                response.raise_for_status()
                                result = await response.json()

                        elif method.upper() == 'POST':
                            async with session.post(url, json=data) as response:
                                response.raise_for_status()
                                result = await response.json()

                        elif method.upper() == 'PATCH':
                            async with session.patch(url, json=data) as response:
                                response.raise_for_status()
                                result = await response.json()

                        elif method.upper() == 'DELETE':
                            async with session.delete(url) as response:
                                response.raise_for_status()
                                if response.status == 204:
                                    return {"success": True, "deleted": True}
                                result = await response.json()

                        elif method.upper() == 'PUT':
                            async with session.put(url, json=data) as response:
                                response.raise_for_status()
                                result = await response.json()

                        else:
                            raise ValueError(f"Unsupported HTTP method: {method}")

                        # FastMCP Fix: Wrappen von Listen
                        if isinstance(result, list):
                            return {"items": result, "count": len(result)}
                        return result

                    except aiohttp.ClientResponseError as e:
                        error_text = await e.response.text() if hasattr(e, 'response') else str(e)
                        logger.error(f"Discord API Error: {e.status} - {error_text}")
                        raise Exception(f"Discord API Error {e.status}: {error_text}")

                    except Exception as e:
                        logger.error(f"Unexpected error: {e}", exc_info=True)
                        raise

            # Client erstellen und verbinden
            self.client = Client(mcp)
            await self.client.__aenter__()

            logger.info("MCP Server als Subprocess gestartet")

        except Exception as e:
            logger.error(f"Fehler beim Starten des MCP Servers: {e}", exc_info=True)
            raise

    async def _connect_to_remote_server(self):
        """Remote-Verbindung zum MCP Server (SSE/HTTP)."""
        try:
            from fastmcp.client import Client

            server_url = self.config.mcp_server_url
            if not server_url:
                raise ValueError(
                    "MCP_SERVER_URL nicht gesetzt fuer remote mode. "
                    "Bitte MCP_SERVER_URL in .env setzen (z.B. http://localhost:8000/sse)"
                )

            logger.info(f"Verbinde mit remote MCP Server: {server_url}")

            # Bearer Token fuer Auth
            api_key = getattr(self.config, "mcp_api_key", None)
            if api_key:
                logger.info("Bearer Token fuer Auth konfiguriert")

            # FastMCP erkennt Transport automatisch anhand der URL
            self.client = Client(server_url, auth=api_key)
            await self.client.__aenter__()

            # Verbindung testen
            tools = await self.client.list_tools()
            tool_names = [t.name for t in tools]
            logger.info(f"Remote MCP Server verbunden - {len(tools)} Tools: {tool_names}")

        except Exception as e:
            logger.error(f"Fehler beim Verbinden zum Remote-Server: {e}", exc_info=True)
            raise

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Listet alle verfügbaren MCP Tools auf"""
        try:
            if not self.connected:
                raise Exception("MCP Client nicht verbunden")

            tools = await self.client.list_tools()
            logger.info(f"Gefundene Tools: {[t.name for t in tools]}")
            return tools

        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Tools: {e}", exc_info=True)
            return []

    async def call_discord_api(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Ruft Discord API über MCP auf

        Args:
            method: HTTP Methode (GET, POST, PATCH, DELETE, PUT)
            endpoint: API Endpoint
            data: Request body (optional)

        Returns:
            API Response
        """
        try:
            if not self.connected:
                raise Exception("MCP Client nicht verbunden")

            logger.info(f"Calling discord_api: {method} {endpoint}")

            # MCP Tool aufrufen
            result = await self.client.call_tool(
                "discord_api",
                arguments={
                    "method": method,
                    "endpoint": endpoint,
                    "data": data
                }
            )

            # Result extrahieren
            if hasattr(result, 'content') and result.content:
                # FastMCP gibt Content als Liste zurück
                content = result.content[0]
                if hasattr(content, 'text'):
                    # Text zu JSON parsen
                    parsed = json.loads(content.text)
                    # Wenn Discord eine Liste zurückgibt, wrappen wir sie
                    if isinstance(parsed, list):
                        return {"items": parsed, "count": len(parsed)}
                    return parsed
                elif hasattr(content, 'data'):
                    return content.data
                else:
                    return {"result": str(content)}
            else:
                return {"result": str(result)}

        except Exception as e:
            logger.error(f"Fehler beim API Call: {e}", exc_info=True)
            raise

    async def create_discord_event(
        self,
        guild_id: str,
        name: str,
        description: str,
        start_time: str,
        end_time: str,
        location: str = None,
        channel_id: str = None,
        entity_type: int = 3
    ) -> Dict[str, Any]:
        """
        Erstellt ein Discord Scheduled Event (Helper Methode)

        Args:
            guild_id: Server ID
            name: Event Name
            description: Event Beschreibung
            start_time: Start Zeit (ISO 8601 Format: 2025-11-03T18:00:00)
            end_time: End Zeit
            location: Ort (für External Events)
            channel_id: Channel ID (für Voice/Stage Events)
            entity_type: 1=STAGE, 2=VOICE, 3=EXTERNAL

        Returns:
            Created event data
        """
        endpoint = f"/guilds/{guild_id}/scheduled-events"

        event_data = {
            "name": name,
            "description": description,
            "scheduled_start_time": start_time,
            "privacy_level": 2,  # GUILD_ONLY
            "entity_type": entity_type
        }

        # End time für alle Event-Types
        event_data["scheduled_end_time"] = end_time

        # Type-spezifische Felder
        if entity_type == 3:  # EXTERNAL
            if not location:
                raise ValueError("Location ist erforderlich für External Events")
            event_data["entity_metadata"] = {"location": location}
        elif entity_type in [1, 2]:  # STAGE oder VOICE
            if not channel_id:
                raise ValueError("Channel ID ist erforderlich für Voice/Stage Events")
            event_data["channel_id"] = channel_id

        return await self.call_discord_api("POST", endpoint, event_data)

    async def disconnect(self):
        """Trennt die MCP Verbindung"""
        try:
            if self.client:
                await self.client.__aexit__(None, None, None)
                logger.info("MCP Client getrennt")

            self.connected = False

        except Exception as e:
            logger.error(f"Fehler beim Trennen: {e}", exc_info=True)
