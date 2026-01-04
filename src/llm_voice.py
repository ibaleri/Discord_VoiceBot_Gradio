"""
LLM API Integration für Voice und Text
Verwendet llm_client für universellen LLM-Zugriff:
- Speech-to-Text (Groq Whisper API oder Faster Whisper lokal)
- Text-Verarbeitung mit LLM (OpenAI, Groq, Gemini, Ollama)
- Konversations-Management
"""

import logging
import json
import os
from typing import Optional, List, Dict, Any
from pathlib import Path

#Lokaler Import des llm_client
from llm_client import LLMClient

#Groq Client für Whisper API
from groq import Groq

#Faster Whisper für lokales Speech-to-Text
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    WhisperModel = None

logger = logging.getLogger(__name__)


def _safe_log(text: str, max_len: int = 200) -> str:
    """Entfernt Emojis und nicht-ASCII-Zeichen für sicheres Logging"""
    if not text:
        return ""
    #Entferne alle Zeichen, die nicht in ASCII kodierbar sind (z.B. Emojis)
    safe = text.encode('ascii', errors='ignore').decode('ascii')
    return safe[:max_len] if len(safe) > max_len else safe


class LLMVoiceInterface:
    """Interface für LLM API mit Voice-Support (via llm_client)"""

    def __init__(self, config):
        self.config = config
        self.llm_client = None
        self.spell_check_client = None
        self.llm_available = False

        #LLM nur initialisieren wenn Provider konfiguriert ist
        if config.llm_provider and config.llm_available:
            self._init_llm_client(config.llm_provider, config.llm_model)
        else:
            logger.warning("Kein LLM Provider konfiguriert - Chat-Funktion deaktiviert")
            logger.info("Gehe zu Einstellungen um einen API Key einzugeben")

        #Speech-to-Text Provider konfigurieren
        self.speech_provider = config.speech_provider
        self.groq_client = None
        self.faster_whisper_model = None

        #Groq Whisper initialisieren
        if self.speech_provider in ["groq", "groq-fallback"]:
            if not config.groq_api_key:
                raise ValueError(
                    "GROQ_API_KEY nicht gesetzt.\n"
                    "Bitte GROQ_API_KEY in .env eintragen für Speech-to-Text."
                )
            self.groq_client = Groq(api_key=config.groq_api_key)
            logger.info(f"Speech-to-Text: Groq Whisper (whisper-large-v3-turbo)")

        #Faster Whisper initialisieren
        if self.speech_provider in ["faster-whisper", "groq-fallback"]:
            if not FASTER_WHISPER_AVAILABLE:
                if self.speech_provider == "faster-whisper":
                    raise ImportError(
                        "faster-whisper nicht installiert.\n"
                        "Bitte installiere: pip install faster-whisper"
                    )
                else:
                    logger.warning("faster-whisper nicht verfügbar, Fallback nicht möglich")
            else:
                try:
                    #Base Model (74MB) ---- Guter Kompromiss zwischen Geschwindigkeit und Qualität
                    self.faster_whisper_model = WhisperModel(
                        "base",               #Modellgröße: tiny, base, small, medium, large-v3
                        device="cpu",         #CPU-Modus (für GPU: "cuda")
                        compute_type="int8"   #Optimiert für CPU
                    )
                    if self.speech_provider == "faster-whisper":
                        logger.info(f"Speech-to-Text: Faster Whisper (base model, CPU)")
                    else:
                        logger.info(f"Speech-to-Text: Groq Whisper + Faster Whisper Fallback")
                except Exception as e:
                    if self.speech_provider == "faster-whisper":
                        raise Exception(f"Faster Whisper konnte nicht geladen werden: {e}")
                    else:
                        logger.warning(f"Faster Whisper Fallback nicht verfügbar: {e}")

        #Log LLM Status
        if self.llm_available:
            logger.info(f"LLM Client initialisiert: {config.llm_provider} - {config.llm_model}")

    def _init_llm_client(self, provider: str, model: str):
        """Initialisiert LLM Client mit gegebenem Provider und Modell"""
        #Setze passenden API Key als Umgebungsvariable für llm_client
        if provider == "openai" and self.config.openai_api_key:
            os.environ['OPENAI_API_KEY'] = self.config.openai_api_key
        elif provider == "groq" and self.config.groq_api_key:
            os.environ['GROQ_API_KEY'] = self.config.groq_api_key
        elif provider == "gemini" and self.config.gemini_api_key:
            os.environ['GEMINI_API_KEY'] = self.config.gemini_api_key
        #Ollama braucht keinen API Key

        #LLM Client initialisieren (flexibel)
        self.llm_client = LLMClient(
            api_choice=provider,
            llm=model,
            temperature=0.7,
            max_tokens=8192
        )

        #Schneller LLM Client für Rechtschreibprüfung (optimiert für Geschwindigkeit)
        spell_check_model = model
        if provider == "gemini":
            #Nutze Flash statt Pro für schnellere Rechtschreibprüfung
            spell_check_model = "gemini-2.5-flash" if "pro" in model.lower() else model
        elif provider == "openai":
            spell_check_model = "gpt-4o-mini" if "gpt-4o" in model else model

        self.spell_check_client = LLMClient(
            api_choice=provider,
            llm=spell_check_model,
            temperature=0.3,  #Niedrigere Temperatur für konsistente Korrektur
            max_tokens=4096   #Erhöht für längere Texte
        )

        self.llm_available = True
        logger.info(f"LLM Client initialisiert: {provider} - {model}")
        logger.info(f"Rechtschreibprüfung: {provider} - {spell_check_model} (optimiert)")

    async def speech_to_text(self, audio_file_path: str) -> str:
        """
        Konvertiert Audio-Datei zu Text

        Args:
            audio_file_path: Pfad zur Audio-Datei (.wav, .mp3, etc.)

        Returns:
            Transkribierter Text
        """
        try:
            #Prüfe ob Datei existiert
            if not Path(audio_file_path).exists():
                raise FileNotFoundError(f"Audio-Datei nicht gefunden: {audio_file_path}")

            #Provider-basierte Speech-to-Text
            if self.speech_provider == "groq":
                #Nur Groq
                return await self._speech_to_text_groq(audio_file_path)

            elif self.speech_provider == "faster-whisper":
                #Nur Faster Whisper
                return await self._speech_to_text_faster_whisper(audio_file_path)

            elif self.speech_provider == "groq-fallback":
                #Groq mit Faster Whisper Fallback
                try:
                    return await self._speech_to_text_groq(audio_file_path)
                except Exception as groq_error:
                    logger.warning(f"Groq fehlgeschlagen ({groq_error}), nutze Faster Whisper Fallback")
                    if self.faster_whisper_model:
                        return await self._speech_to_text_faster_whisper(audio_file_path)
                    else:
                        raise Exception(f"Groq Fehler und kein Fallback verfügbar: {groq_error}")

        except Exception as e:
            logger.error(f"Fehler bei Speech-to-Text: {e}", exc_info=True)
            raise

    async def _speech_to_text_groq(self, audio_file_path: str) -> str:
        """
        Konvertiert Audio zu Text via Groq Whisper API

        Args:
            audio_file_path: Pfad zur Audio-Datei

        Returns:
            Transkribierter Text
        """
        logger.info(f"Konvertiere Audio zu Text (Groq Whisper): {audio_file_path}")

        #Audio-Datei öffnen und an Groq Whisper senden
        with open(audio_file_path, "rb") as audio_file:
            transcription = self.groq_client.audio.transcriptions.create(
                file=(Path(audio_file_path).name, audio_file.read()),
                model="whisper-large-v3-turbo",  #Schnellstes und günstigstes Modell
                language="de",  #Deutsch
                response_format="text"
            )

        #Groq gibt direkt den Text zurück
        text = transcription.strip()
        logger.info(f"Transkription (Groq): {text}")
        return text

    async def _speech_to_text_faster_whisper(self, audio_file_path: str) -> str:
        """
        Konvertiert Audio zu Text via Faster Whisper (lokal)

        Args:
            audio_file_path: Pfad zur Audio-Datei

        Returns:
            Transkribierter Text
        """
        logger.info(f"Konvertiere Audio zu Text (Faster Whisper): {audio_file_path}")

        #Transkribieren
        segments, info = self.faster_whisper_model.transcribe(
            audio_file_path,
            language="de",
            beam_size=5
        )

        #Segmente zu Text kombinieren
        text = " ".join([segment.text for segment in segments]).strip()
        logger.info(f"Transkription (Faster Whisper): {text}")
        return text


    async def process_with_context(
        self,
        user_input: str,
        context: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Verarbeitet Input mit Context und Conversation History

        Args:
            user_input: Benutzer-Eingabe
            context: System-Context (verfügbare Funktionen, etc.)
            conversation_history: Bisherige Konversation

        Returns:
            LLM Antwort (strukturiert als JSON wenn möglich)
        """
        try:
            logger.info(f"Verarbeite mit Context: {user_input[:50]}...")

            #Messages für llm_client erstellen
            messages = [
                {"role": "system", "content": context},
                {"role": "user", "content": user_input}
            ]

            #LLM anfragen
            result = self.llm_client.chat_completion(messages)

            logger.info(f"LLM Context-Antwort: {_safe_log(result, 200)}...")
            return result

        except Exception as e:
            logger.error(f"Fehler bei Context-Verarbeitung: {e}", exc_info=True)
            #Fallback: Einfache Antwort
            return json.dumps({
                "message": f"Fehler bei der Verarbeitung: {str(e)}",
                "actions": []
            })

    async def check_spelling(self, text: str) -> Dict[str, Any]:
        """
        Prüft und korrigiert Rechtschreibung, Interpunktion und Grammatik mit LLM

        Args:
            text: Zu prüfender Text

        Returns:
            Dict mit has_errors, original, corrected, errors
        """
        try:
            if not text or len(text.strip()) == 0:
                return {
                    "has_errors": False,
                    "original": text,
                    "corrected": text,
                    "errors": []
                }

            #Sehr kurze Texte überspringen (< 10 Zeichen)
            if len(text.strip()) < 10:
                return {
                    "has_errors": False,
                    "original": text,
                    "corrected": text,
                    "errors": []
                }

            logger.info(f"Prüfe Text (Rechtschreibung & Interpunktion): {text[:50]}...")

            #Sehr kompakter Prompt - nur korrigierten Text zurückgeben
            prompt = f"""Korrigiere deutschen Text: Rechtschreibung, Kommata, Satzzeichen. Jeder Satz endet mit Punkt/Fragezeichen/Ausrufezeichen.

Gib NUR den korrigierten Text zurück als JSON:
{{"corrected": "..."}}

Text: {text}"""

            messages = [{"role": "user", "content": prompt}]

            #Schnelleren LLM Client für Rechtschreibprüfung nutzen
            result = self.spell_check_client.chat_completion(messages)

            #Prüfe ob Result None ist
            if result is None or not result:
                logger.warning("LLM gab keine Antwort zurück, überspringe Rechtschreibprüfung")
                return {
                    "has_errors": False,
                    "original": text,
                    "corrected": text,
                    "errors": []
                }

            #JSON extrahieren
            result = result.strip()
            if result.startswith("```json"):
                result = result.replace("```json", "").replace("```", "").strip()
            elif result.startswith("```"):
                result = result.replace("```", "").strip()

            #JSON parsen
            try:
                parsed = json.loads(result)
                corrected = parsed.get('corrected', text)

                #Prüfe ob es Änderungen gab
                has_errors = (corrected != text)

                logger.info(f"Rechtschreibung geprüft: {'Änderungen vorgenommen' if has_errors else 'Keine Fehler'}")

                return {
                    "has_errors": has_errors,
                    "original": text,
                    "corrected": corrected,
                    "errors": []  #Nicht mehr benötigt, aber für Kompatibilität
                }
            except json.JSONDecodeError:
                #Fallback bei Parse-Fehler
                logger.warning(f"Konnte JSON nicht parsen: {result[:100]}")
                return {
                    "has_errors": False,
                    "original": text,
                    "corrected": text,
                    "errors": []
                }

        except Exception as e:
            logger.error(f"Fehler bei Rechtschreibprüfung: {e}", exc_info=True)
            #Bei Fehler: Original-Text zurückgeben
            return {
                "has_errors": False,
                "original": text,
                "corrected": text,
                "errors": []
            }

    async def summarize_text(self, prompt: str) -> str:
        """
        Fasst Text zusammen oder beantwortet einen Prompt

        Args:
            prompt: Der Prompt mit dem zu verarbeitenden Text

        Returns:
            Zusammenfassung als String
        """
        try:
            logger.info(f"Erstelle Zusammenfassung...")

            messages = [{"role": "user", "content": prompt}]

            #Haupt-LLM Client für Zusammenfassung nutzen
            result = self.llm_client.chat_completion(messages)

            if result is None or not result:
                logger.warning("LLM gab keine Antwort zurück")
                return "Konnte keine Zusammenfassung erstellen."

            #Bereinige Ergebnis
            result = result.strip()

            logger.info(f"Zusammenfassung erstellt: {result[:100]}...")

            return result

        except Exception as e:
            logger.error(f"Fehler bei Zusammenfassung: {e}", exc_info=True)
            return f"Fehler bei der Zusammenfassung: {str(e)}"


#Backwards-Compatibility Alias
GeminiVoiceInterface = LLMVoiceInterface
