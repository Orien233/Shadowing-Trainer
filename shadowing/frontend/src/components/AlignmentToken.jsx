import { getAlignmentTokenClass, getInsertionLabel } from "../utils/alignmentColors.js";
import { useLanguage } from "../i18n/LanguageContext";
import { getAlignmentTokenTitle } from "../utils/alignmentText.js";
import { splitDisplayText } from "../utils/sentenceTokenText.js";

function joinClasses(...classes) {
  return classes.filter(Boolean).join(" ");
}

export function AlignmentTokenCore({
  token,
  className = "",
  coreProps = {},
  children,
}) {
  return (
    <span {...coreProps} className={joinClasses(getAlignmentTokenClass(token), className)}>
      {children}
    </span>
  );
}

export default function AlignmentToken({
  token,
  wrapClassName = "alignment-token-wrap",
  coreClassName = "",
  coreProps = {},
  children,
}) {
  const { uiLocale, t } = useLanguage();
  const label = getInsertionLabel(token, uiLocale);
  const parts = splitDisplayText(token?.text);
  const title = getAlignmentTokenTitle(token, t);

  return (
    <span className={wrapClassName} title={title}>
      {parts.leading && <span className="alignment-token-punctuation">{parts.leading}</span>}
      <AlignmentTokenCore token={token} className={coreClassName} coreProps={coreProps}>
        {children ? (
          children({ ...parts, label })
        ) : (
          <>
            <span>{parts.core}</span>
            {label && <span className="alignment-token-label">{label}</span>}
          </>
        )}
      </AlignmentTokenCore>
      {parts.trailing && <span className="alignment-token-punctuation">{parts.trailing}</span>}
    </span>
  );
}
