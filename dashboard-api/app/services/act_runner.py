"""act runner: list workflows and run jobs locally."""

import io
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path


def is_act_available() -> bool:
    """Check if act binary is installed and in PATH."""
    return shutil.which("act") is not None


def list_workflow_jobs(workflows_path: str) -> list[dict[str, str]]:
    """
    Parse .github/workflows/*.yml to extract workflow name and job names.
    Returns list of {workflow, workflow_file, job}.
    """
    base = Path(workflows_path)
    workflows_dir = base / ".github" / "workflows"
    if not workflows_dir.exists():
        return []

    jobs: list[dict[str, str]] = []
    for fp in sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml")):
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Extract workflow name from "name: X" at top level
        name_match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
        wf_name = name_match.group(1).strip().strip("'\"").strip() if name_match else fp.stem

        # Find jobs section and extract job names (keys directly under jobs:)
        jobs_match = re.search(r"^jobs:\s*$(.*?)(?=\n\S|\Z)", content, re.MULTILINE | re.DOTALL)
        if not jobs_match:
            continue
        jobs_block = jobs_match.group(1)
        for m in re.finditer(r"^\s{2}([a-zA-Z0-9_-]+)\s*:", jobs_block, re.MULTILINE):
            job_name = m.group(1)
            jobs.append(
                {
                    "workflow": wf_name,
                    "workflow_file": fp.name,
                    "job": job_name,
                }
            )

    return jobs


def _get_docker_client():
    import docker

    from app.config import settings

    return docker.DockerClient(base_url=settings.docker_host)


def extract_workflows_from_container(container_id: str) -> str:
    """
    Copy .github/workflows from container to /tmp/act-{id}. Returns path for act.
    Tries common paths: /app/.github, /workspace/.github, /.github
    """
    client = _get_docker_client()
    try:
        container = client.containers.get(container_id)
    except Exception as exc:
        raise ValueError(f"Container {container_id} not found: {exc}") from exc

    candidates = ["/app/.github", "/workspace/.github", "/.github", "/app"]
    dest = Path("/tmp") / f"act-{container_id[:12]}"
    dest.mkdir(parents=True, exist_ok=True)

    for src in candidates:
        try:
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            dest.mkdir(parents=True, exist_ok=True)
            stream, _ = container.get_archive(src)
            buf = io.BytesIO(b"".join(stream))
            with tarfile.open(fileobj=buf, mode="r") as tar:
                tar.extractall(dest)
            github_wf = dest / ".github" / "workflows"
            if github_wf.exists() and list(github_wf.glob("*.yml")):
                return str(dest)
            github_alt = dest / "github" / "workflows"
            if github_alt.exists():
                (dest / ".github").mkdir(parents=True, exist_ok=True)
                shutil.move(str(dest / "github"), str(dest / ".github"))
                return str(dest)
            for wf_dir in dest.rglob("workflows"):
                if wf_dir.is_dir() and list(wf_dir.glob("*.yml")):
                    target = dest / ".github" / "workflows"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(wf_dir, target)
                    return str(dest)
        except Exception:
            continue

    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    raise ValueError(f"No .github/workflows found in container {container_id}")


def get_workflows_path(container_id: str | None) -> str:
    """Resolve workflows path: from container if provided, else default."""
    if not container_id or not container_id.strip():
        from app.config import settings

        return settings.act_workflows_path
    return extract_workflows_from_container(container_id.strip())


def run_act_job(
    workflows_path: str,
    job_name: str,
    *,
    workflow_file: str | None = None,
    env: dict | None = None,
) -> subprocess.Popen:
    """
    Run act -j job_name in workflows_path. Returns Popen for streaming stdout/stderr.
    workflow_file: e.g. 'ci.yml' to target a specific workflow when job names overlap.
    """
    base = Path(workflows_path)
    if workflow_file:
        wf_path = base / ".github" / "workflows" / workflow_file
        cmd = ["act", "-j", job_name, "-W", str(wf_path)]
    else:
        cmd = ["act", "-j", job_name]
    # Mount Docker socket into job containers so make lint-ci/build can run docker compose
    cmd.extend(["--container-options", "--volume /var/run/docker.sock:/var/run/docker.sock"])
    # Preserve DOCKER_HOST and PATH so act can reach Docker
    proc_env = dict(os.environ)
    proc_env.update(env or {})
    proc_env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    return subprocess.Popen(
        cmd,
        cwd=workflows_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=proc_env,
    )
