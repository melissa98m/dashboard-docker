# Dashboard Docker — Raspberry Pi

Tableau de bord **mobile-first** et **self-hosted** pour monitorer et gérer les conteneurs Docker sur un Raspberry Pi (LAN/VPN).

## Fonctionnalités

| Catégorie | Capacités |
|-----------|-----------|
| **Conteneurs** | Liste (nom, image, statut, uptime) — start / stop / restart — suppression contrôlée |
| **Monitoring** | CPU % et RAM en temps réel (streaming SSE) — métriques par conteneur |
| **Alertes** | Règles par conteneur (CPU/RAM) — cooldown & debounce — notifs ntfy (avec bouton Restart) + Resend (emails) |
| **Débogage** | Derniers logs à l’arrêt — code de sortie, OOM, santé — détection automatique via events Docker |
| **Command Center** | Découverte de commandes par service — exécution allowlistée — historique logs + exit code + durée |
| **Workflows act** | Exécution locale de jobs GitHub Actions via [act](https://github.com/nektos/act) (optionnel) |
| **Auth** | Sessions + rôles (viewer / admin) — audit log pour les actions sensibles |
| **PWA** | Installable sur mobile — mode standalone |

## Démarrage rapide

```bash
cp .env.example .env
make up
```

- **API** : http://localhost:8000
- **Web** : http://localhost:3000
- **UI Alertes** : http://localhost:3000/alerts
- **Workflows act** : Conteneur → Workflows
- **Docs API** : http://localhost:8000/docs

## Commandes

| Commande | Description |
|----------|-------------|
| `make build` | Build les images Docker |
| `make up` | Démarre les services |
| `make down` | Arrête les services |
| `make restart` | Arrête puis redémarre les services |
| `make ps` | Affiche l'état des conteneurs |
| `make dev` | Mode dev avec logs en direct |
| `make logs` | Affiche les logs |
| `make lint` | Lint API + web |
| `make lint-ci` | Lint mode CI (sans services démarrés) |
| `make format` | Formatage du code |
| `make format-check` | Vérifie le format (CI) |
| `make test` | Tests API + web |
| `make test-ci` | Tests mode CI (fail-fast) |
| `make test-e2e` | Tests E2E Playwright via conteneur dédié (démarre API+web automatiquement) |
| `make migrate` | Applique les migrations SQLite |
| `make purge-audit` | Purge les logs d'audit selon la rétention |
| `make create-user USERNAME=<nom> [ROLE=viewer]` | Crée un utilisateur (ROLE: viewer ou admin) |
| `make db-backup` | Sauvegarde SQLite dans `backups/` |
| `make clean` | Arrête les services et purge le cache Docker |
| `make health-check` | Vérifie la santé de l'API |
| `make shell-api` | Shell dans le conteneur API |
| `make shell-web` | Shell dans le conteneur web |

### Création d'un utilisateur

```bash
make create-user USERNAME=operator ROLE=viewer
```

Ou sans Make :

```bash
docker compose exec -it dashboard-api python -m app.cli create-user --username operator --role viewer
```

Mot de passe : minimum 12 caractères, lettres + chiffres.

### Rôles : viewer vs admin

| Capacité | **Viewer** | **Admin** |
|----------|------------|-----------|
| Lecture (conteneurs, logs, alertes, audit, paramètres) | ✅ | ✅ |
| Écriture (start/stop/restart, règles, commandes, utilisateurs) | ❌ | ✅ |

## Stack

- **Backend** : Python FastAPI
- **Frontend** : Next.js 14 (React)
- **Base de données** : SQLite
- **Docker** : socket Unix uniquement (non exposé)

## PWA (installation sur mobile)

Sur téléphone, ouvre l’URL du dashboard dans Chrome/Edge/Safari puis :

- **Chrome/Edge** : Menu (⋮) → « Installer l’application »
- **Safari (iOS)** : Partager → « Sur l’écran d’accueil »

## Sécurité

- Socket Docker non exposé publiquement — déploiement LAN/VPN recommandé
- Auth session obligatoire ; actions write : audit log
- MFA TOTP disponible (QR code) : première connexion = enrôlement OTP, connexions suivantes = mot de passe + code OTP
- Lien Restart signé (TTL court) dans les notifs : `API_SECRET_KEY` + `PUBLIC_API_URL`
- Limite de flux SSE configurable (`SSE_MAX_CONNECTIONS`)

### MFA (OTP) — usage

- Première connexion d'un utilisateur sans OTP: ouverture de la configuration OTP avec QR code (et clé manuelle en fallback).
- Connexions suivantes: étape 1 `username/password`, étape 2 `code OTP`.
- Le QR code peut être regénéré plus tard dans `Paramètres` → `MFA utilisateur`.

Pré-requis `.env`:

- `API_SECRET_KEY=<secret_long_aleatoire>`
- `AUTH_ENABLED=true`

Si plusieurs instances du dashboard tournent sur le meme hote ou domaine, donnez des valeurs
uniques a `AUTH_SESSION_COOKIE_NAME` et `AUTH_CSRF_COOKIE_NAME` pour chaque instance. Les
cookies navigateur ne sont pas isoles par port, ce qui peut provoquer des erreurs `Invalid CSRF token`.

Reset OTP d'un utilisateur (ex: perte de téléphone):

```bash
docker compose exec -T dashboard-api python - <<'PY'
import sqlite3
conn = sqlite3.connect("/data/dashboard.db")
conn.execute("""
UPDATE users
SET totp_enabled = 0, totp_secret_encrypted = NULL, totp_enabled_at = NULL
WHERE username = ?
""", ("melissa",))
conn.commit()
print("MFA reset for melissa")
PY
```

Note: `-T` est requis avec heredoc pour éviter l'erreur `the input device is not a TTY`.

### Règles d’alerte par défaut

Au démarrage, règles CPU 90 % et RAM 90 % créées automatiquement par conteneur (modifiables via `/alerts`).

### Notifications

- **ntfy** : `NTFY_BASE_URL` + `NTFY_TOPIC`
- **Email (Resend)** : `RESEND_API_KEY` + `ALERT_EMAIL_FROM` + `ALERT_EMAIL_TO` — domaine vérifié requis sur [resend.com](https://resend.com)

### Workflows act (optionnel)

`ACT_ENABLED=true` + `ACT_WORKFLOWS_PATH=/workspace` — exécution de jobs GitHub Actions via act dans l’UI.

## Données persistantes

Données stockées dans le volume Docker `dashboard_data`. Persistance entre `make up` / `make down` / `make restart`.

- **Sauvegarde** : `make db-backup`
- **Suppression** : `docker compose down -v` (⚠️ supprime le volume)

**Premier admin automatique** : `AUTH_BOOTSTRAP_ADMIN_USERNAME` + `AUTH_BOOTSTRAP_ADMIN_PASSWORD` dans `.env`.

**Migration depuis `./data`** :

```bash
make up
docker cp ./data/dashboard.db dashboard-api:/data/dashboard.db 2>/dev/null || true
make restart
```

## Documentation

| Fichier | Contenu |
|---------|---------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture et flux |
| [docs/SPEC.md](docs/SPEC.md) | Spécification fonctionnelle |
| [docs/AUTH_OPERATIONS.md](docs/AUTH_OPERATIONS.md) | Auth et exploitation |
| [docs/DEV.md](docs/DEV.md) | Conventions dev et commandes |
| [docs/CICD.md](docs/CICD.md) | CI/CD et déploiement |
| [docs/SECURITY.md](docs/SECURITY.md) | Règles sécurité |
| [docs/RGPD.md](docs/RGPD.md) | RGPD et données personnelles |
| [CHANGELOG.md](CHANGELOG.md) | Historique des versions |
