"""Container env management helpers."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import docker

ENV_KEY_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
SENSITIVE_KEY_PATTERN = re.compile(r"(token|secret|password|api[_-]?key|pwd|auth)", re.IGNORECASE)
MAX_ENV_VALUE_LENGTH = 4000


def is_sensitive_key(key: str) -> bool:
    return bool(SENSITIVE_KEY_PATTERN.search(key))


def validate_env_key(key: str) -> None:
    if not ENV_KEY_PATTERN.match(key):
        raise ValueError(f"Invalid env key: {key}")


def validate_env_value(value: str) -> None:
    if "\n" in value or "\r" in value:
        raise ValueError("Multiline env values are not supported")
    if len(value) > MAX_ENV_VALUE_LENGTH:
        raise ValueError("Env value is too long")


def parse_env_list(items: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if not key:
            continue
        parsed[key] = value
    return parsed


def parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            env[key] = value
    return env


def write_env_file_atomic(path: Path, env: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = [f"{key}={value}" for key, value in sorted(env.items(), key=lambda item: item[0])]
    with NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as tmp:
        tmp.write("\n".join(ordered))
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def detect_env_file(container: Any) -> tuple[str | None, bool, list[str]]:
    attrs = getattr(container, "attrs", {}) or {}
    candidates: list[str] = []
    labels = attrs.get("Config", {}).get("Labels", {}) if isinstance(attrs, dict) else {}
    if isinstance(labels, dict):
        working_dir = labels.get("com.docker.compose.project.working_dir")
        if isinstance(working_dir, str) and working_dir.strip():
            candidates.append(str(Path(working_dir) / ".env"))
    mounts = attrs.get("Mounts", []) if isinstance(attrs, dict) else []
    if isinstance(mounts, list):
        for mount in mounts:
            if not isinstance(mount, dict):
                continue
            source = mount.get("Source")
            destination = mount.get("Destination")
            if isinstance(source, str) and isinstance(destination, str):
                if destination in {"/app", "/workspace"}:
                    candidates.append(str(Path(source) / ".env"))
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            deduped.append(candidate)
    for candidate in deduped:
        path = Path(candidate)
        if path.exists() and path.is_file():
            writable = os.access(path, os.W_OK)
            return str(path), writable, deduped
    return None, False, deduped


def merge_env(
    *,
    current: dict[str, str],
    updates: dict[str, str],
    unset: list[str],
    mode: str,
) -> dict[str, str]:
    for key in updates:
        validate_env_key(key)
        validate_env_value(updates[key])
    for key in unset:
        validate_env_key(key)
    if mode not in {"merge", "replace"}:
        raise ValueError("Mode must be merge or replace")
    merged = dict(current) if mode == "merge" else {}
    for key, value in updates.items():
        merged[key] = value
    for key in unset:
        merged.pop(key, None)
    return merged


def recreate_container_with_env(
    *,
    client: docker.DockerClient,
    container: Any,
    env: dict[str, str],
) -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    attrs = getattr(container, "attrs", {}) or {}
    config = attrs.get("Config", {}) if isinstance(attrs, dict) else {}
    host_config = attrs.get("HostConfig", {}) if isinstance(attrs, dict) else {}
    image = config.get("Image")
    if not isinstance(image, str) or not image.strip():
        raise ValueError("Container image is unavailable")

    env_list = [f"{key}={value}" for key, value in sorted(env.items(), key=lambda item: item[0])]
    original_name = str(getattr(container, "name", "")).lstrip("/")
    if not original_name:
        raise ValueError("Container name is unavailable")

    timestamp = int(time.time())
    old_name = f"{original_name}-old-{timestamp}"
    temp_name = f"{original_name}-new-{timestamp}"
    created_id: str | None = None
    renamed_old = False
    stopped_old = False
    started_new = False

    api = getattr(client, "api", None)
    if api is None:
        raise ValueError("Docker API client unavailable")
    created_host_config = api.create_host_config(
        binds=host_config.get("Binds"),
        port_bindings=host_config.get("PortBindings"),
        restart_policy=host_config.get("RestartPolicy"),
        network_mode=host_config.get("NetworkMode"),
        privileged=host_config.get("Privileged"),
        cap_add=host_config.get("CapAdd"),
        cap_drop=host_config.get("CapDrop"),
        extra_hosts=host_config.get("ExtraHosts"),
    )
    try:
        created = api.create_container(
            image=image,
            command=config.get("Cmd"),
            hostname=config.get("Hostname"),
            user=config.get("User"),
            detach=True,
            name=temp_name,
            environment=env_list,
            host_config=created_host_config,
            working_dir=config.get("WorkingDir"),
            labels=config.get("Labels"),
            entrypoint=config.get("Entrypoint"),
            tty=config.get("Tty"),
            stdin_open=config.get("OpenStdin"),
        )
        created_id = (
            str(created.get("Id")) if isinstance(created, dict) and created.get("Id") else None
        )
        if created_id is None:
            raise ValueError("Unable to create replacement container")
        container.stop()
        stopped_old = True
        container.rename(old_name)
        renamed_old = True
        api.start(created_id)
        started_new = True
        new_container = client.containers.get(created_id)
        new_container.rename(original_name)
        if hasattr(container, "remove"):
            container.remove(v=False, force=True)
        return str(getattr(new_container, "short_id", created_id)), warnings
    except Exception as exc:  # noqa: BLE001
        if started_new and created_id is not None:
            try:
                api.stop(created_id)
            except Exception:  # noqa: BLE001
                warnings.append("Could not stop replacement container during rollback")
            try:
                api.remove_container(created_id, force=True)
            except Exception:  # noqa: BLE001
                warnings.append("Could not remove replacement container during rollback")
        if renamed_old:
            try:
                container.rename(original_name)
            except Exception:  # noqa: BLE001
                warnings.append("Could not restore original container name")
        if stopped_old:
            try:
                container.start()
            except Exception:  # noqa: BLE001
                warnings.append("Could not restart original container during rollback")
        raise ValueError(f"Recreate failed: {exc}") from exc


def load_runtime_env(container: Any) -> dict[str, str]:
    attrs = getattr(container, "attrs", {}) or {}
    config = attrs.get("Config", {}) if isinstance(attrs, dict) else {}
    raw_env = config.get("Env", []) if isinstance(config, dict) else []
    if not isinstance(raw_env, list):
        return {}
    return parse_env_list([item for item in raw_env if isinstance(item, str)])
