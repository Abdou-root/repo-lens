# RepoLens 

AI-powered code intelligence platform. Parses repositories with Tree-sitter, stores structure as a graph in Neo4j, and layers on semantic search and LLM-based Q&A/summarization over the codebase.

## Features

- **Graph visualization** — interactive, pannable/zoomable view of a repo's files, classes, functions, and call/import relationships
- **Semantic search** — find code by natural-language query via vector embeddings, including duplicate/clone detection
- **AI Q&A** — ask questions about the selected code and get answers grounded in its actual context
- **Codebase insights** — entry points, complexity hotspots, architecture hubs, isolated/dead code
- **Demo mode** — explore a preloaded repo without connecting GitHub

## Stack

- **Frontend**: React + TypeScript + Vite, shadcn/ui
- **Backend**: FastAPI (Python 3.11)
- **Database**: Neo4j (graph)
- **Cache/Queue**: Redis + RQ
- **LLM**: DeepSeek / OpenRouter
- **Embeddings**: sentence-transformers

## Quick Start

Requires Docker + Docker Compose, a GitHub OAuth App, and (optionally) an LLM API key.

```bash
git clone https://github.com/Abdou-root/repo-lens.git
cd repolens

cp .env.example .env
# edit .env: GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, JWT_SECRET_KEY, DEEPSEEK_API_KEY

docker-compose up -d
```

- Frontend: http://localhost:8080
- API + docs: http://localhost:8000/docs
- Neo4j Browser: http://localhost:7474

Load demo data (optional): `docker-compose exec api python init_demo_data.py --load`

## Local Development (without Docker)

```bash
# Backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run_worker.py   # in a separate terminal

# Frontend
npm install
npm run dev
```

## Demo without a backend

The three demo repositories are pre-parsed into static JSON under
`public/demo/`, so demo mode works with only the frontend deployed. After
changing the parser or `app/demo/repositories.py`, regenerate them:

```bash
python scripts/build_demo_data.py
```

## Tests

```bash
pytest
```

Covers the Tree-sitter parsers, import/call resolution, and the Neo4j-backed
vector search and Q&A retrieval (against a fake driver, so no database is
needed).

## Project Structure

```
app/                  FastAPI backend
├── api/              routes: llm, search, demo, auth
├── auth/             GitHub OAuth + JWT
├── db/               Neo4j models/driver
├── services/         parsing (Tree-sitter), embeddings, LLM
└── worker/           RQ background jobs (repo parsing)

src/                  React frontend
├── components/graph/ graph view, chat panel, node drawer
├── pages/            Dashboard, GraphExplorer, Landing
├── contexts/         auth state
└── lib/              API client, export, utils
```

## API

Full interactive docs at `/docs` once running. Main groups:

- `POST /api/auth/github` — GitHub OAuth login
- `POST /api/search/semantic` — natural-language code search
- `POST /api/llm/question` — ask a question about a code snippet
- `GET /api/demo/repositories` — browse demo mode repos

## License

MIT
