# Discord MCP Bot mit Gradio Web-Interface

Discord Bot mit Sprachsteuerung und Web-UI. Entwickelt im Rahmen einer Bachelorarbeit.

## Features

- **Sprachsteuerung:** Befehle per Mikrofon oder Text
- **Event-Management:** Discord Events erstellen, auflisten, löschen
- **Nachrichten:** Senden und löschen in Discord-Kanälen
- **Multi-LLM:** OpenAI, Groq, Gemini, Ollama
- **Speech-to-Text:** Groq Whisper API oder Faster Whisper (lokal)

## Installation

```bash
# Virtual Environment erstellen
python -m venv venv
venv\Scripts\activate  # Windows

# Dependencies installieren
pip install -r requirements.txt
```

## Discord Bot einrichten

1. **Bot erstellen:** https://discord.com/developers/applications
   - "New Application" → Name eingeben → "Bot" Tab → "Add Bot"
   - Token kopieren für `.env`

2. **Privileged Gateway Intents aktivieren (Bot Tab):**
   - `SERVER MEMBERS INTENT`
   - `MESSAGE CONTENT INTENT`

3. **Bot-Berechtigungen (OAuth2 → URL Generator):**
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `View Channels`, `Send Messages`, `Read Message History`, `Manage Events`, `Connect`
   - Alternativ Permissions-Integer: `8589936640`

4. **Bot einladen:** Generierte URL öffnen und Server auswählen

5. **Server-ID kopieren:**
   - Discord Einstellungen → Erweitert → Entwicklermodus aktivieren
   - Rechtsklick auf Server → "Server-ID kopieren"

## Konfiguration

`.env` Datei erstellen (siehe `.env.example`):

```env
DISCORD_TOKEN=dein_token
DISCORD_GUILD_ID=deine_server_id

LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
GEMINI_API_KEY=dein_key

SPEECH_PROVIDER=groq
GROQ_API_KEY=dein_groq_key
```

## Start

```bash
cd src
python run_gradio.py
```

Web-UI öffnen: http://localhost:7860

## Projekt-Struktur

```
DiscordBotGradio/
├── src/
│   ├── gradio_app.py       # Web-Interface
│   ├── discord_helpers.py  # Discord API Funktionen
│   ├── llm_voice.py        # LLM & Speech-to-Text
│   ├── mcp_client.py       # MCP Client
│   ├── config.py           # Konfiguration
│   ├── run_gradio.py       # Start-Script
│   └── llm_client/         # LLM Client Library
├── tests/                  # Unit Tests
└── docs/                   # Testprotokolle
```

## Tests

```bash
pytest tests/
```

## Lizenz

Bachelorarbeit-Projekt
