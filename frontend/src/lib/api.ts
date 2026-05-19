import type { Face, Photo } from "../types";

// Dev'de Vite proxy (/api -> 127.0.0.1:8000), prod'da VITE_API_URL env variable
const BASE = import.meta.env.VITE_API_URL ?? "/api";
const API_TIMEOUT_MS = 12000;
const ADMIN_TIMEOUT_MS = 60000;

export const EVENT_ID = "00cb7c6b-7953-4c6a-8ae9-3b3e71451b64";

function apiUrl(path: string) {
  return `${BASE}${path}`;
}

function adminHeaders(token?: string): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function errorMessage(res: Response) {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // Keep the generic HTTP message when the backend did not return JSON.
  }
  return `API error: ${res.status}`;
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
    if (!res.ok) throw new Error(await errorMessage(res));
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

async function post<T>(
  path: string,
  body: unknown,
  token?: string,
  timeoutMs = API_TIMEOUT_MS
): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...adminHeaders(token),
    },
    body: JSON.stringify(body),
  }, timeoutMs);
}

async function deleteRequest<T>(path: string, token: string, timeoutMs = API_TIMEOUT_MS): Promise<T> {
  return request<T>(path, {
    method: "DELETE",
    headers: adminHeaders(token),
  }, timeoutMs);
}

export const api = {
  auth: {
    login: (password: string) => post<{ token: string; expires_at: number }>("/auth/login", { password }),
    session: (token: string) =>
      request<{ ok: boolean }>("/auth/session", { headers: adminHeaders(token) }),
  },
  faces: {
    list: () => get<Face[]>(`/faces/?event_id=${EVENT_ID}`),
    photos: (faceId: string) => get<Photo[]>(`/faces/${encodeURIComponent(faceId)}/photos`),
    download: (faceId: string) => apiUrl(`/faces/${encodeURIComponent(faceId)}/download`),
    merge: (targetFaceId: string, sourceFaceIds: string[], token: string) =>
      post<{ target_face_id: string; merged_face_ids: string[]; photo_count: number }>(
        "/faces/merge",
        { target_face_id: targetFaceId, source_face_ids: sourceFaceIds },
        token,
        ADMIN_TIMEOUT_MS
      ),
    delete: (faceId: string, token: string) =>
      deleteRequest<{ deleted_face_id: string }>(
        `/faces/${encodeURIComponent(faceId)}`,
        token,
        ADMIN_TIMEOUT_MS
      ),
  },
};
