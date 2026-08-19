import type { Evaluation, SentenceLatestEvaluation } from "../../../types";

export function asEvaluation(snapshot: SentenceLatestEvaluation): Evaluation {
  return {
    id: snapshot.evaluation_id,
    recording_id: snapshot.recording_id,
    completeness_score: snapshot.completeness_score,
    fluency_score: snapshot.fluency_score,
    sync_score: snapshot.sync_score,
    pronunciation_score: snapshot.pronunciation_score,
    overall_score: snapshot.overall_score,
    feedback: snapshot.feedback,
    suggestion: snapshot.suggestion,
    raw_metrics: snapshot.raw_metrics,
    word_alignment: snapshot.word_alignment,
    created_at: snapshot.created_at,
  };
}
