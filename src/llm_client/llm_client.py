"""LLM Client Module für universelle LLM-API Zugriffe."""

import json
import logging
import os
from typing import Any, Literal

logger = logging.getLogger(__name__)

from dotenv import load_dotenv

# Optionale Imports – falls nicht installiert, wird das erkannt
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore

try:
    from groq import Groq
except ImportError:
    Groq = None  # type: ignore

try:
    import ollama
except ImportError:
    ollama = None  # type: ignore


class LLMClient:
    """Eine universelle Klasse zur Nutzung von OpenAI, Groq, Gemini oder Ollama.

    Diese Klasse erkennt automatisch verfügbare API-Keys und wählt die
    entsprechende API oder erlaubt manuelle Steuerung per Parameter.

    Attributes:
        api_choice: Die gewählte API ('openai', 'groq', 'gemini' oder 'ollama').
        llm: Name des verwendeten Modells.
        temperature: Sampling-Temperatur für die Generierung.
        max_tokens: Maximale Anzahl zu generierender Tokens.
        keep_alive: Ollama-spezifisch - wie lange Modell im Speicher bleibt.
        client: Instanz des gewählten API-Clients.
        openai_api_key: OpenAI API Key (falls vorhanden).
        groq_api_key: Groq API Key (falls vorhanden).
        gemini_api_key: Gemini API Key (falls vorhanden).

    Examples:
        >>> # Automatische API-Auswahl basierend auf verfügbaren Keys
        >>> client = LLMClient()
        >>> messages = [{"role": "user", "content": "Hello!"}]
        >>> response = client.chat_completion(messages)

        >>> # Manuell Gemini wählen
        >>> client = LLMClient(api_choice="gemini", llm="gemini-2.5-flash")
    """

    def __init__(
        self,
        llm: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        api_choice: Literal["openai", "groq", "gemini", "ollama"] | None = None,
        secrets_path: str = "secrets.env",
        keep_alive: str = "5m",
    ) -> None:
        """Initialisiert den LLM Client.

        Args:
            llm: Name des Modells. Wenn None, wird ein Default-Modell gewählt.
            temperature: Sampling-Temperatur (0.0 bis 2.0). Standard: 0.7.
            max_tokens: Maximale Anzahl zu generierender Tokens. Standard: 512.
            api_choice: Explizite API-Wahl ('openai', 'groq', 'gemini', 'ollama').
                Wenn None, wird automatisch gewählt.
            secrets_path: Pfad zur secrets.env-Datei. Standard: "secrets.env".
            keep_alive: Ollama-Parameter für Modell-Caching. Standard: "5m".

        Raises:
            ValueError: Wenn api_choice einen ungültigen Wert hat.

        Examples:
            >>> client = LLMClient(llm="gpt-4o", temperature=0.5)
            >>> client = LLMClient(api_choice="gemini", llm="gemini-2.5-flash")
        """
        # 1. Lade secrets.env, falls vorhanden
        if os.path.exists(secrets_path):
            load_dotenv(secrets_path)

        self.openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
        self.groq_api_key: str | None = os.getenv("GROQ_API_KEY")
        self.gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")

        # 2. Fallback für Google Colab – Keys einzeln und robust prüfen
        import sys
        if ("google.colab" in sys.modules or "COLAB_GPU" in os.environ):
            try:
                from google.colab import userdata
                try:
                    if not self.openai_api_key:
                        self.openai_api_key = userdata.get("OPENAI_API_KEY")
                except Exception:
                    pass
                try:
                    if not self.groq_api_key:
                        self.groq_api_key = userdata.get("GROQ_API_KEY")
                except Exception:
                    pass
                try:
                    if not self.gemini_api_key:
                        self.gemini_api_key = userdata.get("GEMINI_API_KEY")
                except Exception:
                    pass
            except Exception:
                pass

        # 3. Automatische API-Auswahl
        if api_choice is None:
            if self.openai_api_key:
                self.api_choice: str = "openai"
            elif self.groq_api_key:
                self.api_choice = "groq"
            elif self.gemini_api_key:
                self.api_choice = "gemini"
            else:
                if ("google.colab" in sys.modules or "COLAB_GPU" in os.environ):
                    raise RuntimeError(
                        "Kein API-Key gefunden. Bitte OPENAI_API_KEY, GROQ_API_KEY "
                        "oder GEMINI_API_KEY in Colab-Umgebung setzen."
                    )
                else:
                    self.api_choice = "ollama"
        else:
            valid_choices = {"openai", "groq", "gemini", "ollama"}
            if api_choice.lower() not in valid_choices:
                raise ValueError(
                    f"Invalid api_choice: {api_choice}. " f"Must be one of {valid_choices}"
                )
            self.api_choice = api_choice.lower()

        # 4. Default-Modellauswahl
        if llm:
            self.llm: str = llm
        else:
            if self.api_choice == "openai":
                self.llm = "gpt-4o-mini"
            elif self.api_choice == "groq":
                self.llm = "moonshotai/kimi-k2-instruct-0905"
            elif self.api_choice == "gemini":
                self.llm = "gemini-2.0-flash-exp"
            else:
                self.llm = "llama3.2:1b"

        self.temperature: float = temperature
        self.max_tokens: int = max_tokens
        self.keep_alive: str = keep_alive

        # 5. Clients vorbereiten
        self.client: Any | None = None
        if self.api_choice == "openai" and OpenAI:
            self.client = OpenAI(api_key=self.openai_api_key)
        elif self.api_choice == "groq" and Groq:
            self.client = Groq(api_key=self.groq_api_key)
        elif self.api_choice == "gemini" and OpenAI:
            # Nutze OpenAI-Kompatibilitätsmodus für Gemini
            self.client = OpenAI(
                api_key=self.gemini_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )

    def chat_completion(self, messages: list[dict[str, str]]) -> str:
        """Führt eine Chat-Completion mit der gewählten API aus.

        Args:
            messages: Liste von Nachrichten im Chat-Format.
                Jede Nachricht ist ein Dict mit 'role' und 'content' Keys.
                Beispiel: [{"role": "user", "content": "Hello!"}]

        Returns:
            Der generierte Text als String.

        Raises:
            RuntimeError: Wenn der gewählte Client nicht verfügbar ist.
            ValueError: Wenn api_choice ungültig ist.

        Examples:
            >>> client = LLMClient()
            >>> messages = [
            ...     {"role": "system", "content": "You are helpful."},
            ...     {"role": "user", "content": "Explain AI."}
            ... ]
            >>> response = client.chat_completion(messages)
            >>> print(response)
        """
        if self.api_choice == "openai":
            if not self.client:
                raise RuntimeError("OpenAI client not available or not installed.")

            # GPT-5 und o1/o3 Modelle haben andere Parameter-Anforderungen:
            # - max_completion_tokens statt max_tokens
            # - temperature wird nicht unterstützt (nur default=1)
            is_new_model = self.llm.startswith(('gpt-5', 'o1', 'o3'))

            if is_new_model:
                # GPT-5/o1/o3: Kein temperature, max_completion_tokens statt max_tokens
                response = self.client.chat.completions.create(
                    model=self.llm,
                    messages=messages,
                    max_completion_tokens=self.max_tokens,
                )
            else:
                # GPT-4/3.5: Alte Parameter
                response = self.client.chat.completions.create(
                    model=self.llm,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
            return response.choices[0].message.content

        elif self.api_choice == "groq":
            if not self.client:
                raise RuntimeError("Groq client not available or not installed.")
            response = self.client.chat.completions.create(
                model=self.llm,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.choices[0].message.content

        elif self.api_choice == "gemini":
            if not self.client:
                raise RuntimeError("Gemini client not available or not installed.")
            response = self.client.chat.completions.create(
                model=self.llm,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            # Debug: Prüfe was zurückkommt
            if not response or not response.choices:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Gemini gab leere Response zurück. Response: {response}")
                return None

            content = response.choices[0].message.content
            if not content:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Gemini message.content ist None. Response: {response}")
                logger.error(f"Choices: {response.choices}")
                logger.error(f"Message: {response.choices[0].message}")

            return content

        elif self.api_choice == "ollama":
            if not ollama:
                raise RuntimeError(
                    "Ollama Python package not available. "
                    "Please install it via `pip install ollama`."
                )
            response = ollama.chat(
                model=self.llm,
                messages=messages,
                stream=False,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                    "repeat_penalty": 1.2,
                    "top_k": 10,
                    "top_p": 0.5,
                },
                keep_alive=self.keep_alive,
            )
            return response["message"]["content"]

        else:
            raise ValueError(f"Unsupported API choice: {self.api_choice}")

    def chat_completion_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> dict[str, Any]:
        """Chat-Completion mit nativen Tool-Calls (alle Provider).
        Gibt normalisiertes dict mit role, content und tool_calls zurueck."""
        if self.api_choice in ("openai", "groq", "gemini"):
            if not self.client:
                raise RuntimeError(f"{self.api_choice} client not available.")

            kwargs: dict[str, Any] = {
                "model": self.llm,
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
            }

            is_new_model = self.api_choice == "openai" and self.llm.startswith(
                ("gpt-5", "o1", "o3")
            )
            if is_new_model:
                kwargs["max_completion_tokens"] = self.max_tokens
            else:
                kwargs["temperature"] = self.temperature
                kwargs["max_tokens"] = self.max_tokens

            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            tool_calls_data = None
            if message.tool_calls:
                tool_calls_data = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]

            return {
                "role": "assistant",
                "content": message.content,
                "tool_calls": tool_calls_data,
            }

        elif self.api_choice == "ollama":
            if not ollama:
                raise RuntimeError("Ollama Python package not available.")

            response = ollama.chat(
                model=self.llm,
                messages=messages,
                tools=tools,
                stream=False,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
                keep_alive=self.keep_alive,
            )
            message = response["message"]

            tool_calls_data = None
            if message.get("tool_calls"):
                tool_calls_data = [
                    {
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": json.dumps(
                                tc["function"]["arguments"], ensure_ascii=False
                            )
                            if isinstance(tc["function"]["arguments"], dict)
                            else tc["function"]["arguments"],
                        },
                    }
                    for i, tc in enumerate(message["tool_calls"])
                ]

            return {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": tool_calls_data,
            }

        else:
            raise ValueError(f"Unsupported API choice: {self.api_choice}")

    def __repr__(self) -> str:
        """Gibt eine String-Repräsentation des Clients zurück.

        Returns:
            String-Repräsentation mit API und Modell-Info.
        """
        return (
            f"LLMClient(api={self.api_choice}, model={self.llm}, "
            f"temperature={self.temperature})"
        )
