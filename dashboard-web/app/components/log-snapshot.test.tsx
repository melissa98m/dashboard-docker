import React from "react";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { LogSnapshot, splitLogLines } from "./log-snapshot";

describe("LogSnapshot", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it("renders log lines with numbering and count", async () => {
    await act(async () => {
      root.render(
        <LogSnapshot
          title="Derniers logs (avant arrêt)"
          subtitle="Snapshot de diagnostic"
          lines={["first line", "second line"]}
        />
      );
    });

    expect(container.textContent).toContain("Derniers logs (avant arrêt)");
    expect(container.textContent).toContain("Snapshot de diagnostic");
    expect(container.textContent).toContain("2 lignes");
    expect(container.textContent).toContain("1");
    expect(container.textContent).toContain("2");
    expect(container.textContent).toContain("first line");
    expect(container.textContent).toContain("second line");
  });

  it("renders an empty label when there are no logs", async () => {
    await act(async () => {
      root.render(
        <LogSnapshot
          title="Derniers logs (avant arrêt)"
          lines={[]}
          emptyLabel="Pas de logs capturés"
        />
      );
    });

    expect(container.textContent).toContain("0 ligne");
    expect(container.textContent).toContain("Pas de logs capturés");
  });

  it("splits multiline log payloads while preserving empty lines", () => {
    expect(splitLogLines("alpha\r\nbeta\n\ngamma")).toEqual([
      "alpha",
      "beta",
      "",
      "gamma",
    ]);
    expect(splitLogLines("")).toEqual([]);
  });
});
