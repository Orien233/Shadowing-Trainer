import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  apiBase: "http://api.test",
  getJob: vi.fn(),
  retryJob: vi.fn(),
  uploadRecording: vi.fn(),
  getLanguagePreferences: vi.fn(),
  updateLanguagePreferences: vi.fn(),
}));

vi.mock("../../../lib/api", () => api);

import { LanguageProvider } from "../../../i18n/LanguageContext";
import type { Evaluation, Sentence } from "../../../types";
import RecorderPanel from "./RecorderPanel";

const sentence: Sentence = {
  id: 4,
  material_id: 1,
  display_order: 4,
  start_time: 12.96,
  end_time: 17.28,
  original_start_time: null,
  original_end_time: null,
  clip_audio_path: null,
  clip_duration: 4.32,
  source_text: "Small habits compound into remarkable results.",
  translation: "小习惯会累积成非凡的结果。",
  created_at: "2026-08-24T00:00:00Z",
};

const evaluation: Evaluation = {
  id: 7,
  recording_id: 9,
  recording_duration: 4.18,
  completeness_score: 91,
  fluency_score: 88,
  sync_score: 82,
  pronunciation_score: 85,
  overall_score: 86,
  feedback: "",
  suggestion: "",
  raw_metrics: "{}",
  created_at: "2026-08-24T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.localStorage.setItem("shadowing.uiLocale", "zh-CN");
  api.getLanguagePreferences.mockResolvedValue({
    id: 1,
    ui_locale: "zh-CN",
    learning_language: "en",
    translation_language: "zh-CN",
    updated_at: "2026-08-24T00:00:00Z",
  });
  api.updateLanguagePreferences.mockResolvedValue({});
});

describe("RecorderPanel", () => {
  it("restores a scored recording as a real replayable comparison state", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);

    const { container } = render(
      <LanguageProvider>
        <RecorderPanel
          sentence={sentence}
          evaluation={evaluation}
          onEvaluated={() => undefined}
          onPlayReference={() => undefined}
        />
      </LanguageProvider>,
    );

    expect(await screen.findByText("录音完成")).toBeInTheDocument();
    expect(screen.getByText("00:04.18")).toBeInTheDocument();
    const compare = screen.getByRole("button", { name: /对比评分/ });
    expect(compare).toBeEnabled();

    const audio = container.querySelector("audio");
    expect(audio).toHaveAttribute("src", "http://api.test/api/recordings/9/audio");
    fireEvent.click(compare);
    expect(play).toHaveBeenCalledOnce();
  });
});
