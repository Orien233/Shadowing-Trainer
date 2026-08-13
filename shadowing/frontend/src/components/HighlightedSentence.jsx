import { useLanguage } from "../i18n/LanguageContext";
import AlignmentToken from "./AlignmentToken.jsx";

/**
 * @param {{ tokens?: Array<any>, emptyText?: string }} props
 */
export default function HighlightedSentence({ tokens = [], emptyText }) {
  const { t } = useLanguage();
  if (!tokens.length) return <p className="muted alignment-empty">{emptyText ?? t("alignment.noWords")}</p>;

  return (
    <div className="highlighted-sentence" dir="auto">
      {tokens.map((token) => <AlignmentToken key={`${token.index}-${token.text}`} token={token} />)}
    </div>
  );
}
