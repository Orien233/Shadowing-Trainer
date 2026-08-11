export interface Material {
  id: number;
  title: string;
  file_type: string;
  original_path: string;
  audio_path: string | null;
  duration: number | null;
  status: string;
  job_id?: string | null;
  processing_stage?: string | null;
  processing_progress?: number;
  error_message?: string | null;
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

export interface Job {
  id: string;
  kind: "evaluation" | "material_processing" | "storage_cleanup" | "tts_synthesis";
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  stage: string;
  progress: number;
  result: { recording_id?: number; evaluation?: Evaluation; material_id?: number } | null;
  error_message: string | null;
  attempts: number;
}

export interface RecordingUploadAccepted {
  recording_id: number;
  job_id: string;
  status: string;
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

export type ProviderCapability = "llm" | "tts" | "asr";

export type ProviderConfigFieldType = "string" | "number" | "boolean" | "select";

export interface ProviderConfigField {
  key: string;
  label: string;
  field_type: ProviderConfigFieldType;
  required: boolean;
  options: string[];
  default: unknown;
  placeholder: string | null;
  help_text: string | null;
}

export interface ProviderVoice {
  id: string;
  name: string;
  languages?: string[];
  locale?: string;
  gender?: string | null;
  accent?: string | null;
  styles?: string[];
  preview_url?: string | null;
  provider_metadata?: Record<string, unknown>;
}

export interface ProviderCatalogEntry {
  key: string;
  label: string;
  kind: ProviderCapability;
  capabilities: string[];
  available_capabilities?: string[];
  available_formats?: string[];
  preset?: boolean;
  preset_defaults?: Record<string, unknown>;
  endpoint_mode: "base_url" | "full_endpoint" | "none";
  endpoint_hint: string | null;
  required_fields: string[];
  config_fields: ProviderConfigField[];
  voice_presets: ProviderVoice[];
  docs_url: string | null;
}

export interface ProviderTestResponse {
  ok: boolean;
  message: string;
  capabilities: string[];
  available_capabilities?: string[];
  enabled_capabilities?: string[];
  available_formats?: string[];
  enabled_formats?: string[];
  verification_level: string;
}

export interface AIProvider {
  id: number; name: string; capability: ProviderCapability; provider_type: string;
  base_url: string | null; api_key_masked: string | null; model_name: string | null;
  is_enabled: boolean; is_default: boolean; extra_config: Record<string, unknown>;
  capabilities: string[];
  available_capabilities?: string[];
  enabled_capabilities?: string[];
  available_formats?: string[];
  enabled_formats?: string[];
  is_deprecated?: boolean;
  created_at: string; updated_at: string;
}
export interface ASRSceneSettings {
  material_transcription_use_local: boolean;
  recording_evaluation_use_local: boolean;
  updated_at: string;
  material_transcription_remote_available: boolean;
  material_transcription_missing_capabilities: string[];
  recording_evaluation_remote_available: boolean;
  recording_evaluation_missing_capabilities: string[];
}

export interface ASRSceneSettingsUpdate {
  material_transcription_use_local?: boolean;
  recording_evaluation_use_local?: boolean;
}
export interface TextPractice {
  id: number; title: string; body: string; source_type: string; target_language: string;
  difficulty: string | null; desired_length: number | null; topic: string | null;
  explanation: string | null; requested_words: string[]; used_words: string[]; unused_words: string[];
  llm_provider_id: number | null; tts_provider_id: number | null; tts_status: string;
  tts_job_id: string | null; tts_audio_path: string | null; material_id: number | null;
  created_at: string; updated_at: string;
}
