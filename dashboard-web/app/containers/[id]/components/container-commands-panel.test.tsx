import React from "react";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContainerCommandsPanel } from "./container-commands-panel";

class MockEventSource {
  static instances: MockEventSource[] = [];
  closed = false;

  constructor(public readonly url: string) {
    MockEventSource.instances.push(this);
  }

  addEventListener(_type: string, _callback: (event?: Event) => void) {}

  close() {
    this.closed = true;
  }
}

function buildJsonResponse(body: unknown): Response {
  return {
    ok: true,
    statusText: "OK",
    json: async () => body,
  } as Response;
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe("ContainerCommandsPanel", () => {
  let container: HTMLDivElement;
  let root: Root;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource as unknown as typeof EventSource);

    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/containers/abc123/commands/specs")) {
        return buildJsonResponse([
          { id: 1, container_id: "abc123", service_name: "api", name: "Run tests", argv: ["pytest", "-q"] },
        ]);
      }
      if (url.includes("/api/containers/abc123/commands/discovered")) {
        return buildJsonResponse([
          {
            id: 2,
            container_id: "abc123",
            service_name: "api",
            name: "npm test",
            argv: ["npm", "test"],
            source: "npm",
          },
        ]);
      }
      if (url.includes("/api/containers/abc123/commands/executions")) {
        return buildJsonResponse([
          {
            id: 10,
            command_spec_id: 1,
            container_id: "abc123",
            status: "success",
            started_at: "2026-01-01T00:00:00Z",
            finished_at: "2026-01-01T00:00:03Z",
            exit_code: 0,
            duration_ms: 3000,
            triggered_by: "ui",
          },
        ]);
      }
      if (url.includes("/api/commands/discover")) {
        expect(init?.method).toBe("POST");
        const body = JSON.parse(String(init?.body));
        expect(body.container_id).toBe("abc123");
        return buildJsonResponse({
          container_id: "abc123",
          service_name: "api",
          discovered_count: 2,
          cached: false,
          cache_age_seconds: 0,
        });
      }
      if (url.includes("/api/commands/execute")) {
        expect(init?.method).toBe("POST");
        const body = JSON.parse(String(init?.body));
        expect(body.container_id).toBe("abc123");
        return buildJsonResponse({ execution_id: 11 });
      }
      if (url.includes("/api/commands/executions/11/stream-token")) {
        return buildJsonResponse({ token: "stream-token-123" });
      }
      if (url.includes("/api/commands/executions/11")) {
        return buildJsonResponse({
          id: 11,
          command_spec_id: 1,
          container_id: "abc123",
          status: "running",
          started_at: "2026-01-01T00:00:05Z",
          finished_at: null,
          exit_code: null,
          duration_ms: null,
          triggered_by: "ui",
          stdout_tail: "line out",
          stderr_tail: "",
        });
      }
      return buildJsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads container commands and executes with scoped container id", async () => {
    await act(async () => {
      root.render(<ContainerCommandsPanel containerId="abc123" />);
    });
    await flush();
    await flush();

    expect(container.textContent).toContain("Run tests");
    expect(container.textContent).toContain("npm test");

    const runButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("Exécuter")
    );
    expect(runButton).toBeTruthy();

    await act(async () => {
      runButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();

    const executeCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes("/api/commands/execute")
    );
    expect(executeCalls.length).toBe(1);
    expect(MockEventSource.instances.length).toBe(1);
  });

  it("can trigger command discovery scan from container detail", async () => {
    await act(async () => {
      root.render(<ContainerCommandsPanel containerId="abc123" />);
    });
    await flush();
    await flush();

    const scanButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("Scanner")
    );
    expect(scanButton).toBeTruthy();

    await act(async () => {
      scanButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();

    const discoverCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes("/api/commands/discover")
    );
    expect(discoverCalls.length).toBe(1);
    expect(container.textContent).toContain("commande(s) détectée(s)");
  });
});
