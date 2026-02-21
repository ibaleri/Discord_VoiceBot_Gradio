"""Tool Schemas im OpenAI-Format fuer die Discord Helper Funktionen."""

from datetime import datetime, timedelta


def get_tool_definitions() -> list[dict]:
    """Alle Tool-Definitionen im OpenAI tools-Format."""

    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    date_context = (
        f"Aktuelles Datum: {now.strftime('%d. %B %Y')} ({now.strftime('%A')}). "
        f"'Heute' = {now.strftime('%Y-%m-%d')}, 'Morgen' = {tomorrow.strftime('%Y-%m-%d')}."
    )

    return [
        {
            "type": "function",
            "function": {
                "name": "create_event",
                "description": f"Erstellt ein Discord Scheduled Event. {date_context}",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name des Events"
                        },
                        "start_time": {
                            "type": "string",
                            "description": "Startzeit als natuerliche Zeitangabe (z.B. 'morgen 15 Uhr', '2025-12-01 18:00', 'naechsten Montag 10:00') oder ISO-Format"
                        },
                        "description": {
                            "type": "string",
                            "description": "Beschreibung des Events (optional)"
                        },
                        "duration_hours": {
                            "type": "number",
                            "description": "Dauer in Stunden (Standard: 1.0)"
                        },
                        "location": {
                            "type": "string",
                            "description": "Ort fuer das Event (Standard: 'Discord')"
                        },
                        "event_type": {
                            "type": "string",
                            "enum": ["online", "voice", "stage"],
                            "description": "Event-Typ (Standard: 'online')"
                        },
                        "channel_id": {
                            "type": "string",
                            "description": "Channel ID fuer voice/stage Events (optional)"
                        }
                    },
                    "required": ["name", "start_time"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_upcoming_events",
                "description": (
                    f"Listet kommende Events auf - fuer ZEITRAEUME (naechste Woche, in den naechsten X Tagen, "
                    f"von Datum bis Datum). {date_context}"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximale Anzahl Events (Standard: 50). Nur explizit setzen wenn User ein Limit nennt."
                        },
                        "days_ahead": {
                            "type": "integer",
                            "description": "Events der naechsten X Tage (z.B. 7 fuer naechste Woche)"
                        },
                        "from_date": {
                            "type": "string",
                            "description": "Start-Datum fuer Zeitraum (ISO format YYYY-MM-DD oder natuerliche Sprache)"
                        },
                        "to_date": {
                            "type": "string",
                            "description": "End-Datum fuer Zeitraum (ISO format YYYY-MM-DD oder natuerliche Sprache)"
                        },
                        "location": {
                            "type": "string",
                            "description": "Filter nach Ort/Location (z.B. 'Labor X')"
                        },
                        "group_by_days": {
                            "type": "boolean",
                            "description": "Gruppiere Events nach Tagen (Standard: false)"
                        },
                        "timeframe": {
                            "type": "string",
                            "enum": ["today", "tomorrow", "week", "2weeks", "month"],
                            "description": "Zeitraum-Preset"
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_events_on_specific_day",
                "description": (
                    f"Listet Events an EINEM BESTIMMTEN TAG auf (in 14 Tagen, am 25.11, morgen). {date_context}"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "from_date": {
                            "type": "string",
                            "description": "Datum als natuerliche Zeitangabe (z.B. 'in 14 Tagen', '25. November', 'morgen')"
                        },
                        "to_date": {
                            "type": "string",
                            "description": "End-Datum (optional, Standard: gleicher Tag)"
                        },
                        "location": {
                            "type": "string",
                            "description": "Filter nach Ort/Location"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximale Anzahl Events (Standard: 50)"
                        }
                    },
                    "required": ["from_date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "delete_event_by_name",
                "description": "Loescht ein Event anhand des Namens",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_name": {
                            "type": "string",
                            "description": "Name des zu loeschenden Events"
                        }
                    },
                    "required": ["event_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_event",
                "description": "Aktualisiert ein bestehendes Event",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {
                            "type": "string",
                            "description": "Event ID"
                        },
                        "updates": {
                            "type": "object",
                            "description": "Felder zum Aktualisieren (z.B. name, description, start_time)"
                        }
                    },
                    "required": ["event_id", "updates"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "send_message",
                "description": "Sendet eine Nachricht in einen Discord Channel. channel_id kann ein Channel-NAME sein (z.B. 'allgemein').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "description": "Channel ID oder Channel-Name (z.B. 'allgemein', 'general')"
                        },
                        "content": {
                            "type": "string",
                            "description": "Nachrichteninhalt"
                        },
                        "mentions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Liste von User-IDs zum Erwaehnen (optional)"
                        }
                    },
                    "required": ["channel_id", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_server_info",
                "description": "Ruft Discord Server-Informationen ab (Name, Mitgliederzahl etc.)",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_channels",
                "description": "Listet alle Discord Channels auf",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel_type": {
                            "type": "string",
                            "enum": ["all", "text", "voice"],
                            "description": "Channel-Typ Filter (Standard: 'all')"
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_online_members_count",
                "description": "Gibt die Anzahl der online Mitglieder zurueck",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_online_members",
                "description": "Listet online Mitglieder auf (mit Namen)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Max. Anzahl anzuzeigender Mitglieder (Standard: 20)"
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "delete_message",
                "description": "Loescht eine Nachricht aus einem Channel. Entweder per message_id oder per content-Suche. channel_id kann Channel-Name sein.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "description": "Channel ID oder Channel-Name"
                        },
                        "message_id": {
                            "type": "string",
                            "description": "Direkte Nachrichten-ID (optional)"
                        },
                        "content": {
                            "type": "string",
                            "description": "Nachrichtentext zum Suchen und Loeschen (optional)"
                        }
                    },
                    "required": ["channel_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "delete_last_message",
                "description": "Loescht die letzte (neueste) Nachricht in einem Channel",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "description": "Channel ID oder Channel-Name"
                        }
                    },
                    "required": ["channel_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_channel_messages",
                "description": "Zeigt die letzten Nachrichten aus einem Channel an. channel_id kann Channel-Name sein (z.B. 'allgemein').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "description": "Channel ID oder Channel-Name"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Anzahl der Nachrichten (Standard: 5, Max: 100)"
                        }
                    },
                    "required": ["channel_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "summarize_channel",
                "description": "Fasst die letzten Nachrichten eines Channels zusammen. Fuer 'Worum geht es im Channel X?'",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "description": "Channel ID oder Channel-Name"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Anzahl der Nachrichten zum Zusammenfassen (Standard: 10, Max: 50)"
                        }
                    },
                    "required": ["channel_id"]
                }
            }
        },
    ]
