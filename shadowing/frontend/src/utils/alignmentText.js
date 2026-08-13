export function getAlignmentTokenTitle(token, t) {
  if (!token) return undefined;

  if (token.status === "insertion") {
    const supportedTypes = new Set(["extra", "repetition", "correction"]);
    const type = supportedTypes.has(token.insertion_type) ? token.insertion_type : "extra";
    return t(`alignment.token.insertion.${type}`);
  }

  const keyByStatus = {
    correct: "alignment.token.correct",
    minor: "alignment.token.minor",
    substitution: "alignment.token.substitution",
    deletion: "alignment.token.deletion",
    filler: "alignment.token.filler",
  };
  const key = keyByStatus[token.status];
  return key ? t(key) : undefined;
}
