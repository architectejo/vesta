# Écran — Mercato

> **Remplacé par `docs/ecrans/mercato.md` (révision du Lot 4, 29/09/2026).** Ce document du Lot 0 n'est conservé que pour l'historique ; ne pas l'utiliser pour l'implémentation (déblocage désormais tranché par le 10.2 n° 30, onglet « Aptitude » retiré de la fiche publique vue par un autre club, blocage sans montant côté club offrant).

Sources : CDC 1.2 (espace public), 4.2 (fiche publique), 4.14, 4.17, 6.3 (données publiques), matrice 2.4 (ligne « Mercato : offres et transferts »). Composants : `DataTable`, `PlayerSearch` (portée `public`), `ClubSearch`, `docs/lot0/design-system.md`.

## 1. Objectif

Permettre à chaque joueur de gérer sa disponibilité et ses offres, et aux dirigeants de chercher des joueurs dans tous les clubs, de contacter les autres clubs et de suivre les transferts jusqu'au quitus.

## 2. Accès

Route `/mercato`. Entrée « Mercato ».

| Section | Pdt | VP | DS | Trés | Coach | Adj, Int, Cap, Méd | Joueur |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Ma disponibilité, Mes offres | P | P | P | P | P | P | P |
| Offres du club | É | L | É | L | L | — | — |
| Marché | É (offre) | L | É (offre) | L | L | — | — |
| Messagerie entre clubs | É | — | É | — | — | — | — |

Seules les données publiques des autres clubs sont affichées (6.3) : jamais poids, taille, téléphone, finances ni santé (4.2).

## 3. Structure de la page

**En-tête** : titre « Mercato » ; contexte « {nom du club} · Saison {saison} ». Action principale (Président, DS) : « Faire une offre ». Menu « … » (Président, DS) : « Nouveau message à un club ».

1. **Ma disponibilité** (tous) — SegmentedControl « Fermé aux offres » / « Sur le marché », effet immédiat ; aide « Sur le marché, les dirigeants des autres clubs peuvent voir votre fiche publique et vous faire une offre. » Toast « Vous êtes maintenant sur le marché. » / « Vous êtes fermé aux offres. »
2. **Mes offres** (tous, section masquée si vide et aucune offre passée) — offres me concernant : logo et nom du club offrant, date, `StatusBadge` (En attente, Acceptée, Refusée, Bloquée, Transfert effectué). Clic → modale « Offre reçue ».
3. **Offres du club** (Président, VP, DS, Trésorier, Coach) — `Tabs` « Envoyées » / « Reçues » (offres visant nos joueurs). `DataTable` (> 30 possibles, 3.3) : recherche joueur ; filtre « Statut » ; colonnes Joueur (figée) · Club · Date · Statut. Clic → modale « Offre de transfert ».
4. **Marché** (Président, VP, DS, Trésorier, Coach) — `DataTable` : recherche « Rechercher un joueur » ; filtres « Poste », « Âge » (plage), « Ville », « Club » (ClubSearch), « Note moyenne » (minimum). Colonnes : Joueur (figée : avatar, nom) · Poste · Âge · Club (logo + nom) · Ville · Note moyenne. Tri par défaut : note moyenne décroissante. 20 par page. Les joueurs de notre club apparaissent avec la mention « Votre club » et sans action d'offre. Clic → modale « Fiche publique ».
5. **Messagerie entre clubs** (Président, DS) — 5 dernières conversations (logo et nom du club, dernier message, date, pastille non lu), « Voir plus ». Clic → modale « Conversation ».

Footer.

## 4. Modales

### 4.1 « Fiche publique » (4.2) — taille `lg`

Onglets de la fiche détaillée : « Aperçu » (identité publique, radar, forme récente), « Statistiques », « Évaluations », « Présences », « Discipline », « Carrière », « Aptitude » (apte / restriction / inapte, sans diagnostic). En-tête : avatar, nom, club, `StatusBadge` « Sur le marché ». Pied : « Fermer » / (Président, DS, joueur d'un autre club) « Faire une offre ». Menu « … » (Président, DS) : « Contacter son club ».

### 4.2 « Faire une offre » (4.14) — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Joueur visé | PlayerSearch portée `public` (joueurs « Sur le marché » des autres clubs) ; prérempli depuis la fiche | Oui | « Choisissez un joueur. » ; joueur fermé aux offres : grisé « Fermé aux offres » |
| Message | TextArea | Oui | 1 000 caractères max. |
| Conditions | TextArea | Non | 1 000 caractères max. |

Aide : « Le joueur et son club seront prévenus. Si le joueur accepte, Vesta vérifie qu'il n'a pas de dette dans son club actuel avant le transfert. Des frais d'adhésion à votre club seront dus. » Pied : « Annuler » / « Envoyer l'offre ». Succès : « Offre envoyée à {nom}. »

### 4.3 « Offre reçue » (joueur) — taille `md`

- Lecture : club offrant (logo, nom), message, conditions, date.
- **Chronologie** (4.14) : « Offre envoyée » → « Réponse du joueur » → « Vérification du solde » → « Quitus » → « Transfert effectué », chaque étape avec date et pastille (faite / en cours / bloquée).
- Pied (offre en attente) : « Refuser » (secondaire) / « Accepter ».
  - « Refuser » → ConfirmDialog « Refuser l'offre de {club} ? » — « Refuser ».
  - « Accepter » → ConfirmDialog « Accepter l'offre de {club} ? Si vous n'avez aucune dette, votre adhésion à {club actuel} sera clôturée et vous rejoindrez {club}. Des frais d'adhésion de {montant} y seront dus. » — « Accepter ».
- Résultats :
  - Sans dette : « Transfert effectué. Bienvenue à {club} ! » ; quitus téléchargeable (« Télécharger le quitus »). L'interface prend l'identité du nouveau club à la navigation suivante (club actif déduit de l'adhésion, 6.3).
  - Avec dette : encadré rouge « Transfert bloqué : régularisez {montant} auprès de {club actuel} pour obtenir votre quitus. » + bouton « Contribuer ». Badge « Bloquée ». L'offre reste acceptée. **Proposition par défaut, non tranchée par le 10.2 ni par le 4.14 (question Q8 de `docs/lot0/analyse.md`)** : le transfert se débloque automatiquement dès que le solde calculé repasse positif ou nul, sans nouvelle acceptation du joueur (texte : « Le transfert se fera dès que votre solde sera à jour. »). Si le client décide qu'une nouvelle acceptation est nécessaire, ce texte devient « Une fois votre solde à jour, vous devrez confirmer à nouveau l'offre. » et un bouton « Confirmer le transfert » apparaît à la régularisation.

### 4.4 « Offre de transfert » (dirigeants) — taille `md`

Même lecture et même chronologie que §4.3. *Reporté après le Lot 5, voir `docs/backlog-post-mvp.md` (entrée 8) — non livrable au MVP* : pour une offre envoyée en attente, menu « … » (Président, DS) « Retirer l'offre » (ConfirmDialog — « Retirer »). Aucune action d'opposition pour le club d'origine (voir §7). Pied : « Fermer ».

### 4.5 « Nouveau message à un club » / « Conversation » (4.14) — taille `md`

- Nouveau message : « Club » (ClubSearch), « Destinataire » (SegmentedControl : Président / Directeur sportif), « Message » (TextArea, obligatoire). Pied « Annuler » / « Envoyer ». Succès : « Message envoyé. »
- Conversation : fil des messages (bulles, avatar, nom, rôle, heure), champ de réponse collé en bas avec bouton « Envoyer » (40 px). Mise à jour par interrogation toutes les 30 s (6.5). Pied : « Fermer ».

## 5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Ma disponibilité | Squelette 1 ligne | — | Échec du changement : retour à la valeur précédente + toast « Modification non enregistrée. Réessayez. » |
| Mes offres | 2 lignes | « Aucune offre reçue. » | Modèle standard |
| Offres du club | 5 lignes | Envoyées : « Aucune offre envoyée. » + (Pdt, DS) « Faire une offre » ; Reçues : « Aucune offre reçue pour vos joueurs. » | Modèle standard |
| Marché | 5 lignes | « Aucun joueur sur le marché pour l'instant. » ; avec filtres : « Aucun résultat pour ces filtres. » + « Effacer les filtres » | Modèle standard |
| Messagerie | 3 lignes | « Aucune conversation. » + (Pdt, DS) « Nouveau message à un club » | Modèle standard |

## 6. Mobile (360 px) et ordinateur

- **360 px** : sections empilées ; tableaux avec colonne Joueur figée, défilement horizontal dans le cadre ; filtres du marché dans un panneau bas.
- **≥ 1024 px** : colonne latérale (4) : Ma disponibilité, Mes offres, Messagerie ; colonne principale (8) : Marché, puis Offres du club.

## 7. Décisions par défaut et points ouverts

- **10.2 n° 11** appliquée : le club d'origine **ne peut pas s'opposer** au transfert d'un joueur sans dette (aucun bouton d'opposition) ; **frais d'adhésion dus** au nouveau club (mentionnés dans l'offre et à l'acceptation).
- **Point ouvert — accès** : 1.2 range le mercato dans l'espace public, mais la matrice 2.4 ne donne aux simples joueurs (et à l'adjoint, l'intendant, le capitaine, le médecin) que leurs propres données. **Défaut appliqué : la matrice fait foi** — le tableau « Marché » n'est visible que par Pdt, VP, DS, Trés, Coach.
- **Proposition par défaut non tranchée par le 10.2 (Q8 de `docs/lot0/analyse.md`)** : déblocage automatique d'un transfert bloqué pour dette dès que le solde repasse positif ou nul, sans nouvelle acceptation. Ce n'est pas un fait acquis du cahier des charges (le 4.14 ne le précise pas) ; à confirmer par le client.
- **Reporté après le Lot 5, voir `docs/backlog-post-mvp.md` (entrée 8)** : retrait d'une offre en attente par le club qui l'a envoyée (non décrit au 4.14).
