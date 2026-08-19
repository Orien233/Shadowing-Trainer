import { expect, it } from "vitest";

import { cleanCollectableWordText, normalizeWordText, tokenizeSentenceText } from "./sentenceTokenText";

it("segments Japanese text into collectable units instead of one whitespace token", () => {
  const tokens = tokenizeSentenceText("私は学生です。", "ja");

  expect(tokens.length).toBeGreaterThan(1);
  expect(tokens.some((token: { text: string }) => token.text.includes("学生"))).toBe(true);
  expect(tokens.map((token: { text: string }) => token.text).join("")).toBe("私は学生です。");
});

it("preserves meaningful Arabic combining marks in a collected word", () => {
  expect(cleanCollectableWordText("قَلْب")).toBe("قَلْب");
});

it("uses a Unicode-aware collection key compatible with backend casefolding", () => {
  expect(normalizeWordText("Straße")).toBe("strasse");
  expect(normalizeWordText("ΟΣ")).toBe("οσ");
});
