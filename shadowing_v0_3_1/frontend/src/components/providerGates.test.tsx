import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  createProvider: vi.fn(),
  deleteProvider: vi.fn(),
  generateTextPractice: vi.fn(),
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
  updateProvider: vi.fn(),
  updateTextPractice: vi.fn(),
}));

vi.mock("../lib/api", () => api);

import SettingsPanel from "./SettingsPanel";
import TextGeneratorPanel from "./TextGeneratorPanel";

const scenes = {
  material_transcription_use_local: true,
  recording_evaluation_use_local: false,
  updated_at: "2026-07-21T00:00:00Z",
  material_transcription_remote_available: false,
  material_transcription_missing_capabilities: ["word_timestamps"],
  recording_evaluation_remote_available: true,
  recording_evaluation_missing_capabilities: [],
};

beforeEach(() => {
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
});

describe("provider capability gates", () => {
  it("locks only the ASR scene that lacks word timestamps and explains why", async () => {
    api.listProviders.mockResolvedValue([
      {
        id: 1, name: "MiMo ASR", capability: "asr", provider_type: "mimo_asr",
        base_url: "https://example.test", api_key_masked: "****", model_name: "mimo",
        is_enabled: true, is_default: true, extra_config: {}, capabilities: ["transcribe"],
        created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:00Z",
      },
    ]);
    render(<SettingsPanel />);

    const material = await screen.findByLabelText("Use Local Whisper for material transcription");
    const recording = screen.getByLabelText("Use Local Whisper for recording evaluation");
    expect(material).toBeDisabled();
    expect(recording).not.toBeDisabled();
    expect(screen.getByText(/missing word_timestamps/i)).toBeInTheDocument();
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
    render(<TextGeneratorPanel collections={[]} onMaterialReady={() => undefined} />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Generate text" })).toBeDisabled());
    expect(screen.getByText(/default LLM supports generate_text and generate_json/i)).toBeInTheDocument();
    expect(screen.getByText(/default TTS provider supports synthesize/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create TTS practice" })).toBeDisabled();
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
    render(<SettingsPanel />);

    const material = await screen.findByLabelText("Use Local Whisper for material transcription");
    expect(material).toBeDisabled();
    expect(screen.getAllByText(/effective route: remote/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/install it when local ASR is needed/i)).toBeInTheDocument();
  });
});
