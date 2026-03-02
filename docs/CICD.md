# CI/CD — GitHub Actions

## Vue d'ensemble

- **CI** : lint, tests, build sur chaque push/PR vers `main`
- **Auto Pull Request** : crée/met à jour une PR à chaque push vers une branche hors `main`
- **CD** : déploiement sur le Raspberry Pi à chaque push sur `main` (ou manuel)

## Workflows

| Workflow         | Fichier                            | Déclencheur                     |
|------------------|-------------------------------------|---------------------------------|
| CI               | `.github/workflows/ci.yml`          | Push + PR sur `main`            |
| Auto Pull Request| `.github/workflows/auto-pull-request.yml` | Push branches hors `main`/`master` |
| Deploy           | `.github/workflows/deploy.yml`      | Push sur `main` + `workflow_dispatch` |

## CI

Exécute en parallèle :
- **Lint** : `make lint-ci` (ruff, mypy, ESLint)
- **Test** : `make test-ci` (pytest + Vitest)
- **Build** : `make build` (images Docker)

## Auto Pull Request

Workflow qui crée ou met à jour une PR (corps = messages de commit) à chaque push sur une branche hors `main`/`master`.

**Si erreur 403** (« GitHub Actions is not permitted to create pull requests ») :
1. Crée un Personal Access Token avec scope `repo` : https://github.com/settings/tokens
2. Ajoute le secret `REPO_ACCESS_TOKEN` dans **Settings → Secrets → Actions**

## Déploiement sur Raspberry Pi

### Prérequis

1. **Sur le Raspberry Pi** :
   - Docker + Docker Compose installés
   - Dossier du projet créé (ex. `/home/pi/docker-dashboard`)
   - Clé SSH publique de la clé de déploiement ajoutée dans `~/.ssh/authorized_keys`

2. **Connectivité** : le Pi doit être joignable en SSH depuis Internet (VPN, port forwarding, ou Pi sur réseau exposé — Tailscale/WireGuard recommandé).

### Secrets GitHub

À configurer dans **Settings → Secrets and variables → Actions** :

| Secret           | Description                                      |
|------------------|--------------------------------------------------|
| `DEPLOY_SSH_KEY` | Clé privée SSH pour se connecter au Pi          |
| `DEPLOY_HOST`    | IP ou hostname du Pi (ex. `192.168.1.10` ou `pi.local`) |
| `DEPLOY_USER`    | Utilisateur SSH (ex. `pi`)                       |
| `DEPLOY_PATH`    | Chemin du projet sur le Pi (ex. `/home/pi/docker-dashboard`) |
| `REPO_ACCESS_TOKEN` | *(optionnel)* PAT scope `repo` pour Auto Pull Request si 403 |

### Génération de la clé SSH

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f deploy_key -N ""
```

- **Clé privée** → secret `DEPLOY_SSH_KEY`
- **Clé publique** (`deploy_key.pub`) → copier dans `~/.ssh/authorized_keys` sur le Pi

### Premier déploiement manuel sur le Pi

```bash
ssh pi@<IP_DU_PI>
mkdir -p /home/pi/docker-dashboard
cd /home/pi/docker-dashboard
# Copier .env.example en .env et éditer si besoin
```

Puis lancer un déploiement depuis GitHub Actions (onglet Actions → Deploy to Raspberry Pi → Run workflow).

### Comportement du déploiement

1. Rsync du code vers le Pi (`.env` et dossiers générés exclus)
2. Si `.env` absent, copie depuis `.env.example`
3. `docker compose build` puis `docker compose up -d`

**Important** : le fichier `.env` sur le Pi n’est jamais écrasé (production, secrets).

## Sécurité

- **Secrets** : aucune clé/mot de passe dans le code ou les logs
- **SSH** : clé dédiée au déploiement, avec accès limité
- **Docker socket** : non exposé, uniquement via socket Unix local sur le Pi
- **RGPD** : aucune donnée personnelle dans les workflows ; logs GitHub standard
