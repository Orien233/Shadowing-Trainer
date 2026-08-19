import { useEffect, useMemo, useState } from "react";
import {
  FloppyDisk,
  MagicWand,
  SlidersHorizontal,
  Sparkle,
  SpeakerHigh,
} from "@phosphor-icons/react";
import {
  generateTextPractice,
  getJob,
  importTextPractice,
  listProviderVoices,
  listProviders,
  synthesizeTextPractice,
  updateTextPractice,
} from "../../lib/api";
import type { AIProvider, ProviderVoice, TextPractice, WordCollection } from "../../types";
import { languageLabel, LEARNING_LANGUAGES } from "../../i18n/catalog";
import { useLanguage } from "../../i18n/LanguageContext";
import { stageLabel } from "../../i18n/statusLabels";

function hasCapabilities(
  providers: AIProvider[],
  capability: "llm" | "tts",
  required: string[]
): boolean {
  const provider = providers.find(
    (item) => item.capability === capability && item.is_enabled && item.is_default
  );
  return Boolean(provider && required.every((item) => provider.capabilities.includes(item)));
}

function displayVoice(voice: ProviderVoice): string {
  const languages = voice.languages?.length
    ? " (" + voice.languages.join(", ") + ")"
    : voice.locale
      ? " (" + voice.locale + ")"
      : "";
  return (voice.name || voice.id) + languages;
}

const DRAFT_STORAGE_KEY = "shadowing.textGeneratorDraft";

interface Draft {
  mode?: "random" | "manual" | "none";
  selected?: number[];
  title?: string;
}

function readDraft(): Draft {
  try {
    return JSON.parse(window.sessionStorage.getItem(DRAFT_STORAGE_KEY) || "{}") as Draft;
  } catch {
    return {};
  }
}

interface Props {
  collections: WordCollection[];
  defaultLanguage?: string;
  defaultTranslationLanguage?: string;
  providerRefreshToken?: number;
  onMaterialReady: (materialId: number) => void;
}

export default function TextGeneratorPanel({
  collections,
  defaultLanguage = "en",
  defaultTranslationLanguage = "zh-CN",
  providerRefreshToken = 0,
  onMaterialReady,
}: Props) {
  const {
    uiLocale,
    setLearningLanguage,
    setTranslationLanguage: setGlobalTranslationLanguage,
    t,
  } = useLanguage();
  const initialDraft = useMemo(readDraft, []);
  const [mode, setMode] = useState<"random" | "manual" | "none">(initialDraft.mode || "random");
  const [count, setCount] = useState(5);
  const [selected, setSelected] = useState<number[]>(initialDraft.selected || []);
  const [topic, setTopic] = useState("daily_life");
  const [customTopic, setCustomTopic] = useState("");
  const [language, setLanguage] = useState(defaultLanguage);
  const [translationLanguage, setTranslationLanguage] = useState(defaultTranslationLanguage);
  const [difficulty, setDifficulty] = useState("intermediate");
  const [length, setLength] = useState(180);
  const [practice, setPractice] = useState<TextPractice | null>(null);
  const [title, setTitle] = useState(initialDraft.title || t("textGenerator.defaultTitle"));
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [speed, setSpeed] = useState<"slow" | "normal" | "fast">("normal");
  const [voice, setVoice] = useState("");
  const [accent, setAccent] = useState("");
  const [gender, setGender] = useState("");
  const [ttsModel, setTtsModel] = useState("");
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [providersLoaded, setProvidersLoaded] = useState(false);
  const [voices, setVoices] = useState<ProviderVoice[]>([]);
  const [voicesLoaded, setVoicesLoaded] = useState(false);

  const matchingCollections = useMemo(
    () => collections.filter(
      (item) => String(item.language || "en").replace("_", "-").toLowerCase() ===
        language.replace("_", "-").toLowerCase()
    ),
    [collections, language]
  );
  const effectiveRandomCount = Math.min(count, matchingCollections.length);
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const canGenerate = hasCapabilities(providers, "llm", ["generate_text", "generate_json"]);
  const canSynthesize = hasCapabilities(providers, "tts", ["synthesize"]);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        DRAFT_STORAGE_KEY,
        JSON.stringify({ mode, selected, title })
      );
    } catch {
      // Storage is optional; the editor remains usable without it.
    }
  }, [mode, selected, title]);

  useEffect(() => {
    if (!practice) return;
    setTitle(practice.title);
    setBody(practice.body);
    setLanguage(practice.target_language);
    setTranslationLanguage(practice.translation_language);
  }, [practice]);

  useEffect(() => {
    if (!practice) setLanguage(defaultLanguage);
  }, [defaultLanguage, practice]);

  useEffect(() => {
    if (!practice) setTranslationLanguage(defaultTranslationLanguage);
  }, [defaultTranslationLanguage, practice]);

  useEffect(() => {
    const availableIds = new Set(matchingCollections.map((item) => item.id));
    setSelected((current) => current.filter((id) => availableIds.has(id)));
  }, [matchingCollections]);

  useEffect(() => {
    let cancelled = false;
    async function loadProviderOptions() {
      setProvidersLoaded(false);
      setVoicesLoaded(false);
      try {
        const nextProviders = await listProviders();
        if (cancelled) return;
        setProviders(nextProviders);
        setVoices([]);
        const ttsProvider = nextProviders.find(
          (provider) => provider.capability === "tts" &&
            provider.is_enabled &&
            provider.is_default
        );
        if (!ttsProvider) return;
        try {
          const nextVoices = await listProviderVoices(ttsProvider.id);
          if (!cancelled) setVoices(nextVoices);
        } catch {
          if (!cancelled) setVoices([]);
        }
      } catch (error) {
        if (!cancelled) {
          setMessage(error instanceof Error ? error.message : t("textGenerator.providerLoadFailed"));
        }
      } finally {
        if (!cancelled) {
          setProvidersLoaded(true);
          setVoicesLoaded(true);
        }
      }
    }
    void loadProviderOptions();
    return () => {
      cancelled = true;
    };
  }, [providerRefreshToken, t]);

  async function generate() {
    setBusy(true);
    setMessage("");
    try {
      setPractice(await generateTextPractice({
        word_selection: mode,
        random_word_count: effectiveRandomCount,
        word_collection_ids: selected,
        preset_topic: topic || undefined,
        custom_topic: customTopic || undefined,
        target_language: language,
        translation_language: translationLanguage,
        difficulty,
        desired_length: length,
      }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("textGenerator.generationFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function saveOrImport() {
    setBusy(true);
    setMessage("");
    try {
      const next = practice
        ? await updateTextPractice(practice.id, {
            title,
            body,
            target_language: language,
            translation_language: translationLanguage,
          })
        : await importTextPractice({
            title,
            body,
            target_language: language,
            translation_language: translationLanguage,
            difficulty,
            topic: customTopic || topic,
          });
      setPractice(next);
      setMessage(t("textGenerator.saved"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("textGenerator.saveFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function createSpeech() {
    if (!practice) return;
    setBusy(true);
    setMessage(t("textGenerator.ttsQueued"));
    try {
      const latest = await updateTextPractice(practice.id, {
        title,
        body,
        target_language: language,
        translation_language: translationLanguage,
      });
      setPractice(latest);
      const job = await synthesizeTextPractice(latest.id, {
        speed_preset: speed,
        voice: voice || undefined,
        accent: accent || undefined,
        gender: gender || undefined,
        model: ttsModel || undefined,
      });
      for (let index = 0; index < 180; index += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const current = await getJob(job.job_id);
        setMessage(t("textGenerator.ttsProgress", {
          stage: stageLabel(t, current.stage),
          progress: current.progress,
        }));
        if (current.status === "succeeded") {
          const materialId = current.result?.material_id;
          if (typeof materialId === "number") onMaterialReady(materialId);
          return;
        }
        if (current.status === "failed") {
          throw new Error(current.error_message || t("textGenerator.ttsFailed"));
        }
      }
      throw new Error(t("textGenerator.ttsTimedOut"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("textGenerator.ttsFailed"));
    } finally {
      setBusy(false);
    }
  }

  function selectTranslationLanguage(value: string) {
    setTranslationLanguage(value);
    setGlobalTranslationLanguage(value);
  }

  return (
    <section className="secondary-page text-generator">
      <header className="page-heading">
        <div>
          <span className="eyebrow">Shadowing</span>
          <h2>
            <Sparkle size={26} weight="fill" aria-hidden="true" />
            {t("textGenerator.title")}
          </h2>
          <p>{t("textGenerator.description")}</p>
        </div>
      </header>

      <div className="generator-layout">
        <section className="generator-card generator-setup">
          <header className="section-heading">
            <SlidersHorizontal size={20} weight="regular" aria-hidden="true" />
            <div>
              <h3>{t("textGenerator.setupTitle")}</h3>
              <p>{t("textGenerator.setupDescription")}</p>
            </div>
          </header>
          {providersLoaded && !canGenerate && (
            <p className="inline-notice">{t("textGenerator.generationUnavailable")}</p>
          )}
          <div className="form-grid">
            <label>
              <span>{t("textGenerator.wordSelection")}</span>
              <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
                <option value="random">{t("textGenerator.randomCollection")}</option>
                <option value="manual">{t("textGenerator.chooseWords")}</option>
                <option value="none">{t("textGenerator.noCollectedWords")}</option>
              </select>
            </label>
            {mode === "random" && (
              <label>
                <span>{t("textGenerator.randomCount")}</span>
                <input
                  type="number"
                  min="0"
                  max={matchingCollections.length}
                  value={effectiveRandomCount}
                  onChange={(event) => setCount(
                    Math.max(0, Math.min(Number(event.target.value) || 0, matchingCollections.length))
                  )}
                />
              </label>
            )}
            <label>
              <span>{t("textGenerator.theme")}</span>
              <select value={topic} onChange={(event) => setTopic(event.target.value)}>
                {["daily_life", "travel", "workplace", "campus", "news", "story"].map((item) => (
                  <option key={item} value={item}>{t("textGenerator.theme." + item)}</option>
                ))}
              </select>
            </label>
            <label>
              <span>{t("textGenerator.customTheme")}</span>
              <input value={customTopic} onChange={(event) => setCustomTopic(event.target.value)} />
            </label>
            <label>
              <span>{t("textGenerator.language")}</span>
              <select
                value={language}
                onChange={(event) => {
                  setLanguage(event.target.value);
                  setLearningLanguage(event.target.value);
                }}
              >
                {LEARNING_LANGUAGES.map((item) => (
                  <option key={item.code} value={item.code}>
                    {languageLabel(item.code, uiLocale)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>{t("textGenerator.translationLanguage")}</span>
              <select
                value={translationLanguage}
                onChange={(event) => selectTranslationLanguage(event.target.value)}
              >
                {LEARNING_LANGUAGES.map((item) => (
                  <option key={item.code} value={item.code}>
                    {languageLabel(item.code, uiLocale)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>{t("textGenerator.difficulty")}</span>
              <select value={difficulty} onChange={(event) => setDifficulty(event.target.value)}>
                {["beginner", "intermediate", "advanced"].map((item) => (
                  <option key={item} value={item}>{t("textGenerator.difficulty." + item)}</option>
                ))}
              </select>
            </label>
            <label>
              <span>{t("textGenerator.length")}</span>
              <input
                type="number"
                min="20"
                value={length}
                onChange={(event) => setLength(Number(event.target.value))}
              />
            </label>
          </div>

          {mode === "random" && matchingCollections.length === 0 && (
            <p className="muted">{t("textGenerator.noWordsHint")}</p>
          )}
          {mode === "manual" && (
            <div className="word-picker">
              {matchingCollections.map((word) => (
                <label key={word.id}>
                  <input
                    type="checkbox"
                    checked={selectedSet.has(word.id)}
                    onChange={() => setSelected((previous) =>
                      previous.includes(word.id)
                        ? previous.filter((id) => id !== word.id)
                        : [...previous, word.id]
                    )}
                  />
                  {word.word_text}
                </label>
              ))}
            </div>
          )}
          <div className="panel-actions">
            <button disabled={busy || !canGenerate} onClick={() => void generate()}>
              <MagicWand size={18} weight="fill" />
              {t("textGenerator.generate")}
            </button>
          </div>
        </section>

        <section className="generator-card generator-editor">
          <header className="section-heading">
            <FloppyDisk size={20} weight="regular" aria-hidden="true" />
            <div>
              <h3>{t("textGenerator.editorTitle")}</h3>
              <p>{t("textGenerator.editorDescription")}</p>
            </div>
          </header>
          <label>
            <span>{t("textGenerator.titleLabel")}</span>
            <input dir="auto" value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label className="practice-text-field">
            <span>{t("textGenerator.textLabel")}</span>
            <textarea
              dir="auto"
              rows={12}
              value={body}
              onChange={(event) => setBody(event.target.value)}
              placeholder={t("textGenerator.textPlaceholder")}
            />
          </label>
          {practice?.used_words.length ? (
            <p className="muted" dir="auto">
              {t("textGenerator.usedWords", { words: practice.used_words.join(", ") })}
              {practice.unused_words.length
                ? " · " + t("textGenerator.unusedWords", { words: practice.unused_words.join(", ") })
                : ""}
            </p>
          ) : null}
          <div className="panel-actions">
            <button disabled={busy || !body.trim()} onClick={() => void saveOrImport()}>
              <FloppyDisk size={18} weight="regular" />
              {practice ? t("textGenerator.saveEdits") : t("textGenerator.saveImported")}
            </button>
          </div>
        </section>

        <section className="generator-card generator-voice">
          <header className="section-heading">
            <SpeakerHigh size={20} weight="regular" aria-hidden="true" />
            <div>
              <h3>{t("textGenerator.voiceTitle")}</h3>
              <p>{t("textGenerator.voiceDescription")}</p>
            </div>
          </header>
          {providersLoaded && !canSynthesize && (
            <p className="inline-notice">{t("textGenerator.ttsUnavailable")}</p>
          )}
          <div className="form-grid">
            <label>
              <span>{t("textGenerator.speechSpeed")}</span>
              <select value={speed} onChange={(event) => setSpeed(event.target.value as typeof speed)}>
                {["slow", "normal", "fast"].map((item) => (
                  <option key={item} value={item}>{t("textGenerator.speed." + item)}</option>
                ))}
              </select>
            </label>
            <label>
              <span>{t("textGenerator.voice")}</span>
              <input
                list="tts-voice-options"
                value={voice}
                onChange={(event) => setVoice(event.target.value)}
                placeholder={voices.length
                  ? t("textGenerator.voiceChoose")
                  : t("textGenerator.voiceDefault")}
              />
              {voices.length > 0 && (
                <datalist id="tts-voice-options">
                  {voices.map((item) => (
                    <option key={item.id} value={item.id}>{displayVoice(item)}</option>
                  ))}
                </datalist>
              )}
              {voicesLoaded && (
                <small>
                  {voices.length
                    ? t("textGenerator.voiceCount", { count: voices.length })
                    : t("textGenerator.voiceHint")}
                </small>
              )}
            </label>
            <label>
              <span>{t("textGenerator.accent")}</span>
              <input
                value={accent}
                onChange={(event) => setAccent(event.target.value)}
                placeholder={t("textGenerator.accentPlaceholder")}
              />
            </label>
            <label>
              <span>{t("textGenerator.gender")}</span>
              <select value={gender} onChange={(event) => setGender(event.target.value)}>
                <option value="">{t("textGenerator.genderDefault")}</option>
                <option value="female">{t("textGenerator.genderFemale")}</option>
                <option value="male">{t("textGenerator.genderMale")}</option>
              </select>
            </label>
            <label>
              <span>{t("textGenerator.model")}</span>
              <input
                value={ttsModel}
                onChange={(event) => setTtsModel(event.target.value)}
                placeholder={t("textGenerator.modelPlaceholder")}
              />
            </label>
          </div>
          <div className="panel-actions">
            <button disabled={busy || !practice || !canSynthesize} onClick={() => void createSpeech()}>
              <SpeakerHigh size={18} weight="fill" />
              {t("textGenerator.createSpeech")}
            </button>
          </div>
        </section>
      </div>

      {message && <p className="panel-message" role="status">{message}</p>}
    </section>
  );
}
