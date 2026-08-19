import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getLanguagePreferences: vi.fn(),
  updateLanguagePreferences: vi.fn(),
}));

vi.mock("../../../lib/api", () => api);

import { LanguageProvider } from "../../../i18n/LanguageContext";
import WordAlignmentView from "./WordAlignmentView";

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem("shadowing.uiLocale", "en-US");
  api.getLanguagePreferences.mockResolvedValue({
    id: 1,
    ui_locale: "en-US",
    learning_language: "ja",
    translation_language: "en",
    updated_at: "2026-08-12T00:00:00Z",
  });
  api.updateLanguagePreferences.mockResolvedValue({});
});

it("labels limited CJK alignment as character accuracy rather than word accuracy", () => {
  render(
    <LanguageProvider>
      <WordAlignmentView alignment={{
        language: "ja",
        alignment_mode: "unicode_character",
        support_level: "limited",
        reference_tokens: [],
        user_tokens: [],
        summary: { word_accuracy: 0.75, correct_count: 0, substitution_count: 0, deletion_count: 0, insertion_count: 0, minor_error_count: 0 },
      }} />
    </LanguageProvider>,
  );

  expect(screen.getByText("Character alignment")).toBeInTheDocument();
  expect(screen.getByText("Character accuracy 75%")).toBeInTheDocument();
  expect(screen.getByText(/without English morphology rules/i)).toBeInTheDocument();
  expect(screen.queryByText(/Word accuracy/i)).not.toBeInTheDocument();
});
