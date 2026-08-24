import { Microphone, Play } from "@phosphor-icons/react";
import { languageLabel } from "../../../i18n/catalog";
import { useLanguage } from "../../../i18n/LanguageContext";
import type { AlignmentToken, WordAlignment } from "../../../types";
import { getAlignmentTokenTitle } from "../../../utils/alignmentText";
import HighlightedSentence from "./HighlightedSentence";

function formatAccuracy(value: number | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

function isIssue(token: AlignmentToken) {
  return Boolean(token.status && !["correct", "default"].includes(token.status));
}

export default function WordAlignmentView({
  alignment,
  onReplayReference,
  onRetrySentence,
}: {
  alignment?: WordAlignment | null;
  onReplayReference?: () => void;
  onRetrySentence?: () => void;
}) {
  const { uiLocale, t } = useLanguage();
  if (!alignment) return null;
  const summary = alignment.summary ?? {};
  const mode = alignment.alignment_mode ?? "word";
  const titleKey = mode === "unicode_character" ? "alignment.characterTitle" : mode === "unicode_word" ? "alignment.tokenTitle" : "alignment.title";
  const accuracyKey = mode === "unicode_character" ? "alignment.characterAccuracy" : mode === "unicode_word" ? "alignment.tokenAccuracy" : "alignment.wordAccuracy";
  const emptyKey = mode === "unicode_character" ? "alignment.noRecognizedCharacters" : mode === "unicode_word" ? "alignment.noRecognizedTokens" : "alignment.noRecognizedWords";
  const issues = (alignment.reference_tokens ?? []).filter(isIssue);

  return (
    <div className="word-alignment">
      <div className="word-alignment-header">
        <h4>{t(titleKey)}</h4>
        <span className="muted">{t(accuracyKey, { accuracy: formatAccuracy(summary.word_accuracy) })}</span>
      </div>
      {alignment.support_level && alignment.support_level !== "full" && (
        <p className="muted">{t(`alignment.support.${alignment.support_level}`, { language: languageLabel(alignment.language ?? "", uiLocale) })}</p>
      )}
      {issues.length ? (
        <ol className="alignment-issue-list">
          {issues.map((token, index) => (
            <li className={`alignment-issue-row issue-${token.status ?? "default"}`} key={`${token.index}-${token.text}`}>
              <span className="alignment-issue-index" aria-hidden="true">{index + 1}</span>
              <div className="alignment-issue-copy">
                <strong>{token.text}</strong>
                <span>{getAlignmentTokenTitle(token, t)}</span>
              </div>
              <div className="alignment-issue-actions">
                {onReplayReference && (
                  <button type="button" className="issue-action" onClick={onReplayReference}>
                    <Play size={15} weight="fill" aria-hidden="true" />
                    {t("alignment.listenReference")}
                  </button>
                )}
                {onRetrySentence && (
                  <button type="button" className="issue-action" onClick={onRetrySentence}>
                    <Microphone size={16} weight="regular" aria-hidden="true" />
                    {t("alignment.retrySentence")}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <div className="word-alignment-section">
          <div className="word-alignment-title">{t("alignment.recognizedResult")}</div>
          <HighlightedSentence tokens={alignment.user_tokens ?? []} emptyText={t(emptyKey)} />
        </div>
      )}
    </div>
  );
}
