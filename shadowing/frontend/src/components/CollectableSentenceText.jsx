import { useMemo, useState } from "react";
import { useLanguage } from "../i18n/LanguageContext";
import { collectWord, WordCollectionApiError } from "../lib/api";
import {
  buildCollectedWordKey,
  cleanCollectableWordText,
  normalizeWordText,
  splitCollectableSegments,
  tokenizeSentenceText,
} from "../utils/sentenceTokenText.js";
import { getInsertionLabel } from "../utils/alignmentColors.js";
import { AlignmentTokenCore } from "./AlignmentToken.jsx";
import { getAlignmentTokenTitle } from "../utils/alignmentText.js";

const STATUS_PRIORITY = {
  deletion: 5,
  substitution: 4,
  minor: 3,
  insertion: 2,
  filler: 2,
  correct: 1,
  default: 0,
};

function isCJKLanguage(language) {
  return ["zh", "ja", "ko"].includes(String(language || "en").replace("_", "-").toLowerCase().split("-", 1)[0]);
}

function alignmentUnits(text, language) {
  const normalized = normalizeWordText(text);
  if (!normalized) return [];
  return isCJKLanguage(language) ? Array.from(normalized) : [normalized];
}

function chooseAlignmentToken(matches, displayToken) {
  if (!matches.length) return { ...displayToken, status: "default", severity: "default" };
  return matches.reduce((chosen, candidate) =>
    (STATUS_PRIORITY[candidate.status] ?? 0) > (STATUS_PRIORITY[chosen.status] ?? 0) ? candidate : chosen
  );
}

// Alignment reference tokens are a scoring projection, not a display model.
// Match their status to source-derived display tokens while preserving every
// character (including source whitespace and punctuation) from the transcript.
function attachAlignmentToSourceTokens(sourceTokens, alignmentTokens, language) {
  const remaining = Array.isArray(alignmentTokens) ? [...alignmentTokens] : [];
  return sourceTokens.map((displayToken) => {
    const matches = [];
    for (const unit of alignmentUnits(displayToken.text, language)) {
      const matchIndex = remaining.findIndex((token) => alignmentUnits(token.normalized || token.text, language).includes(unit));
      if (matchIndex >= 0) matches.push(remaining.splice(matchIndex, 1)[0]);
    }
    return { ...chooseAlignmentToken(matches, displayToken), text: displayToken.text, index: displayToken.index };
  });
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
  const { uiLocale, t } = useLanguage();
  const [pendingKeys, setPendingKeys] = useState(() => new Set());
  const rawSourceText = sourceText ?? "";
  const displayTokens = useMemo(
    () => attachAlignmentToSourceTokens(tokenizeSentenceText(rawSourceText, language), tokens, language),
    [language, rawSourceText, tokens]
  );

  async function handleCollect(wordText) {
    const cleanWordText = cleanCollectableWordText(wordText);
    const normalizedWord = normalizeWordText(cleanWordText);
    if (!normalizedWord || !materialId || !sentenceId) return;

    const key = buildCollectedWordKey(normalizedWord, language);
    if (collectedWordSet?.has(key)) {
      alert(t("wordCollection.alreadyCollected"));
      return;
    }
    if (pendingKeys.has(key)) return;

    setPendingKeys((prev) => new Set([...prev, key]));
    try {
      const collection = await collectWord({
        material_id: materialId,
        sentence_id: sentenceId,
        word_text: cleanWordText,
        language,
      });
      onCollected?.(collection);
    } catch (error) {
      if (
        error instanceof WordCollectionApiError &&
        (error.status === 409 || error.detail === "WORD_ALREADY_COLLECTED")
      ) {
        alert(t("wordCollection.alreadyCollected"));
        await onRefreshCollections?.();
        return;
      }
      alert(error instanceof Error ? error.message : t("wordCollection.collectFailed"));
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
    <div
      className="collectable-sentence"
      dir="auto"
      style={{ display: "block", overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}
    >
      {displayTokens.map((token) => {
        const segments = splitCollectableSegments(token.text);
        const wordSegmentIndexes = segments.reduce((indexes, segment, index) => {
          if (segment.type === "word") indexes.push(index);
          return indexes;
        }, []);
        const lastWordSegmentIndex = wordSegmentIndexes[wordSegmentIndexes.length - 1];
        const label = getInsertionLabel(token, uiLocale);

        return (
          <span key={`${token.index}-${token.text}`} className="collectable-token-wrap" title={getAlignmentTokenTitle(token, t)}>
            {segments.map((segment, segmentIndex) => {
              if (segment.type !== "word") {
                return <span key={`${segmentIndex}-${segment.text}`} className="alignment-token-punctuation">{segment.text}</span>;
              }

              const cleanWordText = cleanCollectableWordText(segment.text);
              const normalizedWord = normalizeWordText(cleanWordText);
              const key = buildCollectedWordKey(normalizedWord, language);
              const isCollectable = Boolean(normalizedWord);
              const isCollected = Boolean(collectedWordSet?.has(key));
              const isPending = pendingKeys.has(key);
              const coreProps = isCollectable ? {
                role: "button", tabIndex: 0,
                title: isCollected ? t("wordCollection.alreadyCollected") : t("wordCollection.collect"),
                onClick: () => void handleCollect(cleanWordText),
                onKeyDown: (event) => {
                  if (event.key !== "Enter" && event.key !== " ") return;
                  event.preventDefault();
                  void handleCollect(cleanWordText);
                },
              } : {};

              return (
                <AlignmentTokenCore key={`${segmentIndex}-${segment.text}`} token={token}
                  className={[isCollectable ? "collectable-word-core" : "", isCollected ? "collected" : "", isPending ? "pending" : ""].join(" ")}
                  coreProps={coreProps}>
                  <span>{cleanWordText}</span>
                  {segmentIndex === lastWordSegmentIndex && label && <span className="alignment-token-label">{label}</span>}
                </AlignmentTokenCore>
              );
            })}
          </span>
        );
      })}
    </div>
  );
}
