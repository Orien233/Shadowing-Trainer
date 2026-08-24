import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getLanguagePreferences: vi.fn(),
  updateLanguagePreferences: vi.fn(),
}));

vi.mock("../../../lib/api", () => api);

import { LanguageProvider } from "../../../i18n/LanguageContext";
import type { Evaluation } from "../../../types";
import AlignmentToken from "../alignment/AlignmentToken";
import EvaluationPanel from "./EvaluationPanel";

function evaluation(overrides: Partial<Evaluation> = {}): Evaluation {
  return {
    id: 1,
    recording_id: 1,
    overall_score: 80,
    completeness_score: 80,
    fluency_score: 80,
    sync_score: 80,
    pronunciation_score: 80,
    feedback: "Legacy backend feedback",
    suggestion: "Legacy backend suggestion",
    raw_metrics: "{}",
    created_at: "2026-08-12T00:00:00Z",
    ...overrides,
  };
}

function renderWithLocale(ui: ReactNode, locale: "en-US" | "zh-CN") {
  window.localStorage.clear();
  window.localStorage.setItem("shadowing.uiLocale", locale);
  api.getLanguagePreferences.mockResolvedValue({
    id: 1,
    ui_locale: locale,
    learning_language: "en",
    translation_language: "en",
    updated_at: "2026-08-12T00:00:00Z",
  });
  api.updateLanguagePreferences.mockResolvedValue({});
  return render(<LanguageProvider>{ui}</LanguageProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("evaluation localization", () => {
  it("uses stable raw-metric tags instead of stored English feedback", () => {
    renderWithLocale(
      <EvaluationPanel evaluation={evaluation({
        raw_metrics: JSON.stringify({ tags: ["content_mismatch", "pace_too_slow"] }),
      })} />,
      "en-US",
    );

    expect(screen.getByText(/Some key content from the target sentence/i)).toBeInTheDocument();
    expect(screen.getByText(/pace is a little slow/i)).toBeInTheDocument();
    expect(screen.queryByText("Legacy backend feedback")).not.toBeInTheDocument();
    expect(screen.getByText(/Repeat once more slowly/i)).toBeInTheDocument();
  });

  it("localizes tag-backed feedback in Chinese", () => {
    renderWithLocale(
      <EvaluationPanel evaluation={evaluation({ raw_metrics: JSON.stringify({ tags: ["too_many_pauses"] }) })} />,
      "zh-CN",
    );

    expect(screen.getByText("停顿较多，影响了语句的连贯性。")).toBeInTheDocument();
    expect(screen.getByText("缩短短语之间的停顿，并保持气息连续。")).toBeInTheDocument();
  });

  it("keeps stored feedback for historical rows without tags", () => {
    renderWithLocale(<EvaluationPanel evaluation={evaluation()} />, "en-US");

    expect(screen.getByText("Legacy backend feedback")).toBeInTheDocument();
    expect(screen.getByText("Legacy backend suggestion")).toBeInTheDocument();
  });

  it("uses safe localized generic copy for future unknown tags", () => {
    renderWithLocale(
      <EvaluationPanel evaluation={evaluation({ raw_metrics: JSON.stringify({ tags: ["future_metric"] }) })} />,
      "en-US",
    );

    expect(screen.getByText(/remain unstable across content or rhythm/i)).toBeInTheDocument();
    expect(screen.queryByText(/generally aligned/i)).not.toBeInTheDocument();
  });

  it("uses localized token status text instead of the backend note", () => {
    renderWithLocale(
      <AlignmentToken token={{
        index: 0,
        text: "um",
        normalized: "um",
        status: "filler",
        severity: "default",
        matched_token_index: null,
        note: "Filler word not present in the reference.",
        insertion_type: "filler",
      }}>{({ core }: { core: string }) => <span>{core}</span>}</AlignmentToken>,
      "zh-CN",
    );

    const wrapper = screen.getByText("um").closest(".alignment-token-wrap");
    expect(wrapper).toHaveAttribute("title", "识别到未出现在参考文本中的语气词。");
    expect(wrapper).not.toHaveAttribute("title", "Filler word not present in the reference.");
  });

  it("turns real alignment issues into immediate replay and retry actions", () => {
    const onReplayReference = vi.fn();
    const onRetrySentence = vi.fn();
    renderWithLocale(
      <EvaluationPanel
        evaluation={evaluation({
          word_alignment: {
            language: "en",
            alignment_mode: "word",
            support_level: "full",
            token_unit: "word",
            reference_tokens: [{
              index: 0,
              text: "compound",
              normalized: "compound",
              status: "minor",
              severity: "minor",
              matched_token_index: 0,
            }],
            user_tokens: [],
            summary: {
              correct_count: 0,
              substitution_count: 0,
              deletion_count: 0,
              insertion_count: 0,
              minor_error_count: 1,
              word_accuracy: 0.84,
            },
          },
        })}
        onReplayReference={onReplayReference}
        onRetrySentence={onRetrySentence}
      />,
      "zh-CN",
    );

    expect(screen.getByText("compound")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "听原句" }));
    fireEvent.click(screen.getByRole("button", { name: "重练本句" }));
    expect(onReplayReference).toHaveBeenCalledOnce();
    expect(onRetrySentence).toHaveBeenCalledOnce();
  });
});
