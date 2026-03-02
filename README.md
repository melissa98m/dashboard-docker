# Dashboard Docker — Raspberry Pi

Tableau de bord mobile-friendly pour monitorer et gérer les conteneurs Docker sur un Raspberry Pi.

## Démarrage rapide

```bash
cp .env.example .env
make up
```

- **API** : http://localhost:8000
- **Web** : http://localhost:3000
- **UI Alertes** : http://localhost:3000/alerts
- **Docs API** : http://localhost:8000/docs

## Commandes

| Commande | Description |
|----------|-------------|
| `make build` | Build les images Docker |
| `make up` | Démarre les services |
| `make down` | Arrête les services |
| `make restart` | Arrête puis redémarre les services |
| `make ps` | Affiche l'état des conteneurs |
| `make dev` | Mode dev avec logs en direct (pas de détachement) |
| `make logs` | Affiche les logs |
| `make lint` | Lint API + web |
| `make format` | Formatage du code |
| `make test` | Tests API + web |
| `make migrate` | Applique les migrations SQLite |
| `make purge-audit` | Purge les logs d'audit selon la rétention |
| `make create-user USERNAME=<nom> [ROLE=viewer|admin]` | Crée un utilisateur (mot de passe saisi en prompt masqué) |
| `make db-backup` | Sauvegarde SQLite dans `backups/` (services doivent être démarrés) |
| `make clean` | Arrête les services et purge le cache Docker (ne supprime pas le volume de données) |
| `make health-check` | Vérifie la santé de l'API (pour cron, Uptime Kuma) via `./scripts/health-check.sh` |
| `make shell-api` | Shell dans le conteneur API |
| `make shell-web` | Shell dans le conteneur web |

### Création d'un utilisateur

À exécuter **dans un terminal interactif** (le mot de passe est demandé en saisie masquée) :

```bash
make create-user USERNAME=operator ROLE=viewer
```

Ou sans Make :

```bash
docker compose exec -it dashboard-api python -m app.cli create-user --username operator --role viewer
```

Contraintes du mot de passe : minimum 12 caractères, avec lettres et chiffres.

## Stack

- **Backend** : Python FastAPI
- **Frontend** : Next.js 14 (React)
- **Base de données** : SQLite
- **Docker** : socket Unix uniquement (non exposé)

## Sécurité

- Socket Docker non exposé publiquement
- Déploiement LAN/VPN recommandé
- Actions sensibles write (`start/stop/restart`) : auth + audit log
- Auth session obligatoire sur toute l’API (sauf login et /health) ; docs `/docs` publiques en dev uniquement
- Limite de flux live SSE configurable (`SSE_MAX_CONNECTIONS`)
- Lien de restart signé (TTL court) dans les notifications: configurer `API_SECRET_KEY` + `PUBLIC_API_URL`

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/SPEC.md](docs/SPEC.md) et [docs/AUTH_OPERATIONS.md](docs/AUTH_OPERATIONS.md).
