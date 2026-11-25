# Annexe D — Modèles de documents

Cahier des charges 10.1 (Annexe D) : « Fiche d'adhésion, reçu, quitus,
procès-verbal, aux couleurs du club » — produite au Lot 2 (partie 1 : reçu et
fiche d'adhésion, tâche 2.9 du plan) **et** au Lot 4 (partie 2 : quitus et
procès-verbal d'AG, tâche 4.9).

**État à ce jour (Lot 4, tâche 4.9)** : ce document fixe le **cadre commun**
aux quatre documents (§1) et le gabarit détaillé des deux documents de la
partie 2 : le quitus de transfert (§2) et le procès-verbal d'assemblée
générale (§3). **La partie 1 (reçu, fiche d'adhésion) n'a jamais été livrée
sous forme d'annexe** : aucun fichier de la tâche 2.9 n'existe dans `docs/`.
Elle devra être rédigée dans ce même fichier (sections 4 et 5), en reprenant
le cadre du §1 sans le modifier (voir point ouvert n° 1).

**Règle de synchronisation** (même principe que les annexes C et E). Ce
document est la cible validée. Les générateurs existants
(`backend/apps/mercato/services.py`, `_build_quitus_pdf` ;
`backend/apps/assemblies/services.py`, `_build_minutes_pdf`) ont été écrits
avant lui, avec un gabarit « minimal » assumé dans leurs docstrings. Les écarts
constatés sont listés au §6 : c'est à `backend-dev` (PV) et à `finance-engine`
ou `backend-dev` (quitus, selon l'affectation de la tâche) d'aligner le code,
puis à `test-engineer` de vérifier les textes exacts (extraction du texte du
PDF). Une fois l'écart résorbé, toute modification d'un gabarit passe par ce
document **et** par le code dans le même commit.

Sources : CDC 0.4 (glossaire, « Quitus »), 3.4 (couleurs de statut), 3.5
(« documents PDF : nom et logo du club »), 3.6, 4.14, 4.15, 6.1 (génération PDF
côté serveur), 6.7, 7.2, 7.5, 10.1, 10.2 n° 24, 28, 30, 34 ; CLAUDE.md §2
règles 2, 7, 10, 11, 18, 19, 20 et §7 (fuseau du club) ;
`docs/lot0/design-system.md` §2.4 (couleurs du club = accents seulement, dont
« liseré d'en-tête des PDF »), §2.5, §3.10, §4 (formats) ;
`docs/ecrans/assemblees-page-ag.md` §4.2 et §4.6 ; `docs/ecrans/mercato.md`
§2.1, §4.3, §5 ; `docs/ecrans/mercato-marche.md`.

**Mise à jour (Lot 4, tâche 4.9, implémentation)** : les écarts bloquants du
§6 sont résorbés côté code (`backend/apps/assemblies/services.py`,
`backend/apps/mercato/services.py`, et un nouveau module partagé
`backend/apps/core/pdf.py` qui porte désormais le cadre commun du §1 pour
éviter que les générateurs divergent). Le détail par écart, y compris ce qui
reste ouvert (police embarquée, retour à la ligne du nom de club sur 2
lignes, libellé exact du cas « Président = Vice-président »), est à jour au
§6. Toute nouvelle modification du gabarit doit continuer à passer par ce
document **et** par le code dans le même travail (règle ci-dessus, inchangée).

---

## 1. Cadre commun à tous les documents de l'annexe D

S'applique au quitus et au PV, et s'appliquera tel quel au reçu et à la fiche
d'adhésion.

### 1.1 Format de page

| Élément | Valeur |
| --- | --- |
| Format | A4 portrait (210 × 297 mm) |
| Marges | 18 mm à gauche et à droite ; 16 mm en haut ; 18 mm en bas (pied de page compris) |
| Largeur utile | 174 mm, **une seule colonne** pour tout le corps. Seul le bloc de signatures du PV (§3) utilise deux colonnes. |
| Fond | Blanc. **Aucun aplat de couleur** sur une grande surface (bandeau plein, fond de page) : économie d'encre sur les imprimantes à jet d'encre des clubs, lisibilité en impression noir et blanc, et conformité au `design-system.md` §2.4 (couleurs du club réservées aux accents). |

Justification mobile : le document est ouvert le plus souvent dans la
visionneuse d'un smartphone (360 px de large, `assemblees-page-ag.md` §4.6).
Une colonne unique et un corps à 10 pt restent lisibles après un simple zoom à
la largeur du texte, sans défilement horizontal.

### 1.2 Typographie

Police sans empattement **embarquée dans le PDF**, couvrant le français
complet (accents, « œ », « ’ », guillemets « », tiret —, point médian ·).
Proposition : DejaVu Sans (libre de droits) ou équivalent. Les polices
standard de reportlab (Helvetica, encodage WinAnsi) couvrent le français
courant mais pas tous les caractères qu'un utilisateur peut coller dans un
texte libre (PV, décision) : un caractère non couvert est remplacé par « ? »,
**jamais** par un échec de génération.

| Usage | Taille | Graisse | Couleur |
| --- | --- | --- | --- |
| Nom du club (en-tête) | 13 pt | Gras | `#111827` |
| Ville, pays (en-tête) | 9 pt | Normal | `#4B5563` |
| Titre du document | 16 pt | Gras | `#111827` |
| Sous-titre du document (date, lieu, référence) | 10 pt | Normal | `#4B5563` |
| Titre de section | 11 pt | Gras | `#111827`, filet de 0,5 pt en couleur principale du club dessous (règles de couleur du §1.3) |
| Texte courant, libellés et valeurs | 10 pt | Normal (valeurs importantes en gras) | `#111827` |
| Mentions, aides, texte en italique | 9 pt | Italique | `#4B5563` |
| Pied de page | 8 pt | Normal | `#4B5563` |

Interligne : 1,35 (texte courant à 10 pt → 13,5 pt). Aucune taille supérieure
à 16 pt sur un document (« pas de gros caractères », CDC 3.1, appliqué aussi
aux documents). Aucun texte n'est écrit en couleur du club : le texte reste
`#111827` ou `#4B5563` (contraste ≥ 7:1 sur blanc, lisible imprimé en noir et
blanc comme au soleil).

### 1.3 En-tête (première page)

```
┌──────────────────────────────────────────────────────────────────┐
│ [LOGO]  {Nom du club}                             {Type de doc.} │
│ 18 mm   {Ville}, {Pays}                        Réf. {référence}  │
├══════════════════════════════════════════════════════════════════┤ ← liseré 1,2 mm couleur principale
├──────────────────────────────────────────────────────────────────┤ ← liseré 0,6 mm couleur secondaire
```

- **Logo** (`Club.logo`) : à gauche, dans une boîte de 18 × 18 mm, proportions
  conservées, centré verticalement. **Logo absent, illisible ou dans un format
  non pris en charge** : l'emplacement disparaît, le nom du club s'aligne sur
  la marge gauche ; la génération **n'échoue jamais** à cause du logo (principe
  déjà retenu pour la fiche d'adhésion, `clubs/services.py`,
  `_build_membership_application_pdf`).
- **Nom du club** (`Club.name`), 13 pt gras, à 4 mm à droite du logo. Jamais
  tronqué sur un document officiel : retour à la ligne sur 2 lignes au plus ;
  au-delà, la taille passe à 11 pt.
- **Ville, pays** (`Club.city`, `Club.country`), 9 pt, sous le nom.
- **À droite**, alignés à droite, 9 pt `#4B5563` : type du document
  (« Quitus de transfert », « Procès-verbal d'AG ») et référence du document
  (définie pour chaque document).
- **Liseré** sous l'en-tête, pleine largeur utile : 1,2 mm en couleur
  principale du club (`Club.primary_color`), puis, collé dessous, 0,6 mm en
  couleur secondaire (`Club.secondary_color`).
- Hauteur totale de l'en-tête : 26 mm, liseré compris. 8 mm d'espace avant le
  titre du document.

**Couleurs du club dans le PDF (marque blanche, CLAUDE.md §2.18)** :
- Les deux couleurs viennent **uniquement** des champs du club, au moment de
  la génération. Aucune couleur de club n'est écrite dans le code.
- Couleur absente ou mal formée : le liseré prend la valeur neutre `#4B5563`
  (principale) et `#E1E5EB` (secondaire), c'est-à-dire les neutres du thème
  Clair (`design-system.md` §2.4 point 4). Jamais une couleur « par défaut »
  qui ressemblerait à l'identité d'un club (le bleu marine actuel des
  générateurs, `(0.12, 0.16, 0.32)`, doit disparaître).
- Couleur trop claire pour se voir sur du blanc (contraste avec `#FFFFFF`
  inférieur à 1,5:1, par exemple un club blanc et jaune pâle) : elle est
  assombrie par pas jusqu'à 1,5:1 (même principe que `design-system.md` §2.4
  point 3). Le liseré n'étant pas du texte, ce seuil suffit.
- Les couleurs du club **ne remplacent jamais** les couleurs de statut (§1.6).

### 1.4 En-tête des pages suivantes

Version réduite, 12 mm : nom du club (10 pt gras) à gauche, type du document
et référence (9 pt) à droite, liseré principal de 0,8 mm dessous. Pas de logo
(le logo n'apparaît qu'en première page).

### 1.5 Pied de page (toutes les pages)

```
{Nom du club} — {Type de document} — Réf. {référence}          Page {n} sur {N}
Document généré le {date longue} à {HH:MM}
```

- 8 pt, `#4B5563`, filet supérieur 0,5 pt `#E1E5EB`.
- « Page {n} sur {N} » : le total des pages est obligatoire (un PV peut faire
  plusieurs pages ; une page manquante doit se voir).
- **Aucune mention de l'Éditeur** : ni « IMARA TECH Group », ni la phrase du
  footer de l'interface. Voir §1.8 et point ouvert n° 2.
- **Aucune mention de « Vesta »** dans le pied de page ni dans le corps : le
  document porte l'identité du club seul (marque blanche). Voir point ouvert
  n° 3.

### 1.6 Statuts sur un document

Un statut s'affiche comme dans l'interface (CDC 3.4, `design-system.md` §2.5) :
pastille + libellé, jamais la couleur seule. Pastille ronde de 2,5 mm, libellé
10 pt gras, fond clair arrondi (rayon 1 mm) derrière l'ensemble.

| Famille | Pastille | Fond | Texte |
| --- | --- | --- | --- |
| Vert (« En ordre », « Quorum atteint ») | `#16A34A` | `#DCFCE7` | `#14532D` |
| Orange (« Quorum non atteint ») | `#EA580C` | `#FFEDD5` | `#7C2D12` |
| Gris (« Poste vacant ») | `#6B7280` | `#F3F4F6` | `#1F2937` |

Imprimé en noir et blanc, le libellé porte seul l'information.

### 1.7 Formats (identiques à l'interface, `design-system.md` §4)

- Toutes les dates et heures dans le **fuseau du club** (`ClubSettings.timezone`,
  CLAUDE.md §7), jamais en UTC.
- Date longue : « dimanche 27 septembre 2026 ». Date courte (tableaux) :
  « 27/09/2026 ». Heure : « 07:30 ». Les noms de jours et de mois sont tirés
  d'une table en français dans le code, **pas** de la locale du serveur
  (l'hébergement cPanel ne garantit pas la locale `fr_FR`).
- Pourcentages : virgule décimale, décimales masquées si nulles : « 50 % »,
  « 66,67 % » (jamais « 50.00 % »).
- Montants (s'il y en a) : « 1 250 $ », « 25 000 FC », devise du club.
- Nom d'une personne : « {Prénom} {Nom} » tel qu'enregistré.
- Aucun identifiant technique visible (code de rôle, valeur d'`enum`, nom de
  champ), **aucune référence au cahier des charges** (« CDC 4.14 », « 10.2 n° 28 »)
  dans un texte imprimé.

### 1.8 Ce qui n'apparaît jamais sur un document de l'annexe D

- « IMARA TECH Group » et la phrase du footer de l'interface (CLAUDE.md §2.19 :
  « Nulle part ailleurs (code, textes, documents générés) » ;
  `design-system.md` §3.10 : « ni dans les PDF générés »).
- Un nom, un logo, une couleur ou un lien de paiement de club écrit en dur
  (CLAUDE.md §2.18) ; le repli actuel `club.name or "Club"` n'a pas lieu
  d'être (le nom du club est obligatoire).
- Une donnée médicale (CLAUDE.md §2.11), une donnée financière individuelle
  hors du strict objet du document, une donnée de contact (téléphone, email),
  une date de naissance (minimisation, CDC 7.5).

### 1.9 Métadonnées et fichier

- Métadonnées du PDF : titre = titre du document ; auteur et créateur =
  `Club.name` ; sujet = type du document. Jamais « anonymous » (valeur par
  défaut de reportlab).
- Un document est **figé à sa génération** : il garde le nom, le logo et les
  couleurs du club à cette date et n'est jamais régénéré (les générateurs
  actuels sont déjà idempotents). Un changement d'identité du club ne modifie
  pas les documents déjà émis.
- Fichier servi uniquement par une vue authentifiée (CLAUDE.md §2.10, CDC 6.7).
- Nom du fichier téléchargé : voir chaque document.

---

## 2. Quitus de transfert

### 2.1 Rôle du document

Attestation numérique qu'un joueur n'a aucune dette envers son club (CDC 0.4),
émise **par le club d'origine (club A)**, à ses couleurs (`mercato.md` §4.3),
générée automatiquement quand le transfert est finalisé (CDC 4.14 étape 4).

| | |
| --- | --- |
| Générateur actuel | `backend/apps/mercato/services.py`, `_build_quitus_pdf`, appelé par `complete_transfer` |
| Déclencheur | `_evaluate_debt_and_progress` : `is_in_good_standing(...)` renvoie vrai (acceptation du joueur, ou déblocage automatique après paiement, 10.2 n° 30) |
| Identité portée | Club A (`offer.origin_club`) : logo, nom, ville, pays, couleurs |
| Téléchargement | `OfferQuitusDownloadView` : le joueur, Président et Trésorier du club A, Président et Directeur sportif du club B (proposition `mercato.md` point ouvert n° 7, voir point ouvert n° 6 ci-dessous) |
| Référence | `Q-{offer.pk}` |
| Fichier téléchargé | `quitus-{nom}-{prenom}-{AAAA-MM-JJ}.pdf` (ASCII, sans accents ni espaces ; date de finalisation) |

**Comment `is_in_good_standing` se traduit sur le document.** Un quitus n'est
généré **que** si le joueur est en ordre : il n'existe pas de « quitus
refusé » ni de variante « en dette ». Le blocage pour dette reste une
information de l'interface (bandeau et chronologie, `mercato.md` §5.2), jamais
un document. Le quitus présente donc ce statut sous une seule forme : le
badge vert **« En ordre »** (libellé de la charte, CDC 3.4) dans un cadre
d'attestation, avec la date et l'heure de la vérification
(`offer.debt_checked_at`). **Aucun montant** n'y figure : ni solde, ni avance,
ni historique de paiements. Le club B et ses dirigeants peuvent télécharger le
document ; ils ne doivent rien apprendre de plus que le fait attesté
(`mercato.md` §2.1, points 1 et 2).

### 2.2 Maquette (une page)

```
┌──────────────────────────────────────────────────────────────────┐
│ [LOGO]  {Club A}                               Quitus de transfert│
│         {Ville}, {Pays}                                 Réf. Q-{n}│
├══════════════════════════════════════════════════════════════════┤
│                                                                  │
│ Quitus de transfert                                     (16 pt)  │
│ Établi le {date longue de finalisation} à {HH:MM}       (10 pt)  │
│                                                                  │
│ Joueur ────────────────────────────────────────────────          │
│ Nom                 {Prénom} {Nom}                               │
│ Poste               {Poste}                                      │
│ Membre de {Club A}  du {JJ/MM/AAAA} au {JJ/MM/AAAA}              │
│                                                                  │
│ Transfert ─────────────────────────────────────────────          │
│ Club quitté         {Club A} ({Ville})                           │
│ Club rejoint        {Club B} ({Ville})                           │
│ Offre acceptée le   {JJ/MM/AAAA}                                 │
│ Transfert effectué le {JJ/MM/AAAA}                               │
│                                                                  │
│ ┌ Attestation ─────────────────────────────────────────────┐     │
│ │ ● En ordre                                               │     │
│ │ {Club A} atteste que {Prénom} {Nom} n'a aucune dette     │     │
│ │ envers le club à la date du {date longue}.               │     │
│ │ Solde vérifié automatiquement le {JJ/MM/AAAA} à {HH:MM}. │     │
│ │ Aucun frais de sortie n'est dû à {Club A}.               │     │
│ └──────────────────────────────────────────────────────────┘     │
│                                                                  │
│ Ce quitus est établi automatiquement après vérification du       │
│ solde du joueur. Il ne comporte pas de signature manuscrite.     │
│ Il atteste la situation du joueur à la date de vérification.     │
│                                                                  │
│ (pied de page commun, §1.5)                                      │
└──────────────────────────────────────────────────────────────────┘
```

### 2.3 Contenu, dans l'ordre, avec la source de chaque donnée

| # | Zone | Texte exact | Source |
| --- | --- | --- | --- |
| 1 | En-tête (§1.3) | droite : `Quitus de transfert` / `Réf. Q-{n}` | `offer.origin_club` ; `offer.pk` |
| 2 | Titre | `Quitus de transfert` | — |
| 3 | Sous-titre | `Établi le {date longue} à {HH:MM}` | `offer.quitus_generated_at` (fuseau du club A) |
| 4 | Section « Joueur » : `Nom` | `{Prénom} {Nom}` | `offer.target_membership.user` |
| 5 | `Poste` | libellé français du poste ; ligne omise si vide | `offer.target_membership.position` (champ public, CDC 4.2) |
| 6 | `Membre de {Club A}` | `du {JJ/MM/AAAA} au {JJ/MM/AAAA}` | `joined_on`, `left_on` de l'adhésion au club A |
| 7 | Section « Transfert » : `Club quitté` | `{Club A} ({Ville})` | `offer.origin_club.name`, `.city` |
| 8 | `Club rejoint` | `{Club B} ({Ville})` | `offer.target_club.name`, `.city` |
| 9 | `Offre acceptée le` | `{JJ/MM/AAAA}` | `offer.player_decision_at` |
| 10 | `Transfert effectué le` | `{JJ/MM/AAAA}` | `offer.completed_at` |
| 11 | Cadre « Attestation » : badge | `En ordre` (vert, §1.6) | toujours vrai quand le document existe |
| 12 | Phrase d'attestation (10 pt, gras sur le nom) | `{Club A} atteste que {Prénom} {Nom} n'a aucune dette envers le club à la date du {date longue}.` | `offer.debt_checked_at` |
| 13 | Vérification (9 pt) | `Solde vérifié automatiquement le {JJ/MM/AAAA} à {HH:MM}.` | `offer.debt_checked_at` |
| 14 | Frais de sortie (9 pt) | `Aucun frais de sortie n'est dû à {Club A}.` | Règle 10.2 n° 34 (toujours vraie) |
| 15 | Mention finale (9 pt italique) | `Ce quitus est établi automatiquement après vérification du solde du joueur. Il ne comporte pas de signature manuscrite. Il atteste la situation du joueur à la date de vérification.` | CDC 4.14 étape 4 (génération automatique, aucune signature prévue) |

Cadre « Attestation » : bordure 0,75 pt `#16A34A`, fond blanc (pas d'aplat),
marge intérieure 4 mm, badge en haut à gauche. Le cadre est le seul élément
coloré du corps : c'est l'information du document.

**Exclus du quitus** : message et conditions de l'offre (négociation entre
clubs, éventuellement financière), auteur de l'offre, montant de la dette
passée ou du blocage, date de naissance, numéro de maillot, contacts, frais
d'adhésion au club B (ils concernent le club B, pas l'émetteur).

### 2.4 Mobile et impression

- Une seule page dans tous les cas (aucun texte libre de longueur variable).
- Nom du joueur ou d'un club très long : retour à la ligne dans la colonne des
  valeurs (colonne des libellés fixe à 42 mm), jamais de troncature.

---

## 3. Procès-verbal d'assemblée générale

### 3.1 Rôle du document

PV rédigé dans l'application, signé électroniquement par le Président et le
Vice-président, ou par le Président seul si le poste de Vice-président est
vacant, la vacance étant actée dans le PV (CDC 4.15, 7.2, 10.2 n° 28). Généré
dès que le PV est complet (`assemblees-page-ag.md` §4.6).

| | |
| --- | --- |
| Générateur actuel | `backend/apps/assemblies/services.py`, `_build_minutes_pdf`, appelé par `_generate_minutes_pdf` depuis `sign_minutes` |
| Identité portée | Club de l'AG (`assembly.club`) |
| Téléchargement | Tous les joueurs du club, vue authentifiée (`assemblees-page-ag.md` §2 et §4.6) |
| Référence | `AG-{AAAA-MM-JJ}` (date de l'AG) ; si deux AG le même jour : `AG-{AAAA-MM-JJ}-{assembly.pk}` |
| Fichier téléchargé | `pv-ag-{ordinaire|extraordinaire}-{AAAA-MM-JJ}.pdf` |

### 3.2 Maquette (première page, puis suite)

```
┌──────────────────────────────────────────────────────────────────┐
│ [LOGO]  {Nom du club}                         Procès-verbal d'AG │
│         {Ville}, {Pays}                          Réf. AG-{date}  │
├══════════════════════════════════════════════════════════════════┤
│ Procès-verbal de l'assemblée générale {ordinaire}       (16 pt)  │
│ du {dimanche 27 septembre 2026}                         (16 pt)  │
│ {HH:MM} · {Lieu}                                        (10 pt)  │
│                                                                  │
│ Présences et quorum ──────────────────────────────────           │
│ ● Quorum atteint                                                 │
│ {n} présents sur {total} joueurs actifs — quorum de {seuil} %    │
│ atteint                                                          │
│                                                                  │
│ Ordre du jour et décisions ───────────────────────────           │
│ 1. {Intitulé du point}                            (10 pt gras)   │
│    {Description}                                  (9 pt)         │
│    Pour {n} · Contre {n} · Abstention {n}                        │
│    Décision retenue : {décision}                                 │
│ 2. …                                                             │
│                                                                  │
│ Texte du procès-verbal ───────────────────────────────           │
│ {paragraphes…}                                                   │
│                                                                  │
│ Signatures ───────────────────────────────────────────           │
│ [mention de vacance, si le cas se présente]                      │
│ ┌ Président ───────────────┐  ┌ Vice-président ──────────┐       │
│ │ {Prénom} {Nom}           │  │ {Prénom} {Nom}           │       │
│ │ Signé électroniquement   │  │ Signé électroniquement   │       │
│ └──────────────────────────┘  └──────────────────────────┘       │
│ Signatures électroniques confirmées dans l'application,          │
│ enregistrées dans le journal d'activité du club.                 │
│                                                                  │
│ (pied de page commun, §1.5 : « Page 1 sur N »)                   │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3 Contenu, dans l'ordre, avec la source de chaque donnée

Les textes marqués « écran » reprennent mot pour mot ceux de
`assemblees-page-ag.md` pour que l'interface et le document emploient les
mêmes mots.

| # | Zone | Texte exact | Source |
| --- | --- | --- | --- |
| 1 | En-tête (§1.3) | droite : `Procès-verbal d'AG` / `Réf. AG-{AAAA-MM-JJ}` | `assembly.club` ; `assembly.scheduled_date` |
| 2 | Titre (16 pt, 2 lignes autorisées) | `Procès-verbal de l'assemblée générale {ordinaire / extraordinaire} du {date longue}` (écran §4.6) | `assembly.assembly_type`, `assembly.scheduled_date` |
| 3 | Sous-titre | `{HH:MM} · {Lieu}` (même forme que le sous-titre de la modale, écran §4.2). Lieu vide (données anciennes) : `{HH:MM}` seul | `scheduled_time`, `location` |
| 4 | Section `Présences et quorum` : badge | `Quorum atteint` (vert) / `Quorum non atteint` (orange) | `get_quorum(assembly).reached` |
| 5 | Phrase de quorum | `{n} présents sur {total} joueurs actifs — quorum de {seuil} % {atteint / non atteint}` (écran §4.6), pourcentage au format §1.7 | `get_quorum(...)` : `present`, `total`, `threshold`, `reached` |
| 6 | Section `Ordre du jour et décisions` : un bloc par point, dans l'ordre | `{ordre}. {intitulé}` (10 pt gras) | `AgendaItem.order`, `.title` |
| 7 | Description du point (si non vide) | texte libre, 9 pt, retrait 6 mm | `AgendaItem.description` |
| 8 | Votes | `Pour {n} · Contre {n} · Abstention {n}` (écran §4.2) | `Decision.votes_for`, `votes_against`, `votes_abstain` |
| 9 | Décision | `Décision retenue : {décision}` (écran §4.2), texte libre complet | `Decision.outcome` |
| 10 | Point sans vote saisi | `Aucune décision saisie.` (9 pt italique ; texte de l'état vide de l'écran §5) | absence de `Decision` pour ce point |
| 11 | Section `Texte du procès-verbal` | texte intégral, 10 pt ; une ligne vide = nouveau paragraphe (4 pt d'espace) ; ligne commençant par `- ` ou `• ` = puce ; `1. ` conservé tel quel | `Minutes.content` |
| 12 | Section `Signatures` : mention de vacance (si `vp_vacant_at_signature`) | `Le poste de Vice-président étant vacant à la date de la signature, le procès-verbal est signé par le Président seul.` (écran §4.2, texte servi par l'API ; 9 pt italique, au-dessus des cadres) | `Minutes.vp_vacant_at_signature` |
| 13 | Cadre `Président` | ligne 1 : `{Prénom} {Nom}` (10 pt gras) ; ligne 2 : `Signé électroniquement par {Prénom} {Nom}, Président, le {JJ/MM/AAAA} à {HH:MM}` (écran §4.6, 9 pt) | `president_signed_by`, `president_signed_at` |
| 14 | Cadre `Vice-président`, cas signé | idem avec `Vice-président` | `vp_signed_by`, `vp_signed_at` |
| 15 | Cadre `Vice-président`, cas vacant | ligne 1 : badge gris `Poste vacant` (libellé de l'écran §4.2) ; ligne 2 : `Signature non requise.` (9 pt) | `vp_vacant_at_signature` vrai et `vp_signed_by` vide |
| 16 | Mention sous les cadres (9 pt italique) | `Signatures électroniques confirmées dans l'application, enregistrées dans le journal d'activité du club.` | CDC 7.2, 5.2 |

### 3.4 Zone de signature : les deux cas de figure (10.2 n° 28)

**Cas 1 — Président et Vice-président.** Deux cadres côte à côte, chacun de
84 mm de large, 3 mm d'écart, bordure 0,5 pt `#7B8699`, titre du cadre
(fonction) 9 pt gras `#4B5563` en haut à gauche. Le Président est toujours à
gauche. Aucune mention de vacance.

**Cas 2 — Poste de Vice-président vacant.** La mention de vacance (ligne 12)
s'affiche **au-dessus** des cadres, pleine largeur ; le cadre du Président est
identique au cas 1 ; le cadre du Vice-président est **conservé** (et non
supprimé) avec le badge gris « Poste vacant » : un lecteur voit tout de suite
qu'une seule signature est attendue et pourquoi, et la mise en page ne change
pas d'un PV à l'autre.

**Cas 3 — Président qui cumule le rôle de Vice-président (corrigé à la tâche
4.9).** Le code distinguait mal ce cas d'une vacance réelle : le champ
`vp_vacant_at_signature` valait vrai dans les deux cas, et le PV imprimait à
tort « Le poste de Vice-président étant vacant… » alors que le poste est
occupé par le Président. Un second champ, `Minutes.vp_role_held_by_president`,
distingue désormais les deux cas (calculé dans
`apps.assemblies.services.sign_minutes`, exposé par l'API). Quand il est vrai,
le PV affiche à la place de la mention de vacance : « Le Président exerçant
aussi la fonction de Vice-président, le procès-verbal est signé par lui seul. »
et le cadre Vice-président porte le badge gris « Fonction exercée par le
Président » au lieu de « Poste vacant ». **Ce libellé exact reste un texte
neutre proposé, non tranché par le client** (voir point ouvert n° 5, toujours
ouvert) : seul le cas objectivement faux (poste affiché vacant alors qu'il est
occupé) a été corrigé, pas le libellé définitif. L'écran (`AssemblyDetailModal.tsx`)
n'a pas encore été mis à jour pour ce cas et affiche toujours le texte du cas
2 quel que soit `vp_role_held_by_president` — à faire par `frontend-dev` une
fois le libellé validé.

Règles communes aux trois cas :
- Aucune fausse signature manuscrite, aucune image de signature, aucun trait
  « Signature : ________ » : la signature est électronique (confirmation dans l'application). Le texte
  « Signé électroniquement par… » est la signature affichée.
- Le bloc « Signatures » (titre, mention éventuelle, cadres, mention finale)
  **ne se coupe jamais** entre deux pages : s'il ne tient pas en bas de page, il
  passe entier à la page suivante.
- **Plusieurs titulaires du poste de VP** (10.2 n° 24) : un seul champ
  `vp_signed_by` existe ; le cadre affiche le VP qui a signé. Si le client
  décide que chaque VP en poste doit signer (point ouvert de l'écran §7), le
  gabarit ajoute un cadre par VP, sur une nouvelle ligne de deux cadres.
- **Président qui cumule le rôle de VP** : il signe une seule fois, au titre de
  Président (écran §2). Le code actuel met alors `vp_vacant_at_signature` à
  vrai, ce qui imprime « poste vacant » alors que le poste est occupé par le
  Président. Voir point ouvert n° 5.

### 3.5 Pagination et longueur

- Le PV peut faire plusieurs pages : en-tête réduit (§1.4) et « Page {n} sur
  {N} » (§1.5) sur chaque page.
- **Aucune troncature de texte** : intitulés (jusqu'à 160 caractères),
  descriptions, décisions et texte du PV sont repliés à la largeur utile, sur
  autant de lignes que nécessaire.
- Un titre de section n'est jamais seul en bas de page (au moins 2 lignes de
  son contenu le suivent, sinon il passe à la page suivante). Un bloc de point
  (intitulé + votes + décision) ne se coupe pas s'il fait moins de 1/3 de page.

### 3.6 Exclus du PV

Liste nominative des présents (le CDC 4.15 et l'écran ne prévoient que le
décompte ; voir point ouvert n° 7), toute donnée financière individuelle,
toute donnée médicale ou d'aptitude, « action liée » d'une décision (valeur
technique, non lisible hors de l'application), toute mention de l'Éditeur.

---

## 4. Reçu (partie 1, Lot 2) — à rédiger

Non livré à la tâche 2.9. Doit reprendre le §1 sans le modifier.

**Générateur provisoire (non validé par le client ni par `ui-designer`).**
`backend/apps/treasury/services.py`, `_build_payment_receipt_pdf`, appelé par
`issue_payment_receipt`. En attendant le gabarit de cette section, le contenu
retenu est le plus restreint possible, dans le cadre commun du §1 :

| | |
| --- | --- |
| Déclencheur | Validation du paiement (CDC 4.4.4), après enregistrement effectif en base. Paiements de l'import historique (CDC 4.4.8) : émis par la commande `issue_missing_payment_receipts` (cron), pas pendant l'import. |
| Identité portée | Club du paiement : logo, nom, ville, pays, couleurs (§1.3) |
| Référence | `R-{numéro de reçu}` (numéro séquentiel par club) |
| Titre | `Reçu de paiement n° {n}`, sous-titre `Émis le {date longue} à {HH:MM}` |
| Contenu | Section « Joueur » : nom du joueur concerné. Section « Paiement » : cotisation, montant (devise du paiement, format §1.7), mode, référence (si renseignée), date du paiement, date et heure de validation. Mention finale 9 pt italique : `Ce reçu est émis automatiquement par {Club} à la validation du paiement. Il ne comporte pas de signature manuscrite.` |
| Exclus | Solde, statut « En ordre », répartition par mois (projection recalculable, alors que le reçu est figé), nom du valideur, contacts, toute mention de l'Éditeur ou de « Vesta » |
| Fichier stocké | `recu-c{club}-{numéro sur 6 chiffres}.pdf`, stockage privé ; servi par `PaymentReceiptDownloadView` sous le nom `paiement-{id}-recu.pdf` |
| Figé | Jamais régénéré ni remplacé (verrou dans `Payment.save`) ; conservé en cas d'annulation du paiement. Un paiement annulé qui n'a jamais eu de reçu n'en reçoit pas après coup. |

## 5. Fiche d'adhésion (partie 1, Lot 2) — à rédiger

Non livré à la tâche 2.9. Doit reprendre le §1 sans le modifier. Générateur
existant : `backend/apps/clubs/services.py`, `_build_membership_application_pdf`
(mêmes écarts que ceux du §6 : bandeau plein, pas de logo, UTC, titre « Fiche
d'adhesion » sans accent, référence au CDC dans le texte imprimé).

---

## 6. Écarts constatés entre ce gabarit et les générateurs existants

**Mise à jour tâche 4.9 (implémentation)** : tous les écarts « Bloquant »
ci-dessous sont corrigés (`backend-dev`), avec un module partagé
`backend/apps/core/pdf.py` qui porte le cadre commun du §1 (en-tête, pied de
page paginé « Page n sur N », couleurs assombries jusqu'à un contraste
suffisant, formats de date/pourcentage). Les références de ligne ci-dessous
restent celles du code **avant** la tâche 4.9 (utiles pour retrouver l'écart
d'origine dans l'historique) ; le code a été substantiellement réécrit, pas
seulement corrigé ligne à ligne. Classement inchangé : **bloquant** =
contraire à une règle du CDC ou de CLAUDE.md, ou perte d'information ;
**amélioration** = alignement sur le gabarit.

### 6.1 Procès-verbal — `backend/apps/assemblies/services.py`, `_build_minutes_pdf`

| # | Ligne (avant 4.9) | Écart | Correction attendue | Niveau | Statut |
| --- | --- | --- | --- | --- | --- |
| 1 | 617 | `text[:120]` : toute ligne est **coupée à 120 caractères** sans retour à la ligne. Un intitulé de 160 caractères, une décision ou un paragraphe du PV perdent leur fin. Un PV signé dont le texte est amputé n'est pas fidèle à ce qui a été signé. | Repli à la largeur utile, sans troncature (§3.5) | Bloquant | **Corrigé** (`apps.core.pdf.wrap_text`) |
| 2 | 596-609 | Aucun logo : le CDC 3.5 exige « nom et logo du club » sur les documents PDF | En-tête §1.3 avec `Club.logo`, repli sans échec | Bloquant | **Corrigé** (`apps.core.pdf.draw_header`, `try/except` autour du décodage) |
| 3 | 679, 686 | `president_signed_at.strftime(...)` et `vp_signed_at.strftime(...)` affichent l'heure **UTC** | Conversion dans le fuseau du club (§1.7, CLAUDE.md §7) | Bloquant | **Corrigé** (`.astimezone(tz)` avant formatage) |
| 4 | 596-600 | Bandeau plein de 30 mm en couleur du club, texte blanc dessus, **sans contrôle de contraste** : un club aux couleurs claires (jaune, blanc) produit un nom de club illisible. Contraire au `design-system.md` §2.4 (couleur du club = liseré d'en-tête des PDF) | En-tête blanc, texte `#111827`, liseré (§1.3) | Bloquant | **Corrigé** (`apps.core.pdf.draw_header` + `darken_until_contrast`, seuil 1,5:1) |
| 5 | 628 | `{quorum.threshold} %` imprime « 50.00 % » (point décimal, décimales nulles) | Format §1.7 : « 50 % » | Amélioration | **Corrigé** (`apps.core.pdf.format_percentage`) |
| 6 | 606 | Date du titre en `JJ/MM/AAAA` ; l'écran §4.6 demande la date longue | `du {date longue}` | Amélioration | **Corrigé** (`apps.core.pdf.format_date_longue`) |
| 7 | 626 | « Heure : … · Lieu : Non precise » : libellés et repli non accentué | `{HH:MM} · {Lieu}` (§3.3 ligne 3) | Amélioration | **Corrigé** |
| 8 | 632-653 | Ordre du jour et décisions en deux listes séparées ; les décisions ne rappellent que le numéro du point | Un bloc par point : intitulé, description, votes, décision (§3.3 lignes 6 à 10) | Amélioration | **Corrigé** |
| 9 | 662-688 | Signatures en simples lignes ; pas de cadre VP dans le cas vacant ; bloc coupable entre deux pages | Zone de signature §3.4 (deux cadres, bloc insécable) | Amélioration | **Corrigé pour l'essentiel** : deux cadres, badge « Poste vacant »/« Fonction exercée par le Président ». Le bloc n'est pas garanti insécable dans 100 % des cas limites (un seul `ensure_space` avant le bloc, pas un contrôle exhaustif de tous les sous-éléments) — reste un écart mineur, non testé de façon exhaustive. |
| 10 | 620-624 | Pas d'en-tête sur les pages suivantes, pas de numérotation « Page n sur N » | §1.4 et §1.5 | Amélioration | **Corrigé** (`apps.core.pdf.draw_continuation_header`, `NumberedDocumentCanvas`) |
| 11 | 588-589 | Repli de couleur `(0.12, 0.16, 0.32)` (bleu marine) quand le club n'a pas de couleur | Neutres du §1.3 | Amélioration | **Corrigé** (`NEUTRAL_PRIMARY_RGB`/`NEUTRAL_SECONDARY_RGB`) |
| 12 | 600 | `club.name or "Club"` | Nom du club obligatoire, pas de repli | Amélioration | **Corrigé** |
| 13 | — | Police Helvetica/WinAnsi : un caractère hors WinAnsi collé dans le texte du PV peut faire échouer ou dégrader la génération | Police embarquée (§1.2) | Amélioration | **Non fait** : embarquer une police (DejaVu Sans) est une infrastructure plus lourde (fichier de police à livrer, enregistrement `pdfmetrics`) écartée à ce stade par choix de proportionnalité — signalé au compte rendu, pas tranché en cachette. |
| 14 | — | Métadonnées PDF par défaut (auteur « anonymous ») ; nom de fichier `pv-ag-{id}.pdf` | §1.9 et §3.1 | Amélioration | **Corrigé** (`setTitle`/`setAuthor`/`setCreator`/`setSubject`, nom de fichier `pv-ag-{ordinaire|extraordinaire}-{AAAA-MM-JJ}.pdf` repris tel quel par la vue de téléchargement) |

Non fait, hors §6 d'origine mais constaté à l'implémentation : le nom du club
n'est pas replié sur 2 lignes avec réduction à 11 pt au-delà (§1.3) — reste sur
une seule ligne quelle que soit sa longueur. Écart mineur, signalé.

Conforme : aucune mention de l'Éditeur, aucune donnée financière ni médicale,
génération unique (idempotente). Le cas « Président cumule le rôle de
Vice-président » (§3.4 cas 3, ci-dessus) a aussi été corrigé à cette tâche.

### 6.2 Quitus — `backend/apps/mercato/services.py`, `_build_quitus_pdf`

| # | Ligne (avant 4.9) | Écart | Correction attendue | Niveau | Statut |
| --- | --- | --- | --- | --- | --- |
| 1 | 406 | Texte imprimé « (CDC 4.14) » : référence interne au cahier des charges sur un document remis au joueur et à un autre club | Supprimer ; attestation du §2.3 lignes 11 à 15 | Bloquant | **Corrigé** |
| 2 | 382-388 | Aucun logo (CDC 3.5) ; bandeau plein, texte blanc sans contrôle de contraste (même défaut que PV n° 4) | En-tête §1.3 | Bloquant | **Corrigé** (même `apps.core.pdf.draw_header` que le PV) |
| 3 | 403 | `now.strftime("%d/%m/%Y")` : date **UTC** ; peut afficher la veille ou le lendemain de la date réelle au club autour de minuit | Fuseau du club A (§1.7) | Bloquant | **Corrigé** (date/heure via `.astimezone(tz)`, `tz` du club d'origine) |
| 4 | 400-406 | Le statut « en ordre » n'apparaît que dans une phrase en italique 10 pt en bas de page ; ni date ni heure de vérification (`debt_checked_at` n'est pas imprimé) | Cadre « Attestation » avec badge « En ordre » et date de vérification (§2.3) | Bloquant (c'est l'objet même du document) | **Corrigé** |
| 5 | — | Aucune référence de document, pas de période d'adhésion, pas de date d'acceptation | §2.3 lignes 1, 6, 9, 10 | Amélioration | **Corrigé** |
| 6 | 385 | Nom du club en 18 pt | 13 pt (§1.2) | Amélioration | **Corrigé** |
| 7 | 376 | Repli bleu marine ; pas de liseré secondaire (incohérent avec le PV et la fiche d'adhésion) | §1.3 | Amélioration | **Corrigé** |
| 8 | — | Métadonnées, nom de fichier `quitus-{pk}.pdf` (`views.py` l. 232) | §1.9 et §2.1 | Amélioration | **Corrigé** (métadonnées + nom de fichier `quitus-{nom}-{prenom}-{AAAA-MM-JJ}.pdf`, ASCII sans accents ; la vue de téléchargement reprend ce nom stocké plutôt que d'en recalculer un) |

Remarque hors gabarit, transmise (et corrigée) à l'implémentation :
`_evaluate_debt_and_progress` appelait `is_in_good_standing(..., at_date=now.date())`
avec une date **UTC** et non la date du jour dans le fuseau du club d'origine.
Entre minuit UTC et minuit à Kinshasa (UTC+1), l'échéance du jour pouvait être
comptée ou non selon l'heure. **Corrigé** : la date utilisée pour le contrôle
de dette et celle imprimée sur le quitus (« à la date du … ») viennent
désormais toutes les deux de `_club_today(offer.origin_club, now=now)`, la
même fonction. Constaté au passage (même classe de bug, hors §6 d'origine,
corrigé par cohérence) : `complete_transfer` calculait aussi `left_on`/
`joined_on` avec `now.date()` (UTC) au lieu de la date locale de chaque club ;
ces deux dates utilisent désormais `_club_today(...)` du club concerné.

Non fait, constaté à l'implémentation : le nom du club n'est pas replié sur 2
lignes (même écart mineur que le PV, § ci-dessus).

---

## 7. Couverture du cahier des charges

| Règle | Où |
| --- | --- |
| 10.1 annexe D : quitus et PV « aux couleurs du club » | §1.3 (logo, nom, liseré aux deux couleurs), §2, §3 |
| 3.5 : « documents PDF : nom et logo du club » ; marque blanche | §1.3, §1.8 |
| 3.4 : couleurs de statut fixes, jamais la couleur seule | §1.6, §2.3 ligne 11, §3.3 lignes 4 et 15 |
| 3.1 : pas de gros caractères ; 3.6 : lisibilité en plein soleil | §1.2 (16 pt maximum, texte jamais en couleur du club) |
| 0.4 et 4.14 étape 4 : quitus = absence de dette, généré automatiquement | §2.1, §2.3 |
| 10.2 n° 30 : déblocage automatique | §2.1 (même document, quel que soit le déclencheur) |
| 10.2 n° 34 : aucun frais de sortie | §2.3 ligne 14 |
| 4.15 : PV rédigé, signé électroniquement, généré en PDF ; présences, quorum, votes, décisions | §3 |
| 10.2 n° 28 : Président seul si VP vacant, vacance actée dans le PV | §3.3 lignes 12 et 15, §3.4 cas 2 |
| 10.2 n° 18 : quorum en pourcentage | §3.3 ligne 5 |
| 10.2 n° 24 : plusieurs titulaires | §3.4 |
| 7.2 : signature électronique confirmée dans l'application | §3.4 |
| 6.7, CLAUDE.md §2.10 : fichiers privés par vue authentifiée | §1.9 |
| CLAUDE.md §2.11, 7.5 : pas de donnée médicale, minimisation | §1.8, §2.3 (exclus), §3.6 |
| CLAUDE.md §2.19 : Éditeur absent des documents générés | §1.5, §1.8 |
| CLAUDE.md §7 : affichage dans le fuseau du club | §1.7 |

## 8. Points ouverts

1. **Partie 1 de l'annexe D absente.** La tâche 2.9 (reçu, fiche d'adhésion)
   n'a laissé aucun livrable dans `docs/`. Le cadre commun (§1) est donc posé
   ici pour la première fois ; les sections 4 et 5 restent à rédiger par
   `ui-designer`, et le générateur de la fiche d'adhésion à aligner. Un générateur
   de reçu provisoire existe désormais (§4) ; son contenu reste à valider.
   À replanifier.
2. **Mention « IMARA TECH Group » sur les PDF — non tranchée par le CDC.** Le
   CDC 3.5 place la phrase dans le « footer, sur toutes les pages » et dit que
   c'est « la seule mention de l'Éditeur dans l'application », sans parler des
   documents PDF. CLAUDE.md §2.19 est explicite : « Nulle part ailleurs (code,
   textes, documents générés) », tout comme `design-system.md` §3.10 (« ni dans
   les PDF générés »). Il n'y a pas de contradiction ouverte (le CDC est muet,
   CLAUDE.md précise), et la position appliquée est la plus prudente : **aucune
   mention sur les documents**. Elle doit néanmoins être confirmée par le
   client, car un document remis à un autre club est un support de visibilité
   de l'engagement solidaire (CDC 1.1) que le client pourrait vouloir y voir.
   Si le client le souhaite, c'est CLAUDE.md §2.19 qui devra être modifié
   d'abord, pas le gabarit seul.
3. **Mention « Vesta » sur les documents.** L'annexe E autorise « Vesta »
   (nom du produit) dans les notifications. Sur les documents, le gabarit ne
   l'emploie pas (marque blanche, identité du club seule), y compris dans les
   phrases « Solde vérifié automatiquement… » et « enregistrées dans le journal
   d'activité du club ». À confirmer.
4. **Vérification d'authenticité du quitus.** Un quitus sans signature peut
   être imité. Un code de vérification ou un QR code renvoyant vers une page de
   contrôle n'est pas prévu par le CDC : ce serait une demande nouvelle
   (circuit 9.4), non intégrée au gabarit.
5. **Président qui cumule le rôle de Vice-président — cas objectivement faux
   corrigé à la tâche 4.9, libellé toujours ouvert.** `sign_minutes` distingue
   désormais ce cas d'une vacance réelle via un nouveau champ,
   `Minutes.vp_role_held_by_president` (migration
   `apps/assemblies/migrations/0002_add_vp_role_held_by_president.py`) : le PV
   n'imprime plus « Le poste de Vice-président étant vacant… » quand le poste
   est occupé par le Président. Le texte affiché à la place — « Le Président
   exerçant aussi la fonction de Vice-président, le procès-verbal est signé
   par lui seul. », badge « Fonction exercée par le Président » — reste le
   **texte neutre proposé** ici même, **non validé par le client** : appliqué
   à titre provisoire pour ne pas laisser afficher une contre-vérité, mais pas
   une décision définitive. Le champ est exposé par l'API
   (`MinutesSerializer.vp_role_held_by_president`) ; **l'écran
   (`AssemblyDetailModal.tsx`) n'a pas été mis à jour** et continue d'afficher
   le texte du cas 2 (vacance) quel que soit ce champ — à faire par
   `frontend-dev` une fois le libellé validé par le client.
6. **Qui télécharge le quitus** (`mercato.md` point ouvert n° 7) : la
   proposition codée (joueur ; Président et Trésorier du club A ; Président et
   Directeur sportif du club B) est compatible avec ce gabarit, puisque le
   document ne contient aucun montant. Toujours à valider par le client.
7. **Liste nominative des présents dans le PV.** Un PV d'AG comporte souvent la
   liste des présents. Ni le CDC 4.15 ni l'écran ne la demandent : le gabarit
   s'en tient au décompte. Demande nouvelle si le client la souhaite (circuit
   9.4) ; elle se placerait en annexe du PV, après les signatures.
8. **Modèles de documents modifiables par le Superuser** (CDC 4.18,
   `superuser-espace.md` §3.5, `schema-donnees.md` Q3). L'étendue de ce qui est
   modifiable n'est pas définie. Proposition : seuls les textes de mention
   (§2.3 ligne 15, §3.3 ligne 16) seraient modifiables ; la structure,
   l'identité du club, l'attestation du quitus et la zone de signature restent
   fixes. À trancher avant le Lot 5.
9. **Date d'appréciation de la vacance du VP** : repris sans changement du
   point ouvert de `assemblees-page-ag.md` §7 (date de la signature, position
   provisoire du schéma).
