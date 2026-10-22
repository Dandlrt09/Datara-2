# Datara

Source-available data analysis tool with AI-powered chat. Upload datasets, ask questions in natural language, and get structured analysis with code, charts, and tables — all from your browser.

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

Datara is source-available under the [Functional Source License 1.1, MIT Future
License](LICENSE) (FSL-1.1-MIT).

You may use, copy, modify, and redistribute Datara for any purpose except a
Competing Use: offering it to others as a commercial product or service that
substitutes for Datara, or that offers the same or substantially similar
functionality. Internal use, non-commercial education and research, and
professional services for a licensee are explicitly permitted.

Every version becomes available under the MIT license on the second anniversary
of the date it was made available. See [LICENSE](LICENSE) for the full terms.