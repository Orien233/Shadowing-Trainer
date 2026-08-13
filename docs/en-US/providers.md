# Models, adapters, and tests

[简体中文](../zh-CN/providers.md) | English · [Documentation home](README.md)

Provider profiles are persisted by the backend. The static Adapter Catalog describes the maximum capabilities of a protocol; every user profile then declares the capabilities and formats it is actually allowed to use. Business workflows use only the intersection.

## Current support matrix

| Kind | Quick template / adapter | Endpoint mode | Available capabilities | Available formats |
| --- | --- | --- | --- | --- |
| LLM | OpenAI Chat Completions | Base URL | `generate_text`, `generate_json` | `json_schema`, `response_format`, `prompt_only` |
| TTS | OpenAI Audio TTS | Full endpoint | `synthesize` | WAV, MP3, FLAC, Opus, AAC, PCM |
| TTS | MiMo TTS | Full endpoint | `synthesize` | WAV, MP3, FLAC, Opus, PCM16 |
| ASR | OpenAI Audio Transcription | Base URL | `transcribe`, `word_timestamps` | Not applicable |
| ASR | MiMo ASR | Full endpoint | `transcribe` | Not applicable |

Local Whisper is a system-level local ASR fallback, not a remote database profile. Historical implementations for Azure, Deepgram, ElevenLabs, DashScope, Anthropic, Gemini, Ollama, vLLM, and others remain useful as future source references, but they are not registered in the v0.4.1 Catalog and cannot be created, enabled, tested, or used by business workflows.

## Quick templates and user profiles

Quick templates are read-only metadata. They are not stored in the database, cannot be edited or deleted, and cannot be made the business default. Selecting “Use this template” creates an independent user profile. A profile can:

- Use a custom name, with multiple profiles for the same protocol.
- Store its own endpoint, API key, model, and public extra settings.
- Select capabilities and formats within the protocol's allowed range.
- Be enabled, disabled, tested, made default, or deleted.

Unsupported historical records from an upgraded database are retained but remain disabled and cannot be re-enabled. They are not the same as built-in quick templates.

## Endpoint rules

| Adapter | Value to enter | Example | Path appended by the app |
| --- | --- | --- | --- |
| OpenAI Chat | Base URL | `https://api.openai.com/v1` | `/chat/completions`; connection verification uses `/models` |
| OpenAI ASR | Base URL | `https://api.openai.com/v1` | `/audio/transcriptions` |
| OpenAI TTS | Full speech endpoint | `https://api.openai.com/v1/audio/speech` | None |
| MiMo TTS / ASR | Full Chat Completions endpoint | `https://api.xiaomimimo.com/v1/chat/completions` | None |

A `full_endpoint` URL is used exactly as entered. The application does not append `/audio/speech` or `/chat/completions`. For example, entering `https://api.xiaomimimo.com/v1` for a MiMo profile sends the request directly to that URL and will normally return `404 Not Found`.

## Capability and format declarations

User declarations are backend-enforced boundaries, not frontend hints:

- AI Text requires both `generate_text` and `generate_json` on the default LLM.
- `generate_json` requires at least one JSON method: `json_schema`, `response_format`, or `prompt_only`.
- TTS `synthesize` requires at least one output format.
- `word_timestamps` automatically depends on `transcribe`.
- MiMo ASR has no word timestamps and cannot declare `word_timestamps`.

TTS chooses from the formats enabled on the profile in this order: `wav → mp3 → flac → opus → aac → pcm`. Every result is ultimately normalized to 24 kHz mono sentence WAV files and a merged full-material MP3. Raw PCM also requires a sample rate, channel count, and sample format.

OpenAI TTS does not send `instructions` merely because a practice has a language tag. Enable `send_language_instruction` only after confirming that the compatible endpoint supports the field. Voice instructions explicitly entered by the user are unaffected by this default.

## Configuration checks and model tests

Settings offers three distinct levels, and the response `verification_level` states what was actually checked:

1. **Check configuration (`configuration`)** validates required fields, capabilities, formats, dependencies, and URL shape locally. It sends no network request and has no model cost.
2. **Verify connection (`network`)** accesses the network only when the adapter declares a safe, non-generation request. OpenAI Chat currently uses `GET /models`; audio adapters retain configuration-only validation, so success does not mean an audio model was called.
3. **Run paid test (`inference`)** sends a minimal real generation, synthesis, or transcription request after confirmation. It may incur cost and is subject to quota and content policies.

A failed connection test returns a sanitized readable error and does not change capability declarations, default profiles, or ASR switches. Tests do not persist a verified state and never auto-detect or expand capabilities.

## Credential safety

- API keys are stored only by the backend; reads and test responses return a mask.
- Leaving the API-key field empty during an edit preserves the existing value; a non-empty value replaces it.
- Error messages remove full credentials and sensitive request headers.
- Never place credentials in URLs, README files, `.env.example`, or commits.
- Keep `backend/.env`, databases, and runtime data ignored by Git.

## ASR scene routing

Material transcription and recording evaluation have independent route preferences:

| Scene | Remote requirements |
| --- | --- |
| Material transcription | `transcribe + word_timestamps`, plus material-language support |
| Recording evaluation | `transcribe`, plus material-language support |

At runtime the router checks profile enablement, default selection, user capabilities, language support, and Local Whisper availability:

| Local Whisper | Remote requirements met | Effective route |
| --- | --- | --- |
| Available | Yes | User scene preference |
| Available | No | Forced local |
| Unavailable | Yes | Forced remote |
| Unavailable | No | Explicit unavailable error |

The MiMo ASR protocol accepts only `auto`, `zh`, and `en`. Canonical English tags map to `en` and Chinese tags map to `zh`. Other learning languages are rejected before a remote request and fall back to Local Whisper when available; otherwise the router returns an explicit error. MiMo ASR also has no word timestamps, so it cannot handle remote material transcription.

OpenAI/Whisper uses one `zh` hint for both Simplified and Traditional Chinese. The returned script is model-dependent; inspect the transcript before relying on `zh-TW` character-level scores.

## TTS job consistency

A TTS job freezes the body, title, target/translation languages, provider ID, and options, and writes output to a job-specific directory. Editing text or re-queueing prevents the old job from writing back to the current practice. A failed job can reclaim ownership only when its snapshot still matches and no newer job owns the practice; otherwise retry returns a conflict.
