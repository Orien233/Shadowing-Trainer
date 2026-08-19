import { describe, expect, it } from "vitest";

import { languageLabel, LEARNING_LANGUAGES, UI_LOCALES } from "./catalog";

describe("shared language catalog", () => {
  it("exposes the same complete labels to both UI locales", () => {
    expect(UI_LOCALES).toEqual(["zh-CN", "en-US"]);
    expect(LEARNING_LANGUAGES).toHaveLength(12);
    expect(LEARNING_LANGUAGES.every((item) => (
      Boolean(item.labels["zh-CN"]) && Boolean(item.labels["en-US"])
    ))).toBe(true);
    expect(languageLabel("ja", "zh-CN")).toBe("日语 · 日本語");
  });
});
