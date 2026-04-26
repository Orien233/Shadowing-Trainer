const TOKEN_PATTERN = /\S+/g;
const EDGE_PUNCTUATION_PATTERN = /^([\p{P}]*)(.*?)([\p{P}]*)$/u;
const EDGE_PUNCTUATION = /^[\s!"#$%&()*+,\-./:;<=>?@[\\\]^_`{|}~'“”‘’]+|[\s!"#$%&()*+,\-./:;<=>?@[\\\]^_`{|}~'“”‘’]+$/g;
const WORD_CHAR_PATTERN = /[\p{L}\p{N}]/u;
const APOSTROPHES = new Set(["'", "’", "‘", "‛", "′"]);

function isWordChar(char) {
  return WORD_CHAR_PATTERN.test(char);
}

function isWordApostrophe(chars, index) {
  return (
    APOSTROPHES.has(chars[index]) &&
    index > 0 &&
    index < chars.length - 1 &&
    isWordChar(chars[index - 1]) &&
    isWordChar(chars[index + 1])
  );
}

export function splitDisplayText(text) {
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

export function normalizeWordText(wordText) {
  return cleanCollectableWordText(wordText).replace(/[’‘‛′]/g, "'").toLowerCase();
}

export function buildCollectedWordKey(normalizedWord, language) {
  return `${String(language || "en").trim().toLowerCase() || "en"}:${normalizedWord}`;
}

export function tokenizeSentenceText(sourceText) {
  const tokens = [];
  for (const match of String(sourceText ?? "").matchAll(TOKEN_PATTERN)) {
    tokens.push({
      index: tokens.length,
      text: match[0],
      status: "default",
      severity: "default",
    });
  }
  return tokens;
}

export function splitCollectableSegments(text) {
  const chars = Array.from(String(text ?? ""));
  const segments = [];
  let currentType = null;
  let currentText = "";

  function pushCurrent() {
    if (!currentText) return;
    segments.push({ type: currentType, text: currentText });
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

export function cleanCollectableWordText(wordText) {
  return splitCollectableSegments(String(wordText ?? "").replace(EDGE_PUNCTUATION, ""))
    .filter((segment) => segment.type === "word")
    .map((segment) => segment.text)
    .join("");
}
