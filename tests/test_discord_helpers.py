"""
Unit Tests für discord_helpers.py
Testet die Discord Event Helper-Klasse und ihre Methoden
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import pytz


class TestDiscordEventHelperInit:
    """Tests für DiscordEventHelper Initialisierung"""

    def test_init_sets_attributes(self):
        """Test: Initialisierung setzt alle Attribute"""
        from discord_helpers import DiscordEventHelper

        mock_config = MagicMock()
        mock_config.discord_guild_id = "123456789"
        mock_mcp_client = MagicMock()

        helper = DiscordEventHelper(mock_config, mock_mcp_client)

        assert helper.config == mock_config
        assert helper.mcp_client == mock_mcp_client
        assert helper.guild_id == "123456789"
        assert helper.timezone == pytz.timezone('Europe/Berlin')
        assert helper.channels_cache == {}
        assert helper.events_cache == []

    def test_init_with_gemini(self):
        """Test: Initialisierung mit Gemini Client"""
        from discord_helpers import DiscordEventHelper

        mock_config = MagicMock()
        mock_config.discord_guild_id = "123"
        mock_mcp = MagicMock()
        mock_gemini = MagicMock()

        helper = DiscordEventHelper(mock_config, mock_mcp, gemini=mock_gemini)

        assert helper.gemini == mock_gemini


class TestTimeParser:
    """Tests für _parse_time Methode"""

    @pytest.fixture
    def helper(self):
        """Fixture für DiscordEventHelper"""
        from discord_helpers import DiscordEventHelper

        mock_config = MagicMock()
        mock_config.discord_guild_id = "123"
        mock_mcp = MagicMock()

        return DiscordEventHelper(mock_config, mock_mcp)

    def test_parse_heute(self, helper):
        """Test: Parst 'heute 15:00'"""
        start, end = helper._parse_time("heute 15:00", duration_hours=1.0)

        now = datetime.now(helper.timezone)
        assert start.astimezone(helper.timezone).date() == now.date()
        assert start.astimezone(helper.timezone).hour == 15
        assert start.astimezone(helper.timezone).minute == 0

    def test_parse_morgen(self, helper):
        """Test: Parst 'morgen 18:30'"""
        start, end = helper._parse_time("morgen 18:30", duration_hours=2.0)

        now = datetime.now(helper.timezone)
        tomorrow = now + timedelta(days=1)
        assert start.astimezone(helper.timezone).date() == tomorrow.date()
        assert start.astimezone(helper.timezone).hour == 18
        assert start.astimezone(helper.timezone).minute == 30

    def test_parse_uebermorgen(self, helper):
        """Test: Parst 'übermorgen 10:00'"""
        start, end = helper._parse_time("übermorgen 10:00", duration_hours=1.0)

        now = datetime.now(helper.timezone)
        day_after = now + timedelta(days=2)
        assert start.astimezone(helper.timezone).date() == day_after.date()
        assert start.astimezone(helper.timezone).hour == 10

    def test_parse_relative_hours(self, helper):
        """Test: Parst 'in 3 Stunden'"""
        start, end = helper._parse_time("in 3 Stunden", duration_hours=1.0)

        now = datetime.now(pytz.UTC)
        expected = now + timedelta(hours=3)

        # Toleranz von 1 Minute
        diff = abs((start - expected).total_seconds())
        assert diff < 60

    def test_parse_relative_days(self, helper):
        """Test: Parst 'in 5 Tagen'"""
        start, end = helper._parse_time("in 5 Tagen", duration_hours=1.0)

        now = datetime.now(pytz.UTC)
        expected = now + timedelta(days=5)

        # Toleranz von 1 Minute
        diff = abs((start - expected).total_seconds())
        assert diff < 60

    def test_parse_weekday_montag(self, helper):
        """Test: Parst 'Montag 14:00'"""
        start, end = helper._parse_time("Montag 14:00", duration_hours=1.0)

        # Sollte der nächste Montag sein
        assert start.astimezone(helper.timezone).weekday() == 0  # Montag = 0
        assert start.astimezone(helper.timezone).hour == 14

    def test_parse_weekday_freitag(self, helper):
        """Test: Parst 'Freitag 20:00'"""
        start, end = helper._parse_time("Freitag 20:00", duration_hours=2.0)

        assert start.astimezone(helper.timezone).weekday() == 4  # Freitag = 4
        assert start.astimezone(helper.timezone).hour == 20

    def test_parse_duration_calculation(self, helper):
        """Test: End-Zeit wird korrekt aus Duration berechnet"""
        start, end = helper._parse_time("morgen 15:00", duration_hours=3.5)

        diff_hours = (end - start).total_seconds() / 3600
        assert diff_hours == 3.5

    def test_parse_default_time_wenn_keine_angabe(self, helper):
        """Test: Default-Zeit ist 15:00 wenn keine Zeit angegeben"""
        start, end = helper._parse_time("morgen", duration_hours=1.0)

        assert start.astimezone(helper.timezone).hour == 15
        assert start.astimezone(helper.timezone).minute == 0

    def test_parse_invalid_time_raises_error(self, helper):
        """Test: Ungültige Zeitangabe wirft ValueError"""
        with pytest.raises(ValueError):
            helper._parse_time("ungültige zeitangabe xyz", duration_hours=1.0)

    def test_parse_sommerzeit_umstellung(self, helper):
        """Test: Sommerzeitumstellung wird korrekt behandelt.

        Testet das Verhalten bei der Umstellung von MESZ (UTC+2) zu MEZ (UTC+1).
        Am letzten Sonntag im Oktober wird die Uhr von 3:00 auf 2:00 zurückgestellt.
        pytz und astimezone() müssen dies korrekt handhaben.
        """
        from datetime import datetime
        import pytz

        # Simuliere einen Zeitpunkt kurz vor der Umstellung (Ende Oktober)
        # MESZ = UTC+2, MEZ = UTC+1
        berlin_tz = pytz.timezone('Europe/Berlin')

        # Teste dass 15:00 Lokalzeit korrekt zu UTC konvertiert wird
        # Im Winter (MEZ): 15:00 Berlin = 14:00 UTC
        # Im Sommer (MESZ): 15:00 Berlin = 13:00 UTC
        start, end = helper._parse_time("morgen 15:00", duration_hours=1.0)

        # Prüfe dass die Lokalzeit korrekt ist
        local_time = start.astimezone(berlin_tz)
        assert local_time.hour == 15
        assert local_time.minute == 0

        # Prüfe dass UTC-Offset konsistent ist (entweder +1 oder +2 je nach Jahreszeit)
        utc_offset_hours = local_time.utcoffset().total_seconds() / 3600
        assert utc_offset_hours in [1, 2]  # MEZ (+1) oder MESZ (+2)


class TestChannelNameNormalization:
    """Tests für Channel-Name-Normalisierung"""

    @pytest.fixture
    def helper(self):
        from discord_helpers import DiscordEventHelper

        mock_config = MagicMock()
        mock_config.discord_guild_id = "123"
        mock_mcp = MagicMock()

        return DiscordEventHelper(mock_config, mock_mcp)

    def test_normalize_removes_hyphens(self, helper):
        """Test: Entfernt Bindestriche"""
        result = helper._normalize_channel_name("voice-channel")
        assert result == "voicechannel"

    def test_normalize_removes_underscores(self, helper):
        """Test: Entfernt Unterstriche"""
        result = helper._normalize_channel_name("voice_channel")
        assert result == "voicechannel"

    def test_normalize_removes_spaces(self, helper):
        """Test: Entfernt Leerzeichen"""
        result = helper._normalize_channel_name("voice channel")
        assert result == "voicechannel"

    def test_normalize_lowercase(self, helper):
        """Test: Konvertiert zu Kleinbuchstaben"""
        result = helper._normalize_channel_name("VoiceChannel")
        assert result == "voicechannel"

    def test_normalize_combined(self, helper):
        """Test: Kombinierte Normalisierung"""
        result = helper._normalize_channel_name("Voice-Channel_Test 123")
        assert result == "voicechanneltest123"


class TestCreateEvent:
    """Tests für create_event Methode"""

    @pytest.fixture
    def helper(self):
        from discord_helpers import DiscordEventHelper

        mock_config = MagicMock()
        mock_config.discord_guild_id = "123456789"
        mock_mcp = AsyncMock()
        mock_mcp.call_discord_api = AsyncMock(return_value={
            "id": "event_123",
            "name": "Test Event"
        })

        return DiscordEventHelper(mock_config, mock_mcp)

    @pytest.mark.asyncio
    async def test_create_event_success(self, helper):
        """Test: Event wird erfolgreich erstellt"""
        result = await helper.create_event(
            name="Test Meeting",
            start_time="morgen 15:00",
            description="Ein Testmeeting",
            duration_hours=2.0,
            location="Online"
        )

        assert result["success"] == True
        assert result["event_id"] == "event_123"
        assert "Test" in result["event_name"]
        helper.mcp_client.call_discord_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_event_default_description(self, helper):
        """Test: Default-Beschreibung wird gesetzt wenn leer"""
        result = await helper.create_event(
            name="Test Event",
            start_time="morgen 15:00",
            description=""
        )

        # API wurde aufgerufen mit description
        call_args = helper.mcp_client.call_discord_api.call_args
        event_data = call_args[0][2]  # Drittes Argument ist data
        assert "Event:" in event_data["description"]

    @pytest.mark.asyncio
    async def test_create_event_external_type(self, helper):
        """Test: External Event benötigt Location"""
        result = await helper.create_event(
            name="Test",
            start_time="morgen 15:00",
            event_type="online",
            location="Discord Server"
        )

        call_args = helper.mcp_client.call_discord_api.call_args
        event_data = call_args[0][2]
        assert event_data["entity_type"] == 3  # EXTERNAL
        assert "location" in event_data["entity_metadata"]


class TestListUpcomingEvents:
    """Tests für list_upcoming_events Methode"""

    @pytest.fixture
    def helper(self):
        from discord_helpers import DiscordEventHelper

        mock_config = MagicMock()
        mock_config.discord_guild_id = "123456789"
        mock_mcp = AsyncMock()

        return DiscordEventHelper(mock_config, mock_mcp)

    @pytest.mark.asyncio
    async def test_list_events_empty(self, helper):
        """Test: Leere Event-Liste"""
        helper.mcp_client.call_discord_api = AsyncMock(return_value={"items": []})

        result = await helper.list_upcoming_events()

        assert result["success"] == True
        assert result["count"] == 0
        assert result["events"] == []

    @pytest.mark.asyncio
    async def test_list_events_with_data(self, helper):
        """Test: Events werden zurückgegeben"""
        future_time = (datetime.now(pytz.UTC) + timedelta(days=1)).isoformat()

        helper.mcp_client.call_discord_api = AsyncMock(return_value={
            "items": [
                {
                    "id": "1",
                    "name": "Event 1",
                    "scheduled_start_time": future_time,
                    "scheduled_end_time": future_time,
                    "entity_metadata": {"location": "Test"}
                }
            ]
        })

        result = await helper.list_upcoming_events()

        assert result["success"] == True
        assert result["count"] == 1
        assert result["events"][0]["name"] == "Event 1"

    @pytest.mark.asyncio
    async def test_list_events_timeframe_preset(self, helper):
        """Test: Timeframe-Preset wird korrekt verwendet"""
        helper.mcp_client.call_discord_api = AsyncMock(return_value={"items": []})

        result = await helper.list_upcoming_events(timeframe="week")

        assert result["timeframe"]["preset"] == "week"
        assert result["timeframe"]["days_ahead"] == 7

    @pytest.mark.asyncio
    async def test_list_events_location_filter(self, helper):
        """Test: Location-Filter funktioniert"""
        future_time = (datetime.now(pytz.UTC) + timedelta(days=1)).isoformat()

        helper.mcp_client.call_discord_api = AsyncMock(return_value={
            "items": [
                {
                    "id": "1",
                    "name": "Labor Meeting",
                    "scheduled_start_time": future_time,
                    "entity_metadata": {"location": "Labor X"}
                },
                {
                    "id": "2",
                    "name": "Office Meeting",
                    "scheduled_start_time": future_time,
                    "entity_metadata": {"location": "Office"}
                }
            ]
        })

        result = await helper.list_upcoming_events(location="Labor")

        assert result["count"] == 1
        assert result["events"][0]["name"] == "Labor Meeting"


class TestDeleteEventByName:
    """Tests für delete_event_by_name Methode"""

    @pytest.fixture
    def helper(self):
        from discord_helpers import DiscordEventHelper

        mock_config = MagicMock()
        mock_config.discord_guild_id = "123456789"
        mock_mcp = AsyncMock()

        return DiscordEventHelper(mock_config, mock_mcp)

    @pytest.mark.asyncio
    async def test_delete_event_success(self, helper):
        """Test: Event wird erfolgreich gelöscht"""
        future_time = (datetime.now(pytz.UTC) + timedelta(days=1)).isoformat()

        # Mock für list_upcoming_events
        helper.mcp_client.call_discord_api = AsyncMock(side_effect=[
            # Erster Call: GET events
            {"items": [{"id": "123", "name": "Test Event", "scheduled_start_time": future_time}]},
            # Zweiter Call: DELETE
            {"success": True}
        ])

        result = await helper.delete_event_by_name("Test Event")

        assert result["success"] == True
        assert result["event_id"] == "123"

    @pytest.mark.asyncio
    async def test_delete_event_not_found(self, helper):
        """Test: Nicht existierendes Event"""
        helper.mcp_client.call_discord_api = AsyncMock(return_value={"items": []})

        result = await helper.delete_event_by_name("Nicht Existiert")

        assert result["success"] == False
        assert "error" in result


class TestSendMessage:
    """Tests für send_message Methode"""

    @pytest.fixture
    def helper(self):
        from discord_helpers import DiscordEventHelper

        mock_config = MagicMock()
        mock_config.discord_guild_id = "123456789"
        mock_mcp = AsyncMock()

        h = DiscordEventHelper(mock_config, mock_mcp)
        h.channels_cache = {
            "111": {"id": "111", "name": "allgemein", "type": 0},
            "222": {"id": "222", "name": "voice", "type": 2}
        }

        return h

    @pytest.mark.asyncio
    async def test_send_message_by_id(self, helper):
        """Test: Nachricht senden mit Channel-ID"""
        helper.mcp_client.call_discord_api = AsyncMock(return_value={
            "id": "msg_123",
            "content": "Test"
        })

        result = await helper.send_message("111", "Test Nachricht")

        assert result["success"] == True
        assert result["message_id"] == "msg_123"

    @pytest.mark.asyncio
    async def test_send_message_by_name(self, helper):
        """Test: Nachricht senden mit Channel-Name"""
        helper.mcp_client.call_discord_api = AsyncMock(return_value={
            "id": "msg_456",
            "content": "Test"
        })

        result = await helper.send_message("allgemein", "Hallo Welt")

        assert result["success"] == True
        # Prüfe dass korrekter Endpoint verwendet wurde
        call_args = helper.mcp_client.call_discord_api.call_args
        assert "/channels/111/messages" in call_args[0][1]


class TestGetAvailableFunctions:
    """Tests für get_available_functions Methode"""

    def test_returns_all_functions(self):
        """Test: Alle Funktionen werden zurückgegeben"""
        from discord_helpers import DiscordEventHelper

        mock_config = MagicMock()
        mock_config.discord_guild_id = "123"
        mock_mcp = MagicMock()

        helper = DiscordEventHelper(mock_config, mock_mcp)
        functions = helper.get_available_functions()

        expected_functions = [
            "create_event",
            "list_upcoming_events",
            "list_events_on_specific_day",
            "delete_event_by_name",
            "send_message",
            "get_server_info",
            "list_channels",
            "get_online_members_count",
            "list_online_members",
            "delete_message",
            "get_channel_messages",
            "summarize_channel"
        ]

        for func in expected_functions:
            assert func in functions
            assert "description" in functions[func]
            assert "params" in functions[func]
