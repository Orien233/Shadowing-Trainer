import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getLanguagePreferences: vi.fn(),
  updateLanguagePreferences: vi.fn(),
}));

vi.mock("../lib/api", () => api);
import LanguageSelector from "../components/LanguageSelector";
import { LanguageProvider, useLanguage } from "./LanguageContext";

function CurrentLanguage() {
  const { learningLanguage, translationLanguage } = useLanguage();
  return <><output aria-label="current-learning-language">{learningLanguage}</output><output aria-label="current-translation-language">{translationLanguage}</output></>;
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
  api.updateLanguagePreferences.mockImplementation(async (payload) => ({
    id: 1,
    ...payload,
    updated_at: "2026-08-12T00:00:00Z",
  }));
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
    expect(screen.getByLabelText("current-translation-language")).toHaveTextContent("en");
    await waitFor(() => expect(window.localStorage.getItem("shadowing.learningLanguage")).toBe("ja"));
  });

  it("persists an independent translation language", async () => {
    render(
      <LanguageProvider>
        <LanguageSelector />
        <CurrentLanguage />
      </LanguageProvider>
    );

    fireEvent.change(screen.getByRole("combobox", { name: /Translation language/i }), {
      target: { value: "fr" },
    });

    expect(screen.getByLabelText("current-learning-language")).toHaveTextContent("en");
    expect(screen.getByLabelText("current-translation-language")).toHaveTextContent("fr");
    await waitFor(() => expect(window.localStorage.getItem("shadowing.translationLanguage")).toBe("fr"));
  });

  it("hydrates missing local preferences from the backend", async () => {
    window.localStorage.clear();
    api.getLanguagePreferences.mockResolvedValue({
      id: 1,
      ui_locale: "zh-CN",
      learning_language: "ja",
      translation_language: "fr",
      updated_at: "2026-08-12T00:00:00Z",
    });

    render(
      <LanguageProvider>
        <LanguageSelector />
        <CurrentLanguage />
      </LanguageProvider>
    );

    await waitFor(() => {
      expect(screen.getByLabelText("current-learning-language")).toHaveTextContent("ja");
      expect(screen.getByLabelText("current-translation-language")).toHaveTextContent("fr");
      expect(document.documentElement.lang).toBe("zh-CN");
    });
  });

  it("does not let delayed hydration overwrite a language selected during startup", async () => {
    window.localStorage.clear();
    let resolvePreferences: (value: {
      id: number;
      ui_locale: "en-US";
      learning_language: string;
      translation_language: string;
      updated_at: string;
    }) => void = () => undefined;
    api.getLanguagePreferences.mockImplementationOnce(() => new Promise((resolve) => {
      resolvePreferences = resolve;
    }));

    render(
      <LanguageProvider>
        <LanguageSelector />
        <CurrentLanguage />
      </LanguageProvider>
    );

    fireEvent.change(screen.getByRole("combobox", { name: /Learning language/i }), {
      target: { value: "ja" },
    });
    resolvePreferences({
      id: 1,
      ui_locale: "en-US",
      learning_language: "en",
      translation_language: "en",
      updated_at: "2026-08-12T00:00:00Z",
    });

    await waitFor(() => {
      expect(screen.getByLabelText("current-learning-language")).toHaveTextContent("ja");
    });
  });

  it("serializes preference writes and sends the most recent value after an in-flight write", async () => {
    let resolveFirstWrite: () => void = () => undefined;
    api.updateLanguagePreferences
      .mockImplementationOnce(() => new Promise<void>((resolve) => { resolveFirstWrite = resolve; }))
      .mockResolvedValueOnce({
        id: 1,
        ui_locale: "en-US",
        learning_language: "fr",
        translation_language: "en",
        updated_at: "2026-08-12T00:00:00Z",
      });

    render(
      <LanguageProvider>
        <LanguageSelector />
      </LanguageProvider>
    );

    fireEvent.change(screen.getByRole("combobox", { name: /Learning language/i }), {
      target: { value: "ja" },
    });
    await waitFor(() => expect(api.updateLanguagePreferences).toHaveBeenCalledTimes(1), { timeout: 1_000 });

    fireEvent.change(screen.getByRole("combobox", { name: /Learning language/i }), {
      target: { value: "fr" },
    });
    await new Promise((resolve) => window.setTimeout(resolve, 300));
    expect(api.updateLanguagePreferences).toHaveBeenCalledTimes(1);

    resolveFirstWrite();
    await waitFor(() => expect(api.updateLanguagePreferences).toHaveBeenCalledTimes(2));
    expect(api.updateLanguagePreferences).toHaveBeenLastCalledWith(expect.objectContaining({
      learning_language: "fr",
    }));
  });
});
