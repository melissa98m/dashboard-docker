# Exploitation Auth — API Dashboard

Guide opérationnel court pour l’authentification et la réponse à incident.

## Pré-requis de configuration

Variables minimales recommandées:

- `AUTH_ENABLED=true`
- `AUTH_COOKIE_SECURE=true` (prod HTTPS)
- `AUTH_BOOTSTRAP_ADMIN_USERNAME=admin`
- `AUTH_BOOTSTRAP_ADMIN_PASSWORD=<mot-de-passe-fort>`
- `API_SECRET_KEY=<secret-long-aleatoire>`

Bonnes pratiques:

- Mot de passe admin long et unique (>= 16 conseillé)
- Rotation régulière du mot de passe admin
- Audit des événements d’auth dans `audit_log`

## Flux de base (session + CSRF)

### 1) Login

`POST /api/auth/login` avec `username/password`.

Le serveur renvoie:

- cookie session HttpOnly
- cookie CSRF lisible côté client

Si la 2FA est activée pour l’utilisateur:

- la réponse login indique `mfa_required=true` et renvoie `mfa_token`
- appeler `POST /api/auth/login/verify-2fa` avec `mfa_token` + `otp_code`
- la session n’est créée qu’après validation OTP

### 2) Actions admin

Pour les endpoints sensibles, envoyer:

- cookie session
- header `x-csrf-token` avec la valeur du cookie CSRF

### 3) Logout

`POST /api/auth/logout` invalide la session courante.

## Endpoints utiles en exploitation

- `GET /api/auth/me` — identité courante
- `GET /api/auth/2fa/status` — statut MFA de l’utilisateur courant
- `POST /api/auth/2fa/setup` — démarre l’enrôlement TOTP (clé + URI otpauth)
- `POST /api/auth/2fa/enable` — active la 2FA après vérification OTP
- `POST /api/auth/2fa/disable` — désactive la 2FA (mot de passe + OTP)
- `GET /api/auth/users?q=<search>` — recherche utilisateurs
- `POST /api/auth/users` — création utilisateur
- `PATCH /api/auth/users/{id}/role` — changement de rôle
- `PATCH /api/auth/users/{id}/password` — rotation mot de passe + révocation des sessions de l’utilisateur
- `GET /api/auth/sessions` — sessions actives
- `DELETE /api/auth/sessions/{session_id}` — révoquer une session précise
- `POST /api/auth/sessions/revoke-user` — révoquer toutes les sessions d’un username
- `POST /api/auth/sessions/revoke-user-id` — révoquer toutes les sessions d’un user_id

## Playbook incident response (compromission suspectée)

1. **Qualifier l’incident**
   - Vérifier l’identité courante (`/api/auth/me`)
   - Lister les utilisateurs potentiellement impactés (`/api/auth/users`)
   - Lister les sessions actives (`/api/auth/sessions`)
2. **Confinement immédiat**
   - Révoquer sessions suspectes par `session_id`
   - Si doute large: révoquer toutes les sessions du compte (`revoke-user` ou `revoke-user-id`)
3. **Remédiation**
   - Forcer rotation mot de passe via `PATCH /api/auth/users/{id}/password`
   - Vérifier que `revoked_sessions > 0`
4. **Validation**
   - Vérifier que l’ancien mot de passe ne fonctionne plus
   - Vérifier qu’aucune session inattendue ne reste active
5. **Traçabilité**
   - Contrôler les entrées `audit_log` (auth login/logout/revoke/password update)

## Exemple minimal (curl)

```bash
# 1) Login (stocke cookies)
curl -i -c cookies.txt -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"StrongPass1234"}'

# 2) Extraire le token CSRF depuis cookies.txt
CSRF=$(awk '$6=="dashboard_csrf"{print $7}' cookies.txt)

# 3) Lister sessions actives
curl -b cookies.txt -H "x-csrf-token: $CSRF" \
  "http://localhost:8000/api/auth/sessions?limit=50"
```

## Risques résiduels à surveiller

- `AUTH_COOKIE_SECURE=false` uniquement en dev local HTTP
- Mots de passe faibles si la politique n’est pas respectée côté opérateurs
