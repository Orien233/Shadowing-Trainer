import { languageLabel } from "../../../i18n/catalog";
import { useLanguage } from "../../../i18n/LanguageContext";
import type { WordAlignment } from "../../../types";
import HighlightedSentence from "./HighlightedSentence";

function formatAccuracy(value: number | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

export default function WordAlignmentView({ alignment }: { alignment?: WordAlignment | null }) {
  const { uiLocale, t } = useLanguage();
  if (!alignment) return null;
  const summary = alignment.summary ?? {};
  const mode = alignment.alignment_mode ?? "word";
  const titleKey = mode === "unicode_character" ? "alignment.characterTitle" : mode === "unicode_word" ? "alignment.tokenTitle" : "alignment.title";
  const accuracyKey = mode === "unicode_character" ? "alignment.characterAccuracy" : mode === "unicode_word" ? "alignment.tokenAccuracy" : "alignment.wordAccuracy";
  const emptyKey = mode === "unicode_character" ? "alignment.noRecognizedCharacters" : mode === "unicode_word" ? "alignment.noRecognizedTokens" : "alignment.noRecognizedWords";

  return (
    <div className="word-alignment">
      <div className="word-alignment-header">
        <h4>{t(titleKey)}</h4>
        <span className="muted">{t(accuracyKey, { accuracy: formatAccuracy(summary.word_accuracy) })}</span>
      </div>
      {alignment.support_level && alignment.support_level !== "full" && (
        <p className="muted">{t(`alignment.support.${alignment.support_level}`, { language: languageLabel(alignment.language ?? "", uiLocale) })}</p>
      )}
      <div className="word-alignment-section">
        <div className="word-alignment-title">{t("alignment.recognizedResult")}</div>
        <HighlightedSentence tokens={alignment.user_tokens ?? []} emptyText={t(emptyKey)} />
      </div>
    </div>
  );
}
