# User guide

[简体中文](../zh-CN/user-guide.md) | English · [Documentation home](README.md)

## 1. Choose languages

The header and Settings expose three independent choices:

- **UI language** controls buttons, messages, and status labels only.
- **Learning language** is the default body language for new uploads and text practices.
- **Translation language** is the default for new sentence translations and AI explanations.

Changing a global default does not modify existing material. Every Material and Text Practice stores its own language snapshot. See [Multilingual behaviour](multilingual.md) for the full rules.

## 2. Configure models

Open Settings and choose an OpenAI Chat, OpenAI TTS, OpenAI ASR, MiMo TTS, or MiMo ASR quick template. A template does not take part in business calls by itself; saving it creates an independent profile that can be renamed, enabled, tested, and made default.

Every profile can execute only the capabilities and formats selected by the user. At minimum:

- AI Text needs a default LLM with both `generate_text` and `generate_json`, plus a JSON output method.
- TTS needs a default TTS profile with `synthesize` and at least one output format.
- Remote material transcription needs `transcribe` and `word_timestamps`.
- Remote recording evaluation needs `transcribe` and support for the current content language.

MiMo ASR has no word timestamps, so it cannot handle material transcription by itself. See [Models and providers](providers.md) for configuration details.

## 3. Upload and process material

1. Choose the content and translation languages on the Practice panel.
2. Enter a title and choose an audio or video file.
3. After upload, wait for the durable job to normalize media, run ASR, segment, translate, and create sentence audio.
4. Open the material from the list when processing is complete.

Videos are converted to training media before their audio track is extracted. TTS material has known source text and is not transcribed again with ASR.

When processing fails, the card shows its stage and a readable error. Fix the provider, FFmpeg, or Local Whisper configuration, then retry or reprocess. Durable jobs recover after an application restart.

## 4. Collect and manage words

Select a word in a practice sentence to collect it. Every collection record includes a language, so the same spelling in two languages remains two records.

- The word library shows only collections for the selected language.
- Random and manual AI Text selection use only collections matching the target language.
- The backend rejects mixed-language collections in one generated practice.
- Original display casing and Unicode spelling are preserved while deduplication uses a normalized key.

## 5. Generate or import AI text

Open the AI Text panel:

1. Choose a random count or manually select collected words.
2. Choose a preset topic or enter a custom topic.
3. Set target language, translation language, difficulty, and approximate length.
4. Generate a structured result with title, body, used words, unused words, and an optional note.
5. Edit the title or body before submitting TTS.

You can skip the LLM by switching to text import and pasting content. Imported and generated text share the same Text Practice and TTS workflow, so editing and import remain available even without an LLM.

## 6. Create a TTS practice

Choose speed, voice, accent, gender, or model as applicable. Fields unsupported by a specific protocol may be ignored or explicitly rejected by backend validation.

When submitted, the TTS job freezes the body, title, target/translation languages, provider, and options, then:

1. Splits the body with language-aware sentence rules.
2. Synthesizes each sentence separately.
3. Normalizes sentence audio to 24 kHz mono WAV.
4. Merges a full MP3 and creates time boundaries.
5. Creates Material, Sentence, and sentence translations.

When complete, open the result as a normal material for sentence playback, recording, and evaluation. Editing or re-queueing supersedes the old job so stale output cannot overwrite newer text.

## 7. Shadow, record, and evaluate

- Use previous/next, the timeline, loop, and autoplay controls.
- Video material retains video playback synchronized to sentence boundaries.
- Record on a non-silent segment, preview it, re-record, and submit it for evaluation.
- When the evaluation job completes, review completeness, fluency, synchronization, pronunciation, and alignment feedback.
- English provides full word alignment; other languages display character or Unicode-token accuracy according to their actual support level.

Scores are practice feedback, not exam results. See [Segmentation and scoring boundaries](multilingual.md#segmentation-and-scoring-boundaries).

## 8. Failed jobs and retries

Material processing, recording evaluation, and TTS use durable jobs. Read the error and fix the cause before retrying:

- `404 Not Found` often means a Base URL was entered for an adapter that requires a full endpoint, or the reverse.
- Missing capabilities disable the frontend action and are revalidated by the backend.
- If Local Whisper is unavailable, install its optional requirements and inspect its status in Settings.
- A stale TTS job superseded by an edit or newer job cannot use the generic retry path; create a new TTS job from the current text.

Job recovery never bypasses language, provider-capability, or immutable-snapshot validation.
