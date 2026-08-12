# Provider guide (v0.4.1)

Provider settings are saved by the backend. API reads expose only a masked API
key; leaving an API-key field blank during an edit retains its previous value.
The static Settings catalog is authoritative. It contains only the profiles
below; legacy adapter files and migrated disabled records do not make a profile
available.

## Registered profiles

| Kind | Profile | Endpoint mode | Declared capability | Notes |
| --- | --- | --- | --- | --- |
| LLM | OpenAI Chat Completions | Base URL | `generate_text`, `generate_json` | Appends `/chat/completions` and uses `/models` for metadata verification. |
| TTS | OpenAI Audio TTS | Full endpoint | `synthesize` | Accepts WAV, MP3, FLAC, Opus, AAC, or PCM. |
| TTS | MiMo TTS | Full endpoint | `synthesize` | Uses the MiMo Chat Completions TTS request shape; accepts WAV, MP3, FLAC, Opus, or PCM16. |
| ASR | OpenAI Audio Transcription | Base URL | `transcribe`, `word_timestamps` | Appends `/audio/transcriptions`; word timestamps must be enabled for material transcription. |
| ASR | MiMo ASR | Full endpoint | `transcribe` | Uses MiMo Chat Completions ASR; it is text-only for routing purposes. |

Local Whisper is separately optional and is not a remote profile. Azure,
Deepgram, ElevenLabs, DashScope, and other historical integrations are not
registered supported providers in this release.

## Endpoint rules

- **OpenAI Chat Completions:** enter a base URL, for example
  `https://api.openai.com/v1`; the app adds `/chat/completions`.
- **OpenAI Audio Transcription:** enter a base URL, for example
  `https://api.openai.com/v1`; the app adds `/audio/transcriptions`.
- **OpenAI Audio TTS:** enter the complete speech endpoint, for example
  `https://api.openai.com/v1/audio/speech`.
- **MiMo TTS and MiMo ASR:** enter the complete MiMo Chat Completions endpoint,
  commonly `https://api.xiaomimimo.com/v1/chat/completions`.

For every `full_endpoint` profile, the supplied URL is used as-is: the app does
not add a path. This is important for compatible gateways with nonstandard
paths.

## Boundaries and tests

The catalog advertises protocol maxima, while each saved profile declares the
capabilities and output formats it is allowed to use. The backend enforces
those boundaries:

- LLM JSON generation requires an enabled JSON method.
- TTS synthesis requires an enabled output format.
- ASR profiles do not accept output-format selections.

**Check configuration** is local and non-billable. **Verify connection** uses
the descriptor's safe strategy when available (OpenAI Chat lists models); audio
profiles currently perform configuration-only checks. **Run paid test** requires
confirmation and may send a small live request.

## Language propagation

All new content languages use the controlled catalog in
[MULTILINGUAL.md](MULTILINGUAL.md). A material/text-practice task language
overrides a provider's configured language default.

- OpenAI ASR receives the task language reduced to its primary code where
  required (for example, `zh-CN` becomes `zh`).
- MiMo ASR accepts only `auto`, `zh`, and `en`. Canonical English tags map to
  `en`, Chinese tags map to `zh`, and an absent hint maps to `auto`. Other task
  languages make the MiMo route unusable; the router selects Local Whisper
  when available or returns an explicit unsupported-language error.
- Local Whisper receives the task language when its route is selected.
- OpenAI Audio TTS keeps the language as internal request metadata by default.
  It does **not** send a natural-language TTS `instructions` field merely
  because a task language is present. Enable the explicit
  `send_language_instruction` compatibility option only for an endpoint known
  to support OpenAI's optional `instructions` field.

## ASR routing and conservative fallback matrix

The routes are decided independently for two scenes:

| Scene | Remote requirement | Consequence |
| --- | --- | --- |
| Material transcription | `transcribe` + `word_timestamps` | MiMo ASR alone is insufficient. |
| Recording evaluation | `transcribe` plus task-language support | OpenAI ASR may use any catalog language; MiMo ASR is limited to English/Chinese/auto. |

The saved switch is a preference, not a guarantee. At runtime the router uses
the preferred usable route, otherwise the only usable alternative; it reports
unavailable when neither route works. Therefore:

| Local Whisper | Remote requirement met | Effective route |
| --- | --- | --- |
| available | yes | user preference |
| available | no | local |
| unavailable | yes | remote |
| unavailable | no | unavailable |

Remote material transcription depends on timestamp support from the selected
and enabled profile. The code's registered descriptors and route checks take
precedence over this document if they change.

OpenAI/Whisper exposes one `zh` recognition hint rather than separate
simplified/traditional script locales. A `zh-TW` material retains its `zh-TW`
metadata and alignment label, but the returned script is model-dependent;
verify the transcript before relying on character-level Traditional-Chinese
recording scores.

## TTS output pipeline

TTS jobs synthesize one sentence at a time. The backend chooses the first
enabled acceptable format in this order: WAV, MP3, FLAC, Opus, AAC, then PCM.
It normalizes sentence clips to 24 kHz mono WAV and merges material audio to
MP3. Raw PCM requires explicit sample rate, channel count, and sample format.

TTS jobs retain an immutable snapshot of text, target/translation languages,
provider id, and options. Editing or re-queuing a practice supersedes the old
job rather than allowing it to overwrite newer content.
