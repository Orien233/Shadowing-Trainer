import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LanguageProvider } from "../../i18n/LanguageContext";
import type { Sentence } from "../../types";
import SentenceProgress from "./SentenceProgress";

const sentences: Sentence[] = [1, 2, 3].map((displayOrder) => ({
  id: displayOrder,
  material_id: 10,
  display_order: displayOrder,
  start_time: displayOrder - 1,
  end_time: displayOrder,
  original_start_time: null,
  original_end_time: null,
  clip_audio_path: null,
  clip_duration: 1,
  source_text: `Sentence ${displayOrder}`,
  translation: null,
  created_at: "2026-08-20T00:00:00Z",
}));

describe("SentenceProgress", () => {
  it("exposes the current and evaluated sentence states", () => {
    render(
      <LanguageProvider>
        <SentenceProgress
          sentences={sentences}
          currentSentenceId={2}
          evaluatedSentenceIds={new Set([1])}
          onSelect={() => undefined}
        />
      </LanguageProvider>
    );

    expect(screen.getByRole("button", { name: "Go to sentence 2 of 3" })).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("button", { name: "Go to sentence 1 of 3" })).toHaveClass("complete");
    expect(screen.getByText("Sentence 2 / 3")).toBeInTheDocument();
  });

  it("selects a sentence from the progress strip", () => {
    const onSelect = vi.fn();
    render(
      <LanguageProvider>
        <SentenceProgress
          sentences={sentences}
          currentSentenceId={1}
          evaluatedSentenceIds={new Set()}
          onSelect={onSelect}
        />
      </LanguageProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "Go to sentence 3 of 3" }));
    expect(onSelect).toHaveBeenCalledWith(3);
  });
});
