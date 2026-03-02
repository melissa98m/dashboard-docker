"""act runner: list workflows and run jobs locally."""

import re
import shutil
import subprocess
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
    proc_env = {**(env or {}), "PATH": "/usr/local/bin:/usr/bin:/bin"}
    return subprocess.Popen(
        cmd,
        cwd=workflows_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=proc_env,
    )
