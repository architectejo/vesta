# Guide utilisateur — Coach

> Ce guide décrit les écrans réels de Vesta tels qu'implémentés à ce jour (vérifié dans le code et la spec `docs/ecrans/sport-espace-coach.md`). Aucune capture d'écran : les étapes sont décrites en clair.

Quand vous êtes connecté avec le rôle Coach, votre écran d'accueil devient votre tableau de bord sportif :

- **Disponibilité de l'effectif** : compteurs cliquables (disponibles, en dette, suspendus, inaptes, en attente d'adhésion) — cliquer ouvre la liste correspondante. Un joueur en dette, suspendu, inapte ou en attente ne peut pas être composé ni placé dans un plan.
- **Évaluations à faire** : une ligne par séance/match des dernières 48 h avec des joueurs non encore évalués.
- **Discipline** : suspensions en cours et derniers incidents (cartons).
- **Capitaine actuel**, avec un bouton pour en choisir un autre parmi les joueurs.
- **Plans tactiques** : les 5 derniers, avec un bouton « Nouveau plan ».
- Boutons principaux : « Créer une séance » et « Créer un match ».

## Séances (menu « … » → ou depuis « Vestiaire du jour »)

- Créez une séance (date, heure, lieu).
- Pointez les présences le jour même : Présent / En retard / Absent / Absent excusé. Un retard compte comme absent pour la répartition.
- Répartissez les joueurs présents en deux équipes (A/B) pour l'entraînement.
- Onglet « Évaluations » : notez les joueurs (verrouillé 48 h après le début réel de la séance).

## Matchs (depuis « Vestiaire du jour », ou via un défi accepté)

- Créez un match (adversaire, date, domicile/extérieur) ou acceptez un défi reçu d'un autre club.
- Composez l'équipe (titulaires/remplacants), publiez la composition.
- Saisissez le score et les buteurs.
- Signalez un incident (carton) : la 5e carte jaune de la saison ou un carton rouge direct déclenche automatiquement une suspension.

## Plan tactique et tableau noir

- « Plan tactique » (menu Sport) liste vos plans ; ouvrir un plan affiche le terrain et les consignes en lecture seule.
- Depuis un plan, « Modifier sur le tableau noir » ouvre l'éditeur plein écran : glissez-déposez les joueurs sur le terrain, ajoutez des flèches/zones, publiez le plan.
- Un joueur en dette, suspendu ou inapte ne peut pas être placé sur le terrain.

## Fiches de santé

Vous voyez uniquement l'aptitude du joueur (apte / apte avec restriction / inapte) et sa date de retour prévue — jamais le diagnostic, sans aucune exception.

## Parcours type pour la présentation

1. Depuis l'accueil, montrez les compteurs de disponibilité et cliquez sur « suspendus » ou « en dette » pour illustrer le blocage automatique.
2. Ouvrez un plan tactique déjà composé, puis « Modifier sur le tableau noir » : ajoutez ou déplacez un joueur à la souris — c'est aussi une démonstration du glisser-déposer.
3. Ouvrez une séance et montrez le pointage des présences.
4. Signalez un incident pour montrer la suspension automatique.
