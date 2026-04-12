import type { Evaluation, Material, Sentence } from "../types";

const API_BASE = "http://localhost:8000";

export const apiBase = API_BASE;

export interface RecordingCleanupResult {
  target_dir: string;
  total_files: number;
  deleted_files: number;
  failed_files: Array<{ path: string; reason: string }>;
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

export async function shutdownBackend(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/system/shutdown`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await res.text());
}
