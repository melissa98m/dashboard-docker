import React from "react";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "./page";

const apiJsonMock = vi.fn();

vi.mock("./lib/api-client", () => ({
  apiJson: (...args: unknown[]) => apiJsonMock(...args),
  apiFetch: vi.fn(),
  ApiClientError: class extends Error {
    status = 400;
    constructor(message: string) {
      super(message);
      this.name = "ApiClientError";
    }
  },
}));

vi.mock("./components/confirm-dialog", () => ({
  useConfirm: () => vi.fn().mockResolvedValue(false),
}));

vi.mock("./components/notifications", () => ({
  useNotifications: () => ({
    info: vi.fn(),
    error: vi.fn(),
    success: vi.fn(),
  }),
}));

vi.mock("./contexts/auth-context", () => ({
  useAuth: () => ({ isAdmin: true }),
}));

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

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

function setFormValue(
  element: HTMLInputElement | HTMLSelectElement,
  value: string
) {
  const prototype =
    element instanceof HTMLInputElement
      ? HTMLInputElement.prototype
      : HTMLSelectElement.prototype;
  const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
  descriptor?.set?.call(element, value);
}

describe("Dashboard", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    apiJsonMock.mockResolvedValue([]);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.clearAllMocks();
  });

  it("shows status filter tabs", async () => {
    await act(async () => {
      root.render(<DashboardPage />);
    });
    await flush();
    await flush();

    const tablist = container.querySelector('[role="tablist"]');
    expect(tablist).toBeTruthy();
    expect(tablist?.getAttribute("aria-label")).toMatch(/filtrer par statut/i);
    expect(container.textContent).toMatch(/tous/i);
    expect(container.textContent).toMatch(/en cours/i);
    expect(container.textContent).toMatch(/arrêtés/i);
  });

  it("displays empty state when no containers", async () => {
    await act(async () => {
      root.render(<DashboardPage />);
    });
    await flush();
    await flush();

    expect(container.textContent).toMatch(/aucun conteneur/i);
  });

  it("displays containers when API returns data", async () => {
    apiJsonMock.mockResolvedValue([
      {
        id: "abc123",
        name: "demo",
        image: "demo:latest",
        status: "running",
        uptime_seconds: 3600,
        finished_at: null,
        last_down_reason: null,
      },
    ]);

    await act(async () => {
      root.render(<DashboardPage />);
    });
    await flush();
    await flush();

    expect(container.textContent).toContain("demo");
    expect(container.textContent).toContain("running");
  });

  it("filters containers by search query", async () => {
    apiJsonMock.mockResolvedValue([
      {
        id: "api123",
        name: "api",
        image: "demo-api:latest",
        status: "running",
        uptime_seconds: 3600,
        finished_at: null,
        last_down_reason: null,
      },
      {
        id: "worker123",
        name: "worker",
        image: "demo-worker:latest",
        status: "exited",
        uptime_seconds: null,
        finished_at: "2026-03-01T00:00:00Z",
        last_down_reason: "exit_code_1",
      },
    ]);

    await act(async () => {
      root.render(<DashboardPage />);
    });
    await flush();
    await flush();

    const searchInput = container.querySelector(
      'input[placeholder*="Nom"]'
    ) as HTMLInputElement;
    expect(searchInput).toBeTruthy();

    await act(async () => {
      setFormValue(searchInput, "worker");
      searchInput.dispatchEvent(new Event("input", { bubbles: true }));
      searchInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flush();

    expect(container.textContent).toContain("worker");
    expect(container.textContent).not.toContain("demo-api:latest");
  });

  it("paginates containers", async () => {
    apiJsonMock.mockResolvedValue(
      Array.from({ length: 6 }, (_, index) => ({
        id: `id-${index + 1}`,
        name: `container-${index + 1}`,
        image: `image-${index + 1}`,
        status: "running",
        uptime_seconds: 60,
        finished_at: null,
        last_down_reason: null,
      }))
    );

    await act(async () => {
      root.render(<DashboardPage />);
    });
    await flush();
    await flush();

    const pageSizeSelect = container.querySelector(
      'select[aria-label="Taille de page"]'
    ) as HTMLSelectElement;
    expect(pageSizeSelect).toBeTruthy();

    await act(async () => {
      setFormValue(pageSizeSelect, "5");
      pageSizeSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flush();

    expect(container.textContent).toContain("container-5");
    expect(container.textContent).not.toContain("container-6");

    const nextButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.match(/suivant/i)
    );
    expect(nextButton).toBeTruthy();

    await act(async () => {
      nextButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();

    expect(container.textContent).toContain("container-6");
    expect(container.textContent).not.toContain("container-1");
  });
});
