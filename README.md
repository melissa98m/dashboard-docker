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
- **Workflows act** : dans chaque conteneur (Conteneur → Workflows)
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
| `make lint-ci` | Lint mode CI (sans services démarrés) |
| `make format` | Formatage du code |
| `make test` | Tests API + web |
| `make test-ci` | Tests mode CI (fail-fast, sortie concise) |
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

### Rôles : viewer vs admin

| Capacité | **Viewer** | **Admin** |
|----------|------------|-----------|
| Lecture (liste conteneurs, détails, logs, alertes, audit, paramètres) | ✅ | ✅ |
| Écriture / actions (start/stop/restart, règles, commandes, utilisateurs…) | ❌ | ✅ |

- **Viewer** : consultation uniquement. Peut voir les conteneurs, alertes, historique des commandes, audit ; ne peut pas modifier, démarrer/arrêter des conteneurs, exécuter des commandes ni gérer les utilisateurs.
- **Admin** : lecture + écriture. Toutes les actions sensibles : gestion des conteneurs, règles d’alertes, command center, création/modification d’utilisateurs, sessions, purge de l’audit.

## Stack

- **Backend** : Python FastAPI
- **Frontend** : Next.js 14 (React)
- **Base de données** : SQLite
- **Docker** : socket Unix uniquement (non exposé)

## PWA (installation sur mobile)

L'application est une PWA (Progressive Web App). Sur téléphone, ouvre l'URL du dashboard (ex. `http://<ip-du-pi>:3000`) dans Chrome/Edge/Safari, puis :

- **Chrome/Edge** : Menu (⋮) → « Installer l’application » ou « Ajouter à l’écran d’accueil »
- **Safari (iOS)** : Partager → « Sur l’écran d’accueil »

Le dashboard s’ouvre alors en plein écran, sans barre d’adresse, comme une app native.

## Sécurité

- Socket Docker non exposé publiquement
- Déploiement LAN/VPN recommandé
- Actions sensibles write (`start/stop/restart`) : auth + audit log
- Auth session obligatoire sur toute l’API (sauf login et /health) ; docs `/docs` publiques en dev uniquement
- Limite de flux live SSE configurable (`SSE_MAX_CONNECTIONS`)
- Lien de restart signé (TTL court) dans les notifications: configurer `API_SECRET_KEY` + `PUBLIC_API_URL`

### Notifications (alertes)

- **ntfy** : `NTFY_BASE_URL` + `NTFY_TOPIC` pour les push notifications (downtime, seuils CPU/RAM).
- **Email (Resend)** : `RESEND_API_KEY` + `ALERT_EMAIL_FROM` + `ALERT_EMAIL_TO` pour envoi d’emails sur alertes (style Uptime Robot). Domaine vérifié requis sur [resend.com](https://resend.com).

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/SPEC.md](docs/SPEC.md), [docs/AUTH_OPERATIONS.md](docs/AUTH_OPERATIONS.md) et [docs/CICD.md](docs/CICD.md) (CI/CD).

## Données persistantes (utilisateurs, etc.)

Les utilisateurs et la base SQLite sont stockés dans un **volume Docker nommé** (`dashboard_data`). Les données **persistent** entre `make up`, `make down`, `make restart` et même après un nouveau `git clone` ou changement de répertoire.

- **Sauvegardes** : `make db-backup` (copie la DB dans `backups/`)
- **Supprimer les données** : `docker compose down -v` (⚠️ supprime le volume)

**Premier utilisateur automatique** : définir dans `.env` les variables `AUTH_BOOTSTRAP_ADMIN_USERNAME` et `AUTH_BOOTSTRAP_ADMIN_PASSWORD`. Au premier démarrage avec une base vide, l’admin sera créé automatiquement (voir [docs/AUTH_OPERATIONS.md](docs/AUTH_OPERATIONS.md)).

**Migration depuis l’ancien bind mount `./data`** (si vous aviez déjà des données avant ce changement) :

```bash
make up
docker cp ./data/dashboard.db dashboard-api:/data/dashboard.db 2>/dev/null || true
make restart
```
