"""
Unit Tests für llm_client/llm_client.py
Testet den universellen LLM Client mit Multi-Provider-Support
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestLLMClientInit:
    """Tests für LLMClient Initialisierung"""

    @patch.dict(os.environ, {}, clear=True)
    @patch('llm_client.llm_client.load_dotenv')
    def test_init_auto_select_ollama_when_no_keys(self, mock_dotenv):
        """Test: Wählt automatisch Ollama wenn keine API Keys vorhanden"""
        from llm_client import LLMClient

        # Mock dass secrets.env nicht existiert
        with patch('os.path.exists', return_value=False):
            client = LLMClient()

        assert client.api_choice == "ollama"
        assert client.llm == "llama3.2:1b"

    @patch('llm_client.llm_client.load_dotenv')
    def test_init_auto_select_openai_first(self, mock_dotenv):
        """Test: Priorisiert OpenAI wenn alle Keys vorhanden"""
        env = {
            "OPENAI_API_KEY": "sk-test",
            "GROQ_API_KEY": "gsk-test",
            "GEMINI_API_KEY": "gemini-test"
        }

        with patch.dict(os.environ, env, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient()

        assert client.api_choice == "openai"

    @patch('llm_client.llm_client.load_dotenv')
    def test_init_explicit_api_choice(self, mock_dotenv):
        """Test: Explizite API-Auswahl überschreibt Auto-Selektion"""
        env = {"GEMINI_API_KEY": "gemini-test"}

        with patch.dict(os.environ, env, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(api_choice="gemini")

        assert client.api_choice == "gemini"
        assert "gemini" in client.llm.lower()

    @patch('llm_client.llm_client.load_dotenv')
    def test_init_invalid_api_choice_raises_error(self, mock_dotenv):
        """Test: Ungültige API-Auswahl wirft ValueError"""
        with patch.dict(os.environ, {}, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient

                with pytest.raises(ValueError) as exc_info:
                    LLMClient(api_choice="invalid_provider")

                assert "Invalid api_choice" in str(exc_info.value)

    @patch('llm_client.llm_client.load_dotenv')
    def test_init_custom_model(self, mock_dotenv):
        """Test: Custom Modell wird verwendet"""
        env = {"OPENAI_API_KEY": "sk-test"}

        with patch.dict(os.environ, env, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(llm="gpt-4-turbo")

        assert client.llm == "gpt-4-turbo"

    @patch('llm_client.llm_client.load_dotenv')
    def test_init_custom_temperature(self, mock_dotenv):
        """Test: Custom Temperature wird verwendet"""
        env = {"OPENAI_API_KEY": "sk-test"}

        with patch.dict(os.environ, env, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(temperature=0.3)

        assert client.temperature == 0.3

    @patch('llm_client.llm_client.load_dotenv')
    def test_init_custom_max_tokens(self, mock_dotenv):
        """Test: Custom Max Tokens wird verwendet"""
        env = {"OPENAI_API_KEY": "sk-test"}

        with patch.dict(os.environ, env, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(max_tokens=1024)

        assert client.max_tokens == 1024


class TestLLMClientDefaultModels:
    """Tests für Default-Modell-Auswahl"""

    @patch('llm_client.llm_client.load_dotenv')
    def test_default_model_openai(self, mock_dotenv):
        """Test: Default Modell für OpenAI"""
        env = {"OPENAI_API_KEY": "sk-test"}

        with patch.dict(os.environ, env, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(api_choice="openai")

        assert client.llm == "gpt-4o-mini"

    @patch('llm_client.llm_client.load_dotenv')
    def test_default_model_groq(self, mock_dotenv):
        """Test: Default Modell für Groq"""
        env = {"GROQ_API_KEY": "gsk-test"}

        with patch.dict(os.environ, env, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(api_choice="groq")

        assert "kimi" in client.llm.lower() or "llama" in client.llm.lower()

    @patch('llm_client.llm_client.load_dotenv')
    def test_default_model_gemini(self, mock_dotenv):
        """Test: Default Modell für Gemini"""
        env = {"GEMINI_API_KEY": "gemini-test"}

        with patch.dict(os.environ, env, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(api_choice="gemini")

        assert "gemini" in client.llm.lower()

    @patch('llm_client.llm_client.load_dotenv')
    def test_default_model_ollama(self, mock_dotenv):
        """Test: Default Modell für Ollama"""
        with patch.dict(os.environ, {}, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(api_choice="ollama")

        assert "llama" in client.llm.lower()


class TestLLMClientChatCompletion:
    """Tests für chat_completion Methode"""

    @patch('llm_client.llm_client.load_dotenv')
    @patch('llm_client.llm_client.OpenAI')
    def test_chat_completion_openai(self, mock_openai_class, mock_dotenv):
        """Test: Chat Completion mit OpenAI"""
        env = {"OPENAI_API_KEY": "sk-test"}

        # Mock OpenAI Response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello, I'm an AI assistant!"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        with patch.dict(os.environ, env, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(api_choice="openai")

        messages = [{"role": "user", "content": "Hello!"}]
        response = client.chat_completion(messages)

        assert response == "Hello, I'm an AI assistant!"
        mock_client.chat.completions.create.assert_called_once()

    @patch('llm_client.llm_client.load_dotenv')
    @patch('llm_client.llm_client.Groq')
    def test_chat_completion_groq(self, mock_groq_class, mock_dotenv):
        """Test: Chat Completion mit Groq"""
        env = {"GROQ_API_KEY": "gsk-test"}

        # Mock Groq Response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Groq response here!"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq_class.return_value = mock_client

        with patch.dict(os.environ, env, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(api_choice="groq")

        messages = [{"role": "user", "content": "Test message"}]
        response = client.chat_completion(messages)

        assert response == "Groq response here!"

    @patch('llm_client.llm_client.load_dotenv')
    @patch('llm_client.llm_client.ollama')
    def test_chat_completion_ollama(self, mock_ollama, mock_dotenv):
        """Test: Chat Completion mit Ollama"""
        # Mock Ollama Response
        mock_ollama.chat.return_value = {
            "message": {"content": "Ollama local response!"}
        }

        with patch.dict(os.environ, {}, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(api_choice="ollama")

        messages = [{"role": "user", "content": "Local test"}]
        response = client.chat_completion(messages)

        assert response == "Ollama local response!"
        mock_ollama.chat.assert_called_once()

    @patch('llm_client.llm_client.load_dotenv')
    def test_chat_completion_no_client_raises_error(self, mock_dotenv):
        """Test: Fehlender Client wirft RuntimeError"""
        with patch.dict(os.environ, {}, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient

                # Mock dass OpenAI nicht verfügbar ist
                with patch('llm_client.llm_client.OpenAI', None):
                    client = LLMClient(api_choice="ollama")
                    # Überschreibe api_choice um Fehler zu provozieren
                    client.api_choice = "openai"
                    client.client = None

        messages = [{"role": "user", "content": "Test"}]

        with pytest.raises(RuntimeError) as exc_info:
            client.chat_completion(messages)

        assert "not available" in str(exc_info.value)


class TestLLMClientRepr:
    """Tests für __repr__ Methode"""

    @patch('llm_client.llm_client.load_dotenv')
    def test_repr_contains_info(self, mock_dotenv):
        """Test: __repr__ enthält relevante Informationen"""
        env = {"OPENAI_API_KEY": "sk-test"}

        with patch.dict(os.environ, env, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(api_choice="openai", llm="gpt-4", temperature=0.5)

        repr_str = repr(client)

        assert "openai" in repr_str
        assert "gpt-4" in repr_str
        assert "0.5" in repr_str


class TestLLMClientGeminiCompatibility:
    """Tests für Gemini OpenAI-Kompatibilitätsmodus"""

    @patch('llm_client.llm_client.load_dotenv')
    @patch('llm_client.llm_client.OpenAI')
    def test_gemini_uses_openai_compatibility_layer(self, mock_openai_class, mock_dotenv):
        """Test: Gemini nutzt OpenAI-Kompatibilitätsschicht"""
        env = {"GEMINI_API_KEY": "gemini-test"}

        with patch.dict(os.environ, env, clear=True):
            with patch('os.path.exists', return_value=False):
                from llm_client import LLMClient
                client = LLMClient(api_choice="gemini")

        # Prüfe dass OpenAI mit Gemini base_url aufgerufen wurde
        mock_openai_class.assert_called_with(
            api_key="gemini-test",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
