# Definition of Done (DoD) — Vibe Coding Lead Dev

Cette checklist doit être vraie avant de considérer une tâche “DONE”.

## 1) Fonctionnel
- [ ] Le besoin est implémenté et correspond à la spec.
- [ ] Les cas limites (erreurs, inputs invalides, absence de droits) sont gérés proprement.
- [ ] Les messages d’erreur côté user sont clairs (sans leak technique).

## 2) Code quality / Maintainability
- [ ] Le code suit les conventions du repo (format/lint/naming/structure).
- [ ] Changements minimaux et cohérents (pas de refacto inutile).
- [ ] Aucune dette technique non justifiée. Si dette inévitable : TODO explicite + raison + plan de remboursement.
- [ ] Pas de duplication évitable, responsabilité claire des modules/fonctions.

## 3) Sécurité (OWASP & secure-by-default)
- [ ] Validation/sanitation de toutes les entrées (server-side).
- [ ] AuthN/AuthZ vérifiées sur chaque endpoint/action concerné(e).
- [ ] Pas d’injections (SQL/NoSQL/command/template), pas de XSS, pas de SSRF, pas de RCE.
- [ ] Uploads sécurisés (si concernés) : type/size checks, stockage safe, noms aléatoires.
- [ ] Rate limiting/throttling si endpoint sensible/exposé.
- [ ] Erreurs & logs sûrs : pas de secrets, pas de PII inutile, redaction si besoin.
- [ ] Aucun secret dans le code, les logs, les tests, ou la doc.
- [ ] Headers sécurité / CORS / CSRF correctement configurés selon stack.

## 4) RGPD France (privacy by design)
Si données personnelles touchées :
- [ ] Minimisation des données (collecte strictement nécessaire).
- [ ] Finalité et base légale documentées (au minimum note dev/README).
- [ ] Rétention définie (ou TODO explicite + owner).
- [ ] Logs : pas de PII non nécessaire, anonymisation/pseudonymisation si pertinent.
- [ ] Consentement cookies/trackers non essentiels (si web) pris en compte + doc.
- [ ] Droits utilisateur (accès/suppression/export) considérés si applicable.

## 5) Performance
- [ ] Pas de N+1 / queries inefficaces (ORM/DB).
- [ ] Pagination/limites sur endpoints listant des ressources.
- [ ] Caching / memoization raisonnable quand utile.
- [ ] Front (React) : pas de rerenders inutiles, pas de lourdeur inutile.
- [ ] Bundle/perf impact connu (si applicable).

## 6) SEO / i18n / a11y (si web)
- [ ] SEO : title/description, structure sémantique, pages indexables (SSR/SSG si applicable).
- [ ] i18n : toutes les strings user-facing sont traduisibles, keys cohérentes, fallback OK.
- [ ] a11y : navigation clavier, labels/aria lorsque nécessaire.

## 7) Tests (niveau élevé)
- [ ] Tests ajoutés/ajustés couvrant : happy path + erreurs + permissions + edge cases.
- [ ] Tests non-flaky (déterministes), mocks isolés pour réseau/externes.
- [ ] Couverture élevée sur le nouveau code (objectif indicatif ≥ 85% sur la zone modifiée).
- [ ] Tous les tests passent localement (Docker-first si le projet l’utilise).

## 8) Tooling / CI
- [ ] Lint/format passent (ou commandes fournies pour les exécuter).
- [ ] Build passe (si applicable).
- [ ] Migrations DB (si applicable) : générées, sûres, testées, rollback considéré.

## 9) Documentation
- [ ] README mis à jour si nécessaire (en FR).
- [ ] Docstrings / commentaires utiles (en EN, sans excès).
- [ ] OpenAPI/Swagger mis à jour si API modifiée/ajoutée (schemas + exemples).
- [ ] Notes de configuration (.env.example) mises à jour si nouvelles variables.

## 10) Git / Livraison
- [ ] Commits atomiques, messages clairs (Conventional Commits recommandé).
- [ ] `git diff` propre (pas de debug prints, pas de fichiers temporaires).
- [ ] Aucun fichier sensible ajouté (secrets, dumps, credentials).
- [ ] Récap final fourni : fichiers modifiés, commandes, tests, sécurité/RGPD/perf/SEO/i18n, risques, next steps.

