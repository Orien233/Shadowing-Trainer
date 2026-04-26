import { useMemo, useState } from "react";
import { collectWord, WordCollectionApiError } from "../lib/api";
import { getAlignmentTokenClass, getInsertionLabel } from "../utils/alignmentColors.js";

const TOKEN_PATTERN = /\S+/g;
const EDGE_PUNCTUATION_PATTERN = /^([\p{P}]*)(.*?)([\p{P}]*)$/u;
const EDGE_PUNCTUATION = /^[\s!"#$%&()*+,\-./:;<=>?@[\\\]^_`{|}~'“”‘’]+|[\s!"#$%&()*+,\-./:;<=>?@[\\\]^_`{|}~'“”‘’]+$/g;

export function normalizeWordText(wordText) {
  return String(wordText ?? "").trim().toLowerCase().replace(EDGE_PUNCTUATION, "");
}

function collectedKey(normalizedWord, language) {
  return `${String(language || "en").trim().toLowerCase() || "en"}:${normalizedWord}`;
}

function tokenizeSourceText(sourceText) {
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

function splitDisplayText(text) {
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

export default function CollectableSentenceText({
  sourceText,
  tokens,
  materialId,
  sentenceId,
  language = "en",
  collectedWordSet,
  onCollected,
  onRefreshCollections,
}) {
  const [pendingKeys, setPendingKeys] = useState(() => new Set());
  const rawSourceText = sourceText ?? "";
  const hasAlignmentTokens = Array.isArray(tokens) && tokens.length > 0;
  const displayTokens = useMemo(
    () => (hasAlignmentTokens ? tokens : tokenizeSourceText(rawSourceText)),
    [hasAlignmentTokens, rawSourceText, tokens]
  );

  async function handleCollect(token) {
    const normalizedWord = normalizeWordText(token.text);
    if (!normalizedWord || !materialId || !sentenceId) {
      return;
    }

    const key = collectedKey(normalizedWord, language);
    if (collectedWordSet?.has(key)) {
      alert("已经收藏过了");
      return;
    }
    if (pendingKeys.has(key)) {
      return;
    }

    setPendingKeys((prev) => new Set([...prev, key]));
    try {
      const collection = await collectWord({
        material_id: materialId,
        sentence_id: sentenceId,
        word_text: token.text,
        language,
      });
      onCollected?.(collection);
      alert("已收藏");
    } catch (error) {
      if (
        error instanceof WordCollectionApiError &&
        (error.status === 409 || error.detail === "WORD_ALREADY_COLLECTED")
      ) {
        alert("已经收藏过了");
        await onRefreshCollections?.();
        return;
      }
      alert(error instanceof Error ? error.message : "收藏失败");
    } finally {
      setPendingKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  }

  if (!displayTokens.length) {
    return <span className="muted alignment-empty">{rawSourceText}</span>;
  }

  return (
    <div className="collectable-sentence">
      {displayTokens.map((token) => {
        const { leading, core, trailing } = splitDisplayText(token.text);
        const normalizedWord = normalizeWordText(token.text);
        const key = collectedKey(normalizedWord, language);
        const isCollectable = Boolean(normalizedWord);
        const isCollected = Boolean(collectedWordSet?.has(key));
        const isPending = pendingKeys.has(key);
        const label = getInsertionLabel(token);
        const tokenClass = hasAlignmentTokens ? getAlignmentTokenClass(token) : "border-transparent";

        return (
          <span key={`${token.index}-${token.text}`} className="collectable-token-wrap" title={token.note ?? ""}>
            {leading && <span className="alignment-token-punctuation">{leading}</span>}
            {isCollectable ? (
              <span
                role="button"
                tabIndex={0}
                className={[
                  tokenClass,
                  "collectable-word-core",
                  isCollected ? "collected" : "",
                  isPending ? "pending" : "",
                ].join(" ")}
                title={isCollected ? "已经收藏过了" : "点击收藏"}
                onClick={() => {
                  void handleCollect(token);
                }}
                onKeyDown={(event) => {
                  if (event.key !== "Enter" && event.key !== " ") return;
                  event.preventDefault();
                  void handleCollect(token);
                }}
              >
                <span>{core}</span>
                {label && <span className="alignment-token-label">{label}</span>}
              </span>
            ) : (
              <span>{core}</span>
            )}
            {trailing && <span className="alignment-token-punctuation">{trailing}</span>}
          </span>
        );
      })}
    </div>
  );
}
