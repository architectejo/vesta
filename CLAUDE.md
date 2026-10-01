# CLAUDE.md — Projet Vesta

Vesta est une plateforme SaaS multi-clubs : réseau social de football amateur + gestion de club (trésorerie, présences, matchs, discipline, médical, logistique, mercato, AG). Club pilote : Loisirs Club Discovery (vétérans, Kinshasa).

## 1. Source de vérité

- **`docs/cahier-des-charges.md`** fait foi pour toute règle métier, tout écran et toute permission. Lis la section concernée AVANT de coder.
- Les décisions ouvertes sont listées au chapitre 10.2. **N'invente jamais une règle métier.** Si une règle n'est pas tranchée, applique la « proposition par défaut » du 10.2 et signale-le dans ton compte rendu.
- Toute demande absente du cahier des charges suit le circuit du 9.4 : ne la développe pas, décris-la et demande une décision.
- **Si `CLAUDE.md` et `docs/cahier-des-charges.md` se contredisent sur une règle métier, ne tranche jamais seul entre les deux, même si l'un des deux documents te paraît formulé de façon plus stricte ou plus impérative.** Aucun des deux ne l'emporte automatiquement sur l'autre : `CLAUDE.md` cadre la façon de travailler, le cahier des charges est la source de vérité métier — une contradiction entre eux est un défaut du cadrage, pas un cas à arbitrer par déduction. Documente la contradiction (les deux formulations exactes, avec leurs sections), applique à titre strictement provisoire la position la plus prudente (la plus restrictive en matière de sécurité et de confidentialité) pour ne pas bloquer le travail en cours, marque-la explicitement comme non tranchée dans ton compte rendu, et pose la question au client avant de la considérer close.

## 2. Règles non négociables

### Métier
1. **Tout utilisateur d'un club est un joueur**, Président compris. Les fonctions (Président, Trésorier, Coach, Capitaine, Médecin…) sont des rôles ajoutés au joueur. Seuls les Superusers ne sont pas joueurs.
2. **Le solde d'un joueur est toujours calculé** (paiements validés − montants dus échus, types obligatoires uniquement). Il n'existe AUCUN champ `solde` stocké.
3. Les cotisations **libres** ne créent jamais de dette.
4. Un paiement validé n'est **jamais supprimé** : on crée une écriture d'annulation.
5. Un joueur en dette, suspendu, inapte ou en attente d'adhésion **ne peut être ni composé ni placé** dans un plan tactique.
6. Toute action qui crée, modifie ou supprime une donnée **écrit une entrée dans le journal d'activité** (append-only).
7. Les actions sensibles (validation de paiement ou dépense, dérogation, signature parrain, signature PV, annulation) exigent le **code PIN**.

### Multi-tenant et sécurité
8. **Toute donnée privée est filtrée par club.** Passe toujours par les managers/querysets tenant-aware. Une requête sans club actif est refusée. Jamais de `Model.objects.all()` sur une table privée dans une vue.
9. Le club actif se déduit de l'adhésion en cours, **jamais d'un `tenant_id` figé dans le JWT**.
10. Les fichiers privés (justificatifs, reçus, documents médicaux) sont servis **uniquement** par une vue authentifiée, jamais depuis `public_html`.
11. **Décidé le 25/09/2026 (cahier des charges 10.2 n° 15).** Par défaut, le diagnostic et le suivi médical ne sont visibles que par le Médecin et le joueur concerné. Le Coach ne voit jamais que l'aptitude et la date de retour, sans exception. Le joueur peut donner au Président un accès complet à son dossier médical, depuis son profil, dans une modale. Ce consentement est révocable à tout moment ; la révocation coupe l'accès immédiatement. Chaque consentement, chaque révocation et chaque consultation du dossier par le Président sont journalisés (sans copier le contenu médical dans le journal). L'accord est donné au Président **en tant que fonction** : s'il change de Président, le consentement ne se transfère pas au nouveau titulaire.
12. Aucun secret dans le code : variables d'environnement uniquement.

### Interface (chapitre 3 du cahier des charges)
13. **Tout formulaire s'ouvre dans une boîte modale.** Aucune page ne contient uniquement un formulaire.
14. Listes : N derniers éléments + bouton « Voir plus » ; clic sur un élément = modale de détail.
15. **Jamais de `<select>` pour choisir un joueur** : champ de recherche avec suggestions, ou tableau filtrable.
16. Mobile-first (360 px). Texte 14–16 px, titres ≤ 24 px, boutons 36–40 px de haut. Pas de gros boutons ni de gros caractères.
17. Loader à chaque chargement de page et pendant chaque action. État vide explicite pour chaque section.
18. **Marque blanche** : nom, logo et couleurs du club connecté viennent de l'API. **Aucun nom de club, logo ou lien de paiement écrit en dur.**
19. **« IMARA TECH Group » n'apparaît qu'à un seul endroit** : le footer « VESTA by IMARA TECH Group — une partie de nos revenus est destinée aux orphelinats locaux ». Nulle part ailleurs (code, textes, documents générés).
20. Toute l'interface et tous les messages d'erreur sont **en français clair**.

## 3. Interdits

- **SQLite en production** (base de production : MySQL/MariaDB, ou PostgreSQL si l'hébergement le permet). SQLite est **autorisé en développement** (décision du 25/09/2026) pour la rapidité des cycles locaux, à la stricte condition que rien dans le code ne dépende d'un comportement propre à SQLite (voir §9, « Définition de terminé »).
- Django < 5.2.
- Un dossier `deploy/` ou tout fichier inutile à la racine.
- Des données de démonstration ou un nom de club dans les migrations.
- Désactiver ou contourner un test pour le faire passer.
- Modifier une règle métier « parce que c'est plus simple ».

## 4. Stack

| Couche | Choix |
| --- | --- |
| API | Python 3.12, Django 5.2 LTS, Django REST Framework, SimpleJWT |
| Base | SQLite en développement (rapidité des cycles locaux) ; MySQL/MariaDB en production. Aucun code ne doit dépendre d'un comportement propre à SQLite (verrouillage de lignes, casse des textes, champs JSON — voir §9) |
| Interface | React + TypeScript + Vite, PWA, React Router, TanStack Query |
| Style | Tailwind CSS, thèmes par variables CSS (Classic = couleurs du club, Clair, Sombre) |
| Tests | pytest + pytest-django + factory_boy (API) ; Vitest + Testing Library (interface) ; Playwright (bout en bout) |
| Hébergement | cPanel / LiteSpeed (Passenger), `vesta.eschoolb.com` (interface) et `api.vesta.eschoolb.com` (API) |

Contraintes d'hébergement : pas de processus permanent (tâches périodiques = cron), pas de WebSockets (polling 10–30 s).

## 5. Structure du dépôt

```
/
├── CLAUDE.md
├── docs/cahier-des-charges.md
├── .claude/agents/          # subagents du projet
├── backend/
│   ├── config/              # settings (base, dev, prod), urls, wsgi
│   ├── apps/
│   │   ├── accounts/  clubs/  licences/  treasury/  sport/
│   │   ├── medical/  logistics/  mercato/  assemblies/
│   │   ├── social/  notifications/  audit/
│   │   └── core/            # tenant, permissions, mixins communs
│   ├── passenger_wsgi.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── design-system/   # tokens, Modal, DataTable, PlayerSearch, Loader, EmptyState, StatusBadge
│   │   ├── features/        # un dossier par module
│   │   ├── api/  hooks/  layouts/  routes/
│   └── public/.htaccess
└── data/                    # fichiers réels du club pilote (jamais commités s'ils contiennent des données personnelles)
```

Dans chaque app Django : `models.py`, `services.py` (règles métier), `serializers.py`, `views.py`, `permissions.py`, `tests/`. **Les règles métier vivent dans `services.py`**, jamais dans les vues, les serializers ou l'interface.

## 6. Commandes

```bash
# API
cd backend
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
pytest                          # tous les tests
pytest apps/treasury -x         # un module

# Interface
cd frontend
npm install
npm run dev
npm run build
npm run test
npx playwright test
```

## 7. Conventions de code

- Code, noms de variables, modèles et commits en **anglais** ; textes affichés et messages d'erreur en **français**.
- Montants : `Decimal` côté API, jamais `float`. Devise portée par le club.
- Dates stockées en UTC, affichées dans le fuseau du club.
- Chaque endpoint déclare explicitement ses permissions (rôles de la matrice 2.4).
- Composants d'interface : réutiliser le design system avant d'en créer un nouveau.
- Commits : `type(module): description` — ex. `feat(treasury): répartition des paiements anticipés`.

## 8. Équipe de subagents

| Agent | Quand l'appeler |
| --- | --- |
| `ui-designer` | Avant tout nouvel écran ; pour toute question visuelle ; revue visuelle d'un écran terminé |
| `frontend-dev` | Implémentation d'écrans React à partir d'une spec validée |
| `backend-dev` | Modèles, API et services hors trésorerie |
| `finance-engine` | Tout ce qui touche cotisations, paiements, solde, dépenses, assistance sociale, paiement en ligne |
| `test-engineer` | Tests unitaires, API, étanchéité, bout en bout |
| `data-import` | Imports CSV et jeux de simulation à partir de `data/` |
| `devops-cpanel` | Passenger, `.htaccess`, cron, variables d'environnement, sauvegardes, mise en production |
| `security-auditor` | Revue sécurité après chaque fonctionnalité (lecture seule) |
| `cdc-reviewer` | Contrôle de conformité au cahier des charges en fin de tâche et de lot (lecture seule) |

Flux standard d'une fonctionnalité :
1. `ui-designer` → spec d'écran (si interface)
2. `backend-dev` ou `finance-engine` → modèles, services, API
3. `test-engineer` → tests
4. `frontend-dev` → écran
5. `security-auditor` puis `cdc-reviewer` → rapports ; l'agent concerné corrige

Un subagent ne voit pas cette conversation : transmets-lui toujours la section du cahier des charges concernée, les fichiers touchés et la décision attendue.

## 9. Définition de « terminé »

Une tâche est terminée seulement si :
- [ ] la section concernée du cahier des charges est respectée (règles, cas limites, notifications, logs) ;
- [ ] les tests passent, y compris les tests d'étanchéité entre clubs ;
- [ ] `security-auditor` ne signale aucun écart bloquant ;
- [ ] `cdc-reviewer` valide la conformité ;
- [ ] l'écran respecte le chapitre 3 et a été vérifié en largeur 360 px ;
- [ ] les migrations sont créées et réversibles ;
- [ ] **avant chaque fin de lot** (pas nécessairement à chaque tâche), la suite de tests complète passe aussi sur MySQL/MariaDB, pas seulement sur SQLite (décision du 25/09/2026) ; tout écart de comportement constaté entre les deux moteurs (verrouillage de lignes `select_for_update`, casse des comparaisons de texte, champs JSON) est signalé explicitement dans le compte rendu, même s'il n'empêche pas les tests de passer ;
- [ ] le compte rendu liste les décisions par défaut appliquées et les questions restantes.

## 10. Compte rendu attendu en fin de tâche

1. Ce qui a été fait (fichiers principaux).
2. Règles du cahier des charges couvertes (numéros de section).
3. Décisions par défaut appliquées (numéros du 10.2).
4. Tests ajoutés et résultat.
5. Points ouverts ou écarts restants.
