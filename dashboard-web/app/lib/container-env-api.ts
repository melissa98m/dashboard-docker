"use client";

import { apiJson } from "./api-client";

export interface EnvVarItem {
  key: string;
  value: string;
  sensitive: boolean;
}

export interface EnvProfileResponse {
  container_id: string;
  source_mode: string;
  detected_env_file: string | null;
  writable: boolean;
  pending_apply: boolean;
  last_detect_status: string | null;
  last_apply_status: string | null;
  updated_at: string | null;
  env: EnvVarItem[];
}

interface EnvProfileUpdateRequest {
  mode: "merge" | "replace";
  set: Record<string, string>;
  unset: string[];
}

interface EnvApplyResponse {
  ok: boolean;
  strategy: string;
  message: string;
  old_container_id: string;
  new_container_id: string | null;
  warnings: string[];
}

export async function getContainerEnvProfile(
  containerId: string
): Promise<EnvProfileResponse> {
  return apiJson<EnvProfileResponse>(
    `/api/containers/${encodeURIComponent(containerId)}/env/profile`
  );
}

export async function updateContainerEnvProfile(
  containerId: string,
  payload: EnvProfileUpdateRequest
): Promise<EnvProfileResponse> {
  return apiJson<EnvProfileResponse>(
    `/api/containers/${encodeURIComponent(containerId)}/env/profile`,
    {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export async function applyContainerEnvProfile(
  containerId: string,
  dryRun = false
): Promise<EnvApplyResponse> {
  return apiJson<EnvApplyResponse>(
    `/api/containers/${encodeURIComponent(containerId)}/env/apply`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ dry_run: dryRun }),
    }
  );
}
