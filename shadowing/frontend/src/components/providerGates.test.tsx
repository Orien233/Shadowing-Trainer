import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  createProvider: vi.fn(),
  deleteProvider: vi.fn(),
  generateTextPractice: vi.fn(),
  getLanguagePreferences: vi.fn(),
  getASRSceneSettings: vi.fn(),
  getLocalASRStatus: vi.fn(),
  getJob: vi.fn(),
  importTextPractice: vi.fn(),
  listProviderCatalog: vi.fn(),
  listProviderVoices: vi.fn(),
  listProviders: vi.fn(),
  releaseLocalASR: vi.fn(),
  testLocalASR: vi.fn(),
  synthesizeTextPractice: vi.fn(),
  testProvider: vi.fn(),
  testProviderDraft: vi.fn(),
  updateASRSceneSettings: vi.fn(),
  updateLanguagePreferences: vi.fn(),
  updateProvider: vi.fn(),
  updateTextPractice: vi.fn(),
}));

vi.mock("../lib/api", () => api);

import SettingsPanel from "./SettingsPanel";
import TextGeneratorPanel from "./TextGeneratorPanel";
import { LanguageProvider, useLanguage } from "../i18n/LanguageContext";

const scenes = {
  material_transcription_use_local: true,
  recording_evaluation_use_local: false,
  updated_at: "2026-07-21T00:00:00Z",
  material_transcription_remote_available: false,
  material_transcription_missing_capabilities: ["word_timestamps"],
  recording_evaluation_remote_available: true,
  recording_evaluation_missing_capabilities: [],
};

function renderSettings() {
  return render(<LanguageProvider><SettingsPanel /></LanguageProvider>);
}

function TextGeneratorLocaleHarness() {
  const { setUILocale } = useLanguage();
  return <><button onClick={() => setUILocale("zh-CN")}>switch locale</button><TextGeneratorPanel collections={[]} onMaterialReady={() => undefined} /></>;
}

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
  api.listProviderCatalog.mockResolvedValue([]);
  api.listProviderVoices.mockResolvedValue([]);
  api.getASRSceneSettings.mockResolvedValue(scenes);
  api.getLocalASRStatus.mockResolvedValue({
    installed: true, runtime_ready: true, model_loaded: false, model_cached: true,
    will_download_on_first_use: false, model_name: "small", device: "cpu", compute_type: "int8",
    model_dir: "data/models/whisper", allow_download: true, error: null,
  });
  api.listProviders.mockResolvedValue([]);
  api.getLanguagePreferences.mockResolvedValue({ id: 1, ui_locale: "en-US", learning_language: "en", translation_language: "en", updated_at: "2026-08-12T00:00:00Z" });
  api.updateLanguagePreferences.mockImplementation(async (payload) => ({ id: 1, ...payload, updated_at: "2026-08-12T00:00:00Z" }));
});

describe("provider capability gates", () => {
  it("notifies the mounted AI-text workflow after a saved Provider changes", async () => {
    const onProvidersChanged = vi.fn();
    api.listProviders.mockResolvedValue([
      {
        id: 1, name: "Default LLM", capability: "llm", provider_type: "openai_chat_compatible",
        base_url: "https://example.test/v1", api_key_masked: "****", model_name: "chat",
        is_enabled: true, is_default: true, extra_config: {},
        capabilities: ["generate_text", "generate_json"],
        enabled_capabilities: ["generate_text", "generate_json"],
        enabled_formats: ["response_format"],
        created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:00Z",
      },
    ]);
    api.updateProvider.mockResolvedValue({});
    render(<LanguageProvider><SettingsPanel onProvidersChanged={onProvidersChanged} /></LanguageProvider>);

    fireEvent.click(await screen.findByRole("button", { name: "Disable" }));

    await waitFor(() => expect(api.updateProvider).toHaveBeenCalledWith(1, { is_enabled: false }));
    await waitFor(() => expect(onProvidersChanged).toHaveBeenCalledTimes(1));
  });

  it("locks only the ASR scene that lacks word timestamps and explains why", async () => {
    api.listProviders.mockResolvedValue([
      {
        id: 1, name: "MiMo ASR", capability: "asr", provider_type: "mimo_asr",
        base_url: "https://example.test", api_key_masked: "****", model_name: "mimo",
        is_enabled: true, is_default: true, extra_config: {}, capabilities: ["transcribe"],
        created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:00Z",
      },
    ]);
    renderSettings();

    const material = await screen.findByLabelText("Use Local Whisper for material transcription");
    const recording = screen.getByLabelText("Use Local Whisper for recording evaluation");
    expect(material).toBeDisabled();
    expect(recording).not.toBeDisabled();
    expect(screen.getByText(/missing word timestamps/i)).toBeInTheDocument();
  });

  it("disables generation controls when defaults lack their declared capabilities", async () => {
    api.listProviders.mockResolvedValue([
      {
        id: 2, name: "Text only", capability: "llm", provider_type: "mimo_chat",
        base_url: "https://example.test", api_key_masked: "****", model_name: "mimo",
        is_enabled: true, is_default: true, extra_config: {}, capabilities: ["generate_text"],
        created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:00Z",
      },
      {
        id: 3, name: "Unavailable TTS", capability: "tts", provider_type: "tts",
        base_url: "https://example.test", api_key_masked: "****", model_name: "tts",
        is_enabled: true, is_default: true, extra_config: {}, capabilities: [],
        created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:00Z",
      },
    ]);
    render(<LanguageProvider><TextGeneratorPanel collections={[]} onMaterialReady={() => undefined} /></LanguageProvider>);

    await waitFor(() => expect(screen.getByRole("button", { name: "Generate text" })).toBeDisabled());
    expect(screen.getByText(/default LLM supports generate_text and generate_json/i)).toBeInTheDocument();
    expect(screen.getByText(/default TTS provider supports synthesize/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create TTS practice" })).toBeDisabled();
  });

  it("localizes AI-text controls without discarding draft fields", async () => {
    window.localStorage.setItem("shadowing.uiLocale", "en-US");
    render(<LanguageProvider><TextGeneratorLocaleHarness /></LanguageProvider>);
    const title = screen.getByLabelText("Title");
    fireEvent.change(title, { target: { value: "Keep this draft" } });
    fireEvent.click(screen.getByRole("button", { name: "switch locale" }));

    expect(await screen.findByRole("button", { name: "生成文本" })).toBeInTheDocument();
    expect(screen.getByLabelText("标题")).toHaveValue("Keep this draft");
    expect(screen.getByRole("option", { name: "中级" })).toBeInTheDocument();
  });

  it("only offers manually selected collected words for the active target language", async () => {
    render(
      <LanguageProvider>
        <TextGeneratorPanel
          collections={[
            { id: 11, material_id: 1, sentence_id: 1, word_text: "English word", normalized_word: "english word", language: "en", translation: null, source_type: "sentence", note: null, created_at: "2026-08-12T00:00:00Z", updated_at: "2026-08-12T00:00:00Z" },
            { id: 12, material_id: 2, sentence_id: 2, word_text: "Japanese word", normalized_word: "japanese word", language: "ja", translation: null, source_type: "sentence", note: null, created_at: "2026-08-12T00:00:00Z", updated_at: "2026-08-12T00:00:00Z" },
          ]}
          defaultLanguage="en"
          onMaterialReady={() => undefined}
        />
      </LanguageProvider>
    );

    fireEvent.change(screen.getByLabelText("Word selection"), { target: { value: "manual" } });
    expect(screen.getByLabelText("English word")).toBeInTheDocument();
    expect(screen.queryByLabelText("Japanese word")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "ja" } });
    expect(screen.queryByLabelText("English word")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Japanese word")).toBeInTheDocument();
  });

  it("restores the preferred random count after an async collection load", () => {
    const words = Array.from({ length: 7 }, (_, index) => ({
      id: index + 1,
      material_id: 1,
      sentence_id: 1,
      word_text: `word${index + 1}`,
      normalized_word: `word${index + 1}`,
      language: "en",
      translation: null,
      source_type: "sentence",
      note: null,
      created_at: "2026-08-12T00:00:00Z",
      updated_at: "2026-08-12T00:00:00Z",
    }));
    const view = render(
      <LanguageProvider>
        <TextGeneratorPanel collections={[]} onMaterialReady={() => undefined} />
      </LanguageProvider>,
    );

    expect(screen.getByLabelText("Random count")).toHaveValue(0);
    view.rerender(
      <LanguageProvider>
        <TextGeneratorPanel collections={words} onMaterialReady={() => undefined} />
      </LanguageProvider>,
    );

    expect(screen.getByLabelText("Random count")).toHaveValue(5);
  });

  it("shows a forced remote route when Local Whisper is unavailable", async () => {
    api.getASRSceneSettings.mockResolvedValue({
      ...scenes,
      material_transcription_use_local: false,
      material_transcription_local_available: false,
      material_transcription_local_unavailable_reason: "Local Whisper is not installed.",
      material_transcription_effective_route: "remote",
      material_transcription_available: true,
      recording_evaluation_use_local: false,
      recording_evaluation_local_available: false,
      recording_evaluation_local_unavailable_reason: "Local Whisper is not installed.",
      recording_evaluation_effective_route: "remote",
      recording_evaluation_available: true,
      material_transcription_remote_available: true,
    });
    api.getLocalASRStatus.mockResolvedValue({
      installed: false, runtime_ready: false, model_loaded: false, model_cached: false,
      will_download_on_first_use: false, model_name: "small", device: "cpu", compute_type: "int8",
      model_dir: "data/models/whisper", allow_download: true, error: "Local Whisper is not installed.",
    });
    renderSettings();

    const material = await screen.findByLabelText("Use Local Whisper for material transcription");
    expect(material).toBeDisabled();
    expect(screen.getAllByText(/effective route: remote/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/install it when local ASR is needed/i)).toBeInTheDocument();
  });
});
