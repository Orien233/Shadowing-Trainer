# Development, API, and data layout

[简体中文](../zh-CN/development.md) | English · [Documentation home](README.md)

## Technology stack

- Backend: Python, FastAPI, SQLModel, SQLite, Alembic, and httpx.
- Media and evaluation: FFmpeg/ffprobe, librosa, soundfile, and NumPy; Local Whisper is optional.
- Frontend: React 18, TypeScript, Vite, and Vitest.
- Background work: a database-backed durable job queue for material processing, recording evaluation, and TTS.

## Repository layout

```text
Shadowing_v0_4/
├─ README.md
├─ README.en.md
├─ docs/
│  ├─ zh-CN/
│  └─ en-US/
└─ shadowing/
   ├─ backend/
   │  ├─ alembic/
   │  ├─ app/
   │  │  ├─ api/
   │  │  ├─ models/
   │  │  ├─ schemas/
   │  │  └─ services/
   │  └─ tests/
   └─ frontend/
      └─ src/
```

The source directory uses the version-neutral name `shadowing/`; release versions belong in Git branches rather than runtime directory names.

## Runtime data

The default data root is `shadowing/backend/data/` and is ignored by Git:

- `app.db`: Materials, Sentences, Recordings, Evaluations, Jobs, collections, and provider profiles.
- `materials/`: original uploads.
- `audio/`: normalized full audio, sentence WAV clips, and TTS output.
- `videos/`: converted video output.
- `recordings/`: user recordings and intermediate files.
- `models/`: optional local model cache.

All file cleanup must remain constrained to the data directory. Never commit databases, media, models, temporary `.part` files, or provider credentials.

## Major API groups

The complete OpenAPI schema is available at `/docs` while the backend is running. Common endpoints include:

| Domain | Endpoints |
| --- | --- |
| Languages | `GET /api/languages`; `GET/PUT /api/languages/preferences` |
| Materials | `POST /api/materials/upload`; `GET /api/materials`; `POST /api/materials/{id}/process`; `DELETE /api/materials/{id}` |
| Sentences | `GET /api/materials/{id}/sentences`; `GET /api/materials/{id}/latest-evaluations` |
| Collections | `POST /api/words/collect`; `GET /api/words/collections`; `DELETE /api/words/collections/{id}` |
| Text practices | `GET /api/text-practices`; `POST /generate`; `POST /import`; `PATCH /{id}`; `POST /{id}/tts` |
| Providers | `GET /api/providers/catalog`; provider CRUD, tests, voices, local-ASR status, and ASR scene settings |
| Recordings and evaluation | `POST /api/recordings/upload`; `GET /api/evaluations/{id}` |
| Jobs | `GET /api/jobs/{id}`; `POST /api/jobs/{id}/retry` |

API key reads must remain masked. Business services obtain implementations through the Provider Factory/Router and must not read vendor configuration directly.

## Database migrations

Schema changes require a new Alembic revision and must not rely on startup-time field creation. Run:

```powershell
cd shadowing/backend
.\.venv\Scripts\Activate.ps1
alembic heads
alembic upgrade head
```

Version 0.4.2 is a fresh database baseline: do not upgrade or stamp an old `app.db`. Back up the entire data directory first, then have the user explicitly move or delete only the old `app.db`, preserving materials, audio, video, recordings, and models; run `alembic upgrade head` only against the new database. No compatibility upgrade for the old database is promised.

## Verification commands

Backend:

```powershell
cd shadowing/backend
.\.venv\Scripts\python.exe -m pytest -q
```

Frontend:

```powershell
cd shadowing/frontend
npm test
npm exec tsc -- --noEmit
npm run build
```

Before committing, also check:

```powershell
git diff --check
git status --short
git ls-files --others --exclude-standard
```

Provider, language, and job changes should at minimum cover the Factory, capability gates, API-key masking, ASR routing, TTS snapshots/recovery, the 0.4.2 fresh-database baseline, and backend/frontend regressions.
