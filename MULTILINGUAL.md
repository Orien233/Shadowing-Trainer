# Multilingual behaviour (v0.4.1)

## Independent language settings

The application keeps three distinct settings:

| Setting | Allowed values | Purpose |
| --- | --- | --- |
| `ui_locale` | `zh-CN`, `en-US` | Interface labels and status text only. |
| `learning_language` | controlled learning-language catalog | Default content language for new uploads and text practices. |
| `translation_language` | controlled learning-language catalog | Default language for new sentence translations and AI explanations. |

Changing UI locale does not translate stored content. Changing either global
learning preference affects defaults only: uploaded materials and text
practices persist their language snapshots.

## Controlled content-language catalog

The backend accepts these canonical BCP-47 tags for learning and translation
content: `en` (English), `zh-CN` (Chinese, Simplified), `zh-TW` (Chinese,
Traditional), `ja` (Japanese), `ko` (Korean), `es` (Spanish), `fr` (French),
`de` (German), `it` (Italian), `pt` (Portuguese), `ru` (Russian), and `ar`
(Arabic). Unknown content-language values are rejected. Input casing and `_` in
`zh_cn` / `zh_tw` are normalized to canonical tags.

`auto` is reserved for ASR detection where specifically allowed; it is not a
content-language preference. `und` is only permitted where the backend
explicitly represents an unknown content language.

## Flow hand-offs

| Flow | Language behaviour |
| --- | --- |
| Preferences | UI, learning, and translation choices are stored independently. |
| Upload | Request supplies `content_language` and `translation_language`; the Material saves both. |
| Material processing | Uses the Material's content language for ASR and segmentation; translates sentences from content language to the Material's translation language. |
| Collected words | A word is saved with a canonical language. Collection listing and generated-text word selection are scoped to the target language. |
| LLM text | Generated/imported practice persists `target_language` and `translation_language`; generation rejects selected words from another target language. |
| TTS | A queued job snapshots target/translation languages. TTS must use the practice target language; sentence translations use the snapshot translation language. |
| Recording evaluation | Passes the parent Material's content language to the ASR scene. |

Provider language ranges remain part of routing. MiMo ASR accepts only
automatic detection, Chinese, and English hints; canonical `en*` and `zh*`
values are mapped to its protocol values. A MiMo recording-evaluation route
for any other content language falls back to Local Whisper when available and
otherwise returns an explicit unsupported-language error.

Translation short-circuits when source and target language are identical, so it
does not send a provider request in that case. Translation is enrichment: if no
eligible LLM exists, or an individual translation fails, the source material or
TTS practice still becomes usable with a blank translation that the UI labels
in the selected interface language.

## Segmentation and scoring scope

Sentence assembly uses no inserted spaces for Chinese and Japanese segment
text, and inserts spaces for other language values. It uses conservative
punctuation, duration, and segment-count limits; it is not advertised as a
language-specific linguistic tokenizer.

Scoring publishes an explicit alignment profile instead of calling every result
"word accuracy": English uses the established full word alignment; Chinese,
Japanese, and Korean use limited Unicode-character alignment; other catalog
languages use basic Unicode-word alignment. English contraction, filler, and
minor morphology heuristics are never applied to non-English content. Stored
`raw_metrics` includes `language`, `alignment_mode`, and `support_level`, and
the UI labels word/character/token accuracy accordingly.

Where an ASR/provider cannot satisfy a requested scene (especially timestamp
data for material transcription), routing falls back only to an available local
or remote option as described in [PROVIDERS.md](PROVIDERS.md); otherwise the
operation is unavailable. This capability/degradation matrix is intentionally
conservative and defers to the running adapter catalog.

MiMo ASR accepts only English/Chinese recognition hints (`en`, `zh`, or
`auto`). Other catalog languages are rejected before a remote request and use
Local Whisper only when that runtime is available. Whisper-style ASR uses one
`zh` hint for both `zh-CN` and `zh-TW`; its returned script can vary by model,
so Traditional-Chinese character scores require a transcript/script sanity
check.

## API references

- `GET /api/languages` returns the controlled content-language catalog.
- `GET` / `PUT /api/languages/preferences` reads or updates all three language
  preference fields.
- Upload accepts `content_language` and `translation_language` form fields.
- Word collection accepts and filters by `language`.
- Text-practice generation/import/update accepts target and translation
  language values.
