import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import CommandsLivePage from "./live/page";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("execution=42"),
}));

class MockEventSource {
  static instances: MockEventSource[] = [];
  private listeners = new Map<string, Array<(event?: Event) => void>>();
  closed = false;

  constructor(public readonly url: string) {
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, callback: (event?: Event) => void) {
    const handlers = this.listeners.get(type) ?? [];
    handlers.push(callback);
    this.listeners.set(type, handlers);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, event?: Event) {
    const handlers = this.listeners.get(type) ?? [];
    handlers.forEach((handler) => handler(event));
  }
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

function buildJsonResponse(body: unknown): Response {
  return {
    ok: true,
    statusText: "OK",
    json: async () => body,
  } as Response;
}

describe("Commands live page stream reconnect flow", () => {
  let container: HTMLDivElement;
  let root: Root;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    MockEventSource.instances = [];
    vi.stubGlobal(
      "EventSource",
      MockEventSource as unknown as typeof EventSource
    );

    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/containers")) {
        return buildJsonResponse([
          {
            id: "abc123",
            name: "web",
          },
        ]);
      }
      if (url.includes("/api/commands/specs")) {
        return buildJsonResponse([]);
      }
      if (url.includes("/api/commands/executions")) {
        return buildJsonResponse([
          {
            id: 42,
            command_spec_id: 1,
            container_id: "abc123",
            started_at: "2026-01-01T00:00:00Z",
            finished_at: null,
            exit_code: null,
            triggered_by: "ui",
            stdout_path: "/tmp/stdout.log",
            stderr_path: "/tmp/stderr.log",
          },
        ]);
      }
      if (url.includes("/api/commands/executions/42/stream-token")) {
        return buildJsonResponse({ token: "valid-stream-token-12345" });
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

  it("shows reconnect button after repeated stream errors and reconnects on click", async () => {
    await act(async () => {
      root.render(<CommandsLivePage />);
    });
    await flush();
    await flush();

    expect(MockEventSource.instances.length).toBe(1);
    const source = MockEventSource.instances[0];

    for (let i = 0; i < 6; i += 1) {
      await act(async () => {
        source.emit("error");
      });
    }
    await flush();

    expect(container.textContent).toContain("etat: error");
    const reconnectButton = Array.from(
      container.querySelectorAll("button")
    ).find((button) => button.textContent?.includes("Reconnecter"));
    expect(reconnectButton).toBeTruthy();

    await act(async () => {
      reconnectButton?.dispatchEvent(
        new MouseEvent("click", { bubbles: true })
      );
    });
    await flush();

    expect(MockEventSource.instances.length).toBe(2);
    const streamTokenCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes("/api/commands/executions/42/stream-token")
    );
    expect(streamTokenCalls.length).toBeGreaterThanOrEqual(2);
  });
});
