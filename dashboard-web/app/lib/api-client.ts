"use client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY_STORAGE_KEY = "dashboard-api-key";
const AUTH_ERROR_EVENT = "dashboard-auth-error";
const AUTH_KEY_UPDATED_EVENT = "dashboard-auth-key-updated";
const AUTH_CSRF_COOKIE_NAME = process.env.NEXT_PUBLIC_AUTH_CSRF_COOKIE_NAME || "dashboard_csrf";

interface ApiErrorPayload {
  detail?: string;
}

export class ApiClientError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
  }
}

function toAbsoluteUrl(pathOrUrl: string): string {
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    return pathOrUrl;
  }
  if (pathOrUrl.startsWith("/")) {
    return `${API_URL}${pathOrUrl}`;
  }
  return `${API_URL}/${pathOrUrl}`;
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as ApiErrorPayload;
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
  } catch {
    // Ignore parse errors and fallback on status text.
  }
  return response.statusText || "Erreur API";
}

function emitAuthError(status: number, detail: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(AUTH_ERROR_EVENT, {
      detail: {
        status,
        message: detail,
      },
    })
  );
}

function isUnsafeMethod(method: string | undefined): boolean {
  const normalized = (method || "GET").toUpperCase();
  return normalized !== "GET" && normalized !== "HEAD" && normalized !== "OPTIONS";
}

function getCookieValue(name: string): string {
  if (typeof document === "undefined") return "";
  const prefix = `${encodeURIComponent(name)}=`;
  const raw = document.cookie.split(";").map((chunk) => chunk.trim());
  const matched = raw.find((chunk) => chunk.startsWith(prefix));
  if (!matched) return "";
  return decodeURIComponent(matched.slice(prefix.length));
}

function buildHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers);
  const apiKey = getStoredApiKey();
  if (apiKey && !headers.has("x-api-key")) {
    headers.set("x-api-key", apiKey);
  }
  if (isUnsafeMethod(init?.method) && !headers.has("x-csrf-token")) {
    const csrfToken = getCookieValue(AUTH_CSRF_COOKIE_NAME).trim();
    if (csrfToken) {
      headers.set("x-csrf-token", csrfToken);
    }
  }
  return headers;
}

function shouldEmitAuthEvent(status: number, detail: string): boolean {
  if (status === 401 || status === 403) return true;
  if (status !== 503) return false;
  return detail.toLowerCase().includes("auth");
}

export function getStoredApiKey(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(API_KEY_STORAGE_KEY) ?? "";
}

export function setStoredApiKey(nextValue: string): void {
  if (typeof window === "undefined") return;
  const sanitized = nextValue.trim();
  if (sanitized.length === 0) {
    window.localStorage.removeItem(API_KEY_STORAGE_KEY);
  } else {
    window.localStorage.setItem(API_KEY_STORAGE_KEY, sanitized);
  }
  window.dispatchEvent(new Event(AUTH_KEY_UPDATED_EVENT));
}

export function clearStoredApiKey(): void {
  setStoredApiKey("");
}

export function getAuthEventName(): string {
  return AUTH_ERROR_EVENT;
}

export function getAuthKeyUpdatedEventName(): string {
  return AUTH_KEY_UPDATED_EVENT;
}

export async function apiFetch(pathOrUrl: string, init?: RequestInit): Promise<Response> {
  const url = toAbsoluteUrl(pathOrUrl);
  const response = await fetch(url, {
    ...init,
    credentials: init?.credentials ?? "include",
    headers: buildHeaders(init),
  });
  if (!response.ok) {
    const detail = await parseError(response);
    if (shouldEmitAuthEvent(response.status, detail)) {
      emitAuthError(response.status, detail);
    }
    throw new ApiClientError(detail, response.status);
  }
  return response;
}

export async function apiJson<T>(pathOrUrl: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(pathOrUrl, init);
  return (await response.json()) as T;
}
