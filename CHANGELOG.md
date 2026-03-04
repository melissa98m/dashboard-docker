# Changelog

Toutes les modifications notables du projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et le projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

### Ajouté

- (changements en cours, non encore publiés)

## [0.1.0] — 2025

### Ajouté

- Dashboard Docker pour Raspberry Pi (mobile-first)
- Liste des conteneurs avec statut, uptime, actions start/stop/restart
- Monitoring CPU/RAM en temps réel (SSE)
- Alertes configurables (seuils CPU/RAM, cooldown, debounce)
- Notifications : ntfy (push) + Resend (email)
- Downtime debugging : derniers logs, exit code, OOM
- Command Center : discovery, allowlist, exécution, historique
- Workflows act : exécution locale de GitHub Actions (optionnel)
- PWA installable (manifest, standalone)
- Authentification sessions (viewer / admin)
- Audit log pour toutes les actions sensibles
- Purge automatique de l’audit (rétention configurable)
- Health check pour monitoring externe (cron, Uptime Kuma)
- CI : lint, tests, build (GitHub Actions)
- Déploiement sur Raspberry Pi (rsync + docker compose)
