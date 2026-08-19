import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  deleteWordCollection: vi.fn(),
  getLanguagePreferences: vi.fn(),
  updateLanguagePreferences: vi.fn(),
}));

vi.mock("../../lib/api", () => api);

import { LanguageProvider } from "../../i18n/LanguageContext";
import WordCollectionPanel from "./WordCollectionPanel";

const collection = {
  id: 7,
  material_id: 3,
  sentence_id: 4,
  word_text: "compound",
  normalized_word: "compound",
  language: "en",
  translation: "复利增长",
  source_type: "sentence",
  note: null,
  created_at: "2026-08-20T00:00:00Z",
  updated_at: "2026-08-20T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.setItem("shadowing.uiLocale", "en-US");
  api.getLanguagePreferences.mockResolvedValue({
    id: 1,
    ui_locale: "en-US",
    learning_language: "en",
    translation_language: "zh-CN",
    updated_at: "2026-08-20T00:00:00Z",
  });
  api.updateLanguagePreferences.mockResolvedValue({});
  api.deleteWordCollection.mockResolvedValue(undefined);
});

describe("WordCollectionPanel", () => {
  it("uses an explicit remove control for a collected word", async () => {
    const onDeleted = vi.fn();
    render(
      <LanguageProvider>
        <WordCollectionPanel collections={[collection]} onDeleted={onDeleted} />
      </LanguageProvider>
    );

    expect(screen.getByText("compound")).toBeInTheDocument();
    expect(screen.getByText("复利增长")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove compound" }));

    await waitFor(() => expect(api.deleteWordCollection).toHaveBeenCalledWith(7));
    expect(onDeleted).toHaveBeenCalledWith(7);
  });
});
