# Installation, upgrades, and startup

[简体中文](../zh-CN/getting-started.md) | English · [Documentation home](README.md)

## Requirements

- Python 3.10 or newer (3.12 recommended).
- Node.js 18 or newer with npm.
- FFmpeg and ffprobe available from the terminal `PATH`.
- SQLite is provided through the Python runtime; no separate database service is required.

Verify the media tools:

```powershell
ffmpeg -version
ffprobe -version
```

## Install the backend

Run from the repository root:

```powershell
cd shadowing/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

For CMD, activate with `.venv\Scripts\activate.bat`. On macOS/Linux use `source .venv/bin/activate` and replace `Copy-Item` with `cp`.

`requirements.txt` installs the remote-provider runtime and baseline audio tools; it does not install Local Whisper. Runtime settings come from `backend/.env`, while provider URLs, models, and credentials are stored from the frontend Settings panel.

## Optionally install Local Whisper

Install it only when local material transcription or local recording ASR is required:

```powershell
cd shadowing/backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements-local-whisper.txt
```

The first model load may download files. Relevant `.env` options are:

- `WHISPER_MODEL`: model name.
- `WHISPER_DEVICE`: for example `cpu` or `cuda`.
- `WHISPER_COMPUTE_TYPE`: for example `int8` or `float16`.
- `WHISPER_MODEL_DIR`: model cache directory.
- `WHISPER_ALLOW_DOWNLOAD`: whether automatic downloads are allowed.

Settings can inspect the runtime and explicitly load or release the model. Merely opening Settings does not load it. See [ASR scene routing](providers.md#asr-scene-routing) for local/remote selection.

## Install the frontend

Open another terminal:

```powershell
cd shadowing/frontend
npm install
npm run dev
```

The frontend defaults to <http://localhost:5173> and the backend to <http://localhost:8000>. The frontend points at the local backend by default; set `VITE_API_BASE` to override it.

## First-time configuration

1. Open Settings and choose the UI, learning-content, and translation languages.
2. Create the required LLM, TTS, or ASR profile from a quick template.
3. Enter the endpoint, API key, model, capabilities, and formats, then save.
4. Start with local configuration validation; use a network verification or paid test only when needed.
5. Make an eligible profile the default for its capability.
6. If using remote ASR, review the independent switches for material transcription and recording evaluation.

Endpoint rules and capability dependencies are described in [Models and providers](providers.md).

## Upgrade an existing installation

Stop both processes and back up all of `shadowing/backend/data/` before updating the code. Then run:

```powershell
cd shadowing/backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
```

Alembic preserves existing materials, sentences, evaluations, jobs, collected words, and provider profiles. Do not replace the old `app.db` with an empty database or manually copy individual tables during migration.

## Verify the installation

```powershell
cd shadowing/backend
.\.venv\Scripts\python.exe -m pytest -q

cd ../frontend
npm test
npm run build
```

If the frontend reports `Failed to fetch`, first check that the backend is listening on port 8000, `VITE_API_BASE` is correct, and `.env` `CORS_ORIGINS` includes the active frontend address.
