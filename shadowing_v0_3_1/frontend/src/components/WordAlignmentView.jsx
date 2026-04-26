import HighlightedSentence from "./HighlightedSentence.jsx";

function formatAccuracy(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
}

export default function WordAlignmentView({ alignment }) {
  if (!alignment) {
    return null;
  }

  const summary = alignment.summary ?? {};

  return (
    <div className="word-alignment">
      <div className="word-alignment-header">
        <h4>词级对齐</h4>
        <span className="muted">Word accuracy {formatAccuracy(summary.word_accuracy)}</span>
      </div>

      <div className="word-alignment-section">
        <div className="word-alignment-title">你的识别结果</div>
        <HighlightedSentence tokens={alignment.user_tokens ?? []} emptyText="No recognized words." />
      </div>
    </div>
  );
}
