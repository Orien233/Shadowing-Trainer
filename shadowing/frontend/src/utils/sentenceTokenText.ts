import type { AlignmentToken } from "../types";

export interface DisplayTextParts { leading: string; core: string; trailing: string; }
export interface CollectableSegment { type: "word" | "punctuation"; text: string; }

const DISPLAY_TOKEN_PATTERN = /\S+|\s+/g;
const EDGE_PUNCTUATION_PATTERN = /^([\p{P}]*)(.*?)([\p{P}]*)$/u;
const EDGE_PUNCTUATION = /^[\s!"#$%&()*+,\-./:;<=>?@[\\\]^_`{|}~'“”‘’]+|[\s!"#$%&()*+,\-./:;<=>?@[\\\]^_`{|}~'“”‘’]+$/g;
const WORD_CHAR_PATTERN = /[\p{L}\p{N}\p{M}]/u;
const APOSTROPHES = new Set(["'", "’", "‘", "‛", "′"]);

function isWordChar(char: string) {
  return WORD_CHAR_PATTERN.test(char);
}

function isWordApostrophe(chars: string[], index: number) {
  return (
    APOSTROPHES.has(chars[index]) &&
    index > 0 &&
    index < chars.length - 1 &&
    isWordChar(chars[index - 1]) &&
    isWordChar(chars[index + 1])
  );
}

export function splitDisplayText(text: unknown): DisplayTextParts {
  const displayText = String(text ?? "");
  const match = displayText.match(EDGE_PUNCTUATION_PATTERN);
  if (!match) {
    return { leading: "", core: displayText, trailing: "" };
  }

  const [, leading, core, trailing] = match;
  if (!core) {
    return { leading: "", core: displayText, trailing: "" };
  }

  return { leading, core, trailing };
}

export function normalizeWordText(wordText: unknown): string {
  return cleanCollectableWordText(wordText)
    .normalize("NFKC")
    .replace(/[’‘‛′]/g, "'")
    .toLocaleLowerCase("und")
    .replace(/ß/g, "ss")
    .replace(/ς/g, "σ");
}

export function buildCollectedWordKey(normalizedWord: string, language?: string): string {
  return `${String(language || "en").trim().toLowerCase() || "en"}:${normalizedWord}`;
}

export function tokenizeSentenceText(sourceText: unknown, language = "en"): AlignmentToken[] {
  const value = String(sourceText ?? "");
  const primaryLanguage = String(language || "en").replace("_", "-").toLowerCase().split("-", 1)[0];
  type SegmenterConstructor = new (locale?: string | string[], options?: { granularity?: "grapheme" | "word" | "sentence" }) => { segment: (input: string) => Iterable<{ segment: string; isWordLike?: boolean }> };
  const Segmenter = (Intl as typeof Intl & { Segmenter?: SegmenterConstructor }).Segmenter;
  if (["zh", "ja", "ko"].includes(primaryLanguage) && typeof Segmenter === "function") {
    const tokens = [];
    const segmenter = new Segmenter(language, { granularity: "word" });
    for (const segment of segmenter.segment(value)) {
      if (segment.isWordLike) {
        tokens.push({
          index: tokens.length,
          text: segment.segment,
          status: "default",
          severity: "default",
        });
      } else if (tokens.length) {
        // Preserve punctuation and intentional spacing with the preceding
        // lexical segment while keeping the collectable core separate.
        tokens[tokens.length - 1].text += segment.segment;
      } else if (segment.segment.trim()) {
        tokens.push({
          index: tokens.length,
          text: segment.segment,
          status: "default",
          severity: "default",
        });
      }
    }
    return tokens;
  }

  const tokens = [];
  // Keep whitespace as display tokens.  Sentence text is the authoritative
  // transcript, so rendering must not depend on ASR alignment tokenization.
  for (const match of value.matchAll(DISPLAY_TOKEN_PATTERN)) {
    tokens.push({
      index: tokens.length,
      text: match[0],
      status: "default",
      severity: "default",
    });
  }
  return tokens;
}

export function splitCollectableSegments(text: unknown): CollectableSegment[] {
  const chars = Array.from(String(text ?? ""));
  const segments: CollectableSegment[] = [];
  let currentType: CollectableSegment["type"] | null = null;
  let currentText = "";

  function pushCurrent() {
    if (!currentText) return;
    segments.push({ type: currentType as CollectableSegment["type"], text: currentText });
    currentType = null;
    currentText = "";
  }

  chars.forEach((char, index) => {
    const nextType = isWordChar(char) || isWordApostrophe(chars, index) ? "word" : "punctuation";
    if (currentType !== nextType) {
      pushCurrent();
      currentType = nextType;
    }
    currentText += char;
  });
  pushCurrent();

  return segments;
}

export function cleanCollectableWordText(wordText: unknown): string {
  return splitCollectableSegments(String(wordText ?? "").replace(EDGE_PUNCTUATION, ""))
    .filter((segment) => segment.type === "word")
    .map((segment) => segment.text)
    .join("");
}
