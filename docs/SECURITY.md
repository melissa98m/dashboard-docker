# SECURITY — Règles et mesures projet

## Règles non négociables

- Pas de secrets dans le code, logs, tests ou docs
- Validation server-side de toutes les entrées
- AuthZ sur chaque endpoint protégé (lecture/écriture selon rôle)
- Erreurs safe (pas de leak d’informations sensibles en prod)
- Pas de dépendances ajoutées sans validation explicite
- Socket Docker jamais exposé publiquement (uniquement Unix local)

## Architecture de sécurité

### Authentification et autorisation

- **Session cookies** HttpOnly + CSRF token pour les endpoints sensibles
- **Rôles** : `viewer` (lecture seule), `admin` (lecture + écriture/actions)
- **Policy** : toute requête vers `/api/*` (sauf login et restart-by-token) exige une session valide
- **Lockout** : verrouillage après `AUTH_FAILED_LOGIN_LIMIT` tentatives pendant `AUTH_LOCKOUT_MINUTES`
- **Options cookies** : `AUTH_COOKIE_SECURE=true` en prod ; `SameSite=lax` par défaut

### Docker

- Communication via socket Unix uniquement (`DOCKER_HOST=unix:///var/run/docker.sock`)
- Aucune exposition du socket ou de l’API Docker vers l’extérieur
- Déploiement recommandé : LAN ou VPN (Tailscale/WireGuard)

### Exec / Command Center

- **Allowlist stricte** : seules les commandes promues depuis la discovery peuvent être exécutées
- **argv[] structuré** : pas de shell arbitraire (`sh -c` avec input utilisateur interdit)
- Chaque exécution : audit log + logs persistés (stdout/stderr, exit code, durée)

### Actions sensibles

- Restart via lien signé (notifications) : token HMAC avec TTL court (`RESTART_ACTION_TTL_SECONDS`)
- **Rate limiting** sur `restart-by-token` : `RESTART_TOKEN_RATE_LIMIT_*` (défaut 20 tentatives / 60 s)
- Stream d’exécution : token éphémère (`EXECUTION_STREAM_TOKEN_TTL_SECONDS`)

## Validation et sanitization

| Zone | Mesure |
|------|--------|
| Username | Regex `[A-Za-z0-9._-]{3,120}` |
| Mot de passe | ≥ 12 caractères, lettres + chiffres ; pbkdf2_sha256 (600k itérations) |
| Container IDs | Validation format avant appels Docker |
| Env vars (container_env) | Validation clé/valeur ; clés sensibles redactées dans l’audit |
| Détails audit | Sanitization : clés sensibles (token, secret, password, api_key…) → `[REDACTED]` |
| Snapshots logs | Redaction patterns (`LOG_SNAPSHOT_REDACTION_*`) ; patterns PII/secret masqués |

## OWASP / risques couverts

- **Injection** : requêtes SQL paramétrées (ORM/sqlite3) ; exec via argv[] allowlisté
- **XSS** : React échappe par défaut ; pas de `dangerouslySetInnerHTML` avec contenu non contrôlé
- **CSRF** : cookie CSRF + header `x-csrf-token` pour les mutations
- **IDOR** : vérification d’existence des ressources (container_id, etc.) avant action
- **SSRF** : pas de fetch vers URLs utilisateur ; ntfy/Resend vers URLs configurées
- **Brute-force** : lockout login ; rate limit restart-by-token

## Logs et PII

- Logs d’audit : `triggered_by` = username (traçabilité) ; détails sanitizés
- Snapshots logs conteneurs : patterns sensibles masqués (`LOG_SNAPSHOT_REDACTION_ENABLED`)
- Pas de secrets ni de mots de passe en clair dans les logs

## OpenAPI / docs

- `/docs` et `/openapi.json` désactivés en production (`app_env != development`)
- En dev : exposition pour faciliter les tests ; en prod : pas d’exposition publique

## Checklist opérationnelle

- [ ] `AUTH_COOKIE_SECURE=true` en prod HTTPS
- [ ] `API_SECRET_KEY` défini pour les tokens signés (restart-by-token)
- [ ] `PUBLIC_API_URL` configuré pour les liens de restart dans les notifications
- [ ] CORS restreint aux origines connues
- [ ] ntfy / Resend : URLs et clés stockées en variables d’environnement, jamais en dur
