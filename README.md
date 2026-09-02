# Datara

Open-core data analysis tool with AI-powered chat. Upload datasets, ask questions in natural language, and get structured analysis with code, charts, and tables — all from your browser.

## Architecture

```
datara/
├── core/          # Pure domain models, protocols, parser/profiler
├── server/        # FastAPI app, SQLite store, sandbox, LLM providers
├── web/           # React + Vite + TypeScript SPA
└── tests/         # Unit and integration tests
```

## Quick Start

```bash
# Install with server extras
uv sync --extra server

# Run the server (API + built frontend, if web/dist exists)
# Local DB: ~/.datara/datara.db (override with DATARA_DB_PATH)
uv run uvicorn server.api.main:app

# For frontend development with hot reload
cd web && npm install && npm run dev   # proxies /api to localhost:8000
```

## Development

```bash
uv sync --group dev
uv run pytest
```

## License

MIT