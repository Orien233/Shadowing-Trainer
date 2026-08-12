import { useLanguage } from "../i18n/LanguageContext";
import HighlightedSentence from "./HighlightedSentence.jsx";

function formatAccuracy(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

export default function WordAlignmentView({ alignment }) {
  const { t } = useLanguage();
  if (!alignment) return null;
  const summary = alignment.summary ?? {};

  return (
    <div className="word-alignment">
      <div className="word-alignment-header">
        <h4>{t("alignment.title")}</h4>
        <span className="muted">{t("alignment.wordAccuracy", { accuracy: formatAccuracy(summary.word_accuracy) })}</span>
      </div>
      <div className="word-alignment-section">
        <div className="word-alignment-title">{t("alignment.recognizedResult")}</div>
        <HighlightedSentence tokens={alignment.user_tokens ?? []} emptyText={t("alignment.noRecognizedWords")} />
      </div>
    </div>
  );
}
