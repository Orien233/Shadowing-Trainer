import { useEffect, useRef } from "react";
import { Check } from "@phosphor-icons/react";
import { useLanguage } from "../../i18n/LanguageContext";
import type { Sentence } from "../../types";

interface Props {
  sentences: Sentence[];
  currentSentenceId: number | null;
  evaluatedSentenceIds: Set<number>;
  onSelect: (sentenceId: number) => void;
}

export default function SentenceProgress({
  sentences,
  currentSentenceId,
  evaluatedSentenceIds,
  onSelect,
}: Props) {
  const { t } = useLanguage();
  const activeStepRef = useRef<HTMLButtonElement | null>(null);
  const currentIndex = sentences.findIndex((sentence) => sentence.id === currentSentenceId);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    if (!window.matchMedia("(max-width: 680px)").matches) return;

    activeStepRef.current?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      block: "nearest",
      inline: "center",
    });
  }, [currentSentenceId]);

  return (
    <div className="sentence-progress-bar">
      <div className="sentence-steps" aria-label={t("trainer.sentenceList")}>
        {sentences.map((sentence, index) => {
          const isCurrent = sentence.id === currentSentenceId;
          const isEvaluated = evaluatedSentenceIds.has(sentence.id);
          return (
            <div className="sentence-step-wrap" key={sentence.id}>
              {index > 0 && (
                <span
                  className={`sentence-step-connector ${index <= currentIndex ? "reached" : ""}`}
                  aria-hidden="true"
                />
              )}
              <button
                ref={isCurrent ? activeStepRef : undefined}
                type="button"
                className={`sentence-step ${isCurrent ? "active" : ""} ${isEvaluated ? "complete" : ""}`}
                aria-current={isCurrent ? "step" : undefined}
                aria-label={t("trainer.goToSentence", {
                  current: sentence.display_order,
                  total: sentences.length,
                })}
                title={sentence.source_text}
                onClick={() => onSelect(sentence.id)}
              >
                {isEvaluated && !isCurrent ? (
                  <Check size={13} weight="bold" aria-hidden="true" />
                ) : (
                  sentence.display_order
                )}
              </button>
            </div>
          );
        })}
      </div>
      <strong className="sentence-progress-total">
        {currentIndex >= 0
          ? t("trainer.compactProgress", { current: currentIndex + 1, total: sentences.length })
          : t("trainer.compactTotal", { total: sentences.length })}
      </strong>
    </div>
  );
}
