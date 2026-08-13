import type { Evaluation } from "../types";

type Translate = (key: string) => string;

type LocalizedEvaluationCopy = Pick<Evaluation, "feedback" | "suggestion">;

const DIAGNOSTIC_TAGS = new Set([
  "content_mismatch",
  "weak_imitation",
  "too_many_pauses",
  "pace_too_fast",
  "pace_too_slow",
  "intonation_flat",
  "imitation_unavailable",
  "prosody_unavailable",
  "trimmed_leading_silence",
  "trimmed_trailing_silence",
  "trim_fallback_used",
]);

function readTags(rawMetrics: string): string[] | null {
  try {
    const payload: unknown = JSON.parse(rawMetrics);
    if (!payload || typeof payload !== "object" || !Array.isArray((payload as { tags?: unknown }).tags)) {
      return null;
    }
    return (payload as { tags: unknown[] }).tags.filter((tag): tag is string => typeof tag === "string");
  } catch {
    return null;
  }
}

/**
 * Use stable backend diagnostic tags when available.  Historical rows did not
 * persist tags, so their stored feedback remains the compatibility fallback.
 */
export function getLocalizedEvaluationCopy(
  evaluation: Evaluation,
  t: Translate,
): LocalizedEvaluationCopy {
  const tags = readTags(evaluation.raw_metrics);
  if (tags === null) {
    return { feedback: evaluation.feedback, suggestion: evaluation.suggestion };
  }

  const knownTags = [...new Set(tags)].filter((tag) => DIAGNOSTIC_TAGS.has(tag));
  if (!tags.length) {
    return {
      feedback: t("evaluation.tag.none.feedback"),
      suggestion: t("evaluation.tag.none.suggestion"),
    };
  }
  if (!knownTags.length) {
    return {
      feedback: t("evaluation.tag.generic.feedback"),
      suggestion: t("evaluation.tag.generic.suggestion"),
    };
  }

  const feedback = knownTags.map((tag) => t(`evaluation.tag.${tag}.feedback`)).join(" ");
  const suggestions = knownTags
    .map((tag) => t(`evaluation.tag.${tag}.suggestion`))
    .filter(Boolean)
    .slice(0, 2)
    .join(" ");
  return {
    feedback,
    suggestion: suggestions || t("evaluation.tag.generic.suggestion"),
  };
}
