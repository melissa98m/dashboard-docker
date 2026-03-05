# DEV — Exécution & conventions (Docker-first)

## Local / Raspberry Pi requirements
- Docker + Docker Compose
- A reverse proxy OR VPN access (recommended: Tailscale/WireGuard) for phone access
- Do not expose Docker socket publicly

## Quickstart
- Config: `cp .env.example .env`
- Start: `make up` ou `docker compose up -d`
- Logs: `make logs` ou `docker compose logs -f --tail=200`
- Mode dev (logs attachés + hot reload web, sans rebuild à chaque changement): `make dev`
- Shell (api): `make shell-api` ou `docker compose exec dashboard-api sh`
- Shell (web): `make shell-web` ou `docker compose exec dashboard-web sh`

## Standard commands (must exist)
- Lint: `make lint` (nécessite `make up` pour exec) ; `make lint-ci` (CI, sans stack démarrée)
- Tests: `make test` ; CI: `make test-ci` (fail-fast, sortie concise)
- E2E: `make test-e2e` — exécution Docker-first via service Playwright dédié (`dashboard-e2e`), sans dépendance Node/npm sur l’hôte. La commande démarre automatiquement `dashboard-api` + `dashboard-web`. Creds optionnels (`E2E_USERNAME`, `E2E_PASSWORD`) pour les tests authentifiés.
- Format: `make format` ; vérif: `make format-check` (CI)
- Build: `make build`
- Purge audit logs: `make purge-audit`
- Restart: `make restart`
- Rebuild explicite en mode normal: `make up-build`
- Rebuild explicite en mode dev: `make dev-build`
- État conteneurs: `make ps`
- Sauvegarde DB: `make db-backup` (services démarrés requis)
- Nettoyage cache Docker: `make clean`
- Health check (monitoring externe): `make health-check` — utilise `API_URL` (défaut: http://localhost:8000) pour appeler `/health`

## Notes
- Any change that adds dependencies must be proposed and validated first.
- Any docker exec feature must be allowlisted + audited.
- Auth stricte : `AUTH_ENABLED=true` (session cookies + CSRF). Toute l’API requiert une session valide sauf `/api/auth/login`, `/api/auth/login/verify-2fa` et `/health`.
- Tune `SSE_MAX_CONNECTIONS` for Raspberry Pi capacity.
- Alert auto-evaluation runs in background (`ALERT_ENGINE_ENABLED=true`) every `ALERT_POLL_SECONDS`.
- Event watcher (`EVENT_WATCHER_ENABLED=true`) listens to Docker container die/oom events; on detection, fetches last logs, writes audit, sends ntfy notification with restart link. Optional topic override: `EVENT_WATCHER_NTFY_TOPIC`. Status visible in `GET /api/system/security-status` (`event_watcher_enabled`, `event_watcher_running`).
- ntfy notifications are optional and only active when `NTFY_BASE_URL` + `NTFY_TOPIC` are set.
- Resend email alerts are optional and active when `RESEND_API_KEY` + `ALERT_EMAIL_FROM` + `ALERT_EMAIL_TO` are set. Domaine vérifié requis sur resend.com.
- Default alert rules (CPU 90%, RAM 90%) are auto-seeded at API startup for each running container.
- To enable signed restart action links, set `API_SECRET_KEY` + `PUBLIC_API_URL` (and tune `RESTART_ACTION_TTL_SECONDS`).
- Restart token endpoint is rate-limited with `RESTART_TOKEN_RATE_LIMIT_WINDOW_SECONDS` / `RESTART_TOKEN_RATE_LIMIT_MAX_ATTEMPTS`.
- Command execution SSE stream supports short-lived one-time query tokens via `EXECUTION_STREAM_TOKEN_TTL_SECONDS`.
- Audit retention is configured with `AUDIT_RETENTION_DAYS` and can be purged via API/CLI.
- Automatic audit purge service can be configured with `AUDIT_RETENTION_AUTO_ENABLED` and `AUDIT_RETENTION_POLL_SECONDS`.
- Ops endpoints: `GET /api/system/version` and `GET /api/system/health/deps` (both use read auth policy).
- Container detail (`GET /api/containers/{id}`) inclut `last_down_reason` + `finished_at` pour diagnostic d'arrêt.
- Le snapshot `last_logs` est borné côté backend (max 200 lignes) pour limiter la volumétrie et le risque de fuite.
- Le snapshot de logs masque par défaut certains secrets/PII (`LOG_SNAPSHOT_REDACTION_ENABLED=true`).
- Règles custom possibles via `LOG_SNAPSHOT_REDACTION_EXTRA_PATTERNS` (regex séparées par `||`).
- La page `/settings` affiche un aperçu non sensible: état redaction, règles par défaut actives, nombre de règles custom.
- `/api/system/security-status` expose aussi `runtime_config_loaded_at` (horodatage du chargement config au démarrage API).
- L'écran `/alerts` permet un redémarrage manuel du conteneur lié à une règle via `POST /api/alerts/rules/{id}/restart-container` (write auth + audit).
- L'écran `/alerts` affiche l'historique récent des déclenchements via `GET /api/alerts/history` (source: audit log `alert_triggered`).
- `GET /api/alerts/history` supporte des filtres (`container_id`, `metric_type`, `since_hours`, `triggered_by=all|manual|alert-engine`) + pagination (`limit`, `offset`) + tri (`sort=created_at_desc|created_at_asc`) et retourne aussi `total`.
- Les règles d'alerte supportent `debounce_samples` (défaut 1): nombre de dépassements consécutifs requis avant déclenchement.
- Dashboard web supporte la suppression sûre d'un conteneur: stop puis `DELETE /api/containers/{id}?force=false&volumes=false` avec confirmation.
- Command Center supporte la découverte commandes par conteneur:
  - `POST /api/commands/discover` (scan explicite)
  - `GET /api/commands/discovered` (liste filtrable/paginée)
  - `POST /api/commands/discovered/{id}/allowlist` (promotion en spec)
- Lancement direct côté UI: `Valider et lancer` (allowlist puis `POST /api/commands/execute`).
- **act** (GitHub Actions local): `ACT_ENABLED=true` + volume `.:/workspace`. UI `/workflows` liste les jobs des `.github/workflows/*.yml` et permet d'exécuter un job via `act -j <job>`. Audit `act_job_run`.
- Discovery applique un cache TTL (`COMMAND_DISCOVERY_CACHE_TTL_SECONDS`), contournable avec `force=true` (UI: case “Scan forcé”).
