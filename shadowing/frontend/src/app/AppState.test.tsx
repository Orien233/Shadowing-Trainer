import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  cleanupRecordingFiles: vi.fn(),
  generateTextPractice: vi.fn(),
  getLanguagePreferences: vi.fn(),
  getLatestMaterialEvaluations: vi.fn(),
  getSentences: vi.fn(),
  getJob: vi.fn(),
  importTextPractice: vi.fn(),
  listMaterials: vi.fn(),
  listProviderVoices: vi.fn(),
  listProviders: vi.fn(),
  listWordCollections: vi.fn(),
  shutdownBackend: vi.fn(),
  synthesizeTextPractice: vi.fn(),
  updateLanguagePreferences: vi.fn(),
  updateTextPractice: vi.fn(),
}));

vi.mock("../lib/api", () => api);
vi.mock("../features/materials/MaterialUploader", () => ({ default: () => null }));
vi.mock("../features/practice/SentenceTrainer", () => ({
  default: ({ collectedWordSet }: { collectedWordSet: Set<string> }) => (
    <output aria-label="old-material-word-collected">
      {String(collectedWordSet.has("ja:japaneseword"))}
    </output>
  ),
}));
vi.mock("../features/settings/SettingsPanel", () => ({
  default: ({ onProvidersChanged }: { onProvidersChanged?: () => void }) => (
    <div>
      Settings panel
      <button type="button" onClick={onProvidersChanged}>Simulate provider save</button>
    </div>
  ),
}));
vi.mock("../features/vocabulary/WordCollectionPanel", () => ({
  default: ({ collections }: { collections: Array<{ id: number; word_text: string }> }) => (
    <div>{collections.map((collection) => <span key={collection.id}>{collection.word_text}</span>)}</div>
  ),
}));

import App from "./App";
import { LanguageProvider } from "../i18n/LanguageContext";

const englishCollection = {
  id: 11,
  material_id: 1,
  sentence_id: 1,
  word_text: "English word",
  normalized_word: "english word",
  language: "en",
  translation: null,
  source_type: "sentence",
  note: null,
  created_at: "2026-08-12T00:00:00Z",
  updated_at: "2026-08-12T00:00:00Z",
};

const japaneseCollection = {
  ...englishCollection,
  id: 12,
  word_text: "Japanese word",
  normalized_word: "japanese word",
  language: "ja",
};

function renderApp() {
  return render(<LanguageProvider><App /></LanguageProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.localStorage.setItem("shadowing.uiLocale", "en-US");
  window.localStorage.setItem("shadowing.learningLanguage", "en");
  window.localStorage.setItem("shadowing.translationLanguage", "en");
  api.getLanguagePreferences.mockResolvedValue({
    id: 1,
    ui_locale: "en-US",
    learning_language: "en",
    translation_language: "en",
    updated_at: "2026-08-12T00:00:00Z",
  });
  api.updateLanguagePreferences.mockResolvedValue({});
  api.listMaterials.mockResolvedValue([]);
  api.getSentences.mockResolvedValue([]);
  api.getLatestMaterialEvaluations.mockResolvedValue([]);
  api.listProviders.mockResolvedValue([]);
  api.listProviderVoices.mockResolvedValue([]);
});

describe("App language and panel state", () => {
  it("shows a recoverable error when the material list cannot load", async () => {
    api.listMaterials.mockRejectedValue(new Error("offline"));
    api.listWordCollections.mockResolvedValue([]);
    renderApp();

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load materials.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("indexes an old material's collected words while filtering the visible library", async () => {
    api.listMaterials.mockResolvedValue([{
      id: 1, title: "Japanese material", file_type: "audio", original_path: "source.wav",
      audio_path: "source.wav", duration: 1, status: "ready", content_language: "ja",
      translation_language: "en", created_at: "2026-08-12T00:00:00Z",
    }]);
    api.listWordCollections.mockResolvedValue([englishCollection, japaneseCollection]);
    renderApp();

    await waitFor(() => expect(screen.getByLabelText("old-material-word-collected")).toHaveTextContent("true"));
    fireEvent.click(screen.getByRole("tab", { name: "Library" }));
    expect(await screen.findByText("English word")).toBeInTheDocument();
    expect(screen.queryByText("Japanese word")).not.toBeInTheDocument();
  });

  it("keeps an unsaved AI-text draft and manual selection when changing panels", async () => {
    api.listWordCollections.mockResolvedValue([englishCollection]);
    renderApp();

    fireEvent.click(screen.getByRole("tab", { name: "AI Text" }));
    const title = await screen.findByLabelText("Title");
    fireEvent.change(title, { target: { value: "Keep this draft" } });
    fireEvent.change(screen.getByLabelText("Word selection"), { target: { value: "manual" } });
    const collectedWord = await screen.findByLabelText("English word");
    fireEvent.click(collectedWord);
    expect(collectedWord).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByText("Settings panel")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "AI Text" }));

    expect(screen.getByLabelText("Title")).toHaveValue("Keep this draft");
    expect(screen.getByLabelText("English word")).toBeChecked();
  });

  it("refreshes provider gates after Settings changes without discarding the AI-text draft", async () => {
    const providerBase = {
      base_url: "https://example.test/v1",
      api_key_masked: "se****cret",
      is_enabled: true,
      is_default: true,
      extra_config: {},
      available_capabilities: [],
      enabled_formats: [],
      is_deprecated: false,
      created_at: "2026-08-12T00:00:00Z",
      updated_at: "2026-08-12T00:00:00Z",
    };
    api.listWordCollections.mockResolvedValue([]);
    api.listProviders
      .mockResolvedValueOnce([])
      .mockResolvedValue([
        {
          ...providerBase,
          id: 21,
          name: "LLM",
          capability: "llm",
          provider_type: "openai_chat_compatible",
          model_name: "chat-model",
          capabilities: ["generate_text", "generate_json"],
          enabled_capabilities: ["generate_text", "generate_json"],
        },
        {
          ...providerBase,
          id: 22,
          name: "TTS",
          capability: "tts",
          provider_type: "openai_audio_tts",
          model_name: "tts-model",
          capabilities: ["synthesize"],
          enabled_capabilities: ["synthesize"],
          enabled_formats: ["wav"],
        },
      ]);
    api.listProviderVoices.mockResolvedValue([
      { id: "fresh-voice", name: "Fresh voice", locale: "ja", languages: ["ja"], gender: null },
    ]);
    renderApp();

    fireEvent.click(screen.getByRole("tab", { name: "AI Text" }));
    const title = await screen.findByLabelText("Title");
    fireEvent.change(title, { target: { value: "Keep this provider-refresh draft" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate text" })).toBeDisabled());

    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    fireEvent.click(screen.getByRole("button", { name: "Simulate provider save" }));
    await waitFor(() => expect(api.listProviders).toHaveBeenCalledTimes(1));
    expect(api.listProviderVoices).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("tab", { name: "AI Text" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate text" })).toBeEnabled());
    expect(document.querySelector('datalist option[value="fresh-voice"]')).toHaveTextContent("Fresh voice (ja)");
    expect(screen.queryByText(/default TTS provider supports synthesize/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create TTS practice" })).toBeDisabled();
    expect(screen.getByLabelText("Title")).toHaveValue("Keep this provider-refresh draft");
  });
});
