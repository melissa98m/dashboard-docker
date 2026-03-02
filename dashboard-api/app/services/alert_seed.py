"""Seed default essential alert rules for running containers."""

import logging

import docker

from app.config import settings
from app.db.alerts import seed_default_rules_for_containers

logger = logging.getLogger(__name__)


def run_seed() -> int:
    """
    Discover running containers and seed essential default alert rules.
    Returns the number of rules created. Logs a warning if Docker is unavailable.
    """
    try:
        client = docker.DockerClient(base_url=settings.docker_host)
        containers = client.containers.list()
    except docker.errors.DockerException as exc:
        logger.warning("Alert seed: Docker unavailable (%s)", exc)
        return 0

    pairs = [(c.short_id, c.name) for c in containers]
    created = seed_default_rules_for_containers(pairs)
    if created > 0:
        logger.info(
            "Alert seed: created %d default rule(s) for %d container(s)",
            created,
            len(pairs),
        )
    return created
