import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiClientError,
  apiFetch,
  getAuthEventName,
  getStoredApiKey,
  setStoredApiKey,
} from "./api-client";

function buildJsonResponse(
  body: unknown,
  {
    ok = true,
    status = 200,
    statusText = "OK",
  }: { ok?: boolean; status?: number; statusText?: string } = {}
): Response {
  return {
    ok,
    status,
    statusText,
    json: async () => body,
  } as Response;
}

describe("api-client", () => {
  beforeEach(() => {
    window.localStorage.clear();
    (
      window as Window & {
        __DASHBOARD_RUNTIME_CONFIG__?: { authCsrfCookieName?: string };
      }
    ).__DASHBOARD_RUNTIME_CONFIG__ = undefined;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("injects x-api-key header when key exists", async () => {
    setStoredApiKey("abc-key");
    const fetchMock = vi.fn(async () => buildJsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/containers");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(options.headers);
    expect(headers.get("x-api-key")).toBe("abc-key");
  });

  it("uses same-origin API routes by default", async () => {
    const fetchMock = vi.fn(async () => buildJsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/containers");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/containers",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("injects csrf header from runtime-configured cookie name", async () => {
    (
      window as Window & {
        __DASHBOARD_RUNTIME_CONFIG__?: { authCsrfCookieName?: string };
      }
    ).__DASHBOARD_RUNTIME_CONFIG__ = {
      authCsrfCookieName: "dashboard_csrf_instance_b",
    };
    document.cookie = "dashboard_csrf_instance_b=csrf-token-b";
    const fetchMock = vi.fn(async () => buildJsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/containers/bulk/start", { method: "POST" });

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-token-b");
    document.cookie =
      "dashboard_csrf_instance_b=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  });

  it("defaults string request bodies to application/json", async () => {
    const fetchMock = vi.fn(async () => buildJsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/auth/2fa/enable", {
      method: "POST",
      body: JSON.stringify({ otp_code: "123456" }),
    });

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(options.headers);
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("emits auth event and throws ApiClientError on unauthorized response", async () => {
    const listener = vi.fn();
    window.addEventListener(getAuthEventName(), listener as EventListener);
    const fetchMock = vi.fn(async () =>
      buildJsonResponse(
        { detail: "Unauthorized action" },
        { ok: false, status: 401, statusText: "Unauthorized" }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/api/containers")).rejects.toBeInstanceOf(
      ApiClientError
    );
    expect(listener).toHaveBeenCalledTimes(1);
    const event = listener.mock.calls[0][0] as CustomEvent<{
      status: number;
      message: string;
    }>;
    expect(event.detail.status).toBe(401);
    expect(event.detail.message).toContain("Unauthorized");
  });

  it("clears stored key when empty value is saved", () => {
    setStoredApiKey("abc");
    expect(getStoredApiKey()).toBe("abc");
    setStoredApiKey("");
    expect(getStoredApiKey()).toBe("");
  });
});
