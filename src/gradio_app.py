"""
Discord Voice Bot - Gradio GUI
Moderne Web-basierte Benutzeroberfläche mit Gradio
"""

import gradio as gr
import asyncio
import logging
import os
import sys
import calendar
import json
import re
from datetime import datetime, timedelta
from threading import Thread
import pytz
import dateparser

#Projekt-Imports
from config import Config
from mcp_client import DiscordMCPClient
from llm_voice import LLMVoiceInterface
from discord_helpers import DiscordEventHelper

#Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('discord_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

#Import _safe_log von llm_voice (keine Duplikation)
from llm_voice import _safe_log


class DiscordBotGradio:
    """Discord Voice Bot mit Gradio Web-Interface"""

    def __init__(self):
        self.config = None
        self.mcp_client = None
        self.gemini = None
        self.helper = None
        self.is_initialized = False

        #Event Loop für asynchrone Operationen
        self.loop = None
        self.loop_thread = None
        self._start_event_loop()

    def _start_event_loop(self):
        """Startet einen persistenten Event Loop in einem Thread"""
        self.loop = asyncio.new_event_loop()

        def run_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        self.loop_thread = Thread(target=run_loop, daemon=True)
        self.loop_thread.start()
        logger.info("Event Loop gestartet")

    def _run_async(self, coro):
        """Führt eine Coroutine im persistenten Event Loop aus"""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    async def initialize(self):
        """Bot initialisieren"""
        try:
            logger.info("Initialisiere Discord Bot...")

            #Konfiguration laden
            self.config = Config()
            logger.info("Konfiguration geladen")

            #MCP Client initialisieren
            self.mcp_client = DiscordMCPClient(self.config)
            await self.mcp_client.connect()
            logger.info("MCP Client verbunden")

            #LLM Voice Interface initialisieren
            self.gemini = LLMVoiceInterface(self.config)
            logger.info("LLM Voice Interface initialisiert")

            #Discord Helper initialisieren
            self.helper = DiscordEventHelper(self.config, self.mcp_client, self.gemini)
            await self.helper.initialize()
            logger.info("Discord Helper initialisiert")

            #Audio Recorder nicht benötigt ------ Gradio nutzt Browser-Audio direkt
            logger.info("Audio-Unterstützung: Gradio Browser-Interface")

            self.is_initialized = True
            logger.info("[OK] Bot erfolgreich initialisiert!")

            return "[OK] Bot erfolgreich initialisiert!"

        except Exception as e:
            error_msg = f"[FEHLER] Fehler bei Initialisierung: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    def _preprocess_user_input(self, user_input: str) -> str:
        """Smart-Preprocessing: Wandelt 'vom X bis Y' in 'in den nächsten X Tagen' um"""
        logger.info(f"[Parser] Start: '{user_input}'")

        timezone = pytz.timezone('Europe/Berlin')
        now = datetime.now(timezone)

        #Verschiedene Patterns für "vom X bis Y"
        patterns = [
            r'vom\s+([\d\.]+\s+\w+(?:\s+\d{4})?)\s+bis\s+zum\s+([\d\.]+\s+\w+(?:\s+\d{4})?)',
            r'vom\s+([\d\.]+\s+\w+(?:\s+\d{4})?)\s+bis\s+([\d\.]+\s+\w+(?:\s+\d{4})?)',
            r'vom\s+([\d\.]+\.?\s*\w+\.?)\s+bis\s+zum\s+([\d\.]+\.?\s*\w+\.?)',
            r'vom\s+([\d\.]+\.?\s*\w+\.?)\s+bis\s+([\d\.]+\.?\s*\w+\.?)',
        ]

        for pattern in patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                start_str = match.group(1).strip()
                end_str = match.group(2).strip()

                logger.info(f"Parser: Pattern matched! Start='{start_str}', End='{end_str}'")

                try:
                    #Parse beide Daten OHNE 'future' preference - wir korrigieren manuell
                    start_date = dateparser.parse(
                        start_str,
                        settings={
                            'TIMEZONE': 'Europe/Berlin',
                            'PREFER_DATES_FROM': 'current_period',
                            'RELATIVE_BASE': now,
                            'DATE_ORDER': 'DMY'
                        },
                        languages=['de']
                    )

                    end_date = dateparser.parse(
                        end_str,
                        settings={
                            'TIMEZONE': 'Europe/Berlin',
                            'PREFER_DATES_FROM': 'current_period',
                            'RELATIVE_BASE': now,
                            'DATE_ORDER': 'DMY'
                        },
                        languages=['de']
                    )

                    if start_date and end_date:
                        #Wenn End-Datum vor Start-Datum liegt,
                        #bedeutet das, dass End ins nächste Jahr gehört
                        if end_date < start_date:
                            end_date = end_date.replace(year=end_date.year + 1)
                            logger.info(f"Parser: End-Datum korrigiert auf {end_date.year}")

                        #Wenn Start-Datum in der Vergangenheit liegt
                        #und kein explizites Jahr angegeben wurde, aktuelles Jahr verwenden
                        if start_date.date() < now.date():
                            #(z.B. "1. November" am 28. November -> November 2025, nicht 2026)
                            if start_date.month >= now.month or (start_date.month == now.month and start_date.day >= now.day):
                                #Monat ist aktuell oder zukünftig dieses Jahr
                                pass
                            else:
                                #Monat ist vorbei, aber wir behalten das Jahr
                                pass

                        #Format: YYYY-MM-DD für bessere Kompatibilität
                        start_formatted = start_date.strftime('%Y-%m-%d')
                        end_formatted = end_date.strftime('%Y-%m-%d')

                        replacement = f"von {start_formatted} bis {end_formatted}"
                        new_input = user_input[:match.start()] + replacement + user_input[match.end():]

                        logger.info(f"[OK] Parser: '{start_str}' bis '{end_str}' -> '{start_formatted}' bis '{end_formatted}'")
                        logger.info(f"[OK] Smart-Preprocessing: '{user_input}' -> '{new_input}'")
                        return new_input
                    else:
                        if not start_date:
                            logger.warning(f"Parser: Konnte Start-Datum '{start_str}' nicht parsen")
                        if not end_date:
                            logger.warning(f"Parser: Konnte End-Datum '{end_str}' nicht parsen")
                except Exception as e:
                    logger.warning(f"Parser Fehler: {e}", exc_info=True)

        #Pattern für "im November" etc.
        pattern_month = r'im\s+(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)'
        match_month = re.search(pattern_month, user_input, re.IGNORECASE)

        if match_month:
            month_name = match_month.group(1)
            logger.info(f"Parser: Monat-Pattern matched! Monat='{month_name}'")

            try:
                #Parse Start des Monats im aktuellen Jahr
                month_start = dateparser.parse(
                    f"1. {month_name} {now.year}",
                    settings={
                        'TIMEZONE': 'Europe/Berlin',
                        'RELATIVE_BASE': now
                    },
                    languages=['de']
                )

                if month_start:
                    #Timezone-Aware sicherstellen
                    if month_start.tzinfo is None:
                        month_start = timezone.localize(month_start)

                    #Ende des Monats berechnen
                    next_month = month_start.replace(day=28) + timedelta(days=4)
                    month_end = next_month - timedelta(days=next_month.day)

                    #Prüfe ob Monat schon vorbei ist
                    if month_end.date() < now.date():
                        #Monat liegt in Vergangenheit -> Nutze nächstes Jahr
                        logger.info(f"Parser: Monat '{month_name}' liegt in Vergangenheit, nutze {now.year + 1}")
                        month_start = month_start.replace(year=now.year + 1)
                        next_month = month_start.replace(day=28) + timedelta(days=4)
                        month_end = next_month - timedelta(days=next_month.day)
                        days = (month_end.date() - now.date()).days
                        logger.info(f"Parser: Zukünftiger Monat '{month_name} {now.year + 1}' - {days} Tage von heute")
                    elif month_start.month == now.month and month_start.year == now.year:
                        #Wir sind im Monat -> Nutze Rest des Monats (von heute bis Ende)
                        days = (month_end.date() - now.date()).days
                        logger.info(f"Parser: Im aktuellen Monat '{month_name}' - Rest des Monats = {days} Tage")
                    else:
                        #Monat liegt in der Zukunft (aber dieses Jahr) -> Nutze ganzen Monat
                        days = (month_end.date() - now.date()).days
                        logger.info(f"Parser: Zukünftiger Monat '{month_name} {now.year}' - {days} Tage von heute")

                    if days > 0:
                        replacement = f'in den nächsten {days} Tagen'
                        new_input = user_input[:match_month.start()] + replacement + user_input[match_month.end():]

                        logger.info(f"[OK] Parser: 'im {month_name}' = {days} Tage")
                        logger.info(f"[OK] Smart-Preprocessing: '{user_input}' -> '{new_input}'")
                        return new_input
            except Exception as e:
                logger.warning(f"Parser Monat Fehler: {e}", exc_info=True)

        #Kein Match--- Original zurückgeben
        return user_input

    async def _execute_command(self, text: str) -> str:
        """Führt Befehl aus"""
        try:
            #Smart-Preprocessing: "vom X bis Y" → "in den nächsten X Tagen"
            preprocessed_text = self._preprocess_user_input(text)

            #Context für Gemini erstellen
            context = self._build_context()

            response = await self.gemini.process_with_context(preprocessed_text, context)

            if not response:
                return "[FEHLER] Keine Antwort LLM"

            logger.info(f"LLM Antwort: {_safe_log(response, 200)}")

            #Antwort parsen
            #Prüfe ob response ein String ist
            if isinstance(response, str):
                #1. Versuche JSON-Block zu finden
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(1))
                else:
                    #2. Versuche direktes JSON
                    try:
                        parsed = json.loads(response)
                    except:
                        #Fallback: Response als Text zurückgeben
                        return response
            else:
                parsed = response

            #Nachricht extrahieren
            message = parsed.get('message', '')
            actions = parsed.get('actions', [])

            #Wenn kein actions-Array, aber direkt eine function angegeben
            if not actions and 'function' in parsed:
                actions = [{
                    "type": "helper_function",
                    "function": parsed.get('function'),
                    "params": parsed.get('params', {})
                }]
                logger.info(f"[Parser] Einzelne Action erkannt: {parsed.get('function')}")

            #Aktionen ausführen
            results = []
            for action in actions:
                result = await self._execute_action(action)
                results.append(result)

            #Ergebnis formatieren
            if results:
                formatted_results = []
                for r in results:
                    if not r.get('success'):
                        continue

                    #Spezielle Formatierung für Events
                    #Events können direkt in r['events'] oder in r['result']['events'] sein
                    events_data = None
                    if 'result' in r and isinstance(r['result'], dict) and 'events' in r['result']:
                        events_data = r['result']
                    elif 'events' in r:
                        events_data = r

                    if events_data and 'events' in events_data:
                        events = events_data.get('events', [])
                        if events:
                            formatted_results.append(f"\n**{len(events)} Events gefunden:**\n")
                            for event in events:
                                name = event.get('name', 'Unbekannt')
                                start = event.get('start_time', 'Keine Zeit')
                                desc = event.get('description', '')
                                location = event.get('location', '')

                                #Datum formatieren (nur Datum und Uhrzeit, kein ISO)
                                try:
                                    dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                                    start_formatted = dt.strftime('%d.%m.%Y %H:%M')
                                except:
                                    start_formatted = start

                                event_text = f"📅 **{name}**\n   🕐 {start_formatted}"
                                if desc:
                                    event_text += f"\n   📝 {desc[:100]}..."
                                if location:
                                    event_text += f"\n   📍 {location}"
                                formatted_results.append(event_text)
                        else:
                            #Keine Events gefunden
                            formatted_results.append("\n❌ **Keine Events gefunden**")

                    #Spezielle Formatierung für Channels
                    channels_data = None
                    if 'result' in r and isinstance(r['result'], dict) and 'channels' in r['result']:
                        channels_data = r['result']
                    elif 'channels' in r:
                        channels_data = r

                    if channels_data and 'channels' in channels_data:
                        channels = channels_data.get('channels', [])
                        if channels:
                            formatted_results.append(f"\n**{len(channels)} Channels gefunden:**\n")
                            for channel in channels:
                                name = channel.get('name', 'Unbekannt')
                                ch_type = channel.get('type', -1)

                                #Type zu lesbarem Text
                                type_text = {
                                    0: "💬 Text",
                                    2: "🔊 Voice",
                                    4: "📁 Kategorie",
                                    5: "📢 Ankündigungen",
                                    13: "🎭 Stage",
                                    15: "🧵 Forum"
                                }.get(ch_type, f"❓ Type {ch_type}")

                                channel_text = f"{type_text} **{name}**"
                                formatted_results.append(channel_text)
                        continue

                    #Spezielle Formatierung für Channel-Zusammenfassung
                    summary_data = None
                    if 'result' in r and isinstance(r['result'], dict) and 'summary' in r['result']:
                        summary_data = r['result']
                    elif 'summary' in r:
                        summary_data = r

                    if summary_data and 'summary' in summary_data:
                        channel_name = summary_data.get('channel', 'Unbekannt')
                        summary = summary_data.get('summary', '')
                        message_count = summary_data.get('message_count', 0)
                        if summary:
                            formatted_results.append(f"\n📋 **Zusammenfassung #{channel_name}** ({message_count} Nachrichten):\n")
                            formatted_results.append(summary)
                        continue

                    #Spezielle Formatierung für Channel-Nachrichten
                    messages_data = None
                    if 'result' in r and isinstance(r['result'], dict) and 'messages' in r['result']:
                        messages_data = r['result']
                    elif 'messages' in r:
                        messages_data = r

                    if messages_data and 'messages' in messages_data:
                        messages = messages_data.get('messages', [])
                        channel_name = messages_data.get('channel', 'Unbekannt')
                        if messages:
                            formatted_results.append(f"\n**{len(messages)} Nachrichten aus #{channel_name}:**\n")
                            #älteste zuerst, neueste zuletzt
                            for msg in reversed(messages):
                                author = msg.get('author', 'Unbekannt')
                                content = msg.get('content', '(kein Text)')
                                timestamp = msg.get('timestamp', '')
                                extra_info = msg.get('extra_info', '')

                                msg_text = f"👤 **{author}** ({timestamp}){extra_info}\n   {content}"
                                formatted_results.append(msg_text)
                        else:
                            formatted_results.append(f"\n❌ **Keine Nachrichten in #{channel_name} gefunden**")
                        continue

                    #Spezielle Formatierung für Online-Members
                    members_data = None
                    if 'result' in r and isinstance(r['result'], dict) and 'online_count' in r['result']:
                        members_data = r['result']
                    elif 'online_count' in r:
                        members_data = r

                    if members_data and 'online_count' in members_data:
                        online_count = members_data.get('online_count', 0)
                        total = members_data.get('total_members', 0)
                        msg = members_data.get('message', '')
                        members_list = members_data.get('members', [])

                        if msg:
                            formatted_results.append(f"\n👥 {msg}")

                        if members_list:
                            formatted_results.append(f"\n**Server-Mitglieder:**")
                            for m in members_list:
                                display = m.get('display_name', m.get('username', 'Unbekannt'))
                                formatted_results.append(f"  • {display}")
                        continue

                    #Normale Nachricht
                    result_msg = None
                    if 'result' in r and isinstance(r['result'], dict) and 'message' in r['result']:
                        result_msg = r['result'].get('message')
                    elif 'message' in r:
                        result_msg = r.get('message')

                    if result_msg:
                        formatted_results.append(f"✅ {result_msg}")

                if formatted_results:
                    result_text = "\n".join(formatted_results)
                    #Wenn message leer ist, nur results zurückgeben
                    if message:
                        return f"{message}\n{result_text}"
                    else:
                        return result_text

            #Nur message zurückgeben, wenn sie nicht leer ist
            return message if message else "Befehl ausgeführt."

        except Exception as e:
            logger.error(f"Fehler bei Befehl-Ausführung: {e}", exc_info=True)
            return f"[FEHLER] Fehler: {str(e)}"

    async def _execute_action(self, action: dict) -> dict:
        """Führt eine Action aus"""
        try:
            function_name = action.get('function')
            params = action.get('params', {})

            if hasattr(self.helper, function_name):
                func = getattr(self.helper, function_name)
                result = await func(**params)

                logger.info(f"[OK] Action erfolgreich: {function_name}")
                return {
                    "success": True,
                    "function": function_name,
                    "result": result,
                    "message": result.get('message', 'Erfolgreich ausgeführt')
                }
            else:
                logger.warning(f"[WARN] Unbekannte Funktion: {function_name}")
                return {
                    "success": False,
                    "error": f"Funktion nicht gefunden: {function_name}"
                }

        except Exception as e:
            logger.error(f"[FEHLER] Fehler bei Action: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    def _build_context(self):
        """Erstellt Context für LLM"""
        if not self.helper:
            return ""

        functions = self.helper.get_available_functions()

        #Aktuelles Datum für korrekte Datumsberechnungen
        now = datetime.now()
        tomorrow = now + timedelta(days=1)

        context = f"AKTUELLES DATUM: {now.strftime('%d. %B %Y')} ({now.strftime('%A')})\n"
        context += f"'Heute' = {now.strftime('%Y-%m-%d')}\n"
        context += f"'Morgen' = {tomorrow.strftime('%Y-%m-%d')}\n\n"
        context += "WICHTIG: Antworte NUR mit JSON! Kein Text davor oder danach!\n"
        context += "Deine Antwort MUSS mit '{' beginnen und mit '}' enden.\n\n"
        context += "Verfügbare Discord-Funktionen:\n\n"

        for func_name, func_info in functions.items():
            context += f"**{func_name}**\n"
            context += f"  {func_info['description']}\n"
            context += f"  Parameter: {', '.join(func_info['params'])}\n\n"

        context += "\nAntworte im JSON-Format:\n"
        context += '{"message": "Deine Antwort", "actions": [...]}\n\n'
        context += "WICHTIG - Action Format:\n"
        context += '- Verwende "type": "helper_function"\n'
        context += '- Verwende "params" als Schluessel\n'
        context += '- Beispiel: {"type": "helper_function", "function": "send_message", "params": {...}}\n\n'
        context += "WICHTIG - Channel-Namen:\n"
        context += '- channel_id kann ein Channel-NAME sein (z.B. "allgemein")\n\n'
        context += "WICHTIG - Nachricht löschen:\n"
        context += '- delete_message: Verwende "content" Parameter\n'
        context += '- delete_last_message: Lösche die aktuellste Nachricht (benötigt KEINEN "content"!)\n'
        context += '- Beispiel delete_last_message: {"function": "delete_last_message", "params": {"channel_id": "allgemein"}}\n\n'
        context += "WICHTIG - Events mit Zeitraum:\n"
        context += '- Wenn User "von X bis Y" fragt: Nutze from_date und to_date Parameter!\n'
        context += '- Format erkannt: "von 2025-12-01 bis 2025-12-29" → {"from_date": "2025-12-01", "to_date": "2025-12-29"}\n'
        context += '- Für Zeitraum in Tagen: Nutze days_ahead (z.B. "nächste 7 Tage" → {"days_ahead": 7})\n'
        context += '- WICHTIG: Setze KEIN niedriges limit! Standard ist 50. Nur bei "zeige mir 5 Events" explizit limit setzen.\n\n'
        context += "Beispiele:\n"
        context += '- "Sende Nachricht Hallo in allgemein" → {"function": "send_message", "params": {"channel_id": "allgemein", "content": "Hallo"}}\n'
        context += '- "Events von 2025-12-01 bis 2025-12-29" → {"function": "list_upcoming_events", "params": {"from_date": "2025-12-01", "to_date": "2025-12-29"}}\n'
        context += '- "Events der nächsten 7 Tage" → {"function": "list_upcoming_events", "params": {"days_ahead": 7}}\n'
        context += '- "Lösche die letzte Nachricht in allgemein" → {"function": "delete_last_message", "params": {"channel_id": "allgemein"}}\n'
        context += '- "Zeige letzte Nachrichten in allgemein" → {"function": "get_channel_messages", "params": {"channel_id": "allgemein"}}\n'
        context += '- "Zeige 10 Nachrichten aus general" → {"function": "get_channel_messages", "params": {"channel_id": "general", "limit": 10}}\n'
        context += '- "Worum geht es im Channel allgemein?" → {"function": "summarize_channel", "params": {"channel_id": "allgemein"}}\n'
        context += '- "Fasse die letzten 20 Nachrichten in general zusammen" → {"function": "summarize_channel", "params": {"channel_id": "general", "limit": 20}}\n'

        return context

    async def cleanup(self):
        """Cleanup beim Beenden"""
        try:
            if self.mcp_client:
                await self.mcp_client.disconnect()
            logger.info("[OK] Cleanup abgeschlossen")
        except Exception as e:
            logger.error(f"Fehler beim Cleanup: {e}", exc_info=True)


#Globale Bot-Instanz
bot = DiscordBotGradio()

#Bot beim Start initialisieren
logger.info("Starte automatische Bot-Initialisierung...")
init_status = bot._run_async(bot.initialize())
logger.info(f"Initialisierung abgeschlossen: {init_status}")


#=== LLM PROVIDER MANAGEMENT ===

#Verfügbare Modelle pro Provider (Fallback-Listen, werden dynamisch aktualisiert)
LLM_MODELS = {
    "openai": [
        "gpt-5.2",
        "gpt-5.1",           #Nov 2025
        "gpt-5",             #Aug 2025
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
    ],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-3-flash-preview"],
    "ollama": [],  #Wird dynamisch gefüllt
}

#Preise pro 1M Tokens (Input/Output in USD)
#Werden dynamisch von LiteLLM geladen, Fallback auf hardcodierte Werte
MODEL_PRICES = {}
_prices_loaded = False
_prices_last_update = None

#Fallback-Preise falls LiteLLM nicht erreichbar (Stand: Dezember 2025)
FALLBACK_PRICES = {
    #GPT-5 Serie (2025)
    "gpt-5.2": (3.00, 15.00),        #Dez 2025 - geschätzt
    "gpt-5.1": (2.50, 12.50),        #Nov 2025 - geschätzt
    "gpt-5": (2.00, 10.00),          #Aug 2025 - geschätzt
    "gpt-5-mini": (0.30, 1.20),      #geschätzt
    "gpt-5-nano": (0.10, 0.40),      #geschätzt
    #GPT-4 Serie
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    #Gemini Serie
    "gemini-3-flash-preview": (0.50, 3.00),  #Gemini 3 Flash Preview (Dez 2025)
    "gemini-3-pro": (2.00, 12.00),   #Gemini 3 Pro Preview (Nov 2025)
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    #Groq/Open Source
    "llama-3.3-70b": (0.59, 0.79),
    "llama-3.1-8b": (0.05, 0.08),
    "mixtral-8x7b": (0.24, 0.24),
    "ollama": "free",
}


def fetch_litellm_prices() -> dict:
    """
    Lädt aktuelle Modellpreise von LiteLLM GitHub Repository.

    Returns:
        Dictionary mit Modellpreisen: {model_name: (input_price_per_1M, output_price_per_1M)}
    """
    global MODEL_PRICES, _prices_loaded, _prices_last_update

    LITELLM_PRICES_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"

    try:
        import aiohttp
        import asyncio

        async def _fetch():
            async with aiohttp.ClientSession() as session:
                async with session.get(LITELLM_PRICES_URL, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        return await response.json()
                    return None

        #Führe async aus
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_fetch(), bot.loop)
                data = future.result(timeout=15)
            else:
                data = asyncio.run(_fetch())
        except Exception:
            #Fallback ---synchroner Request
            import urllib.request
            import json
            with urllib.request.urlopen(LITELLM_PRICES_URL, timeout=10) as response:
                data = json.loads(response.read().decode())

        if not data:
            logger.warning("LiteLLM Preise: Keine Daten erhalten")
            return FALLBACK_PRICES

        #Parse Preise ----- LiteLLM Format: kosten per token -> umrechnen in 1M token
        prices = {}
        for model_name, model_info in data.items():
            if isinstance(model_info, dict):
                input_cost = model_info.get('input_cost_per_token', 0)
                output_cost = model_info.get('output_cost_per_token', 0)

                #Manche Modelle haben nur 'input_cost_per_token'????
                if input_cost or output_cost:
                    #Umrechnung: pro Token -> pro 1M Tokens
                    input_per_1m = input_cost * 1_000_000 if input_cost else 0
                    output_per_1m = output_cost * 1_000_000 if output_cost else 0

                    #Speichere unter verschiedenen Varianten des Namens
                    prices[model_name.lower()] = (input_per_1m, output_per_1m)

                    #Extrahiere Modellname ohne Provider-Prefix
                    if '/' in model_name:
                        short_name = model_name.split('/')[-1].lower()
                        if short_name not in prices:
                            prices[short_name] = (input_per_1m, output_per_1m)

        #Füge Ollama als kostenlos hinzu
        prices["ollama"] = "free"

        logger.info(f"LiteLLM Preise geladen: {len(prices)} Modelle")

        MODEL_PRICES = prices
        _prices_loaded = True
        _prices_last_update = datetime.now()

        return prices

    except Exception as e:
        logger.warning(f"Fehler beim Laden der LiteLLM Preise: {e}")
        MODEL_PRICES = FALLBACK_PRICES.copy()
        return FALLBACK_PRICES


def get_prices_status() -> str:
    """Gibt Status der Preisdaten zurück"""
    if _prices_loaded and _prices_last_update:
        age = (datetime.now() - _prices_last_update).seconds // 60
        return f"LiteLLM ({len(MODEL_PRICES)} Modelle, vor {age} Min.)"
    elif MODEL_PRICES:
        return f"Fallback ({len(MODEL_PRICES)} Modelle)"
    else:
        return "Nicht geladen"


def get_model_price(model_name: str, provider: str = None) -> str:
    """
    Gibt den Preis für ein Modell als formatierten String zurück.

    Returns:
        String wie "$0.15/$0.60" (input/output per 1M tokens) oder "free"
    """
    model_lower = model_name.lower()

    #Ollama ist immer kostenlos
    if provider == "ollama":
        return "lokal/free"

    #Sicherstellen dass Preise geladen sind
    if not MODEL_PRICES:
        return "?"

    #Versuche verschiedene Lookup-Strategien
    price_value = None

    #1. Exakter Match mit Provider-Prefix
    if provider:
        provider_key = f"{provider}/{model_lower}"
        if provider_key in MODEL_PRICES:
            price_value = MODEL_PRICES[provider_key]

    #2. Exakter Match ohne Provider
    if not price_value and model_lower in MODEL_PRICES:
        price_value = MODEL_PRICES[model_lower]

    #3. Substring-Match (längster zuerst)
    if not price_value:
        best_match = None
        best_match_len = 0

        for price_key, pv in MODEL_PRICES.items():
            #Prüfe ob price_key im model_name enthalten ist
            if price_key in model_lower:
                if len(price_key) > best_match_len:
                    best_match = pv
                    best_match_len = len(price_key)
            #Oder umgekehrt (model_name im price_key)
            elif model_lower in price_key:
                if len(model_lower) > best_match_len:
                    best_match = pv
                    best_match_len = len(model_lower)

        price_value = best_match

    if price_value:
        if price_value == "free":
            return "free"
        input_price, output_price = price_value
        #Kompakte Formatierung
        if input_price < 1:
            input_str = f"${input_price:.2f}"
        else:
            input_str = f"${input_price:.0f}" if input_price == int(input_price) else f"${input_price:.1f}"
        if output_price < 1:
            output_str = f"${output_price:.2f}"
        else:
            output_str = f"${output_price:.0f}" if output_price == int(output_price) else f"${output_price:.1f}"
        return f"{input_str}/{output_str}"

    return "?"  #Preis unbekannt


def fetch_openai_models(api_key: str) -> list[str]:
    """
    Ruft verfügbare OpenAI-Modelle via API ab.
    Filtert auf Chat-Modelle (gpt-*).
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        models_response = client.models.list()

        #Filtere auf relevante Chat-Modelle
        chat_models = []
        for model in models_response.data:
            model_id = model.id
            #GPT-5, GPT-4 und GPT-3.5 Modelle die für Chat geeignet sind
            if model_id.startswith(('gpt-5', 'gpt-4', 'gpt-3.5')) and 'instruct' not in model_id:
                chat_models.append(model_id)

        logger.info(f"OpenAI API: {len(chat_models)} Chat-Modelle gefunden")

        #Sortiere --- -neueste/beste zuerst (GPT-5.2 > 5.1 > 5 > 4o)
        priority_order = [
            'gpt-5.2', 'gpt-5.1', 'gpt-5-mini', 'gpt-5-nano', 'gpt-5',
            'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo'
        ]

        def sort_key(model):
            for i, prefix in enumerate(priority_order):
                if model.startswith(prefix):
                    return (i, model)
            return (len(priority_order), model)

        chat_models.sort(key=sort_key)

        #Dedupliziere (z.B. gpt-4o und gpt-4o-2024-... ------> behalte nur Hauptversion)
        seen_prefixes = set()
        unique_models = []
        for model in chat_models:
            #Extrahiere Basis-Modellname (ohne Datumssuffix)
            base_name = model.split('-202')[0] if '-202' in model else model
            if base_name not in seen_prefixes:
                seen_prefixes.add(base_name)
                unique_models.append(model)

        #Wichtige Modelle die evtl nicht in der API sind (neueste)
        important_models = [
            "gpt-5.2",       #Dez 2025 - neuestes
            "gpt-5.1",       #Nov 2025
            "gpt-5",         #Aug 2025
            "gpt-5-mini",
            "gpt-5-nano",
        ]

        #Füge wichtige Modelle am Anfang hinzu, falls nicht vorhanden
        for model in reversed(important_models):
            if model not in unique_models:
                unique_models.insert(0, model)

        logger.info(f"OpenAI: {len(unique_models)} Modelle verfügbar: {unique_models[:8]}...")
        return unique_models if unique_models else LLM_MODELS["openai"]

    except Exception as e:
        logger.warning(f"Fehler beim Abrufen der OpenAI-Modelle: {e}")
        return LLM_MODELS["openai"]  #Fallback auf hardcodierte Liste


def fetch_gemini_models(api_key: str) -> list[str]:
    """
    Ruft verfügbare Gemini-Modelle via API ab.
    Nutzt aiohttp (bereits installiert) für den API-Call.
    """
    import asyncio

    async def _fetch():
        try:
            import aiohttp

            #Google AI API Endpoint für Modell-Liste
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.warning(f"Gemini API Fehler: {response.status}")
                        return LLM_MODELS["gemini"]

                    data = await response.json()
                    models = data.get('models', [])

                    logger.info(f"Gemini API: {len(models)} Modelle insgesamt von der API")

                    #Sammle alle Chat-fähigen Modelle
                    chat_models = []
                    skipped_models = []

                    for model in models:
                        model_name = model.get('name', '')
                        short_name = model_name.replace('models/', '')
                        supported_methods = model.get('supportedGenerationMethods', [])

                        #Nur Modelle die generateContent unterstützen (Chat-fähig)
                        if 'generateContent' in supported_methods:
                            #Gemini-Modelle priorisieren, aber auch andere zeigen
                            if 'gemini' in short_name.lower():
                                chat_models.append(short_name)
                            else:
                                #Andere Modelle (z.B. learnlm, text-bison) auch aufnehmen
                                chat_models.append(short_name)
                        else:
                            skipped_models.append(f"{short_name} (no generateContent)")

                    logger.info(f"Gemini: {len(chat_models)} Chat-Modelle, übersprungen: {len(skipped_models)}")
                    if skipped_models:
                        logger.debug(f"Übersprungene Modelle: {skipped_models[:5]}...")

                    #Sortiere ---- Gemini zuerst, dann nach Version (neueste zuerst)
                    priority_order = ['gemini-3', 'gemini-2.5', 'gemini-2.0', 'gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-1.0', 'gemini']

                    def sort_key(model):
                        model_lower = model.lower()
                        #Gemini-Modelle nach Version sortieren
                        for i, prefix in enumerate(priority_order):
                            if model_lower.startswith(prefix):
                                return (i, model)
                        #Nicht-Gemini-Modelle ans Ende
                        return (len(priority_order), model)

                    chat_models.sort(key=sort_key)

                    #Preview-Modelle wie gemini-3-pro werden NICHT automatisch hinzugefügt???????

                    logger.info(f"Gemini: {len(chat_models)} Modelle verfügbar: {chat_models}")
                    return chat_models if chat_models else LLM_MODELS["gemini"]

        except Exception as e:
            logger.warning(f"Fehler beim Abrufen der Gemini-Modelle: {e}")
            return LLM_MODELS["gemini"]

    #Führe async Funktion aus
    try:
        #Prüfe ob ein Event Loop läuft
        loop = asyncio.get_event_loop()
        if loop.is_running():
            #Nutze den Bots Event Loop
            future = asyncio.run_coroutine_threadsafe(_fetch(), bot.loop)
            return future.result(timeout=15)
        else:
            return asyncio.run(_fetch())
    except Exception as e:
        logger.warning(f"Fehler beim Abrufen der Gemini-Modelle (async): {e}")
        return LLM_MODELS["gemini"]


def fetch_groq_models(api_key: str) -> list[str]:
    """
    Ruft verfügbare Groq-Modelle via API ab.
    """
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        models_response = client.models.list()

        chat_models = []
        for model in models_response.data:
            model_id = model.id
            chat_models.append(model_id)

        #Sortiere nach Beliebtheit/Qualität
        priority_keywords = ['llama-3.3', 'llama-3.1-70b', 'llama-3.1-8b', 'mixtral', 'gemma']

        def sort_key(model):
            for i, keyword in enumerate(priority_keywords):
                if keyword in model.lower():
                    return (i, model)
            return (len(priority_keywords), model)

        chat_models.sort(key=sort_key)

        logger.info(f"Groq: {len(chat_models)} Modelle gefunden: {chat_models[:5]}...")
        return chat_models if chat_models else LLM_MODELS["groq"]

    except Exception as e:
        logger.warning(f"Fehler beim Abrufen der Groq-Modelle: {e}")
        return LLM_MODELS["groq"]  #Fallback auf hardcodierte Liste

#Gespeicherte validierte API Keys und aktive Provider
_validated_providers = {
    "openai": {"valid": False, "api_key": None},
    "groq": {"valid": False, "api_key": None},
    "gemini": {"valid": False, "api_key": None},
    "ollama": {"valid": False, "api_key": None},  #Ollama braucht keinen Key, aber valid=True wenn läuft
}

#Ausgewählte Modelle pro Provider (für Dropdown-Filter)
_selected_models = {
    "openai": [],  #Liste der ausgewählten Modellnamen
    "groq": [],
    "gemini": [],
    "ollama": [],
}

#Ollama Status
_ollama_available = False
_ollama_models = []


def check_ollama_available() -> tuple[bool, list[str]]:
    """
    Prüft ob Ollama läuft und gibt verfügbare Modelle zurück

    Returns:
        (available: bool, models: list[str])
    """
    try:
        import ollama
        #Versuche Modelle zu listen ----- wenn das klappt dann läuft Ollama
        models_response = ollama.list()
        models = []

        #Ollama gibt ein ListResponse Objekt zurück mit 'models' Attribut
        model_list = None
        if hasattr(models_response, 'models'):
            #Neues Format: ListResponse Objekt
            model_list = models_response.models
        elif isinstance(models_response, dict) and 'models' in models_response:
            #Altes Format: Dictionary
            model_list = models_response['models']

        if model_list:
            for model in model_list:
                #Model kann ein Objekt oder Dict sein
                if hasattr(model, 'model'):
                    model_name = model.model
                elif isinstance(model, dict):
                    model_name = model.get('name', '') or model.get('model', '')
                else:
                    model_name = str(model)

                if model_name:
                    #Entferne ":latest" Suffix wenn vorhanden
                    if model_name.endswith(':latest'):
                        model_name = model_name.replace(':latest', '')
                    models.append(model_name)

        if models:
            logger.info(f"Ollama verfügbar mit {len(models)} Modellen: {', '.join(models)}")
            return True, models
        else:
            logger.info("Ollama läuft, aber keine Modelle installiert")
            return True, []

    except ImportError:
        logger.debug("Ollama Python-Paket nicht installiert")
        return False, []
    except Exception as e:
        #Ollama nicht erreichbar
        logger.debug(f"Ollama nicht verfügbar: {e}")
        return False, []


#Ollama beim Start prüfen
logger.info("Prüfe Ollama Verfügbarkeit...")
_ollama_available, _ollama_models = check_ollama_available()

if _ollama_available:
    LLM_MODELS["ollama"] = _ollama_models
    _validated_providers["ollama"] = {"valid": True, "api_key": None}
    #Erste 3 Modelle vorauswählen
    _selected_models["ollama"] = _ollama_models[:3] if _ollama_models else []
    logger.info(f"Ollama als LLM-Provider verfügbar: {len(_ollama_models)} lokale Modelle")
else:
    logger.info("Ollama nicht verfügbar nur Cloud-Provider nutzbar")

#LiteLLM Preise beim Start laden
logger.info("Lade aktuelle Modellpreise von LiteLLM..")
try:
    fetch_litellm_prices()
    logger.info(f"Preise geladen: {get_prices_status()}")
except Exception as e:
    logger.warning(f"Preise konnten nicht geladen werden: {e}")
    MODEL_PRICES = FALLBACK_PRICES.copy()

#Aktuell ausgewählter Provider und Modell
_current_llm_config = {
    "provider": bot.config.llm_provider if bot.config else None,
    "model": bot.config.llm_model if bot.config else None
}

#Wenn kein LLM konfiguriert aber Ollama verfügbar, nutze Ollama als default
if (not _current_llm_config["provider"] or not bot.config.llm_available) and _ollama_available and _ollama_models:
    logger.info(f"Kein LLM konfiguriert - nutze Ollama als Fallback: {_ollama_models[0]}")
    _current_llm_config["provider"] = "ollama"
    _current_llm_config["model"] = _ollama_models[0]
    #Initialisiere Ollama im Bot
    if bot.gemini:
        try:
            bot.gemini._init_llm_client("ollama", _ollama_models[0])
            logger.info(f"Ollama LLM aktiviert: {_ollama_models[0]}")
        except Exception as e:
            logger.warning(f"Ollama Initialisierung fehlgeschlagen: {e}")

#Wenn LLM aus .env konfiguriert ist auch als validiert markieren
elif _current_llm_config["provider"] and bot.config.llm_available:
    provider = _current_llm_config["provider"]
    #Hole API Key aus der Umgebung
    api_key = None
    if provider == "openai":
        api_key = bot.config.openai_api_key
    elif provider == "groq":
        api_key = bot.config.groq_api_key
    elif provider == "gemini":
        api_key = bot.config.gemini_api_key

    if api_key or provider == "ollama":
        _validated_providers[provider] = {"valid": True, "api_key": api_key}
        logger.info(f"LLM Provider aus .env als validiert markiert: {provider}")


def _validate_api_key(provider: str, api_key: str) -> tuple[bool, str]:
    """
    Validiert einen API Key durch einen direkten Test-Request

    Returns:
        (success: bool, message: str)
    """
    if not api_key or api_key.strip() == "":
        return False, "Kein API Key eingegeben"

    api_key = api_key.strip()

    try:
        #Direkte API-Validierung ohne LLMClient
        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=5
            )
            if response and response.choices:
                return True, "API Key gültig! Test mit gpt-4o-mini erfolgreich."
            return False, "API Key ungültig oder keine Antwort erhalten"

        elif provider == "groq":
            from groq import Groq
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=5
            )
            if response and response.choices:
                return True, "API Key gültig! Test mit llama-3.1-8b-instant erfolgreich."
            return False, "API Key ungültig oder keine Antwort erhalten"

        elif provider == "gemini":
            #Gemini via OpenAI-kompatible API
            from openai import OpenAI
            client = OpenAI(
                api_key=api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            logger.info(f"Validiere Gemini API Key...")
            response = client.chat.completions.create(
                model="gemini-2.0-flash",
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=5
            )
            if response and response.choices:
                return True, "API Key gültig! Test mit gemini-2.0-flash erfolgreich."
            return False, "API Key ungültig - keine Antwort erhalten"

        else:
            return False, f"Unbekannter Provider: {provider}"

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Validierung fehlgeschlagen für {provider}: {error_msg}")
        if "401" in error_msg or "unauthorized" in error_msg.lower():
            return False, "API Key ungültig --- Authentifizierung fehlgeschlagen"
        elif "403" in error_msg or "forbidden" in error_msg.lower():
            return False, "API Key ungültig --- Zugriff verweigert"
        elif "rate" in error_msg.lower():
            return True, "API Key gültig (Rate Limit erreicht, aber Key funktioniert)"
        elif "invalid" in error_msg.lower() or "api" in error_msg.lower():
            return False, f"API Key ungültig: {error_msg[:80]}"
        else:
            return False, f"Validierung fehlgeschlagen: {error_msg[:100]}"


def validate_openai_key(api_key: str) -> str:
    """Validiert OpenAI API Key und lädt verfügbare Modelle"""
    success, message = _validate_api_key("openai", api_key)
    if success:
        _validated_providers["openai"] = {"valid": True, "api_key": api_key.strip()}
        #Modelle dynamisch laden
        models = fetch_openai_models(api_key.strip())
        LLM_MODELS["openai"] = models
        return f"✅ OpenAI: {message}\n📋 {len(models)} Modelle geladen"
    else:
        _validated_providers["openai"] = {"valid": False, "api_key": None}
        return f"❌ OpenAI: {message}"


def validate_groq_key(api_key: str) -> str:
    """Validiert Groq API Key und lädt verfügbare Modelle"""
    success, message = _validate_api_key("groq", api_key)
    if success:
        _validated_providers["groq"] = {"valid": True, "api_key": api_key.strip()}
        #Modelle dynamisch laden
        models = fetch_groq_models(api_key.strip())
        LLM_MODELS["groq"] = models
        return f"✅ Groq: {message}\n📋 {len(models)} Modelle geladen"
    else:
        _validated_providers["groq"] = {"valid": False, "api_key": None}
        return f"❌ Groq: {message}"


def validate_gemini_key(api_key: str) -> str:
    """Validiert Gemini API Key und lädt verfügbare Modelle"""
    success, message = _validate_api_key("gemini", api_key)
    if success:
        _validated_providers["gemini"] = {"valid": True, "api_key": api_key.strip()}
        #Modelle dynamisch laden
        models = fetch_gemini_models(api_key.strip())
        LLM_MODELS["gemini"] = models
        return f"✅ Gemini: {message}\n📋 {len(models)} Modelle geladen"
    else:
        _validated_providers["gemini"] = {"valid": False, "api_key": None}
        return f"❌ Gemini: {message}"


def refresh_ollama_models() -> str:
    """Aktualisiert die Liste der Ollama-Modelle"""
    global _ollama_available, _ollama_models

    _ollama_available, _ollama_models = check_ollama_available()

    if _ollama_available:
        LLM_MODELS["ollama"] = _ollama_models
        _validated_providers["ollama"] = {"valid": True, "api_key": None}
        if _ollama_models:
            return f"✅ Ollama: {len(_ollama_models)} Modelle gefunden ({', '.join(_ollama_models[:3])}{'...' if len(_ollama_models) > 3 else ''})"
        else:
            return "⚠️ Ollama läuft, aber keine Modelle installiert."
    else:
        LLM_MODELS["ollama"] = []
        _validated_providers["ollama"] = {"valid": False, "api_key": None}
        return "❌ Ollama nicht erreichbar. Stelle sicher dass Ollama läuft."


def get_ollama_status() -> str:
    """Gibt den aktuellen Ollama-Status zurück"""
    if _ollama_available:
        if _ollama_models:
            return f"✅ Läuft ({len(_ollama_models)} Modelle)"
        else:
            return "⚠️ Läuft (keine Modelle)"
    else:
        return "❌ Nicht verfügbar"


def get_validated_models() -> list[str]:
    """Gibt Liste aller validierten Modelle zurück ( Dropdown)"""
    models = []

    #Aktueller Provider aus Config
    current_provider = _current_llm_config.get("provider")
    current_model = _current_llm_config.get("model")

    #Prüfe ob LLM verfügbar
    llm_available = bot.gemini and bot.gemini.llm_available if bot.gemini else False

    #Füge aktuelles Modell hinzu
    if current_model and current_provider and llm_available:
        price = get_model_price(current_model, current_provider)
        models.append(f"{current_provider}: {current_model} [{price}] (aktiv)")

    #Füge validierte Provider hinzu
    for provider, info in _validated_providers.items():
        if info["valid"]:
            selected = _selected_models.get(provider, [])
            available = LLM_MODELS.get(provider, [])

            #Wenn keine Auswahl getroffen wurde zeige alle (max 5 Standard-Modelle)
            if not selected:
                models_to_show = available[:5] if len(available) > 5 else available
            else:
                #Nur ausgewählte Modelle anzeigen
                models_to_show = [m for m in available if m in selected]

            #Trenne empfohlene und andere Modelle
            recommended_models = []
            other_models = []

            for model in models_to_show:
                price = get_model_price(model, provider)
                base_check = f"{provider}: {model}"

                #Prüfe ob Modell bereits in Liste
                if any(base_check in m for m in models):
                    continue

                if is_recommended_model(model):
                    recommended_models.append(f"{provider}: {model} [{price}] (empfohlen)")
                else:
                    other_models.append(f"{provider}: {model} [{price}]")

            #Empfohlene zuerst dann der Rest
            models.extend(recommended_models)
            models.extend(other_models)

    #wenn nichts validiert, zeige Hinweis
    if not models:
        models = ["Kein LLM konfiguriert - bitte API Key in Einstellungen eingeben"]

    return models


def update_selected_models(provider: str, selected: list[str]):
    """Aktualisiert die Modellauswahl für einen Provider"""
    _selected_models[provider] = selected
    logger.info(f"{provider}: {len(selected)} Modelle ausgewählt")


#Empfohlene Modelle (gutes Preis-Leistungs-Verhältnis) #
RECOMMENDED_MODELS = [
    "gemini-2.5-flash",
    "gpt-4o-mini",
]


def is_recommended_model(model_name: str) -> bool:
    """Prüft ob ein Modell empfohlen ist (exakter Match)"""
    return model_name.lower() in [r.lower() for r in RECOMMENDED_MODELS]


def get_model_choices_with_prices(provider: str) -> list[str]:
    """Gibt Modelle mit Preisen als Choices für CheckboxGroup zurück.
    Empfohlene Modelle stehen an erster Stelle."""
    models = LLM_MODELS.get(provider, [])

    recommended = []
    others = []

    for model in models:
        price = get_model_price(model, provider)
        if is_recommended_model(model):
            recommended.append(f"{model} [{price}] (empfohlen)")
        else:
            others.append(f"{model} [{price}]")

    #Empfohlene zuerst dann der Rest
    return recommended + others


def extract_model_name(choice: str) -> str:
    """Extrahiert den Modellnamen aus einer Choice mit Preis und Tags"""
    #"gpt-4o [$2.50/$10] (empfohlen)" -> "gpt-4o"
    import re
    #Entferne (empfohlen), (aktiv) und [preis] Tags
    result = choice
    result = re.sub(r'\s*\(empfohlen\)', '', result)
    result = re.sub(r'\s*\(aktiv\)', '', result)
    result = re.sub(r'\s*\[.*?\]', '', result)
    return result.strip()


def update_model_dropdown():
    """Aktualisiert das Modell-Dropdown mit validierten Modellen"""
    models = get_validated_models()
    return gr.update(choices=models, value=models[0] if models else None)


def switch_llm_model(model_selection: str) -> str:
    """Wechselt das LLM Modell"""
    global _current_llm_config

    if not model_selection:
        return "[WARN] Kein Modell ausgewählt"

    try:
        model_selection = model_selection.replace(" (aktiv)", "")
        model_selection = model_selection.replace(" (empfohlen)", "")
        model_selection = re.sub(r'\s*\[.*?\]', '', model_selection)  #Entferne [preis]

        parts = model_selection.split(": ", 1)
        if len(parts) != 2:
            return f"[FEHLER] Ungültiges Format: {model_selection}"

        provider, model = parts
        provider = provider.strip().lower()
        model = model.strip()

        #Prüfe ob Provider validiert ist oder der aktuelle ist
        current_provider = _current_llm_config.get("provider")
        if provider != current_provider:
            if not _validated_providers.get(provider, {}).get("valid"):
                return f"[FEHLER] {provider} ist nicht validiert. Bitte erst API Key eingeben."

        #API Key setzen falls validiert
        if _validated_providers.get(provider, {}).get("valid"):
            api_key = _validated_providers[provider]["api_key"]
            if api_key:  #Nur setzen wenn nicht None
                os.environ[f"{provider.upper()}_API_KEY"] = api_key

        if bot.gemini:
            bot.gemini._init_llm_client(provider, model)
        else:
            return "[FEHLER] Bot nicht initialisiert"

        _current_llm_config["provider"] = provider
        _current_llm_config["model"] = model

        logger.info(f"LLM gewechselt zu: {provider} - {model}")
        return f"[OK] LLM gewechselt zu: {provider} - {model}"

    except Exception as e:
        logger.error(f"Fehler beim LLM-Wechsel: {e}")
        return f"[FEHLER] LLM-Wechsel fehlgeschlagen: {str(e)}"


def get_current_llm_info() -> str:
    """Gibt Info über aktuelles LLM zurück"""
    provider = _current_llm_config.get("provider")
    model = _current_llm_config.get("model")

    validated_list = [p for p, info in _validated_providers.items() if info["valid"]]
    validated_str = ", ".join(validated_list) if validated_list else "keine"

    #Prüfe ob LLM verfügbar
    llm_available = bot.gemini and bot.gemini.llm_available if bot.gemini else False

    if not provider or not model:
        return f"**Aktuell:** Kein LLM konfiguriert ⚠️\n**Validierte Provider:** {validated_str}"
    elif not llm_available:
        return f"**Aktuell:** {provider} - {model} (nicht aktiv) ⚠️\n**Validierte Provider:** {validated_str}"
    else:
        return f"**Aktuell:** {provider} - {model} ✅\n**Validierte Provider:** {validated_str}"


#Wrapper-Funktionen für Gradio
def init_bot():
    if bot.is_initialized:
        return "[OK] Bot bereits initialisiert!"
    return bot._run_async(bot.initialize())


#Cache für letzte Transkription
_last_transcribed_audio = {"path": None, "text": None}


def transcribe_audio_sync(audio, chat_history):
    """Transkribiert Audio und zeigt es im Chat (sync wrapper)"""
    global _last_transcribed_audio

    if audio is None:
        return chat_history, chat_history, "[INFO] Keine Audio-Datei"

    #Prüfe ob diese Audio-Datei bereits transkribiert wurde
    if _last_transcribed_audio["path"] == audio:
        logger.info(f"Audio bereits transkribiert, überspringe: {audio}")
        return chat_history, chat_history, f"[INFO] Bereits transkribiert"

    try:
        #Nur Transkription keine weitere Verarbeitung
        text = bot._run_async(bot.gemini.speech_to_text(audio))
        logger.info(f"Transkription angezeigt: {text}")

        #Cache aktualisieren
        _last_transcribed_audio = {"path": audio, "text": text}

        #Füge Transkription zum Chat hinzu
        chat_history.append({
            "role": "user",
            "content": f"🎤 **Transkribierte Audiodatei:**\n{text}"
        })

        return chat_history, chat_history, f"[INFO] Transkribiert: {text[:50]}... (Klicke 'Audio verarbeiten' zum Absenden)"
    except Exception as e:
        logger.error(f"Fehler bei Transkription: {e}")
        return chat_history, chat_history, f"[FEHLER] Transkription fehlgeschlagen: {str(e)}"


def process_audio_sync(audio, chat_history):
    """Verarbeitet die bereits transkribierte Audio-Nachricht"""
    global _last_transcribed_audio

    #Prüfe ob LLM verfügbar ist
    if not bot.gemini or not bot.gemini.llm_available:
        error_msg = "Kein LLM konfiguriert. Bitte gehe zu 'Einstellungen' und gib einen API Key ein."
        chat_history.append({"role": "assistant", "content": f"⚠️ {error_msg}"})
        return chat_history, chat_history, f"[WARN] {error_msg}", None

    #Die Transkription ist bereits im Chat
    if not chat_history or len(chat_history) == 0:
        return chat_history, chat_history, "[FEHLER] Keine Transkription gefunden", None

    last_message = chat_history[-1]
    if last_message.get('role') != 'user':
        return chat_history, chat_history, "[FEHLER] Letzte Nachricht ist keine User-Message", None

    #Extrahiere Text aus der Transkription
    content = last_message.get('content', '')
    user_text = content.replace('🎤 **Transkribierte Audiodatei:**\n', '').strip()

    try:
        #Befehl ausführen
        response = bot._run_async(bot._execute_command(user_text))

        #Bot-Antwort hinzufügen
        chat_history.append({"role": "assistant", "content": response})

        #Cache zurücksetzen damit nächste Aufnahme transkribiert wird
        _last_transcribed_audio = {"path": None, "text": None}

        return chat_history, chat_history, f"[OK] Verarbeitet: {user_text[:50]}...", None
    except Exception as e:
        logger.error(f"Fehler bei Audio-Verarbeitung: {e}")
        return chat_history, chat_history, f"[FEHLER] {str(e)}", None


def process_text_sync(text, chat_history):
    """Verarbeitet Text (sync wrapper)"""
    if not text or text.strip() == "":
        return chat_history, chat_history, "[WARN] Keine Eingabe", ""

    #Prüfe ob LLM verfügbar ist
    if not bot.gemini or not bot.gemini.llm_available:
        error_msg = "Kein LLM konfiguriert. Bitte gehe zu 'Einstellungen' und gib einen API Key ein."
        chat_history.append({"role": "user", "content": text})
        chat_history.append({"role": "assistant", "content": f"⚠️ {error_msg}"})
        return chat_history, chat_history, f"[WARN] {error_msg}", ""

    try:
        #Befehl ausführen
        response = bot._run_async(bot._execute_command(text))

        #ChatHistory aktualisieren
        chat_history.append({"role": "user", "content": text})
        chat_history.append({"role": "assistant", "content": response})

        return chat_history, chat_history, "[OK] Verarbeitet", ""
    except Exception as e:
        logger.error(f"Fehler bei Text-Verarbeitung: {e}")
        return chat_history, chat_history, f"[FEHLER] {str(e)}", ""



def generate_calendar_html(year: int, month: int, events: list) -> str:
    """
    Generiert HTML für einen Monatskalender mit markierten Events

    Args:
        year: Jahr
        month: Monat (1-12)
        events: Liste von Events mit 'start_time' und 'name'

    Returns:
        HTML-String für den Kalender
    """
    berlin_tz = pytz.timezone('Europe/Berlin')

    #Events nach Tag gruppieren
    events_by_day = {}
    for event in events:
        start_time_str = event.get('start_time') or event.get('scheduled_start_time')
        if start_time_str:
            try:
                #Parse ISO format
                if isinstance(start_time_str, str):
                    utc_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    berlin_time = utc_time.astimezone(berlin_tz)
                else:
                    berlin_time = start_time_str

                #Nur Events im angezeigten Monat
                if berlin_time.year == year and berlin_time.month == month:
                    day = berlin_time.day
                    if day not in events_by_day:
                        events_by_day[day] = []
                    events_by_day[day].append({
                        'name': event.get('name', 'Event'),
                        'time': berlin_time.strftime('%H:%M'),
                        'location': event.get('location', ''),
                        'description': event.get('description', ''),
                        'duration': event.get('duration', '')
                    })
            except Exception as e:
                logger.warning(f"Fehler beim Parsen von Event-Zeit: {e}")

    #Deutsche Monatsnamen
    month_names = ['', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                   'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

    #Deutsche Wochentage
    weekdays = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

    #Kalender-Daten generieren
    cal = calendar.Calendar(firstweekday=0)  #Montag = 0
    month_days = cal.monthdayscalendar(year, month)

    #Heute markieren
    today = datetime.now(berlin_tz)
    is_current_month = (today.year == year and today.month == month)
    today_day = today.day if is_current_month else -1

    #CSS Styles
    html = f'''
    <style>
        .calendar-container {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 100%;
            margin: 0 auto;
        }}
        .calendar-header {{
            text-align: center;
            font-size: 1.4em;
            font-weight: 600;
            padding: 15px 0;
            color: #333;
        }}
        .calendar-table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            table-layout: fixed;
        }}
        .calendar-table th {{
            padding: 10px 5px;
            text-align: center;
            font-weight: 600;
            color: #666;
            font-size: 0.85em;
            border-bottom: 2px solid #e0e0e0;
        }}
        .calendar-table td {{
            padding: 8px 4px;
            text-align: center;
            vertical-align: top;
            height: 80px;
            border: 1px solid #e8e8e8;
            position: relative;
        }}
        .calendar-table td:hover {{
            background-color: #f5f5f5;
        }}
        .day-number {{
            font-weight: 500;
            font-size: 0.95em;
            margin-bottom: 4px;
            color: #333;
        }}
        .day-number.today {{
            background-color: #4a90d9;
            color: white;
            border-radius: 50%;
            width: 28px;
            height: 28px;
            line-height: 28px;
            display: inline-block;
        }}
        .day-number.weekend {{
            color: #999;
        }}
        .empty-day {{
            background-color: #fafafa;
        }}
        .events-container {{
            max-height: 50px;
            overflow: hidden;
        }}
        .event-item {{
            font-size: 0.7em;
            background-color: #5865F2;
            color: white;
            padding: 2px 4px;
            border-radius: 3px;
            margin: 2px 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            cursor: help;
            display: block;
        }}
        .event-item:hover {{
            background-color: #4752c4;
        }}
        .event-count {{
            font-size: 0.7em;
            color: #5865F2;
            font-weight: 600;
        }}
    </style>
    <div class="calendar-container">
        <div class="calendar-header">{month_names[month]} {year}</div>
        <table class="calendar-table">
            <thead>
                <tr>
    '''

    #Wochentag-Header
    for i, day in enumerate(weekdays):
        weekend_class = ' class="weekend"' if i >= 5 else ''
        html += f'<th{weekend_class}>{day}</th>'
    html += '</tr></thead><tbody>'

    #Wochen generieren
    for week in month_days:
        html += '<tr>'
        for i, day in enumerate(week):
            if day == 0:
                html += '<td class="empty-day"></td>'
            else:
                #Klassen bestimmen
                day_classes = []
                if day == today_day:
                    day_classes.append('today')
                if i >= 5:  #Wochenende
                    day_classes.append('weekend')

                day_class = ' '.join(day_classes)

                html += '<td>'
                html += f'<div class="day-number {day_class}">{day}</div>'

                #Events für diesen Tag
                if day in events_by_day:
                    day_events = events_by_day[day]
                    html += '<div class="events-container">'

                    for idx, evt in enumerate(day_events[:2]):
                        #Event-Name
                        name_escaped = evt["name"].replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                        name_short = evt["name"][:12] + ('...' if len(evt["name"]) > 12 else '')
                        name_short = name_short.replace('<', '&lt;').replace('>', '&gt;')

                        #Tooltip-Text erstellen
                        tooltip_lines = []
                        tooltip_lines.append(evt["name"])
                        tooltip_lines.append("─" * 20)
                        tooltip_lines.append(f"Uhrzeit: {evt['time']} Uhr")

                        if evt.get('duration'):
                            tooltip_lines.append(f"Dauer: {evt['duration']}")

                        if evt.get('location'):
                            tooltip_lines.append(f"Ort: {evt['location']}")

                        if evt.get('description'):
                            tooltip_lines.append("─" * 20)
                            desc = evt["description"][:300]
                            if len(evt["description"]) > 300:
                                desc += "..."
                            tooltip_lines.append(desc)

                        #Title-Attribut
                        tooltip_text = "\n".join(tooltip_lines)
                        tooltip_text = tooltip_text.replace('"', '&quot;')

                        html += f'<div class="event-item" title="{tooltip_text}">{evt["time"]} {name_short}</div>'

                    if len(day_events) > 2:
                        html += f'<div class="event-count">+{len(day_events) - 2} mehr</div>'

                    html += '</div>'

                html += '</td>'
        html += '</tr>'

    html += '</tbody></table></div>'
    return html


#Speichert Events

class EventCache:
    """Cache für Discord Events - lädt einmal, nutzt oft"""

    def __init__(self):
        self.events = []  #Alle Events
        self.last_fetch = None  #Zeitpunkt des letzten API-Calls
        self.cache_duration = 300  #Cache gilt 5 Minuten (in Sekunden)

    def is_valid(self) -> bool:
        """Prüft ob Cache noch gültig ist"""
        if not self.last_fetch:
            return False
        elapsed = (datetime.now() - self.last_fetch).total_seconds()
        return elapsed < self.cache_duration

    def get_events_for_month(self, year: int, month: int) -> list:
        """Filtert gecachte Events für einen bestimmten Monat"""
        berlin_tz = pytz.timezone('Europe/Berlin')
        filtered = []

        for event in self.events:
            start_time_str = event.get('scheduled_start_time')
            end_time_str = event.get('scheduled_end_time')
            if start_time_str:
                try:
                    utc_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    berlin_time = utc_time.astimezone(berlin_tz)

                    #Dauer berechnen
                    duration_str = ""
                    if end_time_str:
                        end_utc = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                        end_berlin = end_utc.astimezone(berlin_tz)
                        duration_minutes = int((end_utc - utc_time).total_seconds() / 60)
                        if duration_minutes >= 60:
                            hours = duration_minutes // 60
                            mins = duration_minutes % 60
                            duration_str = f"{hours}h {mins}min" if mins > 0 else f"{hours}h"
                        else:
                            duration_str = f"{duration_minutes}min"

                    if berlin_time.year == year and berlin_time.month == month:
                        filtered.append({
                            'name': event.get('name'),
                            'start_time': start_time_str,
                            'end_time': end_time_str,
                            'description': event.get('description', ''),
                            'location': (event.get('entity_metadata') or {}).get('location', ''),
                            'duration': duration_str,
                            'creator_id': event.get('creator_id')
                        })
                except Exception:
                    pass

        return filtered

    def update(self, events: list):
        """Aktualisiert den Cache"""
        self.events = events
        self.last_fetch = datetime.now()
        logger.info(f"Event-Cache aktualisiert: {len(events)} Events")


#Globaler Cache
event_cache = EventCache()


async def fetch_all_events_direct(guild_id: str, token: str) -> list:
    """
    Holt ALLE Events direkt von der Discord API - einmalig für Cache.
    Discord gibt alle scheduled events zurück (keine Paginierung nötig).
    """
    import aiohttp

    url = f"https://discord.com/api/v10/guilds/{guild_id}/scheduled-events"
    headers = {
        'Authorization': f'Bot {token}',
        'Content-Type': 'application/json'
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                events = await response.json()
                logger.info(f"Discord API: {len(events)} Events geladen")
                return events
            else:
                logger.error(f"Discord API Fehler: {response.status}")
                return []


def load_calendar_sync(year: int, month: int) -> str:
    """Lädt Events aus Cache und generiert Kalender-HTML"""
    if not bot.is_initialized or not bot.config:
        return "<p style='color: red;'>Bot nicht initialisiert. Bitte warten...</p>"

    try:
        #Cache prüfen und ggf. aktualisieren
        if not event_cache.is_valid():
            logger.info("Event-Cache abgelaufen, lade neu...")
            all_events = bot._run_async(fetch_all_events_direct(
                bot.config.discord_guild_id,
                bot.config.discord_token
            ))
            event_cache.update(all_events)
        else:
            logger.info("Nutze Event-Cache")

        #Events für den Monat aus Cache holen
        filtered_events = event_cache.get_events_for_month(year, month)
        logger.info(f"Kalender: {len(filtered_events)} Events für {month}/{year}")

        return generate_calendar_html(year, month, filtered_events)

    except Exception as e:
        logger.error(f"Fehler beim Laden des Kalenders: {e}", exc_info=True)
        return f"<p style='color: red;'>Fehler beim Laden: {str(e)}</p>"


def refresh_calendar_with_reload(year: int, month: int) -> str:
    """Aktualisiert den Kalender und erzwingt Cache-Reload"""
    event_cache.last_fetch = None  #Cache invalidieren
    return load_calendar_sync(year, month)


def navigate_calendar(year: int, month: int, direction: str) -> tuple:
    """Navigiert im Kalender (vor/zurück)"""
    if direction == "prev":
        if month == 1:
            month = 12
            year -= 1
        else:
            month -= 1
    elif direction == "next":
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1
    elif direction == "today":
        today = datetime.now(pytz.timezone('Europe/Berlin'))
        year = today.year
        month = today.month

    calendar_html = load_calendar_sync(year, month)
    return year, month, calendar_html


#Gradio Interface erstellen
def create_interface():
    """Erstellt Gradio Web-Interface"""

    #Minimalistisches Theme
    theme = gr.themes.Base()

    #Aktuelles Datum für Kalender-Initialisierung
    today = datetime.now(pytz.timezone('Europe/Berlin'))
    initial_year = today.year
    initial_month = today.month

    with gr.Blocks(title="Discord Voice Bot", theme=theme) as demo:
        gr.Markdown("#Discord Voice Bot")

        #Session State für geräte-spezifischen Chat-Verlauf
        chat_state = gr.State([])

        #State für Kalender-Navigation
        calendar_year = gr.State(initial_year)
        calendar_month = gr.State(initial_month)

        #Browser State für API-Keys
        saved_api_keys = gr.BrowserState(
            default_value={"openai": "", "groq": "", "gemini": ""},
            storage_key="discord_bot_api_keys"
        )

        with gr.Tabs():
            with gr.TabItem("Chat"):
                with gr.Row():
                    with gr.Column(scale=3):
                        #Chat-Display
                        chatbot = gr.Chatbot(
                            label="Konversation",
                            height=500,
                            show_label=True,
                            type="messages"  #Nutze Messages-Format (OpenAI-style)
                        )

                        #Status-Zeile
                        status = gr.Textbox(
                            label="Status",
                            interactive=False,
                            value=init_status if bot.is_initialized else "[FEHLER] Initialisierung fehlgeschlagen"
                        )

                    with gr.Column(scale=1):
                        #LLM-Modell Auswahl
                        gr.Markdown("###LLM Modell")
                        llm_dropdown = gr.Dropdown(
                            choices=get_validated_models(),
                            value=get_validated_models()[0] if get_validated_models() else None,
                            label="Aktives Modell",
                            interactive=True
                        )
                        llm_status = gr.Textbox(
                            label="LLM Status",
                            value=get_current_llm_info(),
                            interactive=False,
                            lines=2
                        )

                        gr.Markdown("---")

                        #Audio-Eingabe
                        gr.Markdown("###Spracheingabe")
                        audio_input = gr.Audio(
                            sources=["microphone"],
                            type="filepath",
                            label="Audio aufnehmen"
                        )
                        gr.Markdown("*Transkription erscheint automatisch im Chat*")
                        audio_btn = gr.Button("Audio verarbeiten", variant="secondary")

                        gr.Markdown("---")

                        #Text-Eingabe
                        gr.Markdown("###Texteingabe")
                        text_input = gr.Textbox(
                            label="Befehl",
                            placeholder="z.B. Zeige mir alle Events...",
                            lines=3
                        )
                        text_btn = gr.Button("Text senden", variant="secondary")

                #Beispiele
                gr.Markdown("---")
                gr.Markdown("###Beispiel-Befehle")
                gr.Examples(
                    examples=[
                        ["Zeige mir alle Events in den nächsten 7 Tagen"],
                        ["Erstelle das Event mit dem Titel Schulung morgen um 15 Uhr für 2 Stunden"],
                        ["Welche Events sind morgen im Labor X"],
                        ["Lösche Event Meeting"],
                        ["Liste alle Channels auf."],
                        ["Sende Nachricht Hallo Team in allgemein"],
                        ["Lösche die letzte Nachricht in allgemein"],
                        ["Zeige Events vom 1. Dezember bis 29. Dezember"]
                    ],
                    inputs=[text_input]
                )

            with gr.TabItem("Kalender"):
                gr.Markdown("###Event-Kalender")
                gr.Markdown("*Alle Discord-Events auf einen Blick*")

                #Navigation
                with gr.Row():
                    prev_btn = gr.Button("< Vorheriger Monat", size="sm")
                    today_btn = gr.Button("Heute", variant="primary", size="sm")
                    next_btn = gr.Button("Nächster Monat >", size="sm")
                    refresh_btn = gr.Button("Aktualisieren", variant="secondary", size="sm")

                #Kalender-Anzeige
                calendar_html = gr.HTML(
                    value="<p>Kalender wird geladen...</p>",
                    label="Kalender"
                )

                #Event-Liste für ausgewählten Monat
                gr.Markdown("---")
                gr.Markdown("*Hover über Events für Details. Events werden in Discord-Blau angezeigt.*")

            with gr.TabItem("Einstellungen"):
                gr.Markdown("###LLM Provider Konfiguration")
                gr.Markdown("*Gib deine API Keys ein und validiere sie. Nach der Validierung kannst du auswählen, welche Modelle im Dropdown erscheinen sollen.*")

                with gr.Row():
                    #OpenAI
                    with gr.Column():
                        gr.Markdown("####OpenAI")
                        openai_key_input = gr.Textbox(
                            label="API Key",
                            placeholder="sk-...",
                            type="password",
                            lines=1
                        )
                        openai_validate_btn = gr.Button("Validieren", variant="secondary", size="sm")
                        openai_status = gr.Textbox(
                            label="Status",
                            value="Nicht validiert",
                            interactive=False,
                            lines=2
                        )
                        openai_models_group = gr.CheckboxGroup(
                            choices=[],
                            label="Modelle für Dropdown auswählen",
                            value=[],
                            visible=False
                        )

                    #Groq
                    with gr.Column():
                        gr.Markdown("####Groq")
                        groq_key_input = gr.Textbox(
                            label="API Key",
                            placeholder="gsk_...",
                            type="password",
                            lines=1
                        )
                        groq_validate_btn = gr.Button("Validieren", variant="secondary", size="sm")
                        groq_status = gr.Textbox(
                            label="Status",
                            value="Nicht validiert",
                            interactive=False,
                            lines=2
                        )
                        groq_models_group = gr.CheckboxGroup(
                            choices=[],
                            label="Modelle für Dropdown auswählen",
                            value=[],
                            visible=False
                        )

                    #Gemini
                    with gr.Column():
                        gr.Markdown("####Google Gemini")
                        gemini_key_input = gr.Textbox(
                            label="API Key",
                            placeholder="AIza...",
                            type="password",
                            lines=1
                        )
                        gemini_validate_btn = gr.Button("Validieren", variant="secondary", size="sm")
                        gemini_status = gr.Textbox(
                            label="Status",
                            value="Nicht validiert",
                            interactive=False,
                            lines=2
                        )
                        gemini_models_group = gr.CheckboxGroup(
                            choices=[],
                            label="Modelle für Dropdown auswählen",
                            value=[],
                            visible=False
                        )

                gr.Markdown("---")

                #Ollama (Lokal)
                gr.Markdown("###Lokale Modelle (Ollama)")
                gr.Markdown("*Ollama ermöglicht das Ausführen von LLMs lokal ohne API Key.*")

                with gr.Row():
                    with gr.Column(scale=2):
                        ollama_status = gr.Textbox(
                            label="Ollama Status",
                            value=get_ollama_status(),
                            interactive=False,
                            lines=1
                        )
                    with gr.Column(scale=1):
                        ollama_refresh_btn = gr.Button("🔄 Aktualisieren", variant="secondary", size="sm")

                #Ollama Modellauswahl
                ollama_models_group = gr.CheckboxGroup(
                    choices=[f"{m} [lokal/free]" for m in _ollama_models] if _ollama_models else [],
                    label="Modelle für Dropdown auswählen",
                    value=[f"{m} [lokal/free]" for m in _ollama_models[:3]] if _ollama_models else [],  #Erste 3 vorausgewählt
                    visible=_ollama_available and len(_ollama_models) > 0
                )

                gr.Markdown("*Tipp: Installiere Modelle mit `ollama pull llama3.2` oder `ollama pull mistral`*")

                gr.Markdown("---")

                #Preisdaten-Sektion
                gr.Markdown("###Modellpreise")
                gr.Markdown("*Preise werden von [LiteLLM](https://github.com/BerriAI/litellm) geladen (Input/Output pro 1M Tokens)*")

                with gr.Row():
                    with gr.Column(scale=2):
                        prices_status = gr.Textbox(
                            label="Preisdaten Status",
                            value=get_prices_status(),
                            interactive=False,
                            lines=1
                        )
                    with gr.Column(scale=1):
                        prices_refresh_btn = gr.Button("Preise aktualisieren", variant="secondary", size="sm")

                gr.Markdown("---")
                gr.Markdown("###Hinweise")
                gr.Markdown("""
                - Nach erfolgreicher Validierung erscheinen die Modelle im Dropdown auf dem Chat-Tab
                - API Keys werden nur im Speicher gehalten (nicht gespeichert)
                - Der aktuelle Provider aus der `.env` Datei ist immer verfügbar
                - Validierung testet den Key mit einer kleinen Anfrage
                - **Ollama** wird automatisch erkannt wenn es läuft (kein API Key nötig)
                - **Preise** werden beim Start automatisch von LiteLLM geladen
                """)

            with gr.TabItem("Tutorial"):
                gr.Markdown("###Anleitung")
                gr.Markdown("Diese App ermoeglicht die sprachbasierte Interaktion mit Discord ueber einen MCP Server.")

                gr.Markdown("---")
                gr.Markdown("###Verfuegbare Befehle")

                gr.Markdown("####Nachrichten")
                gr.Markdown("""
| Funktion | Beispiel |
|----------|----------|
| Nachricht senden | "Sende Nachricht Hallo in allgemein" |
| Nachrichten anzeigen | "Zeige letzte Nachrichten in general" |
| Nachrichten anzeigen (mit Limit) | "Zeige 20 Nachrichten aus allgemein" |
| Nachricht loeschen (nach Inhalt) | "Loesche Nachricht mit Inhalt Test in allgemein" |
| Letzte Nachricht loeschen | "Loesche die letzte Nachricht in allgemein" |
| Channel zusammenfassen | "Worum geht es im Channel allgemein?" oder "Fasse Channel zusammen" |
| Channel zusammenfassen (mit Limit) | "Fasse die letzten 50 Nachrichten in general zusammen" |
                """)

                gr.Markdown("####Events")
                gr.Markdown("""
| Funktion | Beispiel |
|----------|----------|
| Event erstellen | "Erstelle Event Meeting morgen um 15 Uhr" |
| Event erstellen (mit Dauer) | "Erstelle Event Schulung am 10.12 um 14 Uhr fuer 3 Stunden" |
| Events anzeigen (Zeitraum) | "Welche Events sind diese Woche?" |
| Events anzeigen (Tage) | "Zeige Events der naechsten 14 Tage" |
| Events an bestimmtem Tag | "Welche Events sind am 15. Dezember?" |
| Events morgen | "Welche Events sind morgen?" |
| Event loeschen | "Loesche Event Meeting" |
                """)

                gr.Markdown("####Server und Mitglieder")
                gr.Markdown("""
| Funktion | Beispiel |
|----------|----------|
| Server-Info | "Zeige Server-Informationen" |
| Channels auflisten | "Welche Channels gibt es?" |
| Nur Text-Channels | "Liste alle Text-Channels auf" |
| Nur Voice-Channels | "Welche Voice-Channels gibt es?" |
| Online-Anzahl | "Wie viele User sind online?" |
| Online-Mitglieder | "Wer ist aktuell online?" |
                """)

                gr.Markdown("---")
                gr.Markdown("###Tabs")
                gr.Markdown("""
| Tab | Beschreibung |
|-----|--------------|
| Chat | Sprach- oder Texteingabe fuer Discord-Befehle |
| Kalender | Monatsuebersicht aller Discord-Events |
| Einstellungen | LLM-Provider und API-Keys konfigurieren |
| Tutorial | Diese Anleitung |
                """)

                gr.Markdown("---")
                gr.Markdown("###Technische Hinweise")
                gr.Markdown("""
- Die App nutzt das Model Context Protocol (MCP) zur Discord-Kommunikation
- Unterstuetzte LLM-Provider: OpenAI, Groq, Google Gemini, Ollama (lokal)
- Speech-to-Text: Groq Whisper API oder Faster Whisper (lokal)
- Bot-Token und Guild-ID muessen in der .env Datei konfiguriert sein
                """)


        #Chat-Events
        audio_input.change(
            fn=transcribe_audio_sync,
            inputs=[audio_input, chat_state],
            outputs=[chatbot, chat_state, status]
        )

        audio_btn.click(
            fn=process_audio_sync,
            inputs=[audio_input, chat_state],
            outputs=[chatbot, chat_state, status, audio_input]
        )

        text_btn.click(
            fn=process_text_sync,
            inputs=[text_input, chat_state],
            outputs=[chatbot, chat_state, status, text_input]
        )

        text_input.submit(
            fn=process_text_sync,
            inputs=[text_input, chat_state],
            outputs=[chatbot, chat_state, status, text_input]
        )

        #Kalender-Events
        def go_prev(year, month):
            return navigate_calendar(year, month, "prev")

        def go_next(year, month):
            return navigate_calendar(year, month, "next")

        def go_today(year, month):
            return navigate_calendar(year, month, "today")

        prev_btn.click(
            fn=go_prev,
            inputs=[calendar_year, calendar_month],
            outputs=[calendar_year, calendar_month, calendar_html]
        )

        next_btn.click(
            fn=go_next,
            inputs=[calendar_year, calendar_month],
            outputs=[calendar_year, calendar_month, calendar_html]
        )

        today_btn.click(
            fn=go_today,
            inputs=[calendar_year, calendar_month],
            outputs=[calendar_year, calendar_month, calendar_html]
        )

        refresh_btn.click(
            fn=refresh_calendar_with_reload,
            inputs=[calendar_year, calendar_month],
            outputs=[calendar_html]
        )

        #Kalender beim Start laden
        demo.load(
            fn=load_calendar_sync,
            inputs=[calendar_year, calendar_month],
            outputs=[calendar_html]
        )

        #=== LLM EINSTELLUNGEN EVENT HANDLERS ===

        #LLM Modell wechseln
        def on_llm_change(model_selection):
            result = switch_llm_model(model_selection)
            info = get_current_llm_info()
            return result, info

        llm_dropdown.change(
            fn=on_llm_change,
            inputs=[llm_dropdown],
            outputs=[status, llm_status]
        )

        #OpenAI validieren
        def on_openai_validate(api_key, saved_keys):
            result = validate_openai_key(api_key)
            if _validated_providers["openai"]["valid"]:
                #Modelle mit Preisen für CheckboxGroup
                choices = get_model_choices_with_prices("openai")
                #Erste 5 vorauswählen
                default_selected = choices[:5]
                #Auswahl speichern
                _selected_models["openai"] = [extract_model_name(c) for c in default_selected]
                checkbox_update = gr.update(choices=choices, value=default_selected, visible=True)
                #API-Key im Browser speichern
                saved_keys["openai"] = api_key.strip()
            else:
                checkbox_update = gr.update(visible=False)
                saved_keys["openai"] = ""  #Bei Fehler Key entfernen
            dropdown_update = update_model_dropdown()
            info = get_current_llm_info()
            return result, checkbox_update, dropdown_update, info, saved_keys

        openai_validate_btn.click(
            fn=on_openai_validate,
            inputs=[openai_key_input, saved_api_keys],
            outputs=[openai_status, openai_models_group, llm_dropdown, llm_status, saved_api_keys]
        )

        #OpenAI Modellauswahl ändern
        def on_openai_models_change(selected):
            model_names = [extract_model_name(s) for s in selected]
            update_selected_models("openai", model_names)
            return update_model_dropdown()

        openai_models_group.change(
            fn=on_openai_models_change,
            inputs=[openai_models_group],
            outputs=[llm_dropdown]
        )

        #Groq validieren
        def on_groq_validate(api_key, saved_keys):
            result = validate_groq_key(api_key)
            if _validated_providers["groq"]["valid"]:
                choices = get_model_choices_with_prices("groq")
                default_selected = choices[:5]
                _selected_models["groq"] = [extract_model_name(c) for c in default_selected]
                checkbox_update = gr.update(choices=choices, value=default_selected, visible=True)
                #API-Key im Browser speichern
                saved_keys["groq"] = api_key.strip()
            else:
                checkbox_update = gr.update(visible=False)
                saved_keys["groq"] = ""
            dropdown_update = update_model_dropdown()
            info = get_current_llm_info()
            return result, checkbox_update, dropdown_update, info, saved_keys

        groq_validate_btn.click(
            fn=on_groq_validate,
            inputs=[groq_key_input, saved_api_keys],
            outputs=[groq_status, groq_models_group, llm_dropdown, llm_status, saved_api_keys]
        )

        #Groq Modellauswahl ändern
        def on_groq_models_change(selected):
            model_names = [extract_model_name(s) for s in selected]
            update_selected_models("groq", model_names)
            return update_model_dropdown()

        groq_models_group.change(
            fn=on_groq_models_change,
            inputs=[groq_models_group],
            outputs=[llm_dropdown]
        )

        #Gemini validieren
        def on_gemini_validate(api_key, saved_keys):
            result = validate_gemini_key(api_key)
            if _validated_providers["gemini"]["valid"]:
                choices = get_model_choices_with_prices("gemini")
                default_selected = choices[:5]
                _selected_models["gemini"] = [extract_model_name(c) for c in default_selected]
                checkbox_update = gr.update(choices=choices, value=default_selected, visible=True)
                #API-Key im Browser speichern
                saved_keys["gemini"] = api_key.strip()
            else:
                checkbox_update = gr.update(visible=False)
                saved_keys["gemini"] = ""
            dropdown_update = update_model_dropdown()
            info = get_current_llm_info()
            return result, checkbox_update, dropdown_update, info, saved_keys

        gemini_validate_btn.click(
            fn=on_gemini_validate,
            inputs=[gemini_key_input, saved_api_keys],
            outputs=[gemini_status, gemini_models_group, llm_dropdown, llm_status, saved_api_keys]
        )

        #Gemini Modellauswahl ändern
        def on_gemini_models_change(selected):
            model_names = [extract_model_name(s) for s in selected]
            update_selected_models("gemini", model_names)
            return update_model_dropdown()

        gemini_models_group.change(
            fn=on_gemini_models_change,
            inputs=[gemini_models_group],
            outputs=[llm_dropdown]
        )

        #Ollama aktualisieren
        def on_ollama_refresh():
            result = refresh_ollama_models()
            status = get_ollama_status()
            if _ollama_available and _ollama_models:
                choices = [f"{m} [lokal/free]" for m in _ollama_models]
                default_selected = choices[:3]  #Erste 3 vorauswählen
                _selected_models["ollama"] = [extract_model_name(c) for c in default_selected]
                checkbox_update = gr.update(choices=choices, value=default_selected, visible=True)
            else:
                checkbox_update = gr.update(choices=[], value=[], visible=False)
            dropdown_update = update_model_dropdown()
            info = get_current_llm_info()
            return status, checkbox_update, dropdown_update, info

        ollama_refresh_btn.click(
            fn=on_ollama_refresh,
            inputs=[],
            outputs=[ollama_status, ollama_models_group, llm_dropdown, llm_status]
        )

        #Ollama Modellauswahl ändern
        def on_ollama_models_change(selected):
            model_names = [extract_model_name(s) for s in selected]
            update_selected_models("ollama", model_names)
            return update_model_dropdown()

        ollama_models_group.change(
            fn=on_ollama_models_change,
            inputs=[ollama_models_group],
            outputs=[llm_dropdown]
        )

        #Preise aktualisieren
        def on_prices_refresh():
            fetch_litellm_prices()
            status = get_prices_status()
            dropdown_update = update_model_dropdown()
            return status, dropdown_update

        prices_refresh_btn.click(
            fn=on_prices_refresh,
            inputs=[],
            outputs=[prices_status, llm_dropdown]
        )

        def on_page_load(saved_keys):
            """Lädt gespeicherte API-Keys aus dem Browser und validiert sie automatisch"""
            results = {
                "openai_key": "",
                "openai_status": "Nicht validiert",
                "openai_checkbox": gr.update(visible=False),
                "groq_key": "",
                "groq_status": "Nicht validiert",
                "groq_checkbox": gr.update(visible=False),
                "gemini_key": "",
                "gemini_status": "Nicht validiert",
                "gemini_checkbox": gr.update(visible=False),
            }

            if not saved_keys:
                return (
                    results["openai_key"], results["openai_status"], results["openai_checkbox"],
                    results["groq_key"], results["groq_status"], results["groq_checkbox"],
                    results["gemini_key"], results["gemini_status"], results["gemini_checkbox"],
                    update_model_dropdown(), get_current_llm_info()
                )

            #OpenAI Key wiederherstellen
            if saved_keys.get("openai"):
                results["openai_key"] = saved_keys["openai"]
                validation_result = validate_openai_key(saved_keys["openai"])
                results["openai_status"] = validation_result
                if _validated_providers["openai"]["valid"]:
                    choices = get_model_choices_with_prices("openai")
                    default_selected = choices[:5]
                    _selected_models["openai"] = [extract_model_name(c) for c in default_selected]
                    results["openai_checkbox"] = gr.update(choices=choices, value=default_selected, visible=True)

            #Groq Key wiederherstellen
            if saved_keys.get("groq"):
                results["groq_key"] = saved_keys["groq"]
                validation_result = validate_groq_key(saved_keys["groq"])
                results["groq_status"] = validation_result
                if _validated_providers["groq"]["valid"]:
                    choices = get_model_choices_with_prices("groq")
                    default_selected = choices[:5]
                    _selected_models["groq"] = [extract_model_name(c) for c in default_selected]
                    results["groq_checkbox"] = gr.update(choices=choices, value=default_selected, visible=True)

            #Gemini Key wiederherstellen
            if saved_keys.get("gemini"):
                results["gemini_key"] = saved_keys["gemini"]
                validation_result = validate_gemini_key(saved_keys["gemini"])
                results["gemini_status"] = validation_result
                if _validated_providers["gemini"]["valid"]:
                    choices = get_model_choices_with_prices("gemini")
                    default_selected = choices[:5]
                    _selected_models["gemini"] = [extract_model_name(c) for c in default_selected]
                    results["gemini_checkbox"] = gr.update(choices=choices, value=default_selected, visible=True)

            return (
                results["openai_key"], results["openai_status"], results["openai_checkbox"],
                results["groq_key"], results["groq_status"], results["groq_checkbox"],
                results["gemini_key"], results["gemini_status"], results["gemini_checkbox"],
                update_model_dropdown(), get_current_llm_info()
            )

        demo.load(
            fn=on_page_load,
            inputs=[saved_api_keys],
            outputs=[
                openai_key_input, openai_status, openai_models_group,
                groq_key_input, groq_status, groq_models_group,
                gemini_key_input, gemini_status, gemini_models_group,
                llm_dropdown, llm_status
            ]
        )

    return demo


if __name__ == "__main__":
    logger.info("Starte Discord Voice Bot Gradio Interface...")

    #Interface erstellen und starten
    demo = create_interface()

    #Server starten
    demo.launch(
        server_name="0.0.0.0",  #Erreichbar im Netzwerk
        server_port=7860,
        share=False,  #Setze auf True für öffentlichen Link
        show_error=True
    )
