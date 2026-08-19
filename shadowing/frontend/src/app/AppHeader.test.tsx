import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LanguageProvider } from "../i18n/LanguageContext";
import AppHeader from "./AppHeader";

vi.mock("../lib/api", () => ({
  getLanguagePreferences: vi.fn().mockImplementation(() => new Promise(() => undefined)),
  updateLanguagePreferences: vi.fn().mockResolvedValue({}),
}));

function renderHeader() {
  return render(
    <LanguageProvider>
      <AppHeader
        activePanel="practice"
        materialTitle="Focused practice"
        currentSentence={4}
        sentenceCount={12}
        onPanelChange={() => undefined}
      />
    </LanguageProvider>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem("shadowing.uiLocale", "en-US");
  window.localStorage.setItem("shadowing.learningLanguage", "en");
  window.localStorage.setItem("shadowing.translationLanguage", "zh-CN");
});

describe("AppHeader popovers", () => {
  it("focuses the language controls and returns focus after Escape", () => {
    renderHeader();
    const trigger = screen.getByRole("button", { name: "EN · 中" });

    fireEvent.click(trigger);
    expect(screen.getByRole("combobox", { name: /^Interface language/ })).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Language preferences" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("makes the help dialog keyboard focusable", () => {
    renderHeader();
    const trigger = screen.getByRole("button", { name: "Help" });

    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Help" });
    expect(dialog).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(trigger).toHaveFocus();
  });
});
