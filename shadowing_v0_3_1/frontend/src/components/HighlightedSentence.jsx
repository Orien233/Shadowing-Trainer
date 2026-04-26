import AlignmentToken from "./AlignmentToken.jsx";

/**
 * @param {{ tokens?: Array<any>, emptyText?: string }} props
 */
export default function HighlightedSentence({ tokens = [], emptyText = "No words." }) {
  if (!tokens.length) {
    return <p className="muted alignment-empty">{emptyText}</p>;
  }

  return (
    <div className="highlighted-sentence">
      {tokens.map((token) => (
        <AlignmentToken key={`${token.index}-${token.text}`} token={token} />
      ))}
    </div>
  );
}
