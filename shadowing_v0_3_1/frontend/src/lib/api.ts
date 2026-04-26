import type {
  Evaluation,
  Material,
  MaterialLatestEvaluationsResponse,
  Sentence,
  SentenceLatestEvaluation,
  WordCollection,
} from "../types";

const API_BASE = "http://localhost:8000";

export const apiBase = API_BASE;

export interface RecordingCleanupResult {
  target_dir: string;
  total_files: number;
  deleted_files: number;
  failed_files: Array<{ path: string; reason: string }>;
}

export interface WordCollectInput {
  material_id: number;
  sentence_id: number;
  word_text: string;
  language?: string;
}

interface WordCollectionErrorPayload {
  detail?: string;
  message?: string;
}

export class WordCollectionApiError extends Error {
  status: number;
  detail?: string;
  serverMessage?: string;

  constructor(status: number, payload: WordCollectionErrorPayload | null) {
    super(payload?.message ?? payload?.detail ?? "Word collection request failed");
    this.status = status;
    this.detail = payload?.detail;
    this.serverMessage = payload?.message;
  }
}

async function readWordCollectionError(res: Response): Promise<WordCollectionApiError> {
  try {
    const payload = (await res.json()) as WordCollectionErrorPayload;
    return new WordCollectionApiError(res.status, payload);
  } catch {
    return new WordCollectionApiError(res.status, null);
  }
}

export async function listMaterials(): Promise<Material[]> {
  const res = await fetch(`${API_BASE}/api/materials`);
  if (!res.ok) throw new Error("Failed to load materials");
  return res.json();
}

export async function uploadMaterial(title: string, file: File): Promise<Material> {
  const formData = new FormData();
  formData.append("title", title);
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/api/materials/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function processMaterial(materialId: number): Promise<Material> {
  const res = await fetch(`${API_BASE}/api/materials/${materialId}/process`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteMaterial(materialId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/materials/${materialId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function getSentences(materialId: number): Promise<Sentence[]> {
  const res = await fetch(`${API_BASE}/api/materials/${materialId}/sentences`);
  if (!res.ok) throw new Error("Failed to load sentences");
  return res.json();
}

export async function getLatestMaterialEvaluations(
  materialId: number,
  userId?: string
): Promise<SentenceLatestEvaluation[]> {
  const url = new URL(`${API_BASE}/api/materials/${materialId}/latest-evaluations`);
  if (userId && userId.trim()) {
    url.searchParams.set("user_id", userId.trim());
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error("Failed to load latest evaluations");
  const data = (await res.json()) as MaterialLatestEvaluationsResponse;
  return data.evaluations;
}

export async function uploadRecording(sentenceId: number, blob: Blob): Promise<Evaluation> {
  const formData = new FormData();
  const file = new File([blob], "recording.webm", { type: blob.type || "audio/webm" });
  formData.append("sentence_id", String(sentenceId));
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/api/recordings/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data.evaluation as Evaluation;
}

export async function cleanupRecordingFiles(): Promise<RecordingCleanupResult> {
  const res = await fetch(`${API_BASE}/api/recordings/cleanup`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function collectWord(payload: WordCollectInput): Promise<WordCollection> {
  const res = await fetch(`${API_BASE}/api/words/collect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language: "en", ...payload }),
  });
  if (!res.ok) throw await readWordCollectionError(res);
  return res.json();
}

export async function listWordCollections(): Promise<WordCollection[]> {
  const res = await fetch(`${API_BASE}/api/words/collections`);
  if (!res.ok) throw await readWordCollectionError(res);
  return res.json();
}

export async function deleteWordCollection(collectionId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/words/collections/${collectionId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw await readWordCollectionError(res);
}

export async function shutdownBackend(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/system/shutdown`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await res.text());
}
