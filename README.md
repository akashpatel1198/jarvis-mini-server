# jarvis-mini-server

FastAPI backend for Jarvis Mini. Takes audio from the phone, transcribes it with Whisper, runs an LLM with tools, and returns a spoken reply plus any phone-side actions to perform.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/akashpatel1198/jarvis-mini-server.git
cd jarvis-mini-server
uv sync
cp .env.example .env
# fill in OPENAI_API_KEY (required), others are optional
make dev
```

Server runs at `http://0.0.0.0:8000`.

## Environment variables

Required for basic chat and transcription:

- `OPENAI_API_KEY`: powers Whisper (`whisper-1`) and the LLM (`gpt-4o-mini` by default).

Optional. Skip these if you don't use the corresponding tool. The tool will just error at call time.

- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`: enables the `play_song` tool. Get them from the [Spotify developer dashboard](https://developer.spotify.com/dashboard).
- `TESLA_CLIENT_ID`, `TESLA_CLIENT_SECRET`, `TESLA_REDIRECT_URI`, `TESLA_DOMAIN`: enables Tesla vehicle status and commands. Requires registering as a Tesla Fleet API partner, which is non-trivial.

Optional model overrides:

- `WHISPER_MODEL` (default `whisper-1`)
- `LLM_MODEL` (default `gpt-4o-mini`)

## Endpoints

- `GET /health`: liveness check.
- `POST /transcribe`: multipart audio upload, returns transcript only.
- `POST /command`: multipart audio upload, returns transcript, LLM reply, and any phone actions.

## Tools

Tool modules live in `tools/`. Each module exports a `TOOLS` list of `(definition, executor)` pairs. The registry in `tools/__init__.py` picks them up automatically.

Bundled tools:

- `get_time`: current time, optional IANA timezone.
- `grocery`: add, list, clear a SQLite-backed grocery list.
- `spotify`: search a track, return the URI for the phone to play.
- `tesla`: read vehicle status, lock, start climate.

## Adding your own tool

Drop a new module in `tools/`, define one or more `(DEFINITION, execute)` pairs, and append it to the `_MODULES` tuple in `tools/__init__.py`. `DEFINITION` follows the OpenAI tool-calling schema.

If the action needs the phone to do something (play audio, open an app, fire an intent), return a `ToolResult` with a `phone_action` payload that the Android client knows how to dispatch.

## Dev commands

```bash
make dev      # run server with reload
make test     # pytest
make lint     # ruff check
make format   # ruff format
```

## Contributing

Issues and PRs welcome. If something doesn't work, isn't documented, or you've added a tool you'd like to upstream, open an issue or send a PR.
