import { useMemo, useState } from "react";
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
    () => (hasAlignmentTokens ? tokens : tokenizeSentenceText(rawSourceText)),
    [hasAlignmentTokens, rawSourceText, tokens]
  );

  async function handleCollect(wordText) {
    const cleanWordText = cleanCollectableWordText(wordText);
    const normalizedWord = normalizeWordText(cleanWordText);
    if (!normalizedWord || !materialId || !sentenceId) {
      return;
    }

    const key = buildCollectedWordKey(normalizedWord, language);
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
        word_text: cleanWordText,
        language,
      });
      onCollected?.(collection);
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
        const segments = splitCollectableSegments(token.text);
        const wordSegmentIndexes = segments.reduce((indexes, segment, index) => {
          if (segment.type === "word") indexes.push(index);
          return indexes;
        }, []);
        const lastWordSegmentIndex = wordSegmentIndexes[wordSegmentIndexes.length - 1];
        const label = getInsertionLabel(token);

        return (
          <span
            key={`${token.index}-${token.text}`}
            className="collectable-token-wrap"
            title={token.note ?? ""}
          >
            {segments.map((segment, segmentIndex) => {
              if (segment.type !== "word") {
                return (
                  <span
                    key={`${segmentIndex}-${segment.text}`}
                    className="alignment-token-punctuation"
                  >
                    {segment.text}
                  </span>
                );
              }

              const cleanWordText = cleanCollectableWordText(segment.text);
              const normalizedWord = normalizeWordText(cleanWordText);
              const key = buildCollectedWordKey(normalizedWord, language);
              const isCollectable = Boolean(normalizedWord);
              const isCollected = Boolean(collectedWordSet?.has(key));
              const isPending = pendingKeys.has(key);
              const coreProps = isCollectable
                ? {
                    role: "button",
                    tabIndex: 0,
                    title: isCollected ? "已经收藏过了" : "点击收藏",
                    onClick: () => {
                      void handleCollect(cleanWordText);
                    },
                    onKeyDown: (event) => {
                      if (event.key !== "Enter" && event.key !== " ") return;
                      event.preventDefault();
                      void handleCollect(cleanWordText);
                    },
                  }
                : {};

              return (
                <AlignmentTokenCore
                  key={`${segmentIndex}-${segment.text}`}
                  token={token}
                  className={[
                    isCollectable ? "collectable-word-core" : "",
                    isCollected ? "collected" : "",
                    isPending ? "pending" : "",
                  ].join(" ")}
                  coreProps={coreProps}
                >
                  <span>{cleanWordText}</span>
                  {segmentIndex === lastWordSegmentIndex && label && (
                    <span className="alignment-token-label">{label}</span>
                  )}
                </AlignmentTokenCore>
              );
            })}
          </span>
        );
      })}
    </div>
  );
}
