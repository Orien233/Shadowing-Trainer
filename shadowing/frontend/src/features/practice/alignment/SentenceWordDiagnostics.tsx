import { useLanguage } from "../../../i18n/LanguageContext";
import type { AlignmentToken } from "../../../types";

function qualityKey(token: AlignmentToken) {
  if (token.status === "correct") return "alignment.quality.correct";
  if (token.status === "minor" || token.status === "insertion" || token.status === "filler") {
    return "alignment.quality.minor";
  }
  if (token.status === "substitution" || token.status === "deletion") return "alignment.quality.major";
  return "alignment.quality.pending";
}

function qualityClass(token: AlignmentToken) {
  if (token.status === "correct") return "correct";
  if (token.status === "minor" || token.status === "insertion" || token.status === "filler") return "minor";
  if (token.status === "substitution" || token.status === "deletion") return "major";
  return "pending";
}

export default function SentenceWordDiagnostics({ tokens }: { tokens: AlignmentToken[] }) {
  const { t } = useLanguage();
  if (!tokens.length) return null;

  return (
    <div className="sentence-word-diagnostics" aria-label={t("alignment.wordQuality")}>
      {tokens.map((token) => (
        <div className={`sentence-word-diagnostic ${qualityClass(token)}`} key={`${token.index}-${token.text}`}>
          <strong>{token.text}</strong>
          <span>{t(qualityKey(token))}</span>
        </div>
      ))}
    </div>
  );
}
