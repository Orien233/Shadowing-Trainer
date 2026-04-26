import { getAlignmentTokenClass, getInsertionLabel } from "../utils/alignmentColors.js";
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
  const label = getInsertionLabel(token);
  const parts = splitDisplayText(token?.text);

  return (
    <span className={wrapClassName} title={token?.note ?? ""}>
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
