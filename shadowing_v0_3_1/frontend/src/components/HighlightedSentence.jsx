import { getAlignmentTokenClass, getInsertionLabel } from "../utils/alignmentColors.js";

const EDGE_PUNCTUATION_PATTERN = /^([\p{P}]*)(.*?)([\p{P}]*)$/u;

function splitDisplayText(text) {
  const displayText = String(text ?? "");
  const match = displayText.match(EDGE_PUNCTUATION_PATTERN);
  if (!match) {
    return { leading: "", core: displayText, trailing: "" };
  }

  const [, leading, core, trailing] = match;
  if (!core) {
    return { leading: "", core: displayText, trailing: "" };
  }

  return { leading, core, trailing };
}

/**
 * @param {{ tokens?: Array<any>, emptyText?: string }} props
 */
export default function HighlightedSentence({ tokens = [], emptyText = "No words." }) {
  if (!tokens.length) {
    return <p className="muted alignment-empty">{emptyText}</p>;
  }

  return (
    <div className="highlighted-sentence">
      {tokens.map((token) => {
        const label = getInsertionLabel(token);
        const { leading, core, trailing } = splitDisplayText(token.text);
        return (
          <span key={`${token.index}-${token.text}`} className="alignment-token-wrap" title={token.note ?? ""}>
            {leading && <span className="alignment-token-punctuation">{leading}</span>}
            <span className={getAlignmentTokenClass(token)}>
              <span>{core}</span>
              {label && <span className="alignment-token-label">{label}</span>}
            </span>
            {trailing && <span className="alignment-token-punctuation">{trailing}</span>}
          </span>
        );
      })}
    </div>
  );
}
