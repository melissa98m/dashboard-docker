# SECURITY — Règles projet (template)

## Règles non négociables
- Pas de secrets dans le code/logs/tests/docs
- Validation server-side de toutes les entrées
- AuthZ sur chaque action/endpoints protégés
- Erreurs safe (pas de leak d’infos en prod)
- Pas de dépendances ajoutées sans validation

## Checklist rapide
- Inputs: validation + sanitation
- OWASP: injection / XSS / SSRF / IDOR / CSRF
- Logs: minimisation PII + redaction
- Rate limiting sur endpoints sensibles

