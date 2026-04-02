import type { AuthLoginResponse } from "./types";

export const AUTH_TOKEN_STORAGE_KEY = "oma_token";
export const AUTH_TOKEN_UPDATED_EVENT = "oma-auth-token-updated";
export const AUTH_TOKEN_CLEARED_EVENT = "oma-auth-token-cleared";
export const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL);

let refreshTokenPromise: Promise<string | null> | null = null;

export function normalizeApiBaseUrl(rawValue: string | undefined): string {
  const value = (rawValue || "").trim();
  return value ? value.replace(/\/+$/, "") : "";
}

export function buildApiUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  if (!API_BASE_URL) return url;
  return url.startsWith("/") ? `${API_BASE_URL}${url}` : `${API_BASE_URL}/${url}`;
}

export function getStoredAuthToken(): string {
  return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || "";
}

export function saveStoredAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
  window.dispatchEvent(new Event(AUTH_TOKEN_UPDATED_EVENT));
}

export function clearStoredAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  window.dispatchEvent(new Event(AUTH_TOKEN_CLEARED_EVENT));
}

export function buildApiHeaders(includeJson: boolean): Record<string, string> {
  const headers: Record<string, string> = {};
  if (includeJson) headers["Content-Type"] = "application/json";
  const token = getStoredAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export async function apiGet<T>(url: string): Promise<T> {
  return requestJson<T>(url, { headers: buildApiHeaders(false) });
}

export async function apiPost<T = unknown>(url: string, body: unknown): Promise<T> {
  return requestJson<T>(url, {
    method: "POST",
    headers: buildApiHeaders(true),
    body: JSON.stringify(body),
  });
}

export async function apiPut<T = unknown>(url: string, body: unknown): Promise<T> {
  return requestJson<T>(url, {
    method: "PUT",
    headers: buildApiHeaders(true),
    body: JSON.stringify(body),
  });
}

export async function apiDelete<T = unknown>(url: string): Promise<T> {
  return requestJson<T>(url, { method: "DELETE", headers: buildApiHeaders(false) });
}

export async function apiDownload(url: string, filename: string): Promise<void> {
  const response = await fetch(buildApiUrl(url), { headers: buildApiHeaders(false) });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response));
  }
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

export async function requestJson<T>(url: string, init: RequestInit): Promise<T> {
  try {
    const response = await fetch(buildApiUrl(url), init);
    if (response.status === 401 && shouldTryTokenRefresh(url)) {
      const refreshedToken = await refreshAccessToken();
      if (refreshedToken) {
        const retryResponse = await fetch(buildApiUrl(url), withAuthHeader(init, refreshedToken));
        return parseResponse<T>(retryResponse);
      }
    }
    return parseResponse<T>(response);
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(`Network error while reaching API (${buildApiUrl(url)}). Check backend availability, proxy, and CORS.`);
    }
    throw error;
  }
}

export async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response));
  }
  return (await response.json()) as T;
}

export function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function shouldTryTokenRefresh(url: string): boolean {
  return !url.includes("/api/auth/login") && !url.includes("/api/auth/refresh");
}

function withAuthHeader(init: RequestInit, token: string): RequestInit {
  const headers = new Headers(init.headers || undefined);
  headers.set("Authorization", `Bearer ${token}`);
  return { ...init, headers };
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshTokenPromise) {
    return refreshTokenPromise;
  }

  refreshTokenPromise = (async () => {
    const token = getStoredAuthToken();
    if (!token) return null;

    try {
      const response = await fetch(buildApiUrl("/api/auth/refresh"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ access_token: token }),
      });
      if (!response.ok) {
        clearStoredAuthToken();
        return null;
      }
      const payload = (await response.json()) as AuthLoginResponse;
      if (!payload.access_token) {
        clearStoredAuthToken();
        return null;
      }
      saveStoredAuthToken(payload.access_token);
      return payload.access_token;
    } catch {
      clearStoredAuthToken();
      return null;
    }
  })();

  try {
    return await refreshTokenPromise;
  } finally {
    refreshTokenPromise = null;
  }
}

async function extractErrorDetail(response: Response): Promise<string> {
  let detail = `${response.status} ${response.statusText}`;
  try {
    const data = (await response.json()) as { detail?: string };
    if (data?.detail) return data.detail;
  } catch {
    // continue
  }

  try {
    const text = await response.text();
    if (text.trim()) return text.slice(0, 180);
  } catch {
    // ignore body parse errors
  }

  return detail;
}
