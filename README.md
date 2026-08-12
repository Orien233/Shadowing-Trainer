# Shadowing Trainer v0.4.1

Shadowing Trainer is a local-first web application for uploading or generating
language-learning material, practising it sentence by sentence, recording, and
reviewing feedback. v0.4.1 adds a controlled multilingual workflow and a
descriptor-driven provider catalog.

## Source directory and upgrade

The active branch is `v0_4_1`, while the runtime source directory remains
`shadowing_v0_3_1/`. This historical directory name is deliberate: it preserves
local scripts and existing data paths. It does **not** indicate that the
application version is v0.3.1.

From the repository root, install and migrate the backend before starting it:

```powershell
cd shadowing_v0_3_1/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Start the frontend separately:

```powershell
cd shadowing_v0_3_1/frontend
npm install
npm run dev
```

The database migration chain creates provider/job tables and adds language
snapshots to existing materials and text practices. Legacy material rows are
backfilled to `content_language=en` and `translation_language=zh-CN`; legacy
text-practice rows receive `translation_language=zh-CN`. Back up production
data before any database migration.

Copy [`shadowing_v0_3_1/backend/.env.example`](shadowing_v0_3_1/backend/.env.example)
to `shadowing_v0_3_1/backend/.env` for runtime settings. Provider credentials
are configured in Settings and stored in the backend database.

## Languages

Three independent choices are persisted:

- UI locale: `zh-CN` or `en-US`.
- Learning/content language: the source language for new uploads and new text
  practices.
- Translation language: the language for sentence translations and AI
  explanations.

Learning and translation languages are selected from the same controlled BCP-47
catalog: `en`, `zh-CN`, `zh-TW`, `ja`, `ko`, `es`, `fr`, `de`, `it`, `pt`, `ru`,
and `ar`. Existing material and text-practice records retain their own language
snapshots when global preferences later change.

The language data flows through uploads, collected-word filtering, LLM text
generation, ASR task hints, translation, text-to-speech (TTS) job snapshots,
and sentence segmentation. A task language takes precedence over any provider
default. See [MULTILINGUAL.md](MULTILINGUAL.md) for the exact boundaries and
fallback behaviour.

## Supported providers

The Settings catalog is the source of truth. The currently registered remote
profiles are:

| Capability | Registered profile |
| --- | --- |
| LLM | OpenAI Chat Completions |
| TTS | OpenAI Audio TTS; MiMo TTS |
| ASR | OpenAI Audio Transcription; MiMo ASR |

Local Whisper is an optional local ASR runtime, not a remote provider profile.
Other adapter source files or saved legacy records are not selectable/runnable
in v0.4.1. In particular, Azure, Deepgram, ElevenLabs, and DashScope are not
current supported profiles. [PROVIDERS.md](PROVIDERS.md) documents capability
requirements, endpoints, and routing.

MiMo ASR accepts only its documented `auto`, Chinese, and English language
hints. The adapter maps canonical English/Chinese tags to that protocol range;
other learning languages require an available Local Whisper route or another
compatible ASR profile and otherwise fail with an explicit routing error.

## Main flows

- **Upload:** Choose content and translation languages when uploading. Material
  processing sends the content language to ASR, segments the transcript, and
  requests translations in the saved translation language.
- **Collected words and AI text:** Collected words have a language tag. Lists
  and random/manual generation are scoped to the target language; cross-language
  selections are rejected.
- **TTS practice:** Generated or imported text has a target and translation
  language. Queueing freezes the text, both language values, provider, and
  options. The job synthesizes sentence clips, translates sentences with the
  frozen languages, normalizes clips for training, and creates a Material.
- **Recording evaluation:** The sentence material's content language is passed
  to the selected ASR route.

Sentence segmentation is language-aware in its joining behaviour (Chinese and
Japanese segments are joined without inserted spaces) and handles common
sentence terminators. It is deliberately a conservative implementation, not a
full tokenizer for every supported script.

Scoring declares its language boundary: English keeps the full word-alignment
heuristics; Chinese, Japanese, and Korean use limited character alignment; the
other catalog languages use basic Unicode-token alignment without English
contraction, filler, or morphology rules. The UI labels the resulting accuracy
unit explicitly. Provider capability and ASR degradation still follow the
registered adapter descriptors and runtime routing checks.

## Optional local ASR

The core install is remote-capable and does not install Local Whisper:

```powershell
pip install -r requirements.txt
```

Install it only if local ASR is needed:

```powershell
pip install -r requirements-local-whisper.txt
```

See the example environment file for Whisper model/cache settings. Settings can
report readiness and load/release the model explicitly; opening Settings does
not load it.

## Verification

```powershell
cd shadowing_v0_3_1/backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm test
npm run build
```
