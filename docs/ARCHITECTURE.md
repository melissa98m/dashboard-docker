# ARCHITECTURE — Raspberry Pi Docker Dashboard

## Stack

| Composant | Choix | Justification |
|-----------|-------|---------------|
| Backend | Python FastAPI | Docker SDK Python natif, async pour stats/events, Pydantic, OpenAPI |
| Frontend | Next.js 14 (React) | App Router, responsive, mobile-first |
| Base de données | SQLite | Config, règles alertes, audit, historique commandes |
| Temps réel | SSE | Streaming stats/logs, adapté au Pi |
| Notifications | ntfy + Resend | ntfy : push self-hosted avec boutons ; Resend : emails (alertes) |

## Target
A self-hosted dashboard (LAN/VPN) to monitor and manage Docker containers running on a Raspberry Pi.
Primary client: mobile browser (responsive UI).

## Components
### 1) dashboard-api (backend)
Responsibilities:
- Docker integration (list/inspect/start/stop/restart)
- Metrics collection (CPU/RAM) via Docker Engine API stats stream
- Container events watcher (die/oom) to detect downtime; fetches last logs and sends ntfy notification with restart link
- Logs retrieval (last N lines on failure, and on-demand streaming)
- Command Center:
  - Discover runnable commands per service (scraper)
  - Execute allowlisted commands inside containers
  - Persist execution history (stdout/stderr, exit code, duration)
- Alerts:
  - Threshold rules per container (CPU%, RAM MB/%)
  - Debounce + cooldown to prevent spam
  - Notifications: ntfy (webhook + "Restart" action), Resend (emails on alert)
  - Background alert engine to auto-evaluate Docker stats on interval

Storage:
- SQLite (config + alert rules + audit log + command history)

Security:
- Auth required for any write action (restart/exec/config)
- Strict allowlist for exec (argv array, no free-form shell)
- Audit log for every action

### 2) dashboard-web (frontend)
Responsibilities:
- Containers list + filters
- Per-container page: live CPU/RAM, last logs, actions (restart, view logs)
- Alerts configuration UI (thresholds, cooldown)
- Command Center UI (discovered commands + execute + logs)
- Workflows UI: run GitHub Actions jobs locally via act (optional)
- Mobile-first UX (touch, big targets, fast load)

Real-time:
- SSE or WebSocket for live stats/logs

## Key flows
1) Monitoring
- API subscribes to stats stream and exposes aggregated metrics (throttled).
2) Downtime detection
- API listens to Docker events; on "die"/"oom" fetch last logs and trigger alert.
  - Container APIs expose failure hints (`last_down_reason`, `finished_at`) and bounded recent logs for UI diagnostics.
  - Snapshot logs are redacted by default for common secrets/PII patterns.
3) Alert + action button
- API sends ntfy message with a signed restart link (short TTL).
4) Command execution
- User selects a command spec; API starts async docker exec with argv[]; stores logs + exit code + audit entry.
5) Alert history timeline
- API exposes recent `alert_triggered` entries from audit log for operational context in `/alerts`.
6) Discovered command flow
- API discovers candidate commands per container and requires allowlist promotion before execution.
7) act (GitHub Actions local, optional)
- When `ACT_ENABLED=true`, API lists workflows from `.github/workflows` and can run jobs via act. Audit `act_job_run`.

## Non-goals (v1)
- Multi-host orchestration
- Multi-tenant users/roles beyond "single admin"
- Exposing Docker remotely without VPN/reverse-proxy auth