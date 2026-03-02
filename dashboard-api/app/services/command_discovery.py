"""Best-effort command discovery from known project files."""

from __future__ import annotations

import json
import re
import tomllib
from typing import Any


def _service_name(container: Any) -> str:
    raw_name = str(getattr(container, "name", "container"))
    return raw_name.lstrip("/") or "container"


def _exec(container: Any, cmd: list[str], *, workdir: str | None = None) -> tuple[int, str]:
    result = container.exec_run(cmd=cmd, workdir=workdir, demux=True)
    stdout_bytes = b""
    stderr_bytes = b""
    if result.output:
        stdout_bytes, stderr_bytes = result.output
    output = (stdout_bytes or b"").decode("utf-8", errors="replace")
    if not output:
        output = (stderr_bytes or b"").decode("utf-8", errors="replace")
    return int(result.exit_code if result.exit_code is not None else 1), output


def _read_file(container: Any, candidates: list[str]) -> tuple[str | None, str]:
    for path in candidates:
        code, output = _exec(container, ["cat", path])
        if code == 0 and output:
            return path, output
    return None, ""


def _discover_package_scripts(container: Any) -> list[dict[str, Any]]:
    path, content = _read_file(container, ["/app/package.json", "package.json"])
    if path is None:
        return []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return []
    commands: list[dict[str, Any]] = []
    for script_name in scripts.keys():
        if not isinstance(script_name, str) or not script_name.strip():
            continue
        commands.append(
            {
                "name": f"npm:{script_name}",
                "argv": ["npm", "run", script_name],
                "cwd": "/app",
                "source": "package.json",
            }
        )
    return commands


def _discover_make_targets(container: Any) -> list[dict[str, Any]]:
    path, content = _read_file(container, ["/app/Makefile", "Makefile"])
    if path is None:
        return []
    commands: list[dict[str, Any]] = []
    for line in content.splitlines():
        if line.startswith("\t") or line.startswith("."):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*", line)
        if not match:
            continue
        target = match.group(1)
        if target == "default":
            continue
        commands.append(
            {
                "name": f"make:{target}",
                "argv": ["make", target],
                "cwd": "/app",
                "source": "Makefile",
            }
        )
    return commands


def _discover_poetry_scripts(container: Any) -> list[dict[str, Any]]:
    path, content = _read_file(container, ["/app/pyproject.toml", "pyproject.toml"])
    if path is None:
        return []
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return []
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return []
    poetry = tool.get("poetry")
    if not isinstance(poetry, dict):
        return []
    scripts = poetry.get("scripts")
    if not isinstance(scripts, dict):
        return []
    commands: list[dict[str, Any]] = []
    for script_name in scripts.keys():
        if not isinstance(script_name, str) or not script_name.strip():
            continue
        commands.append(
            {
                "name": f"poetry:{script_name}",
                "argv": ["poetry", "run", script_name],
                "cwd": "/app",
                "source": "pyproject.toml",
            }
        )
    return commands


def _discover_manage_py(container: Any) -> list[dict[str, Any]]:
    manage_path: str | None = None
    cwd = "/app"
    code, _ = _exec(container, ["cat", "/app/manage.py"])
    if code == 0:
        manage_path = "/app/manage.py"
    else:
        code, _ = _exec(container, ["cat", "manage.py"], workdir="/app")
        if code == 0:
            manage_path = "manage.py"
        else:
            return []

    discovered: list[dict[str, Any]] = []
    for python_bin in ("python", "python3"):
        help_code, output = _exec(
            container,
            [python_bin, manage_path, "help", "--commands"],
            workdir=cwd,
        )
        if help_code != 0:
            continue
        for line in output.splitlines():
            command_name = line.strip()
            if not command_name:
                continue
            if " " in command_name or command_name.startswith("-"):
                continue
            discovered.append(
                {
                    "name": f"django:{command_name}",
                    "argv": [python_bin, manage_path, command_name],
                    "cwd": cwd,
                    "source": "manage.py",
                }
            )
        # Always expose safe base commands even if parsing is partial.
        discovered.extend(
            [
                {
                    "name": "django:showmigrations",
                    "argv": [python_bin, manage_path, "showmigrations"],
                    "cwd": cwd,
                    "source": "manage.py:base",
                },
                {
                    "name": "django:migrate",
                    "argv": [python_bin, manage_path, "migrate"],
                    "cwd": cwd,
                    "source": "manage.py:base",
                },
                {
                    "name": "django:check",
                    "argv": [python_bin, manage_path, "check"],
                    "cwd": cwd,
                    "source": "manage.py:base",
                },
            ]
        )
        return discovered
    return discovered


def _discover_symfony_console(container: Any) -> list[dict[str, Any]]:
    console_path: str | None = None
    cwd = "/app"
    code, _ = _exec(container, ["cat", "/app/bin/console"])
    if code == 0:
        console_path = "/app/bin/console"
    else:
        code, _ = _exec(container, ["cat", "bin/console"], workdir="/app")
        if code == 0:
            console_path = "bin/console"
        else:
            return []

    discovered: list[dict[str, Any]] = []
    # --raw gives one command per line on Symfony CLI.
    list_code, output = _exec(container, ["php", console_path, "list", "--raw"], workdir=cwd)
    if list_code == 0:
        for line in output.splitlines():
            command_name = line.strip()
            if not command_name:
                continue
            if " " in command_name:
                command_name = command_name.split(" ", maxsplit=1)[0]
            discovered.append(
                {
                    "name": f"symfony:{command_name}",
                    "argv": ["php", console_path, command_name],
                    "cwd": cwd,
                    "source": "bin/console",
                }
            )
    # Always expose common base commands.
    discovered.extend(
        [
            {
                "name": "symfony:cache:clear",
                "argv": ["php", console_path, "cache:clear"],
                "cwd": cwd,
                "source": "bin/console:base",
            },
            {
                "name": "symfony:cache:warmup",
                "argv": ["php", console_path, "cache:warmup"],
                "cwd": cwd,
                "source": "bin/console:base",
            },
            {
                "name": "symfony:debug:router",
                "argv": ["php", console_path, "debug:router"],
                "cwd": cwd,
                "source": "bin/console:base",
            },
        ]
    )
    return discovered


def _discover_composer_scripts(container: Any) -> list[dict[str, Any]]:
    path, content = _read_file(container, ["/app/composer.json", "composer.json"])
    if path is None:
        return []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return []
    commands: list[dict[str, Any]] = []
    for script_name in scripts.keys():
        if not isinstance(script_name, str) or not script_name.strip():
            continue
        commands.append(
            {
                "name": f"composer:{script_name}",
                "argv": ["composer", script_name],
                "cwd": "/app",
                "source": "composer.json",
            }
        )
    return commands


def _discover_python_cli(container: Any) -> list[dict[str, Any]]:
    """Discover commands from Python CLI modules (e.g. app.cli)."""
    path, _ = _read_file(container, ["/app/app/cli.py", "app/cli.py"])
    if path is None:
        return []
    cwd = "/app"
    commands: list[dict[str, Any]] = []
    for python_bin in ("python", "python3"):
        code, output = _exec(
            container,
            [python_bin, "-m", "app.cli"],
            workdir=cwd,
        )
        # CLI with no args typically exits 1 and prints usage to stdout
        if code != 0 and not output:
            continue
        # Parse "Usage: ... migrate | purge-audit [days] | create-user ..." for subcommands
        usage_match = re.search(
            r"Usage:.*?app\.cli\s+([^\n]+)",
            output,
            re.IGNORECASE | re.DOTALL,
        )
        if not usage_match:
            continue
        usage_line = usage_match.group(1)
        # Extract subcommand names: migrate, purge-audit, create-user (first word of each | block)
        for part in usage_line.split("|"):
            part = part.strip()
            if not part or part.startswith("--") or part.startswith("["):
                continue
            first = part.split(None, 1)[0]
            if not first or "]" in first or ":" in first or first.startswith("<"):
                continue
            if first[0].isalnum() and len(first) >= 2:
                commands.append(
                    {
                        "name": f"cli:{first}",
                        "argv": [python_bin, "-m", "app.cli", first],
                        "cwd": cwd,
                        "source": "app.cli",
                    }
                )
        if commands:
            break
    return commands


def discover_commands(container: Any) -> tuple[str, list[dict[str, Any]]]:
    """Discover runnable commands for one container."""
    service_name = _service_name(container)
    discovered: list[dict[str, Any]] = []
    discovered.extend(_discover_package_scripts(container))
    discovered.extend(_discover_make_targets(container))
    discovered.extend(_discover_poetry_scripts(container))
    discovered.extend(_discover_manage_py(container))
    discovered.extend(_discover_composer_scripts(container))
    discovered.extend(_discover_symfony_console(container))
    discovered.extend(_discover_python_cli(container))

    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for item in discovered:
        argv = item.get("argv")
        name = item.get("name")
        if not isinstance(argv, list) or not isinstance(name, str):
            continue
        normalized_argv = tuple(str(arg) for arg in argv if str(arg).strip())
        if not normalized_argv:
            continue
        key = (name, normalized_argv)
        if key in seen:
            continue
        seen.add(key)
        unique.append(
            {
                "name": name,
                "argv": list(normalized_argv),
                "cwd": item.get("cwd"),
                "source": item.get("source", "unknown"),
            }
        )
    return service_name, unique
