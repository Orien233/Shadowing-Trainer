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
  created_at: string;
}
