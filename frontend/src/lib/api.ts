import type { Face, Photo } from "../types";

// Dev'de Vite proxy (/api -> 127.0.0.1:8000), prod'da VITE_API_URL env variable
const BASE = import.meta.env.VITE_API_URL ?? "/api";
const API_TIMEOUT_MS = 12000;
const API_MUTATION_TIMEOUT_MS = 60000;

export const EVENT_ID = "00cb7c6b-7953-4c6a-8ae9-3b3e71451b64";

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = API_TIMEOUT_MS
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${BASE}${path}`, { ...init, signal: controller.signal });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json() as Promise<T>;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("API yanıt vermiyor. Backend çalışıyor mu ve proxy doğru porta mı gidiyor?");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function get<T>(path: string): Promise<T> {
  return request<T>(path);
}

async function post<T>(path: string, body: unknown, timeoutMs = API_TIMEOUT_MS): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }, timeoutMs);
}

export const api = {
  faces: {
    list: () => get<Face[]>(`/faces/?event_id=${EVENT_ID}`),
    photos: (faceId: string) => get<Photo[]>(`/faces/${faceId}/photos`),
    merge: (targetFaceId: string, sourceFaceIds: string[]) =>
      post<{ target_face_id: string; merged_face_ids: string[]; photo_count: number }>(
        "/faces/merge",
        { target_face_id: targetFaceId, source_face_ids: sourceFaceIds },
        API_MUTATION_TIMEOUT_MS
      ),
    deleteMany: (faceIds: string[]) =>
      post<{ deleted_face_ids: string[]; deleted_count: number; avatar_delete_failed: boolean }>(
        "/faces/delete",
        { face_ids: faceIds },
        API_MUTATION_TIMEOUT_MS
      ),
  },
};
