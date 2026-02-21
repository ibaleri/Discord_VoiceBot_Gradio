"""
Pytest Konfiguration und gemeinsame Fixtures
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

# Projekt-Root zum Python-Pfad hinzufügen
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


@pytest.fixture
def mock_config():
    """Fixture für Mock-Konfiguration"""
    config = MagicMock()
    config.discord_token = "MTk1234567890.test_token"
    config.discord_guild_id = "123456789012345678"
    config.discord_channel_id = "987654321098765432"
    config.llm_provider = "gemini"
    config.llm_model = "gemini-2.0-flash-exp"
    config.llm_available = True
    config.mcp_mode = "subprocess"
    config.debug_mode = False
    config.log_level = "INFO"
    config.speech_provider = "groq-fallback"
    config.groq_api_key = "test_groq_key"
    config.gemini_api_key = "test_gemini_key"
    return config


@pytest.fixture
def mock_mcp_client():
    """Fixture für Mock MCP Client"""
    client = AsyncMock()
    client.connected = True
    client.call_discord_api = AsyncMock(return_value={"success": True})
    return client


@pytest.fixture
def mock_gemini():
    """Fixture für Mock Gemini/LLM Client"""
    gemini = AsyncMock()
    gemini.chat_completion = AsyncMock(return_value="Mocked LLM response")
    gemini.check_spelling = AsyncMock(return_value={
        "has_errors": False,
        "corrected": "Original text"
    })
    gemini.summarize_text = AsyncMock(return_value="Zusammenfassung des Textes")
    return gemini


@pytest.fixture
def sample_events():
    """Fixture für Beispiel-Events"""
    from datetime import datetime, timedelta
    import pytz

    now = datetime.now(pytz.UTC)

    return [
        {
            "id": "event_1",
            "name": "Weekly Meeting",
            "description": "Wöchentliches Team-Meeting",
            "scheduled_start_time": (now + timedelta(days=1)).isoformat(),
            "scheduled_end_time": (now + timedelta(days=1, hours=1)).isoformat(),
            "entity_type": 3,
            "entity_metadata": {"location": "Online"}
        },
        {
            "id": "event_2",
            "name": "Workshop",
            "description": "Python Workshop",
            "scheduled_start_time": (now + timedelta(days=3)).isoformat(),
            "scheduled_end_time": (now + timedelta(days=3, hours=3)).isoformat(),
            "entity_type": 3,
            "entity_metadata": {"location": "Labor X"}
        },
        {
            "id": "event_3",
            "name": "Sprint Review",
            "description": "Ende-Sprint Review",
            "scheduled_start_time": (now + timedelta(days=7)).isoformat(),
            "scheduled_end_time": (now + timedelta(days=7, hours=2)).isoformat(),
            "entity_type": 3,
            "entity_metadata": {"location": "Online"}
        }
    ]


@pytest.fixture
def sample_channels():
    """Fixture für Beispiel-Channels"""
    return {
        "111111111": {"id": "111111111", "name": "allgemein", "type": 0},
        "222222222": {"id": "222222222", "name": "bot-commands", "type": 0},
        "333333333": {"id": "333333333", "name": "Voice Channel", "type": 2},
        "444444444": {"id": "444444444", "name": "ankündigungen", "type": 0}
    }


@pytest.fixture
def sample_messages():
    """Fixture für Beispiel-Nachrichten"""
    from datetime import datetime, timedelta
    import pytz

    now = datetime.now(pytz.UTC)

    return [
        {
            "id": "msg_1",
            "content": "Hallo zusammen!",
            "author": {"username": "user1", "global_name": "User One"},
            "timestamp": (now - timedelta(hours=1)).isoformat()
        },
        {
            "id": "msg_2",
            "content": "Wie geht's euch?",
            "author": {"username": "user2", "global_name": "User Two"},
            "timestamp": (now - timedelta(minutes=30)).isoformat()
        },
        {
            "id": "msg_3",
            "content": "Alles gut, danke!",
            "author": {"username": "user1", "global_name": "User One"},
            "timestamp": (now - timedelta(minutes=15)).isoformat()
        }
    ]


# Environment Variable Cleanup
@pytest.fixture(autouse=True)
def clean_env():
    """Bereinigt Environment-Variablen vor/nach jedem Test"""
    # Speichere originale Werte
    original_env = os.environ.copy()

    yield

    # Stelle originale Werte wieder her
    os.environ.clear()
    os.environ.update(original_env)
