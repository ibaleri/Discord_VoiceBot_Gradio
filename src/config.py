"""
Konfiguration für Discord Voice Bot
Lädt Environment-Variablen und validiert Einstellungen
"""

import os
import logging
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class Config:
    """Konfigurationsklasse für den Bot"""

    def __init__(self, env_file: Optional[str] = ".env"):
        """
        Lädt Konfiguration aus .env Datei

        Args:
            env_file: Pfad zur .env Datei
        """
        # .env Datei laden
        if env_file and Path(env_file).exists():
            load_dotenv(env_file)
            logger.info(f"Konfiguration geladen aus: {env_file}")
        else:
            logger.warning(f".env Datei nicht gefunden: {env_file}")

        # Discord Konfiguration
        self.discord_token = self._get_env("DISCORD_TOKEN", required=True)
        self.discord_guild_id = self._get_env("DISCORD_GUILD_ID", required=True)
        self.discord_channel_id = self._get_env("DISCORD_CHANNEL_ID")

        # LLM Konfiguration (flexibel: OpenAI, Groq, Gemini, Ollama)
        self.llm_provider = self._get_env("LLM_PROVIDER", default="gemini")
        self.llm_model = self._get_env("LLM_MODEL", default="gemini-2.5-flash")

        # API Keys (je nach Provider)
        self.openai_api_key = self._get_env("OPENAI_API_KEY")
        self.groq_api_key = self._get_env("GROQ_API_KEY")
        self.gemini_api_key = self._get_env("GEMINI_API_KEY")

        # Backwards compatibility: Falls GEMINI_MODEL gesetzt, nutze es
        legacy_gemini_model = self._get_env("GEMINI_MODEL")
        if legacy_gemini_model and not self._get_env("LLM_MODEL"):
            self.llm_model = legacy_gemini_model

        # Validiere dass passender API Key vorhanden ist
        self._validate_llm_keys()

        # MCP Konfiguration
        self.mcp_mode = self._get_env("MCP_MODE", default="subprocess")  # subprocess oder remote
        self.mcp_server_url = self._get_env("MCP_SERVER_URL")  # Für remote mode
        self.mcp_api_key = self._get_env("MCP_API_KEY")  # fuer Remote-Auth

        # MCP Server Konfig (nur fuer mcp_server.py relevant)
        self.mcp_server_host = self._get_env("MCP_SERVER_HOST", default="0.0.0.0")
        self.mcp_server_port = int(self._get_env("MCP_SERVER_PORT", default="8000"))
        self.mcp_transport = self._get_env("MCP_TRANSPORT", default="sse")

        # App Konfiguration
        self.debug_mode = self._get_env("DEBUG_MODE", default="false").lower() == "true"
        self.log_level = self._get_env("LOG_LEVEL", default="INFO")

        # Voice Konfiguration
        self.voice_language = self._get_env("VOICE_LANGUAGE", default="de-DE")
        self.enable_tts = self._get_env("ENABLE_TTS", default="false").lower() == "true"

        # Speech-to-Text Provider
        self.speech_provider = self._get_env("SPEECH_PROVIDER", default="groq-fallback")

        # Validierung
        self._validate()

    def _get_env(self, key: str, required: bool = False, default: Optional[str] = None) -> Optional[str]:
        """
        Holt Environment-Variable

        Args:
            key: Variable-Name
            required: Ob Variable erforderlich ist
            default: Default-Wert

        Returns:
            Variable-Wert oder None

        Raises:
            ValueError: Wenn required=True und Variable nicht gesetzt
        """
        value = os.getenv(key, default)

        if required and not value:
            raise ValueError(
                f"Erforderliche Environment-Variable nicht gesetzt: {key}\n"
                f"Bitte in .env Datei eintragen oder als Environment-Variable setzen."
            )

        return value

    def _validate_llm_keys(self):
        """Validiert LLM Konfiguration - erlaubt Start ohne LLM"""
        provider = self.llm_provider.lower() if self.llm_provider else None

        # Flag ob LLM verfügbar ist
        self.llm_available = False
        self.llm_error = None

        # Kein Provider gesetzt - OK, kann später über UI konfiguriert werden
        if not provider or provider == "none":
            logger.warning("Kein LLM Provider konfiguriert - Chat-Funktion deaktiviert bis API Key eingegeben wird")
            self.llm_provider = None
            self.llm_model = None
            return

        # Provider validieren
        if provider not in ["openai", "groq", "gemini", "ollama"]:
            logger.warning(f"Ungültiger LLM_PROVIDER: {provider} - Chat deaktiviert")
            self.llm_error = f"Ungültiger Provider: {provider}"
            self.llm_provider = None
            self.llm_model = None
            return

        # API Key prüfen (Warnung statt Fehler)
        if provider == "openai" and not self.openai_api_key:
            logger.warning("LLM_PROVIDER=openai, aber OPENAI_API_KEY fehlt - Chat deaktiviert")
            self.llm_error = "OpenAI API Key fehlt"
            self.llm_provider = None
            self.llm_model = None
            return
        elif provider == "groq" and not self.groq_api_key:
            logger.warning("LLM_PROVIDER=groq, aber GROQ_API_KEY fehlt - Chat deaktiviert")
            self.llm_error = "Groq API Key fehlt"
            self.llm_provider = None
            self.llm_model = None
            return
        elif provider == "gemini" and not self.gemini_api_key:
            logger.warning("LLM_PROVIDER=gemini, aber GEMINI_API_KEY fehlt - Chat deaktiviert")
            self.llm_error = "Gemini API Key fehlt"
            self.llm_provider = None
            self.llm_model = None
            return
        elif provider == "ollama":
            # Ollama benötigt keinen API Key (läuft lokal)
            logger.info("Ollama ausgewählt - läuft lokal, kein API Key benötigt")

        # Alles OK - LLM ist verfügbar
        self.llm_available = True
        logger.info(f"LLM Provider validiert: {provider} [OK]")

    def _validate(self):
        """Validiert Konfiguration"""

        # Discord Token Format prüfen
        if not self.discord_token.startswith(('Bot ', 'MTk')):
            logger.warning(
                "Discord Token hat ungewöhnliches Format. "
                "Stelle sicher, dass es ein gültiger Bot Token ist."
            )

        # LLM Provider und Model Info loggen
        logger.info(f"LLM Provider: {self.llm_provider}")
        logger.info(f"LLM Model: {self.llm_model}")

        # MCP Mode prüfen
        if self.mcp_mode not in ["subprocess", "remote"]:
            raise ValueError(f"Ungültiger MCP_MODE: {self.mcp_mode}. Muss 'subprocess' oder 'remote' sein.")

        if self.mcp_mode == "remote" and not self.mcp_server_url:
            raise ValueError("MCP_SERVER_URL muss gesetzt sein wenn MCP_MODE=remote")

        # Transport pruefen
        valid_transports = ["sse", "streamable-http", "http"]
        if self.mcp_transport not in valid_transports:
            raise ValueError(
                f"Ungültiger MCP_TRANSPORT: {self.mcp_transport}. "
                f"Muss einer sein von: {', '.join(valid_transports)}"
            )

        # Speech Provider prüfen
        valid_speech_providers = ["groq", "faster-whisper", "groq-fallback"]
        if self.speech_provider not in valid_speech_providers:
            raise ValueError(
                f"Ungültiger SPEECH_PROVIDER: {self.speech_provider}\n"
                f"Muss einer sein von: {', '.join(valid_speech_providers)}"
            )

        # Groq API Key prüfen wenn Groq verwendet wird
        if self.speech_provider in ["groq", "groq-fallback"] and not self.groq_api_key:
            raise ValueError(
                f"SPEECH_PROVIDER={self.speech_provider} benötigt GROQ_API_KEY.\n"
                "Bitte GROQ_API_KEY in .env eintragen."
            )

        logger.info("Konfiguration validiert [OK]")

    def print_config(self, hide_secrets: bool = True):
        """
        Druckt Konfiguration (für Debugging)

        Args:
            hide_secrets: Ob Secrets versteckt werden sollen
        """
        def mask(value: str, show_chars: int = 4) -> str:
            """Maskiert Secret-Werte"""
            if not value or not hide_secrets:
                return value
            if len(value) <= show_chars:
                return "*" * len(value)
            return value[:show_chars] + "*" * (len(value) - show_chars)

        print("\n" + "="*60)
        print("KONFIGURATION")
        print("="*60)
        print(f"Discord Token:      {mask(self.discord_token)}")
        print(f"Discord Guild ID:   {self.discord_guild_id}")
        print(f"Discord Channel ID: {self.discord_channel_id or 'nicht gesetzt'}")
        print(f"\nLLM Provider:       {self.llm_provider}")
        print(f"LLM Model:          {self.llm_model}")
        if self.openai_api_key:
            print(f"OpenAI API Key:     {mask(self.openai_api_key)}")
        if self.groq_api_key:
            print(f"Groq API Key:       {mask(self.groq_api_key)}")
        if self.gemini_api_key:
            print(f"Gemini API Key:     {mask(self.gemini_api_key)}")
        print(f"\nMCP Mode:           {self.mcp_mode}")
        print(f"MCP Server URL:     {self.mcp_server_url or 'nicht gesetzt'}")
        print(f"MCP Server Host:    {self.mcp_server_host}")
        print(f"MCP Server Port:    {self.mcp_server_port}")
        print(f"MCP Transport:      {self.mcp_transport}")
        print(f"Debug Mode:         {self.debug_mode}")
        print(f"Log Level:          {self.log_level}")
        print(f"\nVoice Language:     {self.voice_language}")
        print(f"TTS Enabled:        {self.enable_tts}")
        print(f"Speech Provider:    {self.speech_provider}")
        print("="*60 + "\n")
