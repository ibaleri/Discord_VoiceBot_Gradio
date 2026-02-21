"""
Unit Tests für config.py
Testet die Konfigurationsklasse und ihre Validierung
"""

import os
import pytest
from unittest.mock import patch, MagicMock


class TestConfig:
    """Tests für die Config-Klasse"""

    @pytest.fixture
    def mock_env_vars(self):
        """Fixture für Mock-Environment-Variablen"""
        return {
            "DISCORD_TOKEN": "MTk1234567890.test_token",
            "DISCORD_GUILD_ID": "123456789012345678",
            "DISCORD_CHANNEL_ID": "987654321098765432",
            "LLM_PROVIDER": "gemini",
            "LLM_MODEL": "gemini-2.0-flash-exp",
            "GEMINI_API_KEY": "test_gemini_key_123",
            "GROQ_API_KEY": "test_groq_key_456",
            "MCP_MODE": "subprocess",
            "DEBUG_MODE": "false",
            "LOG_LEVEL": "INFO",
            "VOICE_LANGUAGE": "de-DE",
            "ENABLE_TTS": "false",
            "SPEECH_PROVIDER": "groq-fallback"
        }

    @patch.dict(os.environ, {}, clear=True)
    @patch('config.load_dotenv')
    @patch('config.Path')
    def test_config_missing_required_vars(self, mock_path, mock_dotenv):
        """Test: Config wirft Fehler bei fehlenden erforderlichen Variablen"""
        mock_path.return_value.exists.return_value = False

        from config import Config

        with pytest.raises(ValueError) as exc_info:
            Config(env_file=None)

        assert "DISCORD_TOKEN" in str(exc_info.value)

    @patch('config.load_dotenv')
    @patch('config.Path')
    def test_config_loads_successfully(self, mock_path, mock_dotenv, mock_env_vars):
        """Test: Config lädt erfolgreich mit gültigen Variablen"""
        mock_path.return_value.exists.return_value = True

        with patch.dict(os.environ, mock_env_vars, clear=True):
            from config import Config
            config = Config(env_file=".env")

            assert config.discord_token == "MTk1234567890.test_token"
            assert config.discord_guild_id == "123456789012345678"
            assert config.llm_provider == "gemini"
            assert config.llm_model == "gemini-2.0-flash-exp"
            assert config.llm_available == True

    @patch('config.load_dotenv')
    @patch('config.Path')
    def test_config_llm_provider_validation(self, mock_path, mock_dotenv, mock_env_vars):
        """Test: LLM Provider-Validierung"""
        mock_path.return_value.exists.return_value = True

        # Ungültiger Provider
        invalid_env = mock_env_vars.copy()
        invalid_env["LLM_PROVIDER"] = "invalid_provider"

        with patch.dict(os.environ, invalid_env, clear=True):
            from config import Config
            config = Config(env_file=".env")

            # Bei ungültigem Provider sollte llm_provider None sein
            assert config.llm_provider is None
            assert config.llm_available == False

    @patch('config.load_dotenv')
    @patch('config.Path')
    def test_config_mcp_mode_validation(self, mock_path, mock_dotenv, mock_env_vars):
        """Test: MCP Mode-Validierung"""
        mock_path.return_value.exists.return_value = True

        # Ungültiger MCP Mode
        invalid_env = mock_env_vars.copy()
        invalid_env["MCP_MODE"] = "invalid_mode"

        with patch.dict(os.environ, invalid_env, clear=True):
            from config import Config

            with pytest.raises(ValueError) as exc_info:
                Config(env_file=".env")

            assert "MCP_MODE" in str(exc_info.value)

    @patch('config.load_dotenv')
    @patch('config.Path')
    def test_config_speech_provider_validation(self, mock_path, mock_dotenv, mock_env_vars):
        """Test: Speech Provider-Validierung"""
        mock_path.return_value.exists.return_value = True

        # Ungültiger Speech Provider
        invalid_env = mock_env_vars.copy()
        invalid_env["SPEECH_PROVIDER"] = "invalid_speech"

        with patch.dict(os.environ, invalid_env, clear=True):
            from config import Config

            with pytest.raises(ValueError) as exc_info:
                Config(env_file=".env")

            assert "SPEECH_PROVIDER" in str(exc_info.value)

    @patch('config.load_dotenv')
    @patch('config.Path')
    def test_config_debug_mode_boolean(self, mock_path, mock_dotenv, mock_env_vars):
        """Test: Debug Mode wird korrekt zu Boolean konvertiert"""
        mock_path.return_value.exists.return_value = True

        # Debug Mode = true
        env_with_debug = mock_env_vars.copy()
        env_with_debug["DEBUG_MODE"] = "true"

        with patch.dict(os.environ, env_with_debug, clear=True):
            from config import Config
            config = Config(env_file=".env")
            assert config.debug_mode == True

        # Debug Mode = false
        env_without_debug = mock_env_vars.copy()
        env_without_debug["DEBUG_MODE"] = "false"

        with patch.dict(os.environ, env_without_debug, clear=True):
            from config import Config
            config = Config(env_file=".env")
            assert config.debug_mode == False

    @patch('config.load_dotenv')
    @patch('config.Path')
    def test_config_ollama_no_api_key_needed(self, mock_path, mock_dotenv, mock_env_vars):
        """Test: Ollama benötigt keinen API Key"""
        mock_path.return_value.exists.return_value = True

        ollama_env = mock_env_vars.copy()
        ollama_env["LLM_PROVIDER"] = "ollama"
        # Entferne LLM API Keys (aber behalte GROQ für Speech Provider)
        ollama_env.pop("GEMINI_API_KEY", None)
        ollama_env.pop("OPENAI_API_KEY", None)
        # Groq bleibt für SPEECH_PROVIDER=groq-fallback

        with patch.dict(os.environ, ollama_env, clear=True):
            from config import Config
            config = Config(env_file=".env")

            assert config.llm_provider == "ollama"
            assert config.llm_available == True

    @patch('config.load_dotenv')
    @patch('config.Path')
    def test_config_gemini_model_backwards_compatibility(self, mock_path, mock_dotenv, mock_env_vars):
        """Test: Backwards-Kompatibilität für GEMINI_MODEL"""
        mock_path.return_value.exists.return_value = True

        legacy_env = mock_env_vars.copy()
        legacy_env.pop("LLM_MODEL", None)
        legacy_env["GEMINI_MODEL"] = "gemini-1.5-pro"

        with patch.dict(os.environ, legacy_env, clear=True):
            from config import Config
            config = Config(env_file=".env")

            assert config.llm_model == "gemini-1.5-pro"

    @patch('config.load_dotenv')
    @patch('config.Path')
    def test_config_print_config_masks_secrets(self, mock_path, mock_dotenv, mock_env_vars, capsys):
        """Test: print_config maskiert sensible Daten"""
        mock_path.return_value.exists.return_value = True

        with patch.dict(os.environ, mock_env_vars, clear=True):
            from config import Config
            config = Config(env_file=".env")
            config.print_config(hide_secrets=True)

            captured = capsys.readouterr()
            # Token sollte maskiert sein (nur erste 4 Zeichen sichtbar)
            assert "MTk1" in captured.out
            assert "test_token" not in captured.out


class TestConfigMultiProvider:
    """Tests für Multi-LLM-Provider Unterstützung"""

    @pytest.fixture
    def base_env(self):
        """Basis-Environment ohne LLM-spezifische Variablen"""
        return {
            "DISCORD_TOKEN": "MTk1234567890.test_token",
            "DISCORD_GUILD_ID": "123456789012345678",
            "MCP_MODE": "subprocess",
            "SPEECH_PROVIDER": "groq-fallback",
            "GROQ_API_KEY": "test_groq_key"
        }

    @patch('config.load_dotenv')
    @patch('config.Path')
    def test_openai_provider(self, mock_path, mock_dotenv, base_env):
        """Test: OpenAI Provider Konfiguration"""
        mock_path.return_value.exists.return_value = True

        env = base_env.copy()
        env["LLM_PROVIDER"] = "openai"
        env["OPENAI_API_KEY"] = "sk-test-openai-key"

        with patch.dict(os.environ, env, clear=True):
            from config import Config
            config = Config(env_file=".env")

            assert config.llm_provider == "openai"
            assert config.llm_available == True
            assert config.openai_api_key == "sk-test-openai-key"

    @patch('config.load_dotenv')
    @patch('config.Path')
    def test_groq_provider(self, mock_path, mock_dotenv, base_env):
        """Test: Groq Provider Konfiguration"""
        mock_path.return_value.exists.return_value = True

        env = base_env.copy()
        env["LLM_PROVIDER"] = "groq"
        env["GROQ_API_KEY"] = "gsk-test-groq-key"

        with patch.dict(os.environ, env, clear=True):
            from config import Config
            config = Config(env_file=".env")

            assert config.llm_provider == "groq"
            assert config.llm_available == True

    @patch('config.load_dotenv')
    @patch('config.Path')
    def test_provider_without_api_key_disables_llm(self, mock_path, mock_dotenv, base_env):
        """Test: Provider ohne API Key deaktiviert LLM"""
        mock_path.return_value.exists.return_value = True

        env = base_env.copy()
        env["LLM_PROVIDER"] = "openai"
        # Kein OPENAI_API_KEY gesetzt

        with patch.dict(os.environ, env, clear=True):
            from config import Config
            config = Config(env_file=".env")

            assert config.llm_provider is None
            assert config.llm_available == False
            assert "OpenAI API Key fehlt" in config.llm_error
