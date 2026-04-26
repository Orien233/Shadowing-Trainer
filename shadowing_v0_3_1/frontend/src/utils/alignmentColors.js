const BASE_TOKEN_CLASS =
  "inline-flex items-center gap-1 rounded px-1.5 py-0.5 border align-baseline";

const STATUS_CLASSES = {
  correct: "text-green-700 bg-green-50 border-green-200",
  minor: "text-yellow-800 bg-yellow-50 border-yellow-200",
  insertion: "text-yellow-800 bg-yellow-50 border-yellow-200",
  filler: "border-transparent underline decoration-dotted underline-offset-4",
  substitution: "text-red-700 bg-red-50 border-red-200",
  deletion: "text-red-700 bg-red-50 border-red-200 line-through",
  default: "border-transparent",
};

const SEVERITY_CLASSES = {
  correct: STATUS_CLASSES.correct,
  minor: STATUS_CLASSES.minor,
  major: STATUS_CLASSES.substitution,
  default: STATUS_CLASSES.default,
};

export function getAlignmentTokenClass(token) {
  const status = token?.status ?? "default";
  const severity = token?.severity ?? "default";
  const statusClass = STATUS_CLASSES[status] ?? SEVERITY_CLASSES[severity] ?? STATUS_CLASSES.default;
  return `${BASE_TOKEN_CLASS} ${statusClass}`;
}

export function getInsertionLabel(token) {
  if (!token) return null;
  if (token.status === "filler") return "filler";
  if (token.status !== "insertion") return null;
  if (token.insertion_type === "repetition") return "repeat";
  if (token.insertion_type === "correction") return "self-correction";
  return "extra";
}
