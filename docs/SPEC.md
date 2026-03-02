# SPEC — Raspberry Pi Docker Dashboard (v1)

## Must-have
- Responsive UI (phone first)
- Containers list:
  - name, image, status, uptime
  - actions: start/stop/restart
- Per-container monitoring:
  - CPU% + RAM usage (live-ish)
- Alerts:
  - threshold per container (CPU/RAM)
  - cooldown/debounce
  - notification with "Restart" action
- Downtime debugging:
  - show last N log lines on down event
  - show exit code / OOM / health status if available
- Command Center:
  - discover commands from the project (per service)
  - execute command (allowlisted argv[]) in container
  - store logs + exit code + duration
  - show history

## Nice-to-have
- PWA install + push
- GitHub Actions local run button via `act`

## Acceptance criteria
- No arbitrary shell execution from user input
- Every action is authenticated + audit logged
- CPU/RAM values match docker stats within reasonable tolerance
- Alerts do not spam when CPU spikes briefly

## Security
- Default deployment is LAN/VPN only
- Docker socket never exposed
- Signed tokens for restart actions (short TTL)