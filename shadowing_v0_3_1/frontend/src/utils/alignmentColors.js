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

const INSERTION_LABELS = {
  "zh-CN": { filler: "\u8bed\u6c14\u8bcd", repetition: "\u91cd\u590d", correction: "\u81ea\u6211\u4fee\u6b63", extra: "\u591a\u4f59" },
  "en-US": { filler: "filler", repetition: "repeat", correction: "self-correction", extra: "extra" },
};

function getUILocale() {
  if (typeof document !== "undefined" && document.documentElement.lang.toLowerCase().startsWith("zh")) return "zh-CN";
  return "en-US";
}

export function getAlignmentTokenClass(token) {
  const status = token?.status ?? "default";
  const severity = token?.severity ?? "default";
  const statusClass = STATUS_CLASSES[status] ?? SEVERITY_CLASSES[severity] ?? STATUS_CLASSES.default;
  return `${BASE_TOKEN_CLASS} ${statusClass}`;
}

export function getInsertionLabel(token) {
  if (!token) return null;
  const labels = INSERTION_LABELS[getUILocale()];
  if (token.status === "filler") return labels.filler;
  if (token.status !== "insertion") return null;
  if (token.insertion_type === "repetition") return labels.repetition;
  if (token.insertion_type === "correction") return labels.correction;
  return labels.extra;
}
