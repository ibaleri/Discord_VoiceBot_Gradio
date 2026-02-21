# Discord MCP Bot with Gradio Web Interface

Discord bot with voice control and web UI. Developed as part of a bachelor's thesis.

## Update

This repository contains a major update compared to the original version. Key changes:

- **Native Tool Calling**: The command pipeline was migrated from manual JSON parsing to native LLM tool calling. The LLM receives real tool definitions (`tool_schemas.py`) and returns structured `tool_calls` that are executed directly. A multi-turn loop (max 5 rounds) allows the LLM to call multiple tools sequentially.
- **Remote MCP Server** (`mcp_server.py`): Standalone server that exposes Discord functions as 14 high-level tools over SSE/HTTP. Multiple clients can connect simultaneously. Includes bearer token auth, role-based permissions (reader/writer/admin), and per-user rate limiting.
- **Audit Log** (`audit_log.py`): All tool calls in remote mode are logged to a SQLite database (client ID, user, action, parameters, success/failure).
- **Tool Definitions** (`tool_schemas.py`): Central file containing all tool schemas in OpenAI format, used by both the LLM client and the MCP server.
- **Real Remote Connection**: The MCP client (`mcp_client.py`) now supports a full remote mode with SSE/HTTP transport instead of subprocess only.
- **LLM Tool Calling API** (`llm_client.py`): New method `chat_completion_with_tools()` for all providers (OpenAI, Groq, Gemini, Ollama).
- **Timeout Handling**: Async calls now have a configurable timeout (default: 120s) instead of waiting indefinitely.

> **Note on tests**: The existing unit tests in `tests_deprecated/` were carried over from the previous version and are partially outdated. In particular, `test_mcp_client.py::test_connect_remote_mode_fallback` tests old behavior (fallback to subprocess) that has been replaced by a real remote connection. The new modules (`mcp_server.py`, `tool_schemas.py`, `audit_log.py`) and the new `chat_completion_with_tools()` method do not have tests yet.

## Features

- **Voice Control**: Commands via microphone or text input
- **Event Management**: Create, list, and delete Discord scheduled events
- **Messaging**: Send and delete messages in Discord channels
- **Multi-LLM**: OpenAI, Groq, Gemini, Ollama
- **Speech-to-Text**: Groq Whisper API or Faster Whisper (local)
- **Remote MCP Server**: Central server with SSE/HTTP transport, bearer token auth, and role-based permissions
- **Audit Log**: All tool calls are logged to SQLite (user, action, timestamp)
- **Rate Limiting**: Per-user request limits in remote mode

## Installation

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

## Discord Bot Setup

1. Create bot: https://discord.com/developers/applications
   - "New Application" → Enter name → "Bot" tab → "Add Bot"
   - Copy token for `.env`

2. Enable Privileged Gateway Intents (Bot tab):
   - SERVER MEMBERS INTENT
   - MESSAGE CONTENT INTENT

3. Bot permissions (OAuth2 → URL Generator):
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: View Channels, Send Messages, Read Message History, Manage Events, Connect
   - Alternative permissions integer: `8589936640`

4. Invite bot: Open the generated URL and select your server

5. Copy server ID:
   - Discord Settings → Advanced → Enable Developer Mode
   - Right-click server → "Copy Server ID"

## Configuration

### Local Development (Subprocess Mode)

Everything runs in a single process. Create `.env`:

```env
DISCORD_TOKEN=your_token
DISCORD_GUILD_ID=your_server_id
MCP_MODE=subprocess

LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
GEMINI_API_KEY=your_key

SPEECH_PROVIDER=groq-fallback
GROQ_API_KEY=your_groq_key
```

### Remote Mode (Client/Server Separated)

The MCP server runs centrally and exposes Discord functions as tools. Multiple clients can connect.

**Server** (`.env` on the server):
```env
DISCORD_TOKEN=your_token
DISCORD_GUILD_ID=your_server_id
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8000
MCP_TRANSPORT=sse
```

API keys are managed in `api_keys.json` (created on first startup).

**Client** (`.env` on the user's machine):
```env
MCP_MODE=remote
MCP_SERVER_URL=http://my-server:8000/sse
MCP_API_KEY=sk-user-your-key-here

LLM_PROVIDER=ollama
LLM_MODEL=llama3.2
SPEECH_PROVIDER=groq-fallback
GROQ_API_KEY=your_groq_key
```

## Usage

### Local Development
```bash
cd src
python run_gradio.py
```

### Remote Mode
```bash
# Start server
python src/mcp_server.py

# Start client (on another machine or terminal)
cd src
python run_gradio.py
```

Open Web UI: http://localhost:7860

## Project Structure

```
DiscordBotGradio/
├── src/
│   ├── gradio_app.py       # Web interface (chat, calendar, settings)
│   ├── discord_helpers.py  # Discord API functions
│   ├── llm_voice.py        # LLM & speech-to-text
│   ├── mcp_client.py       # MCP client (subprocess + remote)
│   ├── mcp_server.py       # MCP server (standalone, SSE/HTTP)
│   ├── tool_schemas.py     # Tool definitions for native LLM tool calling
│   ├── audit_log.py        # SQLite audit logger
│   ├── config.py           # Configuration
│   ├── run_gradio.py       # Startup script
│   └── llm_client/         # LLM client library
│       ├── __init__.py
│       ├── llm_client.py   # Multi-provider LLM client (incl. tool calling)
│       └── adapter.py      # Provider adapter
├── tests_deprecated/       # Unit tests (from previous version, partially outdated)
├── docs/                   # Test protocols
├── .env.example            # Configuration template
└── requirements.txt        # Python dependencies
```

## Tests

The tests in `tests_deprecated/` are from the previous version. They cover base functionality (config, time parsing, channel normalization, event CRUD, LLM init) but have not been updated for the new modules and the changed tool calling flow.

```bash
pytest tests_deprecated/
```

## License

Bachelor's thesis project
