import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import LanguageSelector from "../components/LanguageSelector";
import { LanguageProvider, useLanguage } from "./LanguageContext";

function CurrentLanguage() {
  const { learningLanguage } = useLanguage();
  return <output aria-label="current-learning-language">{learningLanguage}</output>;
}

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem("shadowing.uiLocale", "en-US");
});

describe("language preferences", () => {
  it("switches UI messages immediately and persists the selected locale", async () => {
    render(
      <LanguageProvider>
        <LanguageSelector />
      </LanguageProvider>
    );

    fireEvent.change(screen.getByRole("combobox", { name: /Interface language/i }), {
      target: { value: "zh-CN" },
    });

    expect(screen.getByText("界面语言")).toBeInTheDocument();
    await waitFor(() => {
      expect(window.localStorage.getItem("shadowing.uiLocale")).toBe("zh-CN");
      expect(document.documentElement.lang).toBe("zh-CN");
    });
  });

  it("keeps the learning language independent from the UI locale", async () => {
    render(
      <LanguageProvider>
        <LanguageSelector />
        <CurrentLanguage />
      </LanguageProvider>
    );

    fireEvent.change(screen.getByRole("combobox", { name: /Learning language/i }), {
      target: { value: "ja" },
    });

    expect(screen.getByLabelText("current-learning-language")).toHaveTextContent("ja");
    expect(screen.getByRole("combobox", { name: /Interface language/i })).toHaveValue("en-US");
    await waitFor(() => expect(window.localStorage.getItem("shadowing.learningLanguage")).toBe("ja"));
  });
});
