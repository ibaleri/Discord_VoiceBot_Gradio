"""
Unit Tests für mcp_client.py
Testet den Discord MCP Client
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import json


class TestDiscordMCPClientInit:
    """Tests für DiscordMCPClient Initialisierung"""

    def test_init_sets_config(self):
        """Test: Initialisierung setzt config"""
        from mcp_client import DiscordMCPClient

        mock_config = MagicMock()
        mock_config.mcp_mode = "subprocess"

        client = DiscordMCPClient(mock_config)

        assert client.config == mock_config
        assert client.server_process is None
        assert client.client is None
        assert client.connected == False


class TestDiscordMCPClientConnect:
    """Tests für connect Methode"""

    @pytest.fixture
    def client(self):
        from mcp_client import DiscordMCPClient

        mock_config = MagicMock()
        mock_config.mcp_mode = "subprocess"
        mock_config.discord_token = "test_token"

        return DiscordMCPClient(mock_config)

    @pytest.mark.asyncio
    async def test_connect_subprocess_mode(self, client):
        """Test: Verbindung im subprocess Modus"""
        with patch.object(client, '_start_server_subprocess', new_callable=AsyncMock) as mock_start:
            await client.connect()

            mock_start.assert_called_once()
            assert client.connected == True

    @pytest.mark.asyncio
    async def test_connect_remote_mode_fallback(self, client):
        """Test: Remote Mode fällt auf subprocess zurück"""
        client.config.mcp_mode = "remote"

        with patch.object(client, '_start_server_subprocess', new_callable=AsyncMock) as mock_start:
            await client.connect()

            # Remote mode fällt auf subprocess zurück (siehe Implementierung)
            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_invalid_mode_raises_error(self, client):
        """Test: Ungültiger Modus wirft Fehler"""
        client.config.mcp_mode = "invalid"

        with pytest.raises(ValueError) as exc_info:
            await client.connect()

        assert "Ungültiger MCP Mode" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_connect_error_handling(self, client):
        """Test: Fehlerbehandlung bei Verbindungsproblemen"""
        with patch.object(client, '_start_server_subprocess', new_callable=AsyncMock) as mock_start:
            mock_start.side_effect = Exception("Connection failed")

            with pytest.raises(Exception) as exc_info:
                await client.connect()

            assert "Connection failed" in str(exc_info.value)
            assert client.connected == False


class TestDiscordMCPClientAPICall:
    """Tests für call_discord_api Methode"""

    @pytest.fixture
    def connected_client(self):
        from mcp_client import DiscordMCPClient

        mock_config = MagicMock()
        mock_config.mcp_mode = "subprocess"
        mock_config.discord_token = "test_token"

        client = DiscordMCPClient(mock_config)
        client.connected = True
        client.client = AsyncMock()

        return client

    @pytest.mark.asyncio
    async def test_api_call_not_connected_raises_error(self):
        """Test: API Call ohne Verbindung wirft Fehler"""
        from mcp_client import DiscordMCPClient

        mock_config = MagicMock()
        client = DiscordMCPClient(mock_config)
        client.connected = False

        with pytest.raises(Exception) as exc_info:
            await client.call_discord_api("GET", "/test")

        assert "nicht verbunden" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_api_call_get_request(self, connected_client):
        """Test: GET Request wird korrekt verarbeitet"""
        # Mock Response
        mock_content = MagicMock()
        mock_content.text = '{"id": "123", "name": "Test"}'

        mock_result = MagicMock()
        mock_result.content = [mock_content]

        connected_client.client.call_tool = AsyncMock(return_value=mock_result)

        result = await connected_client.call_discord_api("GET", "/guilds/123")

        assert result["id"] == "123"
        assert result["name"] == "Test"

        # Prüfe dass call_tool aufgerufen wurde
        connected_client.client.call_tool.assert_called_once_with(
            "discord_api",
            arguments={
                "method": "GET",
                "endpoint": "/guilds/123",
                "data": None
            }
        )

    @pytest.mark.asyncio
    async def test_api_call_post_request_with_data(self, connected_client):
        """Test: POST Request mit Daten"""
        mock_content = MagicMock()
        mock_content.text = '{"id": "new_123"}'

        mock_result = MagicMock()
        mock_result.content = [mock_content]

        connected_client.client.call_tool = AsyncMock(return_value=mock_result)

        data = {"name": "Test Event", "description": "Test"}
        result = await connected_client.call_discord_api("POST", "/events", data)

        assert result["id"] == "new_123"

        # Prüfe dass data übergeben wurde
        call_args = connected_client.client.call_tool.call_args
        assert call_args[1]["arguments"]["data"] == data

    @pytest.mark.asyncio
    async def test_api_call_list_wrapped(self, connected_client):
        """Test: Listen werden korrekt gewrappt"""
        mock_content = MagicMock()
        mock_content.text = '[{"id": "1"}, {"id": "2"}]'

        mock_result = MagicMock()
        mock_result.content = [mock_content]

        connected_client.client.call_tool = AsyncMock(return_value=mock_result)

        result = await connected_client.call_discord_api("GET", "/events")

        assert "items" in result
        assert "count" in result
        assert result["count"] == 2


class TestDiscordMCPClientCreateEvent:
    """Tests für create_discord_event Helper-Methode"""

    @pytest.fixture
    def connected_client(self):
        from mcp_client import DiscordMCPClient

        mock_config = MagicMock()
        mock_config.discord_token = "test_token"

        client = DiscordMCPClient(mock_config)
        client.connected = True
        client.call_discord_api = AsyncMock(return_value={"id": "event_123"})

        return client

    @pytest.mark.asyncio
    async def test_create_external_event(self, connected_client):
        """Test: External Event erstellen"""
        result = await connected_client.create_discord_event(
            guild_id="123",
            name="Test Event",
            description="Ein Test",
            start_time="2025-12-01T15:00:00",
            end_time="2025-12-01T17:00:00",
            location="Online",
            entity_type=3
        )

        assert result["id"] == "event_123"

        # Prüfe API Call
        call_args = connected_client.call_discord_api.call_args
        assert call_args[0][0] == "POST"
        assert "/guilds/123/scheduled-events" in call_args[0][1]

        event_data = call_args[0][2]
        assert event_data["name"] == "Test Event"
        assert event_data["entity_type"] == 3
        assert "location" in event_data["entity_metadata"]

    @pytest.mark.asyncio
    async def test_create_voice_event_requires_channel(self, connected_client):
        """Test: Voice Event benötigt Channel ID"""
        with pytest.raises(ValueError) as exc_info:
            await connected_client.create_discord_event(
                guild_id="123",
                name="Voice Event",
                description="Test",
                start_time="2025-12-01T15:00:00",
                end_time="2025-12-01T17:00:00",
                entity_type=2  # VOICE
                # Keine channel_id!
            )

        assert "Channel ID" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_external_event_requires_location(self, connected_client):
        """Test: External Event benötigt Location"""
        with pytest.raises(ValueError) as exc_info:
            await connected_client.create_discord_event(
                guild_id="123",
                name="External Event",
                description="Test",
                start_time="2025-12-01T15:00:00",
                end_time="2025-12-01T17:00:00",
                entity_type=3  # EXTERNAL
                # Keine location!
            )

        assert "Location" in str(exc_info.value)


class TestDiscordMCPClientListTools:
    """Tests für list_tools Methode"""

    @pytest.fixture
    def connected_client(self):
        from mcp_client import DiscordMCPClient

        mock_config = MagicMock()
        client = DiscordMCPClient(mock_config)
        client.connected = True
        client.client = AsyncMock()

        return client

    @pytest.mark.asyncio
    async def test_list_tools_returns_tools(self, connected_client):
        """Test: list_tools gibt Tool-Liste zurück"""
        mock_tool = MagicMock()
        mock_tool.name = "discord_api"

        connected_client.client.list_tools = AsyncMock(return_value=[mock_tool])

        tools = await connected_client.list_tools()

        assert len(tools) == 1
        assert tools[0].name == "discord_api"

    @pytest.mark.asyncio
    async def test_list_tools_not_connected(self):
        """Test: list_tools ohne Verbindung gibt leere Liste"""
        from mcp_client import DiscordMCPClient

        mock_config = MagicMock()
        client = DiscordMCPClient(mock_config)
        client.connected = False

        tools = await client.list_tools()

        assert tools == []


class TestDiscordMCPClientDisconnect:
    """Tests für disconnect Methode"""

    @pytest.mark.asyncio
    async def test_disconnect_calls_aexit(self):
        """Test: disconnect ruft __aexit__ auf"""
        from mcp_client import DiscordMCPClient

        mock_config = MagicMock()
        client = DiscordMCPClient(mock_config)
        client.connected = True
        client.client = AsyncMock()
        client.client.__aexit__ = AsyncMock()

        await client.disconnect()

        client.client.__aexit__.assert_called_once()
        assert client.connected == False

    @pytest.mark.asyncio
    async def test_disconnect_handles_no_client(self):
        """Test: disconnect ohne Client wirft keinen Fehler"""
        from mcp_client import DiscordMCPClient

        mock_config = MagicMock()
        client = DiscordMCPClient(mock_config)
        client.connected = False
        client.client = None

        # Sollte keinen Fehler werfen
        await client.disconnect()

        assert client.connected == False
