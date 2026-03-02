# SNIPPETS — Cursor Agent Workflow

## 1) Kickoff (démarrage d’une tâche)
Contexte:
- Objectif: <décris la feature / bug>
- Contrainte(s): <perf/seo/i18n/rgpd/sécu>
- Stack: <react/django/laravel/etc>
- Docker: <oui/non> (si oui: services concernés)

Règles:
- Propose d’abord des questions si nécessaire, puis un plan.
- Attends mon "GO" avant toute modification.
- Pas de nouvelles dépendances sans accord.
- Pas de breaking API sans accord.
- Tests élevés + récap détaillé en fin d’itération.

Sortie attendue:
- Patch/diff + fichiers (si utile) + commandes terminal
- Tests ajoutés/ajustés + commandes
- Récap: fichiers modifiés, commits atomiques, sécurité, RGPD, perf, SEO, i18n, risques, next steps

---

## 2) GO (validation + implémentation)
GO.

Implémente selon le plan.
- Donne d’abord le patch/diff.
- Ensuite les commandes à exécuter (Docker-first si applicable).
- Ajoute/ajuste les tests (niveau élevé).
- Termine par un récap détaillé + suggestions de commits atomiques (Conventional Commits).

---

## 3) Apply & Verify (appliquer + exécuter checks)
Applique le patch (sans ajouter de dépendances).
Ensuite exécute et reporte les résultats:
1) git status
2) git diff
3) lint/format (si présent)
4) tests (niveau élevé)
5) build (si applicable)

Puis fais le récap détaillé + propose une liste de commits atomiques (messages inclus).

---

## 4) Review mode (audit sécurité/qualité avant merge)
Passe en mode REVIEW (lead dev).
- Vérifie sécurité (OWASP, validation inputs, authz, secrets, logs/PII)
- Vérifie RGPD (minimisation, consentement cookies/trackers si web, retention, logs)
- Vérifie perf (N+1, queries, caching, re-renders)
- Vérifie SEO/i18n (meta, indexabilité, strings traduisibles)
- Vérifie tests (couverture utile, non-flaky)
- Liste: problèmes bloquants vs améliorations
- Propose les corrections sous forme de patch/diff + commandes

---

## 5) Runbook auth (astreinte, 10 lignes)
1) Login admin + récupère cookie session/CSRF.
2) `GET /api/auth/users?q=<user>` pour identifier le compte.
3) `GET /api/auth/sessions?user_id=<id>` pour voir les sessions actives.
4) Incident ciblé: `DELETE /api/auth/sessions/{session_id}`.
5) Incident large: `POST /api/auth/sessions/revoke-user-id`.
6) Compte compromis: `PATCH /api/auth/users/{id}/password`.
7) Vérifie `revoked_sessions > 0` après rotation.
8) Re-teste: ancien mot de passe KO, nouveau OK.
9) Contrôle `audit_log` (login/revoke/password update).
10) En prod: `AUTH_COOKIE_SECURE=true`.

