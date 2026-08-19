import type { AlignmentToken } from "../types";

export function getAlignmentTokenTitle(token: AlignmentToken | undefined, t: (key: string) => string) {
  if (!token) return undefined;

  if (token.status === "insertion") {
    const supportedTypes = new Set(["extra", "repetition", "correction"]);
    const type = supportedTypes.has(token.insertion_type ?? "") ? token.insertion_type ?? "extra" : "extra";
    return t(`alignment.token.insertion.${type}`);
  }

  const keyByStatus: Record<string, string> = {
    correct: "alignment.token.correct",
    minor: "alignment.token.minor",
    substitution: "alignment.token.substitution",
    deletion: "alignment.token.deletion",
    filler: "alignment.token.filler",
  };
  const key = keyByStatus[token.status ?? ""];
  return key ? t(key) : undefined;
}
