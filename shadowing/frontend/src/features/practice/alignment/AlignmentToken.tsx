import { getAlignmentTokenClass, getInsertionLabel } from "../../../utils/alignmentColors";
import { useLanguage } from "../../../i18n/LanguageContext";
import { getAlignmentTokenTitle } from "../../../utils/alignmentText";
import { splitDisplayText } from "../../../utils/sentenceTokenText";

function joinClasses(...classes: Array<string | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function AlignmentTokenCore({
  token,
  className = "",
  coreProps = {},
  children,
}: { token?: AlignmentTokenType; className?: string; coreProps?: HTMLAttributes<HTMLSpanElement>; children?: ReactNode }) {
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
}: { token: AlignmentTokenType; wrapClassName?: string; coreClassName?: string; coreProps?: HTMLAttributes<HTMLSpanElement>; children?: (parts: { leading: string; core: string; trailing: string; label: string | null }) => ReactNode }) {
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
import type { HTMLAttributes, ReactNode } from "react";
import type { AlignmentToken as AlignmentTokenType } from "../../../types";
