# Release history

[简体中文](../zh-CN/changelog.md) | English · [Documentation home](README.md)

This page preserves the release history previously carried in the root README. Follow the current [installation guide](getting-started.md) and [user guide](user-guide.md) for current instructions.

## v0.4.2 — Breaking fresh baseline

- This release is a fresh database baseline; the old `backend/data/app.db` must not be upgraded or stamped.
- The user must back up the data first, then explicitly move or delete the old `app.db` so the new release can create its database; materials, audio, video, recordings, and models in the data directory must not be deleted.
- No compatibility upgrade from the old database is promised; see [Installation and startup](getting-started.md).
- The historical Alembic chain is replaced by one 0.4.2 baseline, and startup now identifies and rejects an old database through a read-only preflight.
- Removed unregistered provider adapters, the duplicate evaluation snapshot table, handwritten migration compatibility, and verified dead services and settings.
- Completed the frontend TypeScript migration, organized it by product feature, and established one language catalog shared by both stacks.
- Moved material processing, evaluation history, and provider testing out of API routes into dedicated services, with backend tests grouped by domain.

## v0.4.1

- Separated and persisted UI, learning-content, and translation languages, with Chinese and English interfaces.
- Completed language hand-offs across Materials, Text Practices, ASR, translation, TTS, collected words, and scoring.
- Added a controlled BCP-47 catalog, multilingual segmentation, and explicit scoring support levels.
- Made Local Whisper optional and routed by ASR scene and provider language capability.
- Strengthened TTS job snapshots, edit invalidation, output isolation, and safe retries.
- Moved runtime source from a historical versioned name to the neutral `shadowing/` directory.

## v0.4

- Added LLM text generation, user text import, and sentence-level TTS practice.
- Introduced the Provider Factory, Adapter Catalog, user capability/format declarations, and built-in quick templates.
- Narrowed remote support to OpenAI Chat, OpenAI Audio, and MiMo; historical adapters are no longer registered.
- Added LLM/TTS/ASR profile CRUD, credential masking, and tiered tests.
- Added independent ASR route settings for material transcription and recording evaluation.
- Normalized TTS output to sentence WAV, merged full MP3, and reused Material/Sentence training structures.

## v0.3.2

- Moved material processing and recording evaluation to durable SQLite jobs with progress, retry, and restart recovery.
- Consolidated evaluation snapshots in the main database and adopted Alembic upgrades.
- Added streamed temporary uploads and ffprobe validation, plus video limits, conversion, and audio extraction.
- Added permission errors, countdown, preview, re-recording, and job status to the recorder.
- Added `VITE_API_BASE` support for the frontend API address.

## v0.3.1

- Added reference/user-ASR word alignment for correct, substituted, deleted, inserted, repeated, and filler tokens.
- Stored alignment in `raw_metrics` and restored the latest evaluation for every sentence.
- Added token highlighting to the trainer and evaluation panel.
- Stored more precise word boundaries to reduce clipped sentence audio.
- Added alignment, media-safety, and trainer regressions.

## v0.3

- Added VAD silence trimming before evaluation with safe fallback.
- Introduced latest material/sentence evaluation snapshots with fallback to the main evaluation table.
- Improved media recognition, clip boundaries, timeline synchronization, and playback errors.

## v0.2

- Automatically started processing after upload and added reprocessing and cascading deletion.
- Added material action menus, progress, and selected-item fallback after deletion.
- Distinguished sentence and silence timeline segments, with autoplay and segment loop.
- Embedded video playback synchronized with sentence boundaries.

## Initial release

- Established the FastAPI, SQLModel/SQLite, and React/Vite application.
- Implemented material upload, local Whisper transcription, segmentation, translation, sentence playback, recording, and baseline scoring.
