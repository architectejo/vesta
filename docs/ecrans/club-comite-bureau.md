# Écran — Comité et bureau

Sources : CDC 2.2, 2.3 (qui nomme qui), 2.4, 3.5 (identité du club en modale), 4.1 (ajout et import de joueurs), 4.3 (parrain), 4.6 (lien de paiement du club). Composants : `PlayerSearch`, `DataTable`, `docs/lot0/design-system.md`.

## 1. Objectif

Montrer à tous qui dirige le club, et permettre au Président (et au Coach pour le Capitaine) de gérer l'identité du club, les nominations et l'effectif, sans quitter la page.

## 2. Accès

Route `/club/comite`. Entrée « Club › Comité et bureau ». Tous les joueurs du club en lecture.

| Action | Qui |
| --- | --- |
| Modifier l'identité du club (nom, logo, couleurs, lien de paiement) | Président |
| Nommer / révoquer VP, DS, Trésorier, Trésorier adjoint, Intendant, Médecin | Président |
| Ajouter / retirer le Coach | Président |
| Choisir / changer le Capitaine | Coach |
| Transmettre la présidence | Président |
| Désigner les joueurs autorisés à ajouter des joueurs | Président |
| Ajouter un joueur, importer des joueurs | Président + joueurs désignés (D) |

## 3. Structure de la page

**En-tête** : titre « Comité et bureau » ; contexte « {nom du club} · {n} joueurs ». Action principale (Président ou désigné) : « Ajouter un joueur ». Menu « … » : « Importer des joueurs (CSV) » (même public).

1. **Identité du club** — logo 48 px, nom, pastilles des couleurs principale et secondaire, ville, pays, devise, fuseau horaire ; « Lien de paiement : configuré » / « non configuré » (visible par le Président seulement). Action de carte (Président) : « Modifier ».
2. **Président** — avatar 40, nom, « Président depuis le {date} ». Menu « … » (Président) : « Transmettre la présidence ».
3. **Bureau** (2.2) — une ligne par rôle, dans cet ordre : Vice-président, Directeur sportif, Trésorier, Trésorier adjoint, Intendant, Médecin. Ligne : libellé du rôle, avatar + nom du titulaire, ou `StatusBadge` gris « Poste vacant ». Clic → modale « Rôle : {rôle} ».
4. **Encadrement sportif** — « Coach » (titulaire ou « Poste vacant ») ; clic → modale « Rôle : Coach » (Président). « Capitaine » ; clic → modale « Changer de capitaine » (Coach) — définie dans `sport-espace-coach.md` §4.7.
5. **Ajout de joueurs** — « Joueurs autorisés à ajouter des joueurs » : puces avatar + nom. Action de carte (Président) : « Gérer ». Vide : « Seul le Président peut ajouter des joueurs. »
6. **Effectif** — `DataTable` (> 30 joueurs possibles) : recherche « Rechercher un joueur » ; filtres « Poste », « Statut », « Rôle ». Colonnes : Joueur (figée : avatar, nom) · N° · Poste · Rôles · Statut. Tri par défaut : nom. Clic → modale « Fiche du joueur » (fiche publique 4.2 + rôles ; pas de finances ni de santé).

Footer.

## 4. Modales

### 4.1 « Identité du club » (3.5) — taille `md`, Président

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Nom du club | TextField | Oui | 120 caractères max. (aligné sur le schéma de données, `Text(120)`) ; « Ce champ est obligatoire. » ; « 120 caractères au maximum. » |
| Logo | FileField (JPEG, PNG, WebP) + aperçu | Non | Formats standard |
| Couleur principale | Pastilles proposées depuis le logo + sélecteur + saisie hexadécimale | Oui | « Saisissez une couleur au format #RRGGBB. » |
| Couleur secondaire | Idem | Oui | Idem |
| Ville | TextField | Oui | — |
| Pays | TextField avec suggestions | Oui | — |
| Devise | SegmentedControl : USD / CDF | Oui | Défaut USD (4.1) |
| Fuseau horaire | Select | Oui | Défaut : fuseau du pays |
| Lien de paiement | TextField `url` | Non | « Saisissez une adresse commençant par https:// » |

- Au téléversement du logo : bloc « Couleurs proposées à partir du logo » avec deux pastilles et « Utiliser ces couleurs » (principe : design-system 2.4).
- **Aperçu** en direct : mini barre latérale (logo, nom, élément actif) et bouton principal aux couleurs choisies ; si l'ajustement de lisibilité s'applique : « Pour rester lisible, la teinte sera légèrement assombrie à l'affichage. »
- Si des paiements existent, le champ « Devise » est en lecture seule avec l'aide « La devise ne peut plus être changée : des paiements existent déjà. » (voir §7).
- Pied : « Annuler » / « Enregistrer ». Succès : « Identité du club mise à jour. » ; la barre latérale et le thème Classic se mettent à jour sans rechargement.

### 4.2 « Rôle : {rôle} » (2.3) — taille `md`

- Lecture : titulaire (avatar, nom, « depuis le {date} ») ou « Poste vacant ».
- Président, poste vacant : PlayerSearch « Choisir un joueur » (portée club, joueurs partis exclus) ; pied « Annuler » / « Nommer ». Aide : « Un joueur peut cumuler plusieurs rôles. »
- Président, poste occupé : pied « Fermer » / « Remplacer » (affiche le PlayerSearch, avec l'aide « {nom actuel} sera révoqué de ce rôle. ») ; menu « … » : « Révoquer » → ConfirmDialog « Révoquer {nom} du rôle de {rôle} ? Il sera prévenu. » — « Révoquer ».
- Succès : « {nom} est nommé {rôle}. Il a été prévenu. » / « {nom} n'est plus {rôle}. » (2.3 : log + notification).
- Erreur : « {rôle} a déjà un titulaire. » (si l'API refuse parce que le nombre de titulaires autorisé pour ce rôle est atteint, 10.2 n° 3 et 24).

### 4.3 « Transmettre la présidence » (2.3) — taille `md`, Président

- Texte : « Vous désignez votre successeur. Vous resterez joueur du club, sans le rôle de Président. Cette action est immédiate. »
- PlayerSearch « Nouveau président ».
- Pied : « Annuler » / « Transmettre » → ConfirmDialog « Transmettre la présidence à {nom} ? Vous perdrez immédiatement les droits de Président. » — « Transmettre ». Succès : « {nom} est le nouveau Président. »
- Aide en bas (lien) : « En cas de blocage, le changement peut être fait par le support Vesta, sur demande écrite du club après une assemblée générale. »

### 4.4 « Joueurs autorisés à ajouter des joueurs » — taille `md`, Président

PlayerSearch multiple ; puces « Retirer {nom} ». Pied : « Annuler » / « Enregistrer ». Succès : « Autorisations mises à jour. »

### 4.5 « Ajouter un joueur » (4.1) — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Prénom | TextField | Oui | — |
| Nom | TextField | Oui | — |
| Email | TextField `email` | Oui | « Cette adresse email est déjà utilisée. » |
| Téléphone (WhatsApp) | TextField `tel` | Non | — |
| Poste | SegmentedControl : Gardien / Défenseur / Milieu / Attaquant | Oui | « Choisissez un poste. » |
| Poste précis | TextField | Non | Ex. « Arrière gauche » |
| Numéro de maillot | NumberField | Non | « Le numéro {n} est déjà porté par {nom}. » |
| Date de naissance | DateField | Non | — |
| Poids (kg), Taille (cm) | NumberField × 2 | Non | — |
| Type de cotisation mensuelle | Select (types mensuels actifs) | Oui | « Choisissez un type de cotisation. » |
| Parrain | PlayerSearch (`role="parrain"` : joueurs inscrits seulement) | Oui | « Choisissez un parrain. » |

Aide en bas : « Le mot de passe initial est l'email. {prénom} devra le changer à sa première connexion. Il restera « En attente » jusqu'au paiement de l'adhésion et à la signature du parrain. » Pied : « Annuler » / « Ajouter le joueur ». Succès : « {nom} a été ajouté. Statut : En attente. »

Suite du parcours d'adhésion (hors de cette page) : la signature de la fiche par le parrain (code PIN) et la décision du Président après un refus ou un silence du parrain s'ouvrent depuis **deux points d'entrée** (la carte « À faire » de l'accueil est reportée après le Lot 5, voir `docs/backlog-post-mvp.md` — ces deux actions font partie du MVP et ne peuvent pas en dépendre) : la notification correspondante (fiche à signer, refus ou silence du parrain, CDC 4.3 et 4.17), et le bouton dédié dans la modale « Fiche du joueur » de l'Effectif (§4.7 ci-dessous). Spec minimale dans `club-accueil.md` §5.4 et §5.5 ; **modales détaillées au Lot 1 (adhésion, cf. CDC 4.3)**.

### 4.6 « Importer des joueurs » (4.1) — assistant `xl`, 2 étapes

1. **Fichier** : FileField `.csv` ; lien « Télécharger le modèle CSV » ; aide « Colonnes : email, prenom, nom, telephone, poste, numero, date_naissance, poids, taille, type_cotisation. Seuls email, prénom et nom sont obligatoires. Dates au format JJ/MM/AAAA ou AAAA-MM-JJ. Un email déjà présent met la fiche à jour. Les joueurs importés sont inscrits directement, sans parrainage. » Bouton « Importer ».
2. **Rapport** : « {n} joueurs créés · {m} mis à jour · {k} lignes en échec » ; liste des échecs « Ligne 12 : email invalide ». Bouton « Télécharger le rapport » ; pied « Fermer ».

### 4.7 « Fiche du joueur » — taille `lg`

Fiche publique (4.2 : carte, statistiques, aptitude sans diagnostic) + rôles actuels + statut. Pied : « Fermer », plus, uniquement quand l'adhésion du joueur est **En attente** (CDC 4.3) :
- **« Signer la fiche d'adhésion »** — visible seulement par le parrain désigné de ce joueur ; ouvre la modale de signature par code PIN (détaillée au Lot 1).
- **« Décider de l'adhésion »** — visible seulement par le Président, et seulement après un refus ou un silence du parrain (CDC 4.3, cas limites) ; ouvre la modale de décision (désigner un autre parrain ou annuler l'adhésion, détaillée au Lot 1).

Aucune donnée financière ni médicale détaillée.

## 5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Identité | Squelette logo + 3 lignes | Logo absent : initiales ; couleurs absentes : « Couleurs non définies. » | Modèle standard |
| Bureau | 6 lignes squelettes | Chaque rôle vide : « Poste vacant » | Modèle standard |
| Encadrement | 2 lignes | « Poste vacant » ; Capitaine vide : « Aucun capitaine désigné. » | Modèle standard |
| Effectif | 5 lignes | « Aucun joueur dans le club. » + (Pdt, D) « Ajouter un joueur » | Modèle standard |

## 6. Mobile (360 px) et ordinateur

- **360 px** : cartes empilées ; lignes de rôle sur deux niveaux (rôle en 13 px muted au-dessus, titulaire en dessous). Effectif : colonne Joueur figée, défilement horizontal dans le cadre.
- **≥ 1024 px** : deux colonnes 6/6 pour Identité + Président / Bureau + Encadrement ; Effectif sur toute la largeur en dessous.

## 7. Décisions par défaut et points ouverts

- **10.2 n° 3, étendu par le n° 24 (décidé, cahier des charges 10.2 n° 24)** : nombre de titulaires par rôle du bureau configurable par club, un seul par défaut. Cet écran décrit le cas par défaut (nommer sur un poste occupé = remplacer) ; le réglage du nombre de titulaires par rôle et l'affichage de plusieurs titulaires ne sont pas encore spécifiés ici — **point ouvert** à traiter dans une révision de cette spec.
- **Point ouvert** : la passation de présidence n'exige pas de code PIN dans la liste du 7.2, alors qu'elle est irréversible pour le Président sortant. Proposé : confirmation simple (conforme au CDC) ; ajout du PIN à décider par le client.
- **Point ouvert** : qui configure le lien de paiement (4.6 « dans ses paramètres ») ? Défaut appliqué : le Président, dans la modale d'identité.
- **Point ouvert** : changement de devise après des paiements — non traité par le CDC. Défaut d'interface : lecture seule dès qu'un paiement existe (à confirmer avec `finance-engine`).
- **Proposition** : tableau « Effectif » placé sur cette page, faute d'écran « Joueurs » dédié dans le 3.7.
