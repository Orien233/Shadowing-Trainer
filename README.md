# Shadowing Trainer v0.2

Shadowing Trainer is a local-first web app for spoken English shadowing practice.  
It supports the full workflow from media upload to sentence-level practice, recording, and scoring.

## Change Summary (v0_2 branch)

This branch includes the following major updates:

- Added automatic background processing right after material upload.
- Added material deletion (`DELETE /api/materials/{material_id}`) with cascading cleanup:
  - Deletes related `sentence`, `recording`, and `evaluation` rows.
  - Safely deletes generated audio clips and recording artifacts on disk.
  - Cancels in-flight background processing if the material is being processed.
- Added material action menu in the frontend:
  - Start processing / reprocess.
  - Delete material.
- Improved sentence trainer timeline logic:
  - Uses a global timeline aligned with original media timestamps.
  - Includes silent-gap segments for cleaner navigation.
  - Supports segment autoplay and loop mode.
- Improved video training experience:
  - Embedded video player in practice mode.
  - Bidirectional sync between video time and segment timeline.

## Core Features

- Upload audio or video materials.
- Automatically extract and normalize audio to WAV (16kHz, mono).
- ASR transcription with `faster-whisper`.
- Sentence segmentation from ASR output.
- Sentence translation to Simplified Chinese through DeepSeek API.
- Sentence-level playback and timeline scrubbing.
- Recording upload and automatic scoring:
  - Completeness
  - Fluency
  - Sync
  - Pronunciation
- Optional reprocessing of existing materials.
- Material-level deletion with data/file cleanup.

## Architecture

### Backend

- Python 3.10+
- FastAPI
- SQLModel + SQLite
- `faster-whisper`
- FFmpeg / ffprobe
- librosa + soundfile
- httpx (for DeepSeek translation requests)

### Frontend

- React 18
- TypeScript
- Vite

## Project Structure

```text
shadowing_v0_2/
  backend/
    app/
    data/                 # runtime data (ignored in git)
    requirements.txt
    .env                  # local config (not committed)
  frontend/
    src/
  README.md
```

## Prerequisites

1. Python 3.10 or newer
2. Node.js 18+ and npm
3. FFmpeg and ffprobe available in `PATH`

Verify FFmpeg:

```bash
ffmpeg -version
ffprobe -version
```

Optional GPU acceleration (for Whisper) requires PyTorch + CUDA.

## Quick Start

### 1) Backend setup

```bash
cd shadowing_v0_2/backend
python -m venv .venv
```

Activate venv:

- PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

- CMD:

```bat
.venv\Scripts\activate.bat
```

- macOS/Linux:

```bash
source .venv/bin/activate
```

Install backend dependencies:

```bash
pip install -r requirements.txt
```

Install PyTorch (choose one):

- CPU:

```bash
pip install torch torchvision torchaudio
```

- CUDA 12.1:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Create `backend/.env` (example below), then start backend:

```bash
uvicorn app.main:app --reload --port 8000
```

### 2) Frontend setup

```bash
cd shadowing_v0_2/frontend
npm install
npm run dev
```

Default local URLs:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`

## Environment Variables (`backend/.env`)

```env
APP_NAME=Shadowing Trainer
DEBUG=true
HOST=0.0.0.0
PORT=8000

CORS_ORIGINS=http://localhost:5173

DATA_DIR=./data
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8

DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_KEY=

TRANSLATION_CONCURRENCY=5
TRANSLATION_REQUEST_TIMEOUT_SECONDS=60
TRANSLATION_MAX_RETRIES=2
TRANSLATION_RETRY_BASE_SECONDS=0.8
TRANSLATION_MAX_CONNECTIONS=200
TRANSLATION_MAX_KEEPALIVE_CONNECTIONS=50

PROCESSING_LOCK_TIMEOUT_SECONDS=1800
PROCESSING_LOCK_HEARTBEAT_SECONDS=10
```

## Data Storage

Backend runtime data is under `backend/data`:

- `materials/` original uploaded files
- `audio/` normalized full-material audio
- `audio/sentences/material_{id}/` sentence clip WAVs
- `recordings/` user recording files and converted artifacts
- `app.db` SQLite database

## Database Notes

On startup, lightweight schema migration is applied automatically.  
Current migration includes additional sentence columns:

- `original_start_time`
- `original_end_time`
- `clip_audio_path`
- `clip_duration`

Legacy rows are backfilled with safe defaults.

## API Overview

### Materials

- `POST /api/materials/upload`
- `GET /api/materials`
- `GET /api/materials/{material_id}`
- `POST /api/materials/{material_id}/process`
- `DELETE /api/materials/{material_id}`
- `GET /api/materials/{material_id}/audio`
- `GET /api/materials/{material_id}/video`

### Sentences

- `GET /api/materials/{material_id}/sentences`

### Recordings and Evaluation

- `POST /api/recordings/upload`
- `DELETE /api/recordings/cleanup`
- `GET /api/evaluations/{evaluation_id}`

### System

- `POST /api/system/shutdown`

## Notes

- The first `faster-whisper` run may download model files and take longer.
- If `DEEPSEEK_API_KEY` is empty, translation falls back to a placeholder message.
- This scoring pipeline is intended for practice feedback, not high-stakes language assessment.
