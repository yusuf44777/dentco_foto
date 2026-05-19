import type { Face, Photo } from "../types";

// Dev'de Vite proxy (/api -> 127.0.0.1:8000), prod'da VITE_API_URL env variable
const BASE = import.meta.env.VITE_API_URL ?? "/api";
const API_TIMEOUT_MS = 12000;

export const EVENT_ID = "00cb7c6b-7953-4c6a-8ae9-3b3e71451b64";

function apiUrl(path: string) {
  return `${BASE}${path}`;
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = API_TIMEOUT_MS
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(apiUrl(path), { ...init, signal: controller.signal });
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

export const api = {
  faces: {
    list: () => get<Face[]>(`/faces/?event_id=${EVENT_ID}`),
    photos: (faceId: string) => get<Photo[]>(`/faces/${encodeURIComponent(faceId)}/photos`),
    download: (faceId: string) => apiUrl(`/faces/${encodeURIComponent(faceId)}/download`),
  },
};
