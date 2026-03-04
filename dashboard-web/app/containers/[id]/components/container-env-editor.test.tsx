import React from "react";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContainerEnvEditor } from "./container-env-editor";

const getContainerEnvProfile = vi.fn();
const updateContainerEnvProfile = vi.fn();
const applyContainerEnvProfile = vi.fn();

vi.mock("../../../lib/container-env-api", () => ({
  getContainerEnvProfile: (...args: unknown[]) =>
    getContainerEnvProfile(...args),
  updateContainerEnvProfile: (...args: unknown[]) =>
    updateContainerEnvProfile(...args),
  applyContainerEnvProfile: (...args: unknown[]) =>
    applyContainerEnvProfile(...args),
}));

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value"
  )?.set;
  if (setter) {
    setter.call(input, value);
  } else {
    input.value = value;
  }
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("ContainerEnvEditor", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    getContainerEnvProfile.mockResolvedValue({
      container_id: "abc123",
      source_mode: "db_fallback",
      detected_env_file: null,
      writable: true,
      pending_apply: true,
      last_detect_status: null,
      last_apply_status: null,
      updated_at: null,
      env: [
        { key: "FOO", value: "bar", sensitive: false },
        { key: "SECRET_TOKEN", value: "secret", sensitive: true },
      ],
    });
    updateContainerEnvProfile.mockResolvedValue({
      container_id: "abc123",
      source_mode: "db_fallback",
      detected_env_file: null,
      writable: true,
      pending_apply: true,
      last_detect_status: "env_updated",
      last_apply_status: "pending",
      updated_at: "2026-02-28T10:00:00Z",
      env: [
        { key: "FOO", value: "new", sensitive: false },
        { key: "SECRET_TOKEN", value: "secret", sensitive: true },
      ],
    });
    applyContainerEnvProfile.mockResolvedValue({
      ok: true,
      strategy: "recreate",
      message: "ok",
      old_container_id: "abc123",
      new_container_id: "new123",
      warnings: [],
    });
    vi.stubGlobal(
      "confirm",
      vi.fn(() => true)
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.restoreAllMocks();
  });

  it("masks sensitive values and applies after confirmation", async () => {
    await act(async () => {
      root.render(<ContainerEnvEditor containerId="abc123" />);
    });
    await flush();
    expect(getContainerEnvProfile).toHaveBeenCalledWith("abc123");

    const toggleButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("Afficher")
    );
    expect(toggleButton).toBeTruthy();

    const inputs = Array.from(container.querySelectorAll("input"));
    const fooInput = inputs.find(
      (input) => (input as HTMLInputElement).value === "bar"
    );
    expect(fooInput).toBeTruthy();
    await act(async () => {
      setInputValue(fooInput as HTMLInputElement, "new");
    });
    await flush();

    const saveButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("Sauvegarder le brouillon")
    );
    expect(saveButton).toBeTruthy();
    await act(async () => {
      saveButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();
    expect(updateContainerEnvProfile).toHaveBeenCalled();

    const applyButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("Appliquer (recreate)")
    );
    expect(applyButton).toBeTruthy();
    await act(async () => {
      applyButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();
    expect(applyContainerEnvProfile).toHaveBeenCalledWith("abc123", false);
  });
});
