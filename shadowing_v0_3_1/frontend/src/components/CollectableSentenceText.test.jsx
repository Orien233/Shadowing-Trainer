import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  collectWord: vi.fn(),
  getLanguagePreferences: vi.fn(),
  updateLanguagePreferences: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  ...api,
  WordCollectionApiError: class WordCollectionApiError extends Error {},
}));

import CollectableSentenceText from "./CollectableSentenceText.jsx";
import { LanguageProvider } from "../i18n/LanguageContext";

function renderSentence(props) {
  return render(
    <LanguageProvider>
      <CollectableSentenceText materialId={1} sentenceId={2} collectedWordSet={new Set()} {...props} />
    </LanguageProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.localStorage.setItem("shadowing.uiLocale", "en-US");
  api.getLanguagePreferences.mockResolvedValue({
    id: 1,
    ui_locale: "en-US",
    learning_language: "en",
    translation_language: "en",
    updated_at: "2026-08-12T00:00:00Z",
  });
  api.updateLanguagePreferences.mockResolvedValue({});
  api.collectWord.mockResolvedValue({ id: 1 });
});

it("keeps source spaces and punctuation after scoring while retaining the mapped highlight", () => {
  const { container } = renderSentence({
    sourceText: "Hello,  world!",
    language: "en",
    tokens: [
      { index: 0, text: "Hello", normalized: "hello", status: "correct", severity: "correct" },
      { index: 1, text: "world", normalized: "world", status: "deletion", severity: "major" },
    ],
  });

  const sentence = container.querySelector(".collectable-sentence");
  expect(sentence?.textContent).toBe("Hello,  world!");
  expect(sentence).toHaveStyle({ display: "block", whiteSpace: "pre-wrap" });
  expect(screen.getByRole("button", { name: "world" })).toHaveClass("line-through");
});

it("uses CJK display-word units for collection after character-level scoring", async () => {
  const { container } = renderSentence({
    sourceText: "私は学生です。",
    language: "ja",
    tokens: [
      { index: 0, text: "私", normalized: "私", status: "correct", severity: "correct" },
      { index: 1, text: "は", normalized: "は", status: "correct", severity: "correct" },
      { index: 2, text: "学", normalized: "学", status: "deletion", severity: "major" },
      { index: 3, text: "生", normalized: "生", status: "correct", severity: "correct" },
      { index: 4, text: "で", normalized: "で", status: "correct", severity: "correct" },
      { index: 5, text: "す", normalized: "す", status: "correct", severity: "correct" },
    ],
  });

  const sentence = container.querySelector(".collectable-sentence");
  expect(sentence?.textContent).toBe("私は学生です。");
  expect(sentence).toHaveStyle({ display: "block", whiteSpace: "pre-wrap" });
  const word = screen.getByRole("button", { name: "学生" });
  expect(word).toHaveClass("line-through");
  fireEvent.click(word);

  expect(api.collectWord).toHaveBeenCalledWith(expect.objectContaining({
    word_text: "学生",
    language: "ja",
  }));
});
