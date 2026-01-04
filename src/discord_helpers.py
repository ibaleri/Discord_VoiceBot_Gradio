"""
Discord Helper-Funktionen für benutzerfreundliche Event-Erstellung
Wrapper um die rohe Discord API mit zusätzlicher Intelligenz
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import dateparser  #python-dateparser für natürliche Zeitangaben
import pytz

logger = logging.getLogger(__name__)


class DiscordEventHelper:
    """
    High-Level Helper-Klasse für Discord Event-Management

    Bietet benutzerfreundliche Funktionen für:
    - Event-Erstellung mit natürlichen Zeitangaben
    - Event-Verwaltung (Listen, Bearbeiten, Löschen)
    - Automatische Zeitzone-Konvertierung
    - Channel- und Server-Management
    """

    def __init__(self, config, mcp_client, gemini=None):
        self.config = config
        self.mcp_client = mcp_client
        self.gemini = gemini  #Für Rechtschreibprüfung
        self.guild_id = config.discord_guild_id
        self.timezone = pytz.timezone('Europe/Berlin')  #Deutsche Zeitzone
        self.channels_cache = {}
        self.events_cache = []

    async def initialize(self):
        """Initialisiert Helper (lädt Channels, etc.)"""
        try:
            logger.info("Initialisiere Discord Helper...")

            #Channels laden und cachen
            await self._load_channels()

            logger.info(f"Discord Helper initialisiert - {len(self.channels_cache)} Channels geladen")

        except Exception as e:
            logger.error(f"Fehler bei Helper-Initialisierung: {e}", exc_info=True)

    def get_available_functions(self) -> Dict[str, Any]:
        """Gibt Liste der verfügbaren Helper-Funktionen zurück"""
        return {
            "create_event": {
                "description": "Erstellt ein Discord Scheduled Event",
                "params": ["name", "description", "start_time", "duration_hours", "location", "event_type"]
            },
            "list_upcoming_events": {
                "description": "Listet kommende Events auf - für ZEITRÄUME (nächste Woche, in den nächsten X Tagen)",
                "params": ["limit", "days_ahead", "timeframe", "location", "group_by_days"]
            },
            "list_events_on_specific_day": {
                "description": "Listet Events an EINEM BESTIMMTEN TAG auf (in 14 Tagen, am 25.11, morgen)",
                "params": ["from_date", "location", "limit"]
            },
            "delete_event_by_name": {
                "description": "Löscht ein Event anhand des Namens",
                "params": ["event_name"]
            },
            "send_message": {
                "description": "Sendet eine Nachricht in einen Channel (channel_id kann Channel-Name wie 'allgemein' oder ID sein)",
                "params": ["channel_id", "content", "mentions"]
            },
            "get_server_info": {
                "description": "Server-Informationen abrufen",
                "params": []
            },
            "list_channels": {
                "description": "Listet Channels auf",
                "params": ["channel_type"]
            },
            "get_online_members_count": {
                "description": "Gibt die Anzahl der online Mitglieder zurück",
                "params": []
            },
            "list_online_members": {
                "description": "Listet online Mitglieder auf (mit Namen)",
                "params": ["limit"]
            },
            "delete_message": {
                "description": "Löscht eine Nachricht (channel_id kann Channel-Name oder ID sein, content ist der Nachrichtentext zum Suchen ODER message_id ist die direkte Nachrichten-ID)",
                "params": ["channel_id", "message_id", "content"]
            },
            "get_channel_messages": {
                "description": "Zeigt die letzten Nachrichten aus einem Channel an",
                "params": ["channel_id", "limit"]
            },
            "summarize_channel": {
                "description": "Fasst die letzten Nachrichten eines Channels zusammen (Worum geht es im Channel X?)",
                "params": ["channel_id", "limit"]
            }
        }

    async def create_event(
        self,
        name: str,
        start_time: str,
        description: str = "",
        duration_hours: float = 1.0,
        location: str = "Discord",
        event_type: str = "online",
        channel_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Erstellt ein Discord Scheduled Event mit benutzerfreundlichen Parametern

        Args:
            name: Event-Name
            start_time: Natürliche Zeitangabe (z.B. "morgen 15 Uhr", "nächste Woche Montag 18:00")
            description: Event-Beschreibung (optional, Standard: "Event: {name}")
            duration_hours: Dauer in Stunden (Standard: 1.0)
            location: Ort für Online-Events
            event_type: "online" (external), "voice", oder "stage"
            channel_id: Channel ID für voice/stage Events (optional)

        Returns:
            Created event data
        """
        try:
            logger.info(f"Erstelle Event: {name} - {start_time}")

            #Fallback für leere Beschreibung
            if not description or description.strip() == "":
                description = f"Event: {name}"

            #Name und Beschreibung normalisieren und korrigieren
            name = await self._normalize_and_correct_text(name)
            description = await self._normalize_and_correct_text(description)

            #Zeitangabe parsen
            start_dt, end_dt = self._parse_time(start_time, duration_hours)

            #Entity type bestimmen
            entity_type_map = {
                "online": 3,    #EXTERNAL
                "voice": 2,     #VOICE
                "stage": 1      #STAGE_INSTANCE
            }
            entity_type = entity_type_map.get(event_type.lower(), 3)

            #Event-Daten zusammenstellen
            event_data = {
                "name": name,
                "description": description,
                "scheduled_start_time": start_dt.strftime('%Y-%m-%dT%H:%M:%S'),
                "scheduled_end_time": end_dt.strftime('%Y-%m-%dT%H:%M:%S'),
                "privacy_level": 2,
                "entity_type": entity_type
            }

            #Type-spezifische Felder
            if entity_type == 3:  #External
                event_data["entity_metadata"] = {"location": location}
            elif entity_type in [1, 2]:  #Voice/Stage
                if not channel_id:
                    #Versuche ersten Voice Channel zu fiden
                    channel_id = await self._find_voice_channel()
                if channel_id:
                    event_data["channel_id"] = channel_id
                else:
                    raise ValueError("Channel ID erforderlich für Voice/Stage Events")

            #Event erstellen via MCP
            endpoint = f"/guilds/{self.guild_id}/scheduled-events"
            result = await self.mcp_client.call_discord_api("POST", endpoint, event_data)

            logger.info(f"[OK] Event erstellt: {result.get('id', 'unknown')}")

            #Cache aktualisieren
            self.events_cache.append(result)

            #Konvertiere UTC zurück zu Berlin-Zeit für Anzeige
            start_berlin = start_dt.astimezone(self.timezone)
            end_berlin = end_dt.astimezone(self.timezone)

            return {
                "success": True,
                "event_id": result.get('id'),
                "event_name": name,
                "description": description,  #Beschreibung für GUI
                "location": location,        #Location für GUI
                "duration_hours": duration_hours,  #Dauer für GUI
                "start_time": start_berlin.strftime('%Y-%m-%d %H:%M'),
                "end_time": end_berlin.strftime('%Y-%m-%d %H:%M'),
                "data": result
            }

        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Events: {e}", exc_info=True)
            raise

    async def list_upcoming_events(
        self,
        limit: int = 50,
        days_ahead: Optional[int] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        location: Optional[str] = None,
        group_by_days: bool = False,
        timeframe: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Listet kommende Events auf

        Args:
            limit: Maximale Anzahl Events
            days_ahead: Optional - Events der nächsten X Tage (z.B. 7 für nächste Woche)
            from_date: Optional - Start-Datum für Zeitraum-Filter (ISO format oder natürliche Sprache)
            to_date: Optional - End-Datum für Zeitraum-Filter (ISO format oder natürliche Sprache)
            location: Optional - Filter nach Ort/Location (z.B. "Labor X", "Raum 123")
            group_by_days: Optional - Gruppiere Events nach Tagen (Standard: False)
            timeframe: Optional - Zeitraum-Preset: "today", "tomorrow", "week", "2weeks", "month"
                       (wird in days_ahead umgewandelt)

        Returns:
            Liste der Events mit erweiterten Informationen
            Wenn group_by_days=True: Gruppiert nach Tagen mit deutscher Zeitzone
        """
        #Timeframe-Preset in days_ahead umwandeln falls angegeben
        if timeframe and not days_ahead:
            timeframe_map = {
                "today": 1,
                "tomorrow": 2,
                "week": 7,
                "2weeks": 14,
                "month": 30
            }
            days_ahead = timeframe_map.get(timeframe, 7)
        try:
            logger.info(f"Lade kommende Events (limit={limit}, days_ahead={days_ahead}, from_date={from_date}, to_date={to_date}, location={location})...")

            endpoint = f"/guilds/{self.guild_id}/scheduled-events"
            result = await self.mcp_client.call_discord_api("GET", endpoint)

            #Handle wrapped list format 
            events = result.get('items', []) if isinstance(result, dict) and 'items' in result else result

            #Zeitraum bestimmen
            now = datetime.now(pytz.UTC)

            #Start-Zeit (Standard: jetzt)
            start_filter = now
            if from_date:
                #_parse_time gibt (start_dt, end_dt) Tuple zurück
                parsed_from, _ = self._parse_time(from_date)
                start_filter = parsed_from  #Ist bereits ein datetime Objekt

            #End-Zeit bestimmen
            end_filter = None
            if days_ahead:
                end_filter = now + timedelta(days=days_ahead)
            elif to_date:
                #_parse_time gibt (start_dt, end_dt) Tuple zurück
                parsed_to, _ = self._parse_time(to_date)
                end_filter = parsed_to  #Ist bereits ein datetime Objekt

                #Wenn end_filter VOR start_filter liegt, muss es im nächsten Jahr sein
                #z.B. "28. November bis 3. März" -> März muss 2026 sein, nicht 2025
                if end_filter < start_filter:
                    end_filter = end_filter.replace(year=end_filter.year + 1)
                    logger.info(f"End-Datum korrigiert auf nächstes Jahr: {end_filter}")

            #Events filtern
            filtered_events = []
            for event in events:
                start_time_str = event.get('scheduled_start_time')
                if start_time_str:
                    start_time = dateparser.parse(start_time_str)

                    #Muss nach start_filter sein
                    if start_time < start_filter:
                        continue

                    #Wenn end_filter gesetzt, muss Event davor sein
                    if end_filter and start_time > end_filter:
                        continue

                    #Location-Filter (falls angegeben)
                    if location:
                        event_location = None
                        #Location aus entity_metadata holen
                        entity_metadata = event.get('entity_metadata')
                        if entity_metadata:
                            event_location = entity_metadata.get('location', '')

                        #Fuzzy-Match: Case-insensitive substring-Suche
                        if not event_location or location.lower() not in event_location.lower():
                            continue  #Event überspringen, wenn Location nicht passt

                    #Event hinzufügen mit zusätzlichen berechneten Feldern
                    event_data = event.copy()

                    #End-Zeit berechnen falls vorhanden
                    end_time_str = event.get('scheduled_end_time')
                    if end_time_str:
                        end_time = dateparser.parse(end_time_str)
                        duration_minutes = int((end_time - start_time).total_seconds() / 60)
                        event_data['duration_minutes'] = duration_minutes

                    filtered_events.append(event_data)

            #Sortieren nach Start-Zeit
            filtered_events.sort(key=lambda e: e.get('scheduled_start_time', ''))

            #Limit anwenden
            filtered_events = filtered_events[:limit]

            #Cache aktualisieren
            self.events_cache = filtered_events

            logger.info(f"[OK] {len(filtered_events)} Events gefunden")

            #Events für Response vorbereiten
            events_list = [
                {
                    "id": e.get('id'),
                    "name": e.get('name'),
                    "description": e.get('description'),
                    "start_time": e.get('scheduled_start_time'),
                    "end_time": e.get('scheduled_end_time'),
                    "duration_minutes": e.get('duration_minutes'),
                    "creator_id": e.get('creator_id'),
                    "status": e.get('status'),
                    "entity_type": e.get('entity_type'),
                    "location": e.get('entity_metadata', {}).get('location') if e.get('entity_metadata') else None
                }
                for e in filtered_events
            ]

            #Basis-Response
            response = {
                "success": True,
                "count": len(filtered_events),
                "timeframe": {
                    "from": start_filter.isoformat(),
                    "to": end_filter.isoformat() if end_filter else None,
                    "days_ahead": days_ahead,
                    "preset": timeframe
                },
                "location_filter": location,
                "events": events_list
            }

            #Falls group_by_days---- Gruppierung nach Tagen hinzufügen
            if group_by_days:
                events_by_day = {}
                berlin_tz = pytz.timezone('Europe/Berlin')

                for event in events_list:
                    start_time_str = event.get('start_time')
                    if start_time_str:
                        #In Berlin-Zeit konvertieren
                        utc_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                        berlin_time = utc_time.astimezone(berlin_tz)

                        #Tag
                        day_key = berlin_time.strftime('%Y-%m-%d')
                        weekday = berlin_time.strftime('%A')

                        #Deutsche Wochentage
                        weekday_de = {
                            'Monday': 'Montag', 'Tuesday': 'Dienstag',
                            'Wednesday': 'Mittwoch', 'Thursday': 'Donnerstag',
                            'Friday': 'Freitag', 'Saturday': 'Samstag',
                            'Sunday': 'Sonntag'
                        }.get(weekday, weekday)

                        if day_key not in events_by_day:
                            events_by_day[day_key] = {
                                'date': day_key,
                                'weekday': weekday_de,
                                'events': []
                            }

                        #Event-Details mit Berlin-Zeit
                        event_info = event.copy()
                        event_info['start_time_berlin'] = berlin_time.strftime('%H:%M')

                        if event.get('end_time'):
                            end_utc = datetime.fromisoformat(event['end_time'].replace('Z', '+00:00'))
                            end_berlin = end_utc.astimezone(berlin_tz)
                            event_info['end_time_berlin'] = end_berlin.strftime('%H:%M')

                        events_by_day[day_key]['events'].append(event_info)

                #Nach Datum sortieren
                sorted_days = sorted(events_by_day.values(), key=lambda d: d['date'])

                #Gruppierte Daten zur Response hinzufügen
                response['events_by_day'] = sorted_days
                response['days_with_events'] = len(sorted_days)
                response['total_events'] = len(events_list)

            return response

        except Exception as e:
            logger.error(f"Fehler beim Laden der Events: {e}", exc_info=True)
            raise

    async def list_events_on_specific_day(
        self,
        from_date: str,
        to_date: Optional[str] = None,
        location: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Listet Events an einem bestimmten Tag auf (vereinfachte Funktion für LLM)

        Args:
            from_date: Start-Datum (natürliche Zeitangabe wie "in 14 Tagen", "25. November")
            to_date: Optional - End-Datum (wird ignoriert, automatisch der ganze Tag)
            location: Optional - Filter nach Ort/Location
            limit: Maximale Anzahl Events (Standard: 50)

        Returns:
            Events gruppiert nach Tagen
        """
        try:
            #Parse from_date und setze auf Tagesbeginn (00:00)
            from_dt, _ = self._parse_time(from_date)

            #Konvertiere UTC zu Berlin Zeit, um korrekten Tag zu bekommen
            from_dt_berlin = from_dt.astimezone(self.timezone)

            #Setze auf Tagesbeginn
            from_dt_start_berlin = from_dt_berlin.replace(hour=0, minute=0, second=0, microsecond=0)

            #End-Zeit: Nächster Tag 00:00 in Berlin Zeit (
            to_dt_end_berlin = from_dt_start_berlin + timedelta(days=1)

            #Zurück zu UTC konvertieren für API-Call
            from_dt_start = from_dt_start_berlin.astimezone(pytz.UTC)
            to_dt_end = to_dt_end_berlin.astimezone(pytz.UTC)

            #Konvertiere zu Strings für list_upcoming_events
            from_date_str = from_dt_start.strftime("%Y-%m-%d %H:%M")
            to_date_str = to_dt_end.strftime("%Y-%m-%d %H:%M")

            logger.info(f"list_events_on_specific_day: {from_date} -> {from_dt_start_berlin.date()} (ganzer Tag)")

            #Rufe list_upcoming_events mit group_by_days=True auf
            return await self.list_upcoming_events(
                limit=limit,
                from_date=from_date_str,
                to_date=to_date_str,
                location=location,
                group_by_days=True
            )

        except Exception as e:
            logger.error(f"Fehler bei list_events_on_specific_day: {e}", exc_info=True)
            raise

    async def get_events_in_timeframe(
        self,
        timeframe: str = "week",
        limit: int = 100,
        location: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        [WRAPPER] Listet Events gruppiert nach Tagen auf und nutzt intern list_upcoming_events()

        Dies ist ein Wrapper um list_upcoming_events(group_by_days=True)
        für Labor-Buchungen und Kalenderansichten.

        Args:
            timeframe: Zeitraum-Preset: "today", "tomorrow", "week", "2weeks", "month"
            limit: Maximale Anzahl Events (Standard: 100)
            location: Optional - Filter nach Ort/Location

        Returns:
            Events gruppiert nach Tagen mit deutscher Zeitzone
        """
        return await self.list_upcoming_events(
            limit=limit,
            timeframe=timeframe,
            location=location,
            group_by_days=True  #Aktiviert Tag-Gruppierung
        )

    async def delete_event_by_name(self, event_name: str) -> Dict[str, Any]:
        """
        Löscht ein Event anhand des Namens (einfache Hilfsfunktion)

        Args:
            event_name: Name des zu löschenden Events

        Returns:
            Erfolgs-Status mit gelöschtem Event-Namen
        """
        try:
            logger.info(f"Lösche Event mit Namen: {event_name}")

            #Event ID automatisch finden
            event_id = await self._find_event_by_name(event_name)

            #Event löschen
            endpoint = f"/guilds/{self.guild_id}/scheduled-events/{event_id}"
            await self.mcp_client.call_discord_api("DELETE", endpoint)

            logger.info(f"[OK] Event '{event_name}' erfolgreich gelöscht (ID: {event_id})")

            #Cache aktualisieren
            self.events_cache = [e for e in self.events_cache if e.get('id') != event_id]

            return {
                "success": True,
                "event_name": event_name,
                "event_id": event_id,
                "message": f"Event '{event_name}' erfolgreich gelöscht"
            }

        except Exception as e:
            logger.error(f"Fehler beim Löschen von Event '{event_name}': {e}", exc_info=True)
            return {
                "success": False,
                "event_name": event_name,
                "error": str(e)
            }

    async def update_event(self, event_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aktualisiert ein Event

        Args:
            event_id: Event ID
            updates: Dict mit zu aktualisierenden Feldern

        Returns:
            Aktualisierte Event-Daten
        """
        try:
            logger.info(f"Aktualisiere Event: {event_id}")

            #Zeit-Felder parsen falls vorhanden
            if 'start_time' in updates:
                start_dt, _ = self._parse_time(updates['start_time'])
                updates['scheduled_start_time'] = start_dt.strftime('%Y-%m-%dT%H:%M:%S')
                del updates['start_time']

            endpoint = f"/guilds/{self.guild_id}/scheduled-events/{event_id}"
            result = await self.mcp_client.call_discord_api("PATCH", endpoint, updates)

            logger.info(f"[OK] Event aktualisiert: {event_id}")

            return {
                "success": True,
                "event_id": event_id,
                "data": result
            }

        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren des Events: {e}", exc_info=True)
            raise

    async def send_message(
        self,
        channel_id: str,
        content: str,
        mentions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Sendet eine Nachricht in einen Channel

        Args:
            channel_id: Channel ID oder Channel-Name
            content: Nachricht
            mentions: Optional, Liste von User-IDs

        Returns:
            Gesendete Nachricht
        """
        try:
            #Channel ID auflösen falls Name gegeben
            if not channel_id.isdigit():
                channel_id = await self._find_channel_by_name(channel_id)

            logger.info(f"Sende Nachricht in Channel: {channel_id}")

            #Nachricht normalisieren und korrigieren
            content = await self._normalize_and_correct_text(content)

            #Mentions hinzufügen
            if mentions:
                mention_str = " ".join([f"<@{uid}>" for uid in mentions])
                content = f"{mention_str} {content}"

            endpoint = f"/channels/{channel_id}/messages"
            result = await self.mcp_client.call_discord_api(
                "POST",
                endpoint,
                {"content": content}
            )

            logger.info(f"[OK] Nachricht gesendet: {result.get('id')}")

            return {
                "success": True,
                "message_id": result.get('id'),
                "content": content
            }

        except Exception as e:
            logger.error(f"Fehler beim Senden der Nachricht: {e}", exc_info=True)
            raise

    async def get_server_info(self) -> Dict[str, Any]:
        """Ruft Server-Informationen ab"""
        try:
            logger.info("Lade Server-Info...")

            endpoint = f"/guilds/{self.guild_id}"
            result = await self.mcp_client.call_discord_api("GET", endpoint)

            return {
                "success": True,
                "server": {
                    "id": result.get('id'),
                    "name": result.get('name'),
                    "description": result.get('description'),
                    "member_count": result.get('approximate_member_count'),
                    "created_at": result.get('id')  #Snowflake enthält Timestamp
                }
            }

        except Exception as e:
            logger.error(f"Fehler beim Laden der Server-Info: {e}", exc_info=True)
            raise

    async def list_channels(self, channel_type: str = "all") -> Dict[str, Any]:
        """
        Listet Channels auf

        Args:
            channel_type: "text", "voice", "all"

        Returns:
            Liste der Channels
        """
        try:
            await self._load_channels()

            channels = list(self.channels_cache.values())

            #Filtern nach Type
            if channel_type == "text":
                channels = [c for c in channels if c.get('type') == 0]
            elif channel_type == "voice":
                channels = [c for c in channels if c.get('type') == 2]

            return {
                "success": True,
                "count": len(channels),
                "channels": [
                    {
                        "id": c.get('id'),
                        "name": c.get('name'),
                        "type": c.get('type')
                    }
                    for c in channels
                ]
            }

        except Exception as e:
            logger.error(f"Fehler beim Laden der Channels: {e}", exc_info=True)
            raise

    async def get_online_members_count(self) -> Dict[str, Any]:
        """
        Gibt die Anzahl der online Mitglieder zurück

        Returns:
            Anzahl der online Mitglieder
        """
        try:
            logger.info("Lade Online-Member-Anzahl...")

            #Verwende Guild-Info mit Counts 
            endpoint = f"/guilds/{self.guild_id}?with_counts=true"
            guild_info = await self.mcp_client.call_discord_api("GET", endpoint)

            presence_count = guild_info.get('approximate_presence_count', 0)
            member_count = guild_info.get('approximate_member_count', 0)

            logger.info(f"Online: ~{presence_count} von {member_count} Mitgliedern")

            return {
                "success": True,
                "online_count": presence_count,
                "total_members": member_count,
                "message": f"{presence_count} von {member_count} Mitgliedern sind online"
            }

        except Exception as e:
            logger.error(f"Fehler beim Laden der Online-Member-Anzahl: {e}", exc_info=True)
            raise

    async def list_online_members(self, limit: int = 20) -> Dict[str, Any]:
        """
        Listet Server-Mitglieder und Online-Anzahl auf

        HINWEIS: Die Discord REST API gibt keinen Online-Status pro User zurück.
        Der Online-Status (Presence) ist nur über Gateway/WebSocket verfügbar.
        Diese Funktion zeigt daher:
        - approximate_presence_count (ca. Anzahl online)
        - Liste aller Server-Mitglieder (wenn Server Members Intent aktiviert)

        Args:
            limit: Max. Anzahl anzuzeigender Mitglieder (Standard: 20)

        Returns:
            Online-Anzahl und Member-Liste (ohne Online-Status pro User)
        """
        try:
            logger.info(f"Lade Member-Liste und Online-Anzahl (limit: {limit})...")

            #Hole erst die Guild-Info mit Online-Anzahl
            endpoint_guild = f"/guilds/{self.guild_id}?with_counts=true"
            guild_info = await self.mcp_client.call_discord_api("GET", endpoint_guild)

            presence_count = guild_info.get('approximate_presence_count', 0)
            member_count = guild_info.get('approximate_member_count', 0)

            logger.info(f"Server: ~{presence_count} online von ~{member_count} Mitgliedern")

            #Versuche Members zu laden
            endpoint = f"/guilds/{self.guild_id}/members?limit=1000"
            try:
                members = await self.mcp_client.call_discord_api("GET", endpoint)

                #Handle wrapped list format
                if isinstance(members, dict) and 'items' in members:
                    members = members.get('items', [])

                #Filtere Bots raus und formatiere
                all_members = []
                for member in members:
                    user = member.get('user', {})

                    #Bots überspringen
                    if user.get('bot', False):
                        continue

                    username = user.get('username', 'Unknown')
                    global_name = user.get('global_name') or username
                    discriminator = user.get('discriminator', '0')

                    #Display-Name aus Member-Daten
                    display_name = member.get('nick') or global_name

                    all_members.append({
                        "id": user.get('id'),
                        "username": username,
                        "display_name": display_name,
                        "discriminator": discriminator if discriminator != '0' else None
                    })

                #Limitiere Ausgabe
                limited_members = all_members[:limit]

                logger.info(f"Member-Liste: {len(all_members)} Mitglieder geladen (zeige {len(limited_members)})")

                #Wenn nur wenige Members geladen werden konnten 
                if len(all_members) < 3 and member_count > 3:
                    return {
                        "success": True,
                        "online_count": presence_count,
                        "total_members": member_count,
                        "showing": 0,
                        "members": [],
                        "message": f"~{presence_count} von {member_count} Mitgliedern sind online. (Member-Liste nicht verfügbar - Server Members Intent fehlt)"
                    }

                return {
                    "success": True,
                    "online_count": presence_count,
                    "total_members": member_count,
                    "showing": len(limited_members),
                    "members": limited_members,
                    "message": f"~{presence_count} von {member_count} Mitgliedern sind online."
                }

            except Exception as member_error:
                #Wenn Member-Liste nicht verfügbar ist (403 Forbidden)
                logger.warning(f"Kann Member-Liste nicht laden: {member_error}")

                return {
                    "success": True,
                    "online_count": presence_count,
                    "total_members": member_count,
                    "showing": 0,
                    "members": [],
                    "message": f"~{presence_count} von {member_count} Mitgliedern sind online. (Member-Namen nicht abrufbar)"
                }

        except Exception as e:
            logger.error(f"Fehler beim Laden der Online-Member-Liste: {e}", exc_info=True)
            raise

    async def delete_message(
        self,
        channel_id: str,
        message_id: str = None,
        content: str = None
    ) -> Dict[str, Any]:
        """
        Löscht eine Nachricht (entweder per ID oder nach Inhalt)

        Args:
            channel_id: Channel ID oder Channel-Name
            message_id: Nachrichten-ID zum Löschen (optional)
            content: Nachrichteninhalt zum Suchen und Löschen (optional)

        Returns:
            Erfolgsmeldung
        """
        try:
            #Channel ID auflösen falls Name gegeben
            if not channel_id.isdigit():
                channel_id = await self._find_channel_by_name(channel_id)

            #Wenn content gegeben, suche nach Nachricht
            if content and not message_id:
                logger.info(f"Suche Nachricht mit Inhalt '{content}' in Channel {channel_id}")

                #Lade letzte 100 Nachrichten
                endpoint = f"/channels/{channel_id}/messages?limit=100"
                messages = await self.mcp_client.call_discord_api("GET", endpoint)

                #Handle wrapped list format
                if isinstance(messages, dict) and 'items' in messages:
                    messages = messages.get('items', [])

                #Suche nach passender Nachricht
                found_message = None
                for msg in messages:
                    msg_content = msg.get('content', '').lower()
                    search_content = content.lower()

                    #Entferne Interpunktion für flexiblere Suche
                    punctuation = ',.!?;:-"\'()[]'
                    msg_normalized = msg_content
                    search_normalized = search_content
                    for p in punctuation:
                        msg_normalized = msg_normalized.replace(p, ' ')
                        search_normalized = search_normalized.replace(p, ' ')

                    #Normalisiere Whitespace
                    msg_normalized = ' '.join(msg_normalized.split())
                    search_normalized = ' '.join(search_normalized.split())

                    #Suche mit normalisiertem Text
                    if search_normalized in msg_normalized:
                        found_message = msg
                        break

                if not found_message:
                    logger.warning(f"Nachricht mit Inhalt '{content}' nicht gefunden")
                    raise ValueError(f"Nachricht mit Inhalt '{content}' nicht in den letzten 100 Nachrichten gefunden")

                message_id = found_message.get('id')
                logger.info(f"Gefunden: Nachricht ID {message_id}")

            if not message_id:
                raise ValueError("Entweder message_id oder content muss angegeben werden")

            logger.info(f"Lösche Nachricht {message_id} in Channel {channel_id}")

            endpoint = f"/channels/{channel_id}/messages/{message_id}"
            await self.mcp_client.call_discord_api("DELETE", endpoint)

            logger.info(f"[OK] Nachricht gelöscht: {message_id}")

            return {
                "success": True,
                "message_id": message_id,
                "message": "Nachricht wurde gelöscht"
            }

        except Exception as e:
            logger.error(f"Fehler beim Löschen der Nachricht: {e}", exc_info=True)
            raise

    async def delete_last_message(self, channel_id: str) -> Dict[str, Any]:
        """
        Löscht die letzte Nachricht in einem Channel

        Args:
            channel_id: Channel ID oder Channel-Name

        Returns:
            Erfolgsmeldung
        """
        try:
            #Channel ID auflösen falls Name gegeben
            if not channel_id.isdigit():
                channel_id = await self._find_channel_by_name(channel_id)

            logger.info(f"Lösche letzte Nachricht in Channel {channel_id}")

            #Lade letzte Nachricht
            endpoint = f"/channels/{channel_id}/messages?limit=1"
            messages = await self.mcp_client.call_discord_api("GET", endpoint)

            #Handle wrapped list format
            if isinstance(messages, dict) and 'items' in messages:
                messages = messages.get('items', [])

            if not messages or len(messages) == 0:
                raise ValueError("Keine Nachrichten im Channel gefunden")

            #Erste Nachricht ist die neueste
            last_message = messages[0]
            message_id = last_message.get('id')
            message_content = last_message.get('content', '(keine Textinhalt)')

            logger.info(f"Gefunden: Letzte Nachricht ID {message_id} - '{message_content[:50]}'")

            #Nachricht löschen
            endpoint = f"/channels/{channel_id}/messages/{message_id}"
            await self.mcp_client.call_discord_api("DELETE", endpoint)

            logger.info(f"[OK] Letzte Nachricht gelöscht: {message_id}")

            return {
                "success": True,
                "message_id": message_id,
                "content": message_content,
                "message": "Letzte Nachricht wurde gelöscht"
            }

        except Exception as e:
            logger.error(f"Fehler beim Löschen der letzten Nachricht: {e}", exc_info=True)
            raise

    async def get_channel_messages(
        self,
        channel_id: str,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Zeigt die letzten Nachrichten aus einem Channel an

        Args:
            channel_id: Channel ID oder Channel-Name (z.B. "allgemein")
            limit: Anzahl der Nachrichten (Standard: 5, Max: 100)

        Returns:
            Liste der Nachrichten mit Autor, Inhalt und Zeitstempel
        """
        try:
            #Channel ID auflösen falls Name gegeben
            original_channel = channel_id
            if not channel_id.isdigit():
                channel_id = await self._find_channel_by_name(channel_id)

            #Limit begrenzen
            limit = min(max(1, limit), 100)

            logger.info(f"Lade letzte {limit} Nachrichten aus Channel {channel_id}")

            #Nachrichten laden
            endpoint = f"/channels/{channel_id}/messages?limit={limit}"
            messages = await self.mcp_client.call_discord_api("GET", endpoint)

            #Handle wrapped list format
            if isinstance(messages, dict) and 'items' in messages:
                messages = messages.get('items', [])

            if not messages:
                return {
                    "success": True,
                    "channel": original_channel,
                    "count": 0,
                    "messages": [],
                    "message": f"Keine Nachrichten in #{original_channel} gefunden"
                }

            #Nachrichten formatieren
            formatted_messages = []
            for msg in messages:
                #Autor extrahieren
                author = msg.get('author', {})
                author_name = author.get('global_name') or author.get('username', 'Unbekannt')

                #Zeitstempel formatieren
                timestamp_str = msg.get('timestamp', '')
                try:
                    utc_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    berlin_time = utc_time.astimezone(pytz.timezone('Europe/Berlin'))
                    formatted_time = berlin_time.strftime('%d.%m.%Y %H:%M')
                except:
                    formatted_time = timestamp_str

                #Inhalt (max 500 Zeichen)
                content = msg.get('content', '')
                if len(content) > 500:
                    content = content[:500] + '...'

                #Attachments zählen
                attachments = msg.get('attachments', [])
                attachment_info = f" [{len(attachments)} Anhang/Anhänge]" if attachments else ""

                # zählen
                embeds = msg.get('embeds', [])
                embed_info = f" [{len(embeds)} Embed(s)]" if embeds else ""

                formatted_messages.append({
                    "id": msg.get('id'),
                    "author": author_name,
                    "content": content if content else "(kein Text)",
                    "timestamp": formatted_time,
                    "attachments": len(attachments),
                    "embeds": len(embeds),
                    "extra_info": attachment_info + embed_info
                })

            logger.info(f"[OK] {len(formatted_messages)} Nachrichten aus #{original_channel} geladen")

            return {
                "success": True,
                "channel": original_channel,
                "count": len(formatted_messages),
                "messages": formatted_messages,
                "message": f"{len(formatted_messages)} Nachrichten aus #{original_channel}"
            }

        except Exception as e:
            logger.error(f"Fehler beim Laden der Nachrichten: {e}", exc_info=True)
            raise

    async def summarize_channel(
        self,
        channel_id: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Fasst die letzten Nachrichten eines Channels zusammen

        Args:
            channel_id: Channel ID oder Channel-Name (z.B. "allgemein")
            limit: Anzahl der Nachrichten zum Zusammenfassen (Standard: 10, Max: 50)

        Returns:
            Zusammenfassung der Unterhaltung
        """
        try:
            #Limit begrenzen
            limit = min(max(1, limit), 50)

            #Nachrichten laden
            messages_result = await self.get_channel_messages(channel_id, limit)

            if not messages_result.get('success') or not messages_result.get('messages'):
                return {
                    "success": True,
                    "channel": messages_result.get('channel', channel_id),
                    "summary": f"Keine Nachrichten in #{messages_result.get('channel', channel_id)} gefunden."
                }

            messages = messages_result.get('messages', [])
            channel_name = messages_result.get('channel', channel_id)

            #Nachrichten für LLM formatieren (chronologisch
            conversation_text = ""
            for msg in reversed(messages):
                author = msg.get('author', 'Unbekannt')
                content = msg.get('content', '')
                timestamp = msg.get('timestamp', '')

                if content and content != "(kein Text)":
                    conversation_text += f"[{timestamp}] {author}: {content}\n"

            if not conversation_text.strip():
                return {
                    "success": True,
                    "channel": channel_name,
                    "summary": f"Keine Textnachrichten in #{channel_name} zum Zusammenfassen gefunden."
                }

            #LLM für Zusammenfassung nutzen
            if self.gemini:
                prompt = f"""Fasse die folgende Discord-Unterhaltung kurz und prägnant auf Deutsch zusammen.
Nenne die wichtigsten Themen und Punkte. Halte die Zusammenfassung unter 200 Wörtern.

Unterhaltung aus #{channel_name}:
{conversation_text}

Zusammenfassung:"""

                summary = await self.gemini.summarize_text(prompt)

                logger.info(f"[OK] Channel #{channel_name} zusammengefasst ({len(messages)} Nachrichten)")

                return {
                    "success": True,
                    "channel": channel_name,
                    "message_count": len(messages),
                    "summary": summary
                }
            else:
                #Fallback ohne LLM
                return {
                    "success": True,
                    "channel": channel_name,
                    "message_count": len(messages),
                    "summary": f"LLM nicht verfügbar. {len(messages)} Nachrichten in #{channel_name} gefunden."
                }

        except Exception as e:
            logger.error(f"Fehler beim Zusammenfassen des Channels: {e}", exc_info=True)
            raise

    #HELPER-METHODEN

    async def _normalize_and_correct_text(self, text: str) -> str:
        """
        Normalisiert Text: Großbuchstabe am Anfang + Rechtschreibprüfung

        Args:
            text: Zu normalisierender Text

        Returns:
            Korrigierter Text
        """
        if not text or len(text.strip()) == 0:
            return text

        #Ersten Buchstaben großschreiben
        text = text.strip()
        if len(text) > 0:
            text = text[0].upper() + text[1:]

        #Rechtschreibprüfung
        if self.gemini:
            try:
                spelling_result = await self.gemini.check_spelling(text)
                if spelling_result.get('has_errors'):
                    corrected = spelling_result.get('corrected', text)
                    logger.info(f"Rechtschreibung korrigiert")
                    logger.debug(f"Original: {text}")
                    logger.debug(f"Korrigiert: {corrected}")
                    return corrected
            except Exception as e:
                logger.warning(f"Rechtschreibprüfung fehlgeschlagen: {e}")

        return text

    async def _load_channels(self):
        """Lädt alle Channels und cached sie"""
        try:
            endpoint = f"/guilds/{self.guild_id}/channels"
            result = await self.mcp_client.call_discord_api("GET", endpoint)

            channels = result.get('items', []) if isinstance(result, dict) and 'items' in result else result

            self.channels_cache = {c['id']: c for c in channels}

            #Debug---- Liste der Text-Channels loggen
            text_channels = [c['name'] for c in channels if c.get('type') == 0]
            voice_channels = [c['name'] for c in channels if c.get('type') == 2]
            all_channels = [(c['name'], c.get('type')) for c in channels]

            logger.info(f"Channels geladen: {len(self.channels_cache)} insgesamt")
            logger.info(f"   Alle Channels (Name, Type): {all_channels}")
            logger.info(f"   Text-Channels (type=0): {', '.join(text_channels) if text_channels else 'keine'}")
            logger.info(f"   Voice-Channels (type=2): {', '.join(voice_channels) if voice_channels else 'keine'}")

        except Exception as e:
            logger.warning(f"Konnte Channels nicht laden: {e}")
            self.channels_cache = {}

    def _normalize_channel_name(self, name: str) -> str:
        """Normalisiert Channel-Namen für Vergleiche (entfernt Sonderzeichen, lowercase)"""
        #Lowercase, Leerzeichen/Bindestriche/Unterstriche entfernen
        normalized = name.lower()
        normalized = re.sub(r'[\s\-_]+', '', normalized)  #Entferne Leerzeichen, Bindestriche, Unterstriche
        return normalized

    async def _find_channel_by_name(self, name: str) -> str:
        """Findet Channel ID by Name (mit Fuzzy-Matching)"""
        name_lower = name.lower()
        name_normalized = self._normalize_channel_name(name)

        #Exakte Suche (case-insensitive)
        for channel in self.channels_cache.values():
            if channel.get('name', '').lower() == name_lower:
                return channel['id']

        #Normalisierte Suche (ignoriert Leerzeichen, Bindestriche, etc.)
        for channel in self.channels_cache.values():
            channel_normalized = self._normalize_channel_name(channel.get('name', ''))
            if channel_normalized == name_normalized:
                logger.info(f"Channel via Normalisierung gefunden: '{channel['name']}' für '{name}'")
                return channel['id']

        #Fuzzy-Matching---- Teilstring-Suche (auch normalisiert)
        matches = []
        for channel in self.channels_cache.values():
            channel_name = channel.get('name', '').lower()
            channel_normalized = self._normalize_channel_name(channel.get('name', ''))
            #Prüfe sowohl original als auch normalisiert
            if (name_lower in channel_name or channel_name in name_lower or
                name_normalized in channel_normalized or channel_normalized in name_normalized):
                matches.append(channel)

        if len(matches) == 1:
            logger.info(f"Channel via Fuzzy-Match gefunden: '{matches[0]['name']}' für '{name}'")
            return matches[0]['id']
        elif len(matches) > 1:
            match_names = [c['name'] for c in matches]
            raise ValueError(f"Mehrere Channels gefunden für '{name}': {', '.join(match_names)}")

        #Kein Match
        available = [c.get('name', 'unknown') for c in self.channels_cache.values() if c.get('type') == 0]
        raise ValueError(f"Channel nicht gefunden: '{name}'. Verfügbare Text-Channels: {', '.join(available)}")

    async def _find_voice_channel(self) -> Optional[str]:
        """Findet ersten Voice Channel"""
        for channel in self.channels_cache.values():
            if channel.get('type') == 2:  #Voice Channel
                return channel['id']
        return None

    async def _find_event_by_name(self, name: str) -> Optional[str]:
        """Findet Event ID by Name (case-insensitive, auch Teilstring-Match)"""
        #Cache updaten
        await self.list_upcoming_events(limit=100)

        name_lower = name.lower().strip()

        #Erst exakte Übereinstimmung versuchen
        for event in self.events_cache:
            event_name = event.get('name', '').lower().strip()
            if event_name == name_lower:
                logger.info(f"Event gefunden (exakt): {event.get('name')} -> {event['id']}")
                return event['id']

        #Dann Teilstring-Match versuchen
        for event in self.events_cache:
            event_name = event.get('name', '').lower().strip()
            if name_lower in event_name or event_name in name_lower:
                logger.info(f"Event gefunden (Teilstring): {event.get('name')} -> {event['id']}")
                return event['id']

        #Liste verfügbare Events für bessere Fehlermeldung
        available_events = [e.get('name', 'Unbenannt') for e in self.events_cache]
        logger.error(f"Event '{name}' nicht gefunden. Verfügbare Events: {available_events}")
        raise ValueError(f"Event '{name}' nicht gefunden. Verfügbare Events: {', '.join(available_events)}")

    def _parse_time(self, time_str: str, duration_hours: float = 1.0) -> tuple:
        """
        Parst natürliche Zeitangaben zu DateTime-Objekten

        Args:
            time_str: Natürliche Zeitangabe
            duration_hours: Dauer in Stunden

        Returns:
            (start_datetime, end_datetime) als UTC
        """
        try:
            now = datetime.now(self.timezone)

            #Relative Zeitangaben behandeln
            time_lower = time_str.lower().strip()

            #"heute" / "today"
            if 'heute' in time_lower or 'today' in time_lower:
                base_date = now
                time_part = re.search(r'(\d{1,2}):?(\d{2})?', time_lower)
                if time_part:
                    hour = int(time_part.group(1))
                    minute = int(time_part.group(2)) if time_part.group(2) else 0
                    start_dt = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    start_dt = base_date.replace(hour=15, minute=0, second=0, microsecond=0)

            #"übermorgen" (MUSS vor "morgen" geprüft werden!!!!
            elif 'übermorgen' in time_lower:
                base_date = now + timedelta(days=2)
                time_part = re.search(r'(\d{1,2}):?(\d{2})?', time_lower)
                if time_part:
                    hour = int(time_part.group(1))
                    minute = int(time_part.group(2)) if time_part.group(2) else 0
                    start_dt = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    start_dt = base_date.replace(hour=15, minute=0, second=0, microsecond=0)

            #"morgen" / "tomorrow" (MUSS nach "übermorgen" geprüft werden!)
            elif 'morgen' in time_lower or 'tomorrow' in time_lower:
                base_date = now + timedelta(days=1)
                time_part = re.search(r'(\d{1,2}):?(\d{2})?', time_lower)
                if time_part:
                    hour = int(time_part.group(1))
                    minute = int(time_part.group(2)) if time_part.group(2) else 0
                    start_dt = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    start_dt = base_date.replace(hour=15, minute=0, second=0, microsecond=0)

            #"in X Stunden/Tagen" (Deutsch und Englisch)
            elif 'in' in time_lower or 'from now' in time_lower:
                #Versuche "in X days/hours/minutes"
                match = re.search(r'in (\d+) (stunden?|tagen?|minuten?|hours?|days?|minutes?)', time_lower)
                if not match:
                    #Versuche "X days/hours/minutes from now"
                    match = re.search(r'(\d+) (stunden?|tagen?|minuten?|hours?|days?|minutes?) from now', time_lower)

                if match:
                    amount = int(match.group(1))
                    unit = match.group(2)
                    #Deutsch: stunde/stunden, tag/tagen, minute/minuten
                    #Englisch: hour/hours, day/days, minute/minutes
                    if unit.startswith('stunde') or unit.startswith('hour'):
                        start_dt = now + timedelta(hours=amount)
                    elif unit.startswith('tag') or unit.startswith('day'):
                        start_dt = now + timedelta(days=amount)
                    elif unit.startswith('minute'):
                        start_dt = now + timedelta(minutes=amount)
                else:
                    raise ValueError(f"Konnte relative Zeit nicht parsen: {time_str}")

            #Wochentage (deutsch und Englisch)
            elif any(day in time_lower for day in ['montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag', 'samstag', 'sonntag', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
                #Deutsche und englische Wochentage
                days_map = {
                    'montag': 0, 'monday': 0,
                    'dienstag': 1, 'tuesday': 1,
                    'mittwoch': 2, 'wednesday': 2,
                    'donnerstag': 3, 'thursday': 3,
                    'freitag': 4, 'friday': 4,
                    'samstag': 5, 'saturday': 5,
                    'sonntag': 6, 'sunday': 6
                }

                for day_name, day_num in days_map.items():
                    if day_name in time_lower:
                        days_ahead = day_num - now.weekday()
                        if days_ahead <= 0:
                            days_ahead += 7

                        #"übernächsten" / "after next" bedeutet +7 Tage zusätzlich
                        #"nächsten" / "next" ist bereits im normalen days_ahead enthalten
                        if 'übernächste' in time_lower or 'übernächsten' in time_lower or 'after_next' in time_lower:
                            days_ahead += 7

                        base_date = now + timedelta(days=days_ahead)

                        time_part = re.search(r'(\d{1,2}):?(\d{2})?', time_lower)
                        if time_part:
                            hour = int(time_part.group(1))
                            minute = int(time_part.group(2)) if time_part.group(2) else 0
                        else:
                            hour, minute = 15, 0

                        start_dt = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        break

            else:
                #Versuche mit dateparser
                start_dt = dateparser.parse(
                    time_str,
                    settings={
                        'TIMEZONE': 'Europe/Berlin',
                        'PREFER_DATES_FROM': 'future',
                        'RELATIVE_BASE': now
                    }
                )

                if not start_dt:
                    raise ValueError(f"Konnte Zeit nicht parsen: {time_str}")

                #Timezone setzen
                if start_dt.tzinfo is None:
                    start_dt = self.timezone.localize(start_dt)

            #Automatische Jahr-Korrektur für Datumsangaben
            is_iso_format = re.match(r'\d{4}-\d{2}-\d{2}', time_str)

            if is_iso_format:
                #Bei ISO-Format: Korrigiere NUR auf aktuelles Jahr wenn das Jahr in der Vergangenheit liegt
                #z.B. "2024-11-01" am 28.11.2025 -> 2025-11-01
                #ABER: "2027-04-07" bleibt 2027 (zukünftiges Jahr ist gewollt)
                if start_dt.year < now.year:
                    original_year = start_dt.year
                    start_dt = start_dt.replace(year=now.year)
                    logger.info(f"Jahr korrigiert (ISO): {original_year} -> {now.year}")



            elif start_dt <= now:
                #Für natürliche Datumsangaben
                is_specific_date = any(month in time_str.lower() for month in [
                    'januar', 'februar', 'märz', 'april', 'mai', 'juni',
                    'juli', 'august', 'september', 'oktober', 'november', 'dezember',
                    'january', 'february', 'march', 'april', 'may', 'june',
                    'july', 'august', 'september', 'october', 'november', 'december'
                ])

                if is_specific_date:
                    #Nur ein Jahr inkrementieren wenn nötig
                    if start_dt.year < now.year:
                        original_year = start_dt.year
                        start_dt = start_dt.replace(year=now.year)
                        logger.info(f"Jahr korrigiert: {original_year} -> {now.year}")
                #Für vergangene Daten im aktuellen Jahr

            #End-Zeit berechnen
            end_dt = start_dt + timedelta(hours=duration_hours)

            #Zu UTC konvertieren
            start_utc = start_dt.astimezone(pytz.UTC)
            end_utc = end_dt.astimezone(pytz.UTC)

            logger.info(f"Zeit geparst: {time_str} -> {start_utc} bis {end_utc}")

            return start_utc, end_utc

        except Exception as e:
            logger.error(f"Fehler beim Parsen der Zeit '{time_str}': {e}", exc_info=True)
            raise ValueError(f"Konnte Zeit nicht parsen: {time_str}. Fehler: {e}")
