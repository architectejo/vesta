# Écran — Mon profil

Sources : CDC 4.1 (page « Mon profil », modale à onglets), 4.2, 4.4.7 (sa propre ligne de grille), 4.5.3 (assistance sociale), 4.6 (Contribuer, J'ai payé), 2.4 et 4.12 (aptitude, consentement médical, 10.2 n° 15), 4.14 (disponibilité mercato), 4.17 (préférence email), 7.1, 7.5. Composants : `docs/lot0/design-system.md`.

## 1. Objectif

Permettre à chaque joueur de consulter en un coup d'œil sa situation (statut, finances, statistiques, aptitude) et de tout modifier sans quitter la page, via des modales.

## 2. Accès

Route `/profil`. Tout joueur du club, pour **ses propres données** (P dans la matrice 2.4). Les Superusers n'ont pas de profil joueur. La fiche d'un autre joueur s'ouvre en modale depuis les autres écrans (fiche publique 4.2) ; ce document ne couvre que le profil personnel.

## 3. Structure de la page

**En-tête de page** : titre « Mon profil » ; contexte « {nom du club} · Saison {saison} ». Action principale : « Modifier mon profil ». Menu « … » : « Voir ma carte de joueur », « Télécharger mes données », « Déconnecter tous mes appareils », « Demander la suppression de mon compte ».

Sections en cartes :

1. **Identité** — Avatar 72 px, nom (20 px/600), « {poste} · n° {numéro} » (texte « Poste non renseigné » / « Sans numéro » si vide), rôles en puces neutres (« Président », « Capitaine »…), `StatusBadge` financier + badges superposés (Suspendu, Blessé). Mention sous poste et numéro : « Poste et numéro sont attribués par le Coach. »
2. **Situation financière** (4.1, 4.6)
   - Ligne principale : « Solde » {montant signé} (20 px, tabular-nums) + `StatusBadge` (« En ordre » / « En dette · {montant} »).
   - Aide si en dette : « Réglez {montant} pour être à nouveau en ordre et pouvoir être composé. »
   - Action principale de la carte : « Contribuer » (ouvre le lien de paiement du club, nouvel onglet). Action secondaire : « J'ai payé ». Si aucun lien n'est configuré : bouton masqué et texte « Le club n'a pas encore configuré de lien de paiement. Réglez auprès du trésorier. »
   - Sous-section « Prochaines échéances » : 3 prochaines (mois, type, montant, date d'échéance).
   - Sous-section « Derniers paiements » : 20 derniers (3.3) — date, type, montant, `StatusBadge` (« Validé », « À valider », « Annulé »). « Voir plus ». Clic → modale « Détail du paiement ».
   - Sous-section « Mes cotisations {année} » (4.4.7) : sa ligne de la grille de chaque type auquel il est rattaché, sous forme de mini-grille 4 × 3 (mois abrégés, cellules colorées selon design-system 2.6, montant). Sélecteur d'année « ‹ {année} › ». Clic sur un mois → modale « Détail du mois ».
3. **Assistance sociale** (4.5.3) — demandes du joueur (5 dernières, 3.3) : événement, date, montant, statut. Bouton « Voir plus » en pied de liste (charge les 5 suivantes ; masqué s'il n'y en a pas d'autres). Action de carte : « Demander une assistance ». Clic → modale de détail (état, motif de refus éventuel).
4. **Informations personnelles** — âge (calculé), date de naissance, poids, taille, téléphone, email (identifiant). Chaque valeur absente affiche « Non renseigné ». Mention : « Ces informations ne sont jamais publiques. » (4.2).
5. **Statistiques de la saison** (4.2) — six indicateurs en toutes lettres, sans troncature : « Matchs », « Buts », « Passes décisives », « Cartons », « Taux de présence », « Note moyenne ». Grille 2 × 3 sur mobile. Lien « Voir ma fiche détaillée » (modale fiche 4.2). Sous-section « Carrière » : clubs successifs sur Vesta (logo, nom, période).
6. **Santé** (4.12) — `StatusBadge` d'aptitude (« Apte » / « Apte avec restriction » / « Inapte »), date de retour prévue si inapte. Action de carte : « Ma fiche de santé » (modale ; le joueur voit son diagnostic, 2.4 P).
   - Sous-section **« Consentement médical »** (2.4, 4.12, 10.2 n° 15) — visible **uniquement par le joueur lui-même** sur son propre profil ; jamais affichée dans la fiche d'un joueur ouverte par un tiers (Président, Coach, Médecin compris). Une ligne d'état :
     - accordé : `StatusBadge` vert « Accordé » + « Le Président peut consulter votre dossier médical complet depuis le {date}. » ;
     - non accordé : `StatusBadge` gris « Non accordé » + « Le Président voit seulement votre aptitude et votre date de retour prévue. »
     - Lien-bouton secondaire « Gérer » → modale « Consentement médical » (§4.5). Une seule action principale reste celle de la carte (« Ma fiche de santé »).
7. **Mercato** (4.14) — contrôle segmenté « Fermé aux offres » / « Sur le marché » à effet immédiat (toast « Vous êtes maintenant sur le marché. » / « Vous êtes fermé aux offres. »). Lien « Voir mes offres » (page Mercato) avec compteur des offres en attente.
8. **Préférences** — interrupteur « Recevoir aussi mes notifications par email » (4.17), effet immédiat, toast « Préférence enregistrée. » Le thème se règle dans le menu utilisateur de la barre latérale.

Footer.

## 4. Modales

### 4.1 « Modifier mon profil » (4.1) — taille `md`, 3 onglets, un « Enregistrer » par onglet

**Onglet « Informations »**

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Prénom | TextField | Oui | « Ce champ est obligatoire. » |
| Nom | TextField | Oui | « Ce champ est obligatoire. » |
| Téléphone (WhatsApp) | TextField `tel` | Non | Format international accepté ; « Numéro de téléphone invalide. » |
| Date de naissance | DateField | Non | Passée ; « La date ne peut pas être dans le futur. » |
| Poids (kg) | NumberField | Non | 30 à 200 ; « Saisissez un poids entre 30 et 200 kg. » |
| Taille (cm) | NumberField | Non | 120 à 230 ; « Saisissez une taille entre 120 et 230 cm. » |
| Poste, numéro | Lecture seule | — | Aide : « Modifiables par le Coach uniquement. » (2.4) |

Succès : « Profil mis à jour. »

**Onglet « Photo »** : photo actuelle 96 px ; boutons « Choisir une photo » et, sur mobile, « Prendre une photo » ; recadrage carré ; compression dans le navigateur avant envoi (6.7). Action secondaire « Retirer la photo » (ConfirmDialog « Retirer votre photo ? Vos initiales seront affichées à la place. »). Pied : « Annuler » / « Enregistrer la photo ». Erreurs : formats et poids standard. Succès : « Photo mise à jour. »

**Onglet « Identifiant et mot de passe »** (7.1)

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Email (identifiant de connexion) | TextField `email` | Oui | Unique sur la plateforme ; « Cette adresse email est déjà utilisée. » |
| Nouveau mot de passe | TextField `password` + bouton « Afficher » | Non (si seul l'email change) | 8 caractères min., différent de l'email |
| Confirmez le mot de passe | TextField `password` | Si nouveau mot de passe | « Les deux mots de passe ne correspondent pas. » |
| Mot de passe actuel | TextField `password` | Oui | « Mot de passe actuel incorrect. » |

Succès : « Identifiants mis à jour. »

### 4.2 « J'ai payé » (4.6) — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Type de cotisation | Select (types actifs du joueur) | Oui | Défaut : sa mensuelle |
| Montant | MoneyField (devise du club) | Oui | « Saisissez un montant supérieur à 0. » |
| Référence de transaction | TextField | Oui | « Indiquez la référence reçue lors du paiement. » |
| Capture du paiement | FileField | Non | Formats standard |

Aide en haut : « Déclarez ici un paiement fait par le lien du club. Le trésorier le vérifiera avant de l'ajouter à votre solde. » Pied : « Annuler » / « Envoyer la déclaration ». Succès : « Déclaration envoyée. Le trésorier la validera. » La ligne apparaît dans « Derniers paiements » avec le badge « À valider ».

### 4.3 « Demander une assistance » (4.5.3) — taille `md`

| Champ | Composant | Obligatoire | Règle / erreur |
| --- | --- | --- | --- |
| Événement | SegmentedControl : Naissance / Mariage / Décès | Oui | — |
| Date de l'événement | DateField | Oui | « La date ne peut pas être dans le futur. » |
| Description | TextArea | Oui | « Ce champ est obligatoire. » |
| Pièce justificative | FileField | Oui | Formats standard |

**Bloc d'éligibilité** (calculé par l'API dès que l'événement et la date sont remplis, avant l'envoi) :
- Éligible : encadré vert « Vous êtes éligible. Montant prévu : {montant}. Délai de traitement : {délai}. »
- Non éligible : bandeau d'avertissement orange « Vous n'étiez pas en ordre à cette date. Régularisez {montant} pour devenir éligible. Vous pouvez tout de même envoyer votre demande : le Président ou le Vice-président décidera au cas par cas. » + bouton secondaire « Contribuer ». Le montant à régulariser vient de l'API (solde calculé), jamais d'un calcul de l'interface.

Pied : « Annuler » / « Envoyer la demande », **toujours actif**, que le joueur soit éligible ou non (décision Q14 de `docs/lot0/analyse.md`). Succès (éligible) : « Demande envoyée. Le Président et le Vice-président ont été prévenus. » Succès (non éligible) : « Demande envoyée. Le Président et le Vice-président ont été prévenus que vous n'étiez pas en ordre à la date de l'événement ; ils décideront au cas par cas. »

### 4.4 Modales de consultation

- **« Détail du paiement »** : date, type, montant, mode, référence, statut, répartition par mois (tableau mois / montant), n° de reçu. Pied : « Fermer » / « Télécharger le reçu » (PDF servi par vue authentifiée). Si « À valider » : « En attente de validation par le trésorier. »
- **« Détail du mois »** : type, mois, montant dû, montant affecté, état, paiements ayant alimenté le mois.
- **« Ma fiche de santé »** (4.12) : groupe sanguin, allergies, antécédents, traitements, contact d'urgence, déclaration du joueur, aptitude, blessures et suivi. Action principale : « Mettre à jour ma déclaration » (modale niveau 2 : TextArea « Déclaration sur mon état de santé », Checkbox de consentement si absent). Les champs remplis par le Médecin sont en lecture seule.
- **« Ma carte de joueur »** : carte style FC (4.2) ; lien « Voir la fiche détaillée ».

### 4.5 « Consentement médical » (2.4, 4.12, 10.2 n° 15) — taille `sm`

Ouverte depuis le lien « Gérer » de la sous-section « Consentement médical » de la carte Santé. Accessible **au seul joueur concerné** (l'API refuse toute lecture ou écriture de ce consentement par un autre utilisateur).

Titre : « Autoriser le Président à consulter mon dossier médical complet ».

Corps, dans l'ordre :
1. **État actuel** (ligne mise en avant) :
   - accordé : `StatusBadge` vert « Accordé » + « Autorisation accordée depuis le {date}. »
   - non accordé : `StatusBadge` gris « Non accordé » + « Autorisation non accordée. »
2. **Explication** : « Par défaut, le Président voit seulement votre aptitude (apte, apte avec restriction, inapte) et votre date de retour prévue, comme le Coach. Si vous l'autorisez, il pourra aussi consulter votre diagnostic, vos blessures et leur suivi. Le Coach, lui, ne voit jamais votre diagnostic. »
3. **Texte d'aide** (encadré neutre, icône information) : « Cette autorisation est donnée à la fonction de Président, pas à la personne. Si le club change de Président, votre autorisation ne le suit pas automatiquement ; vous devrez l'accorder à nouveau au nouveau titulaire si vous le souhaitez. »
4. **Mention de traçabilité** : « Votre autorisation, sa révocation et chaque consultation de votre dossier par le Président sont enregistrées dans le journal du club. Le contenu médical n'y est jamais copié. »

Pied (toujours visible) :
- non accordé : « Annuler » / « Autoriser » (action principale). Succès : toast « Autorisation accordée au Président. » ; la modale se ferme, la carte Santé affiche « Accordé ».
- accordé : « Fermer » / « Révoquer » (bouton de type danger). Clic → ConfirmDialog « Révoquer l'autorisation ? » — texte « La révocation prend effet immédiatement : le Président ne pourra plus consulter votre dossier médical complet. » — boutons « Annuler » / « Révoquer ». Succès : toast « Autorisation révoquée. » ; la carte Santé affiche « Non accordé ».

Pas de confirmation à l'octroi ; confirmation uniquement pour la révocation. Bouton en état `loading` pendant l'envoi. Erreur : message réseau standard, l'état affiché reste l'état serveur précédent (aucune mise à jour optimiste). Un club a toujours un et un seul Président (CDC 2.3) : l'autorisation vise toujours le titulaire en fonction au moment où elle est donnée.

### 4.6 Actions du menu « … »

- **Télécharger mes données** (7.5) : bouton en état `loading` puis téléchargement du fichier. Erreur : message réseau standard.
- **Déconnecter tous mes appareils** (7.1) : ConfirmDialog « Déconnecter tous vos appareils ? Vous devrez vous reconnecter partout, y compris ici. » — « Déconnecter ».
- **Demander la suppression de mon compte** (7.5) : ConfirmDialog « Demander la suppression de votre compte ? Vos écritures financières seront conservées de façon anonyme, comme la loi l'exige. » — TextArea « Motif (facultatif) » — « Envoyer la demande ». Succès : « Demande envoyée. »

## 5. États

| Zone | Chargement | Vide | Erreur |
| --- | --- | --- | --- |
| Identité | Squelette avatar + 3 lignes | — | Erreur de page (tout le profil en dépend) + « Réessayer » |
| Prochaines échéances | 3 lignes squelettes | « Aucune échéance à venir. » | Modèle standard |
| Derniers paiements | 5 lignes squelettes | « Aucun paiement enregistré pour l'instant. » | Modèle standard |
| Mes cotisations | Squelette de grille | « Vous n'êtes rattaché à aucun type de cotisation. » | Modèle standard |
| Assistance sociale | 2 lignes | « Aucune demande d'assistance. » + « Demander une assistance » | Modèle standard |
| Statistiques | Squelette KPI 2 × 3 | Indicateurs à 0, pas de message | Modèle standard |
| Carrière | 1 ligne | « Aucun autre club sur Vesta. » | Modèle standard |
| Santé | 1 ligne | « Fiche de santé non encore complétée par le Médecin. » | Modèle standard |
| Consentement médical | 1 ligne squelette | — (toujours un état : « Accordé » ou « Non accordé ») | Modèle standard ; bouton « Gérer » masqué tant que l'état n'est pas connu |

## 6. Mobile (360 px) et ordinateur

- **360 px** : une colonne dans l'ordre du §3. En-tête d'identité : avatar à gauche, nom et badges à droite. « Contribuer » et « J'ai payé » côte à côte sous le solde. Mini-grille 4 colonnes × 3 lignes (cellules de 76 px).
- **≥ 1024 px** : deux colonnes 8/4. Principale : Situation financière, Statistiques, Assistance sociale. Latérale : Identité, Santé, Informations personnelles, Mercato, Préférences. Mini-grille sur une ligne de 12 mois.

## 7. Décisions par défaut et points ouverts

- **Décidé, cahier des charges 10.2 n° 15 (Q1)** : consentement médical au Président, donné depuis le profil (carte Santé + modale §4.5), révocable avec effet immédiat, journalisé, attaché à la fonction de Président et non transmis à un successeur.
- **Décidé, cahier des charges 10.2 n° 33 (Q14)** : un joueur non éligible (en dette à la date de l'événement) peut tout de même envoyer sa demande d'assistance. Le bouton « Envoyer la demande » reste toujours actif ; un bandeau d'avertissement affiche le montant à régulariser pour devenir éligible ; le Président ou le Vice-président tranche au cas par cas à réception (sans pouvoir la valider tant que le joueur n'est pas éligible, 10.2 n° 37).
- **Point ouvert** : caractère obligatoire des champs « Référence » et « Capture » de « J'ai payé » (le 4.6 les liste sans le préciser). Proposition : référence obligatoire, capture facultative.
- **Point ouvert** : qui traite une demande de suppression de compte (7.5) — Superuser proposé.
- Limites de poids et de taille : propositions de contrôle de saisie, à valider.
