import type {
  Job, Material, MaterialLatestEvaluationsResponse, RecordingUploadAccepted,
  AIProvider, ASRSceneSettings, Sentence, SentenceLatestEvaluation, TextPractice, WordCollection,
} from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE || "http://localhost:8000").replace(/\/$/, "");
const ADMIN_TOKEN = import.meta.env.VITE_LOCAL_ADMIN_TOKEN || "";
export const apiBase = API_BASE;

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 20_000): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const headers = new Headers(init.headers);
  if (ADMIN_TOKEN) headers.set("X-Local-Admin-Token", ADMIN_TOKEN);
  try {
    const response = await fetch(`${API_BASE}${path}`, { ...init, headers, signal: controller.signal });
    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      try {
        const payload = await response.json();
        message = payload.message || payload.detail || message;
      } catch { message = (await response.text()) || message; }
      throw new ApiError(response.status, message);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(408, "Request timed out. Please retry.");
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export interface RecordingCleanupResult { target_dir: string; total_files: number; deleted_files: number; failed_files: Array<{ path: string; reason: string }>; }
export interface WordCollectInput { material_id: number; sentence_id: number; word_text: string; language?: string; }
export type WordCollectionSortMode = "collected_time_asc" | "collected_time_desc" | "alphabetical";
export interface WordCollectionListOptions { sort?: WordCollectionSortMode; }
export class WordCollectionApiError extends ApiError {}

export const listMaterials = () => request<Material[]>("/api/materials");
export const uploadMaterial = (title: string, file: File) => {
  const body = new FormData(); body.append("title", title); body.append("file", file);
  return request<Material>("/api/materials/upload", { method: "POST", body }, 60_000);
};
export const processMaterial = (id: number) => request<Material>(`/api/materials/${id}/process`, { method: "POST" });
export const deleteMaterial = (id: number) => request<void>(`/api/materials/${id}`, { method: "DELETE" });
export const getSentences = (id: number) => request<Sentence[]>(`/api/materials/${id}/sentences`);
export async function getLatestMaterialEvaluations(id: number, userId?: string): Promise<SentenceLatestEvaluation[]> {
  const suffix = userId?.trim() ? `?user_id=${encodeURIComponent(userId.trim())}` : "";
  return (await request<MaterialLatestEvaluationsResponse>(`/api/materials/${id}/latest-evaluations${suffix}`)).evaluations;
}
export async function uploadRecording(sentenceId: number, blob: Blob): Promise<RecordingUploadAccepted> {
  const body = new FormData();
  body.append("sentence_id", String(sentenceId));
  body.append("file", new File([blob], "recording.webm", { type: blob.type || "audio/webm" }));
  return request<RecordingUploadAccepted>("/api/recordings/upload", { method: "POST", body }, 60_000);
}
export const getJob = (id: string) => request<Job>(`/api/jobs/${id}`);
export const retryJob = (id: string) => request<Job>(`/api/jobs/${id}/retry`, { method: "POST" });
export const cleanupRecordingFiles = () => request<RecordingCleanupResult>("/api/recordings/cleanup", { method: "DELETE" });
export async function collectWord(payload: WordCollectInput): Promise<WordCollection> {
  try {
    return await request<WordCollection>("/api/words/collect", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ language: "en", ...payload }) });
  } catch (error) {
    if (error instanceof ApiError) throw new WordCollectionApiError(error.status, error.message);
    throw error;
  }
}
export async function listWordCollections(options: WordCollectionListOptions = {}): Promise<WordCollection[]> {
  const suffix = options.sort ? `?sort=${options.sort}` : "";
  return request<WordCollection[]>(`/api/words/collections${suffix}`);
}
export const deleteWordCollection = (id: number) => request<void>(`/api/words/collections/${id}`, { method: "DELETE" });
export const shutdownBackend = () => request<void>("/api/system/shutdown", { method: "POST" });

export type ProviderInput = { name: string; capability: "llm" | "tts" | "asr"; provider_type: string; base_url?: string | null; api_key?: string | null; model_name?: string | null; is_enabled?: boolean; is_default?: boolean; extra_config?: Record<string, unknown>; };
export const listProviders = () => request<AIProvider[]>("/api/providers");
export const createProvider = (payload: ProviderInput) => request<AIProvider>("/api/providers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
export const updateProvider = (id: number, payload: Partial<ProviderInput>) => request<AIProvider>(`/api/providers/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
export const deleteProvider = (id: number) => request<void>(`/api/providers/${id}`, { method: "DELETE" });
export const testProvider = (id: number) => request<{ ok: boolean; message: string; capabilities: string[] }>(`/api/providers/${id}/test`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }, 130_000);
export const getASRSceneSettings = () => request<ASRSceneSettings>("/api/providers/asr-scenes/settings");
export const updateASRSceneSettings = (payload: Partial<ASRSceneSettings>) => request<ASRSceneSettings>("/api/providers/asr-scenes/settings", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
export type TextGenerationInput = { word_selection: "random" | "manual" | "none"; random_word_count: number; word_collection_ids: number[]; preset_topic?: string; custom_topic?: string; target_language: string; difficulty: string; desired_length: number; };
export const generateTextPractice = (payload: TextGenerationInput) => request<TextPractice>("/api/text-practices/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }, 90_000);
export const importTextPractice = (payload: { title: string; body: string; target_language?: string; difficulty?: string; topic?: string }) => request<TextPractice>("/api/text-practices/import", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
export const updateTextPractice = (id: number, payload: { title?: string; body?: string }) => request<TextPractice>(`/api/text-practices/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
export const synthesizeTextPractice = (id: number, payload: { speed_preset: "slow" | "normal" | "fast"; accent?: string; gender?: string; voice?: string; model?: string; provider_id?: number }) => request<{ text_practice_id: number; job_id: string; status: string }>(`/api/text-practices/${id}/tts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
