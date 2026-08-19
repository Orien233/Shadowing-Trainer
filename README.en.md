# Shadowing Trainer v0.4.2

[简体中文](README.md) | English

Shadowing Trainer is a local-first multilingual shadowing web application. Upload audio or video, generate practice text from collected words, or import your own text. The application turns the content into sentence-level exercises with playback, recording, scoring, and token-level feedback.

## Main features

- Upload audio or video for transcription, segmentation, and translation.
- Collect words from exercises and keep the library scoped by learning language.
- Generate coherent text from collected words with an LLM, or paste your own text.
- Create sentence-level TTS audio and reuse the result as a normal practice material.
- Play, loop, record, and review multidimensional feedback sentence by sentence.
- Configure LLM, TTS, remote ASR, and optional Local Whisper independently.
- Chinese and English interfaces with separate learning and translation languages.

See the [User guide](docs/en-US/user-guide.md) for the complete workflow.

## Prerequisites

- Python 3.10 or newer
- Node.js 20.19 or newer with npm
- FFmpeg and ffprobe available on `PATH`

Local Whisper is optional and is not required when all ASR work uses remote providers. See [Installation and startup](docs/en-US/getting-started.md) for details.

## Quick start

Configure and start the backend from the repository root:

```powershell
cd shadowing/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Start the frontend in another terminal:

```powershell
cd shadowing/frontend
npm install
npm run dev
```

Default addresses:

- Frontend: <http://localhost:5173>
- Backend API: <http://localhost:8000>
- OpenAPI documentation: <http://localhost:8000/docs>

After the first start, create the required provider profiles on the Settings panel. Endpoint rules and test levels are documented in the [Model and provider guide](docs/en-US/providers.md).

## The 0.4.2 fresh baseline

Version 0.4.2 is a fresh database baseline: the old `shadowing/backend/data/app.db` must not be upgraded or stamped. Back up the entire `shadowing/backend/data/` first, then explicitly move or delete the old `app.db` at the user's direction; do not delete materials, audio, video, recordings, or models in the data directory. Run `alembic upgrade head` afterward so the application creates a new database.

## Documentation

- [Documentation home](docs/en-US/README.md)
- [Installation, upgrades, and startup](docs/en-US/getting-started.md)
- [User guide](docs/en-US/user-guide.md)
- [Model adapters, capability declarations, and tests](docs/en-US/providers.md)
- [Multilingual behaviour and scoring boundaries](docs/en-US/multilingual.md)
- [Development, API, and data layout](docs/en-US/development.md)
- [Release history](docs/en-US/changelog.md)

## Important notes

- Version 0.4.2 does not promise compatibility upgrades for an old database; follow the fresh-baseline procedure above.
- Provider credentials are stored by the backend and API reads return only a mask. Never commit `.env`, databases, or secrets.
- Scores are practice feedback and must not be treated as formal language proficiency results.
- Runtime source is stored in the version-neutral `shadowing/` directory.
