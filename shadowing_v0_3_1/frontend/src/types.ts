export interface Material {
  id: number;
  title: string;
  file_type: string;
  original_path: string;
  audio_path: string | null;
  duration: number | null;
  status: string;
  created_at: string;
}

export interface Sentence {
  id: number;
  material_id: number;
  display_order: number;
  start_time: number;
  end_time: number;
  original_start_time: number | null;
  original_end_time: number | null;
  clip_audio_path: string | null;
  clip_duration: number | null;
  source_text: string;
  translation: string | null;
  created_at: string;
}

export interface WordAlignmentToken {
  index: number;
  text: string;
  normalized: string;
  status: string;
  severity: string;
  matched_token_index: number | null;
  note?: string;
  insertion_type?: string;
}

export interface WordAlignmentSummary {
  correct_count: number;
  substitution_count: number;
  deletion_count: number;
  insertion_count: number;
  minor_error_count: number;
  filler_count?: number;
  word_accuracy: number;
}

export interface WordAlignment {
  reference_tokens: WordAlignmentToken[];
  user_tokens: WordAlignmentToken[];
  summary: WordAlignmentSummary;
}

export interface Evaluation {
  id: number;
  recording_id: number;
  completeness_score: number;
  fluency_score: number;
  sync_score: number;
  pronunciation_score: number;
  overall_score: number;
  feedback: string;
  suggestion: string;
  raw_metrics: string;
  word_alignment?: WordAlignment | null;
  created_at: string;
}

export interface SentenceLatestEvaluation {
  sentence_id: number;
  main_db_recording_id: number | null;
  main_db_evaluation_id: number | null;
  completeness_score: number;
  fluency_score: number;
  sync_score: number;
  pronunciation_score: number;
  overall_score: number;
  feedback: string;
  suggestion: string;
  raw_metrics: string;
  word_alignment?: WordAlignment | null;
  created_at: string;
}

export interface MaterialLatestEvaluationsResponse {
  material_id: number;
  user_id: string;
  evaluations: SentenceLatestEvaluation[];
}

export interface WordCollection {
  id: number;
  material_id: number;
  sentence_id: number;
  word_text: string;
  normalized_word: string;
  language: string;
  translation: string | null;
  source_type: string;
  note: string | null;
  created_at: string;
  updated_at: string;
}
