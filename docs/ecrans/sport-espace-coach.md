# Écran — Espace coach

Sources : CDC 2.3 (choix du Capitaine), 3.5 (nom et logo du club dans l'espace Coach), 4.7, 4.8 (création de match, défis), 4.9, 4.10, 4.11, 4.12 (aptitude), matrice 2.4. Composants : `docs/lot0/design-system.md`.

## 1. Objectif

Tableau de bord sportif : savoir qui est disponible, ce qui se passe aujourd'hui, et lancer les séances, matchs, évaluations et incidents sans chercher.

## 2. Accès

Route `/coach`. Entrée « Sport › Espace coach ».

| Rôle | Accès |
| --- | --- |
| Coach | Tout (création séance/match, incidents, évaluations, choix du Capitaine, plans) |
| Capitaine | Lecture ; ouvrir le pointage ; signaler un incident ; déclarer une blessure |
| Président | Lecture ; pointage et répartition A/B ; évaluations |
| Vice-président | Lecture ; évaluations |
| Directeur sportif | Lecture, **y compris les évaluations en lecture seule** (matrice 2.4, ligne « Évaluation des performances » : L) ; aucune saisie ni modification de note |
| Autres rôles | Pas d'entrée « Espace coach » ; ils consultent les pages Séances, Matchs, Discipline |

## 3. Structure de la page

**En-tête** : logo du club 32 px à gauche du titre (3.5) ; titre « Espace coach » ; contexte « {nom du club} · Saison {saison} ». Action principale (Coach) : « Créer une séance ». Secondaire (Coach) : « Créer un match ». Menu « … » : « Plans tactiques », « Discipline ».

1. **Aujourd'hui** — seulement s'il y a une séance ou un match aujourd'hui. Ligne : type, heure de rassemblement, heure limite, lieu, compteur « {n} présents · {m} non pointés », `StatusBadge` « Ouverte ». Action principale de la carte : « Ouvrir le pointage » (→ page Séance ou page du match). Si rien aujourd'hui : carte masquée.
2. **Disponibilité de l'effectif** — compteurs cliquables en une ligne : « {n} disponibles », « {n} en dette », « {n} suspendus », « {n} inaptes », « {n} en attente d'adhésion ». Chaque compteur non nul ouvre la modale « Joueurs indisponibles » filtrée. Données de l'API (le Coach ne voit que l'aptitude, jamais le diagnostic).
3. **Évaluations à faire** (Coach, Président, VP) — une ligne par séance/match des dernières 48 h avec des joueurs non évalués : « {Séance du 27/09} · {n} joueurs à évaluer · reste {h} h ». Bouton `sm` « Évaluer ». Section masquée si vide. Le Directeur sportif (lecture seule) ne voit pas cette section d'action ; il consulte les évaluations via l'onglet « Évaluations » des modales « Séance » et « Match ».
4. **Matchs** — deux sous-listes : « À venir » (5 prochains) et « Joués » (5 derniers), « Voir plus » chacune (3.3). Ligne : date, adversaire, type, domicile/extérieur, score si joué, badge (« Défi en attente », « Composition publiée »). Clic → modale « Match ».
5. **Séances** — 5 dernières (3.3), « Voir plus ». Ligne : date, terrain (« Terrain non précisé » si vide), « {n} présents », badge « Ouverte » / « Verrouillée ». Clic → modale « Séance ».
6. **Discipline** — « Suspensions en cours » (5 premières, triées par nombre de matchs restants décroissant, « Voir plus », 3.3 : avatar, nom, « encore {n} match(s) ») puis « Derniers incidents » (5, « Voir plus », 4.9) : avatar, nom, type (icône carton jaune/rouge + texte), cause, date. Action de carte (Coach, Capitaine) : « Signaler un incident ». Clic → modale « Incident ».
7. **Capitaine** — avatar, nom du Capitaine actuel. Action (Coach) : « Changer de capitaine ».
8. **Plans tactiques** — 5 derniers plans (nom, formation, match rattaché), « Voir plus » (3.3) ; action (Coach) « Nouveau plan » (→ page Plan tactique). Clic → page du plan (lecture seule pour les autres rôles).

Footer.

## 4. Modales

### 4.1 « Créer une séance » (4.7) — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Date | DateField | Oui | Défaut : aujourd'hui ; « La date ne peut pas être passée. » |
| Heure de rassemblement | TimeField | Oui | « Ce champ est obligatoire. » |
| Heure limite d'arrivée | TimeField | Oui | « L'heure limite doit être égale ou postérieure à l'heure de rassemblement. » |
| Terrain | TextField | Non | 120 caractères max. ; si vide, affiché « Terrain non précisé » |
| Maillots équipe A | Sélecteur de pastilles (palette design-system 2.7) | Oui | Défaut : Bleu |
| Maillots équipe B | Sélecteur de pastilles | Oui | Défaut : Rouge ; « Les deux équipes doivent avoir des couleurs différentes. » |
| Consignes | TextArea | Non | 1 000 caractères max. |

Pied : « Annuler » / « Créer la séance ». Succès : « Séance créée. Les joueurs ont été prévenus. » (4.17).

### 4.2 « Créer un match » (4.8) — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Adversaire | SegmentedControl : Club Vesta / Équipe extérieure | Oui | — |
| Club adverse | ClubSearch (si Club Vesta) | Oui | « Choisissez un club. » |
| Nom de l'équipe | TextField (si Équipe extérieure) | Oui | « Ce champ est obligatoire. » |
| Date | DateField | Oui | — |
| Heure | TimeField | Oui | — |
| Lieu | TextField | Non | Si vide, affiché « Lieu non précisé » |
| Type | SegmentedControl : Amical / Championnat / Tournoi | Oui | — |
| Domicile ou extérieur | SegmentedControl : Domicile / Extérieur | Oui | — |

Si « Club Vesta » et « Amical » : aide « Une demande de défi sera envoyée à {club}. Le match apparaîtra chez les deux clubs après acceptation. » ; bouton principal « Envoyer le défi » (sinon « Créer le match »). Succès : « Match créé. Les joueurs ont été prévenus. » / « Défi envoyé à {club}. »

### 4.3 « Séance » (détail, 4.7) — taille `lg`

En-tête : « Séance du {date} » ; sous-titre « {terrain} · rassemblement {heure} · limite {heure} » ; badge Ouverte/Verrouillée.
Onglets : « Présences » (compteurs + liste : avatar, nom, heure d'arrivée, badge Présent / En retard / Absent / Absent excusé), « Équipes » (`PitchBoard` `readonly`), « Incidents » (5 + Voir plus), « Évaluations » (moyennes par joueur ; visibles par Coach, Président, VP et Directeur sportif selon la matrice 2.4 — DS en lecture seule, sans bouton « Évaluer » ; chaque joueur ne voit que ses propres notes), « Consignes ».
Pied : « Fermer » (4.7) / action principale : « Ouvrir la séance » si ouverte (→ page Séance), sinon aucune. Verrouillée : bandeau « Séance verrouillée depuis minuit. Seul le support peut la corriger, à la demande du Président. »

### 4.4 « Match » (détail) — taille `lg`

En-tête : « {nom du club} – {adversaire} » ; sous-titre « {type} · {domicile/extérieur} · {date heure} · {lieu} ». Corps : score, composition (si publiée ou si Coach), buteurs, cartons. Pied : « Fermer » / « Ouvrir la feuille de match » (→ page du match). Défi en attente (club destinataire, Président ou Coach) : boutons « Refuser » / « Accepter le défi ».

### 4.5 « Signaler un incident » (4.9) — taille `md`, fonctionne hors connexion

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Séance ou match | Liste de choix des 5 derniers événements (non-joueurs) | Oui | Défaut : événement du jour |
| Joueur | PlayerSearch (suggestions : présents à l'événement d'abord) | Oui | « Choisissez un joueur. » |
| Minute | NumberField | Non | 0 à 130 ; « Saisissez une minute entre 0 et 130. » |
| Type | SegmentedControl : Carton jaune / Carton rouge / Sanction interne | Oui | Icônes carton + texte |
| Cause | SegmentedControl ou liste : Contestation / Faute grossière / Comportement / Retard / Autre | Oui | — |
| Précision | TextArea | Non | 500 caractères max. |
| Arbitre ou auteur de la sanction | TextField | Non | Aide : « Facultatif : laissez vide si vous ne connaissez pas le nom de l'arbitre. » ; 120 caractères max. |

Pied : « Annuler » / « Enregistrer ». Succès : « Incident enregistré. » ; si l'API déclenche une suspension : « Incident enregistré. {nom} est suspendu pour {n} match(s). » Hors connexion : « Incident enregistré sur ce téléphone. Il sera envoyé au retour du réseau. »

Détail d'un incident : lecture des champs + auteur de la saisie ; menu « … » (Coach, le jour même de l'événement) : « Modifier », « Supprimer » (ConfirmDialog).

### 4.6 « Évaluer les joueurs » (4.10) — taille `xl` (plein écran mobile)

- En-tête : « Évaluer — {séance ou match du date} » ; sous-titre « Modifiable encore {h} h ».
- Corps : liste des joueurs présents (recherche en haut). Ligne : avatar 40, nom, curseur « Note globale » 0 à 10 (pas de 0,5), valeur affichée à droite (16 px), bouton « Détails » qui déplie : 5 curseurs facultatifs « Technique », « Physique », « Tactique », « Mental », « Attitude » ; TextArea « Commentaire (facultatif) » ; interrupteur « Commentaire visible par le joueur ».
- Joueur non noté = pas de note (le curseur démarre sur « — » et non sur 0).
- Récapitulatif collant en haut : « {n} joueurs notés sur {m} ».
- Pied : « Annuler » / « Enregistrer ({n} notes) ». Succès : « Évaluations enregistrées. »
- Après 48 h : ouverture en lecture seule, bandeau « Évaluation verrouillée (plus de 48 heures). »

### 4.7 « Changer de capitaine » (2.3) — taille `md`

PlayerSearch « Nouveau capitaine » (portée club ; joueurs partis exclus). Aide : « {nom actuel} ne sera plus capitaine. » Pied : « Annuler » / « Enregistrer ». Succès : « {nom} est le nouveau capitaine. Il a été prévenu. »

### 4.8 « Joueurs indisponibles » — taille `md`

Onglets « En dette », « Suspendus », « Inaptes », « En attente ». Ligne : avatar, nom, raison fournie par l'API (« {montant} dû », « encore {n} match(s) », « Inapte · retour prévu le {date} », « Adhésion non finalisée »). Aucun diagnostic médical. Pied : « Fermer ».

## 5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Disponibilité | Squelette d'une ligne | « {n} disponibles » seul | Modèle standard |
| Matchs à venir | 3 lignes | « Aucun match prévu. » + (Coach) « Créer un match » | Modèle standard |
| Matchs joués | 3 lignes | « Aucun match joué pour l'instant. » | Modèle standard |
| Séances | 3 lignes | « Aucune séance pour l'instant. » + (Coach) « Créer une séance » | Modèle standard |
| Suspensions | 1 ligne | « Aucun joueur suspendu. » | Modèle standard |
| Derniers incidents | 3 lignes | « Aucun incident pour l'instant. » + (Coach, Cap.) « Signaler un incident » | Modèle standard |
| Capitaine | 1 ligne | « Aucun capitaine désigné. » + (Coach) « Choisir un capitaine » | Modèle standard |
| Plans tactiques | 2 lignes | « Aucun plan tactique. » + (Coach) « Nouveau plan » | Modèle standard |

## 6. Mobile (360 px) et ordinateur

- **360 px** : ordre du §3. Compteurs de disponibilité en puces défilantes sur une ligne. Matchs « À venir » / « Joués » en onglets dans la carte.
- **≥ 1024 px** : deux colonnes 8/4. Principale : Aujourd'hui, Matchs, Séances, Discipline. Latérale : Disponibilité, Évaluations à faire, Capitaine, Plans tactiques.

## 7. Décisions par défaut et points ouverts

- **10.2 n° 8** appliquée : message de suspension issu de l'API (1 match par défaut, 5e jaune de la saison — voir aussi `docs/lot0/analyse.md` 1.6).
- **10.2 n° 9** appliquée : note globale sur 10 + 5 critères facultatifs (technique, physique, tactique, mental, attitude).
- **10.2 n° 10** : sans Médecin, le Coach fixe l'aptitude — l'action sera dans le module médical, pas sur cet écran.
- **Point ouvert — écart à la charte** : le 4.10 parle d'« un écran » de saisie rapide ; conformément à 3.2, c'est une **modale plein écran**. À valider.
- **Point ouvert** : périmètre d'accès à l'« Espace coach » (Coach, Capitaine, Président, VP, DS) déduit de la matrice 2.4 ; le CDC ne le définit pas.
- **Proposition** : pas de 0,5 sur les notes ; minute limitée à 130.
- **Corrigé après contrôle `cdc-reviewer`** : « Arbitre ou auteur de la sanction » est **facultatif** (un Capitaine ou un Coach ne connaît pas toujours le nom exact de l'arbitre) ; le terrain d'une séance et le lieu d'un match sont **facultatifs**, conformément au schéma de données ; le Directeur sportif a accès aux évaluations en lecture seule (matrice 2.4).
- **Proposition** : modification ou suppression d'un incident limitée au jour même (alignée sur le verrouillage des séances 4.7).
