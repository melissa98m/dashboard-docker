# RGPD (France) — Privacy by design

## Contexte

Ce dashboard est un outil d’exploitation interne, déployé en LAN/VPN. Les données traitées concernent principalement les comptes administrateurs/opérateurs et les traces d’audit associées.

## Données personnelles

| Donnée | Table / source | Finalité |
|--------|----------------|----------|
| Username | `users` | Identification, traçabilité (audit) |
| Mot de passe (hash pbkdf2) | `users` | Authentification |
| Rôle (viewer/admin) | `users` | Contrôle d’accès |
| Tentatives de connexion / verrouillage | `users` | Protection contre le brute-force |
| Last login | `users` | Conformité / sécurité |
| Sessions (token hash, CSRF, dates) | `auth_sessions` | Authentification, révocation |
| `triggered_by` (username) dans l’audit | `audit_log` | Traçabilité des actions sensibles |

Les logs Docker, métriques CPU/RAM et exécutions de commandes ne sont pas des données personnelles au sens RGPD (données techniques liées aux conteneurs).

## Finalités

1. **Accès au dashboard** : authentification et contrôle d’accès (rôles viewer/admin).
2. **Audit des actions** : traçabilité des actions sensibles (restart, exec, gestion utilisateurs, purge audit) pour conformité et incident response.
3. **Exploitation** : monitoring des conteneurs ; pas de profilage ni de décision automatisée.

## Base légale

- **Intérêt légitime** : exploitation technique et sécurité du système.
- Pour un usage B2B / interne : exécution du contrat ou intérêt légitime de l’organisme.

## Rétention

| Donnée | Durée | Mécanisme |
|--------|-------|-----------|
| Audit log | 90 jours (configurable `AUDIT_RETENTION_DAYS`) | Purge manuelle via `/api/audit/purge` ou service automatique `AUDIT_RETENTION_AUTO_ENABLED` |
| Sessions | TTL configurable (`AUTH_SESSION_TTL_SECONDS`, défaut 8 h) + révocation possible | Expiration + nettoyage périodique des sessions expirées |
| Utilisateurs | Tant que le compte est actif | Suppression manuelle (non exposée en UI v1 ; possible via CLI/DB si besoin) |
| Historique exécutions commandes | `COMMAND_RETENTION_*` si configuré | Service de purge dédié |
| Logs snapshots (last_logs) | Non persistés en DB ; servis à la volée | N/A |

## Principes appliqués

- **Minimisation** : collecte limitée aux champs nécessaires (username, rôles, traces d’audit).
- **Logs** : redaction des clés sensibles dans les détails d’audit (`password`, `token`, `api_key`, etc.) ; masquage de patterns PII dans les snapshots de logs (`LOG_SNAPSHOT_REDACTION_ENABLED`).
- **Cookies** : cookies de session (HttpOnly) et CSRF uniquement ; pas de trackers tiers.
- **Droits utilisateurs** : v1 ne propose pas d’export/suppression via UI ; à considérer si ouverture à des utilisateurs finaux.

## Contact

Pour toute question relative au traitement des données personnelles, contacter l’administrateur du déploiement ou le DPO de l’organisme.
