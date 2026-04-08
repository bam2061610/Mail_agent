import type { AuthLoginResponse } from "./types";

export const AUTH_TOKEN_STORAGE_KEY = "oma_token";
export const AUTH_TOKEN_UPDATED_EVENT = "oma-auth-token-updated";
export const AUTH_TOKEN_CLEARED_EVENT = "oma-auth-token-cleared";
export const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL);

let refreshTokenPromise: Promise<string | null> | null = null;

export type ApiErrorDetails = Record<string, unknown> | null;

export type StructuredApiErrorPayload = {
  error_code: string;
  message: string;
  details?: ApiErrorDetails;
};

export class ApiError extends Error {
  status: number;
  errorCode: string;
  details: ApiErrorDetails;
  isNetworkError = false;

  constructor(status: number, payload: StructuredApiErrorPayload) {
    super(payload.message);
    this.name = "ApiError";
    this.status = status;
    this.errorCode = payload.error_code;
    this.details = payload.details ?? null;
  }
}

export class NetworkError extends Error {
  isNetworkError = true;

  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}

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
  return requestJson<T>(url, {
    method: "DELETE",
    headers: buildApiHeaders(false),
  });
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
      throw new NetworkError(`Network error while reaching API (${buildApiUrl(url)}). Check backend availability, proxy, and CORS.`);
    }
    throw error;
  }
}

export async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorDetail(response));
  }
  return (await response.json()) as T;
}

export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError || error instanceof NetworkError) {
    return error.message;
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

export function getApiErrorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.errorCode : null;
}

export function isAuthError(error: unknown): boolean {
  return error instanceof ApiError && error.errorCode === "auth_required";
}

export function isSetupRequiredError(error: unknown): boolean {
  return error instanceof ApiError && error.errorCode === "setup_required";
}

export function isMailboxContextError(error: unknown): boolean {
  return error instanceof ApiError && (error.errorCode === "mailbox_context_missing" || error.errorCode === "mailbox_context_mismatch");
}

export function isNetworkError(error: unknown): boolean {
  return error instanceof NetworkError;
}

export type ReplyRequestPayload = {
  body: string;
  to?: string[];
  cc?: string[];
  bcc?: string[];
  subject?: string;
  save_as_sent_record?: boolean;
};

export function buildReplyPayload(payload: ReplyRequestPayload): ReplyRequestPayload {
  const cleanRecipients = (values?: string[]) =>
    (values || [])
      .map((value) => value.trim())
      .filter(Boolean);

  return {
    body: payload.body,
    to: cleanRecipients(payload.to),
    cc: cleanRecipients(payload.cc),
    bcc: cleanRecipients(payload.bcc),
    subject: payload.subject?.trim() || undefined,
    save_as_sent_record: payload.save_as_sent_record ?? true,
  };
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

async function extractErrorDetail(response: Response): Promise<StructuredApiErrorPayload> {
  const fallbackPayload: StructuredApiErrorPayload = {
    error_code: inferErrorCodeFromStatus(response.status),
    message: `${response.status} ${response.statusText}`.trim(),
  };
  let rawBody = "";
  try {
    rawBody = await response.clone().text();
  } catch {
    rawBody = "";
  }
  if (!rawBody.trim()) {
    return fallbackPayload;
  }

  try {
    const data = JSON.parse(rawBody) as {
      error_code?: string;
      message?: string;
      details?: ApiErrorDetails;
      detail?: string | { message?: string; error_code?: string; details?: ApiErrorDetails };
      error?: string;
    };
    if (typeof data?.error_code === "string" && typeof data?.message === "string" && data.message.trim()) {
      return { error_code: data.error_code, message: data.message, details: data.details ?? null };
    }
    if (typeof data?.detail === "string" && data.detail.trim()) {
      return { error_code: inferErrorCodeFromMessage(response.status, data.detail), message: data.detail };
    }
    if (data?.detail && typeof data.detail === "object") {
      const nested = data.detail as { message?: string; error_code?: string; details?: ApiErrorDetails };
      const nestedMessage = typeof nested.message === "string" ? nested.message.trim() : "";
      if (nestedMessage) {
        return {
          error_code: typeof nested.error_code === "string" ? nested.error_code : inferErrorCodeFromMessage(response.status, nestedMessage),
          message: nestedMessage,
          details: nested.details ?? null,
        };
      }
    }
    if (typeof data?.error === "string" && data.error.trim()) {
      return { error_code: inferErrorCodeFromMessage(response.status, data.error), message: data.error };
    }
    if (typeof data?.message === "string" && data.message.trim()) {
      return { error_code: inferErrorCodeFromMessage(response.status, data.message), message: data.message };
    }
  } catch {
    // continue
  }

  return {
    error_code: inferErrorCodeFromMessage(response.status, rawBody),
    message: rawBody.slice(0, 180),
  };
}

function inferErrorCodeFromStatus(status: number): string {
  switch (status) {
    case 401:
      return "auth_required";
    case 403:
      return "forbidden";
    case 404:
      return "not_found";
    case 409:
      return "conflict";
    case 422:
      return "validation_error";
    case 429:
      return "rate_limited";
    case 502:
      return "imap_move_failed";
    case 503:
      return "setup_required";
    case 504:
      return "gateway_timeout";
    default:
      return "request_failed";
  }
}

function inferErrorCodeFromMessage(status: number, message: string): string {
  const lowered = message.toLowerCase();
  if (status === 503 && lowered.includes("setup")) return "setup_required";
  if (status === 401) return "auth_required";
  if (lowered.includes("mailbox context is missing")) return "mailbox_context_missing";
  if (lowered.includes("mailbox context") && lowered.includes("mismatch")) return "mailbox_context_mismatch";
  if (lowered.includes("email not found")) return "email_not_found";
  if (lowered.includes("imap folder") && lowered.includes("resolve")) return "imap_folder_resolution_failed";
  if (lowered.includes("imap") && (lowered.includes("move") || lowered.includes("restore") || lowered.includes("spam"))) return "imap_move_failed";
  if (lowered.includes("stale lock") || lowered.includes("background lock")) return "stale_lock_file";
  if (lowered.includes("data_dir") || lowered.includes("data dir")) return "data_dir_unavailable";
  if (lowered.includes("diagnostic")) return "diagnostics_unavailable";
  return inferErrorCodeFromStatus(status);
}
