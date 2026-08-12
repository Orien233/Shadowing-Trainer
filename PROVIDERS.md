# Provider guide

Provider credentials are configured in **Settings** and stored only in the
backend. Provider list APIs return only an API-key mask; leaving the key blank
while editing retains the saved value.

## Supported remote profiles

| Capability | Profile | Protocol shape | User-selectable boundaries |
| --- | --- | --- | --- |
| LLM | OpenAI Chat Completions | `POST /chat/completions` | `generate_text`, `generate_json`; JSON schema, response format, or prompt JSON |
| TTS | OpenAI Audio TTS | Full `/audio/speech` endpoint | `synthesize`; WAV, MP3, FLAC, Opus, AAC, or PCM |
| TTS | MiMo TTS | Full MiMo Chat Completions endpoint | `synthesize`; WAV, MP3, FLAC, Opus, or PCM16 |
| ASR | OpenAI Audio Transcription | Base URL + `/audio/transcriptions` | `transcribe`, optional `word_timestamps` |
| ASR | MiMo ASR | Full MiMo Chat Completions endpoint | `transcribe` only |

The adapter catalog describes protocol maximums. A saved configuration profile
must explicitly select its usable capabilities and formats; those selections
are enforced by the backend for generation, TTS jobs, and ASR routing.

## Built-in templates and configuration profiles

OpenAI and MiMo entries in Settings are read-only templates. Choosing one
pre-fills a new configuration but never stores a key automatically. Saved
profiles can be renamed, enabled/disabled, made default, tested, or deleted
independently. A single protocol can have multiple profiles.

For `full_endpoint` adapters, enter the complete documented endpoint. The app
does not append `/audio/speech` or `/audio/transcriptions` for you. For OpenAI
ASR, enter the API base URL; the adapter appends `/audio/transcriptions`.

## Test levels

Settings exposes three deliberate test levels:

- **Check configuration** validates required fields and selected boundaries.
  It makes no network request and is non-billable.
- **Verify connection** uses an adapter's safe metadata strategy when one is
  available. A configuration-only adapter clearly reports that it did not make
  a network request.
- **Run paid test** sends a minimal live request after confirmation: a tiny
  LLM prompt, a short TTS phrase, or a synthetic silent WAV for ASR. It does
  not save content or alter provider capability gates, but it can incur cost.

Errors are redacted before they reach the browser; API keys and authorization
headers are never returned.

## Local Whisper is optional

Remote-only deployments can install only the core runtime:

```powershell
pip install -r requirements.txt
```

Install local ASR only when it is needed:

```powershell
pip install -r requirements-local-whisper.txt
```

The Local Whisper section in Settings reports whether the package is present,
whether the configured CPU/CUDA runtime is usable, whether the model is cached,
and whether the first use will download it. It never downloads or loads a model
merely by opening Settings. **Load model** is explicit; **Release model memory**
removes the in-process cache.

Relevant environment options:

```env
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_MODEL_DIR=./data/models/whisper
WHISPER_ALLOW_DOWNLOAD=true
```

Set `WHISPER_ALLOW_DOWNLOAD=false` in offline deployments after placing the
model in the configured cache directory.

## ASR scene routing

The two scenes are independent:

| Scene | Remote requirement |
| --- | --- |
| Material transcription | `transcribe` and `word_timestamps` |
| Recording evaluation | `transcribe` |

The toggle records a preferred route. At execution time the router safely
selects the preferred route when available, otherwise the only viable fallback:

- local available + remote available: user choice;
- local available + remote unavailable: Local Whisper is forced;
- local unavailable + remote available: remote ASR is forced;
- neither available: the operation is disabled with both reasons reported.

MiMo ASR intentionally exposes ordinary transcription only, so it may handle
remote recording evaluation but cannot handle remote material segmentation.
OpenAI ASR can be configured with word timestamps for both scenes.

## TTS material pipeline

TTS jobs synthesize each sentence separately. Every response is normalized to
24 kHz mono WAV for the trainer, then sentence WAV files are merged into a
complete MP3 Material. This preserves existing SentenceTrainer playback,
recording, scoring, and task-recovery behavior. TTS format selection is
automatic from the profile's enabled formats, preferring WAV, MP3, FLAC, Opus,
AAC, then PCM.
