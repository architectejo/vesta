# Backlog post-MVP — éléments de confort reportés après le Lot 5

Décision du client (25/09/2026, voir `docs/lot0/analyse.md` §4) : ces éléments, relevés par `cdc-reviewer` ou proposés par `ui-designer` pendant le Lot 0, n'ont aucune base explicite dans `docs/cahier-des-charges.md`. Ils sont **reportés après le Lot 5** (mise en production du MVP pour Discovery) et ne doivent pas être développés avant, sauf nouvelle demande explicite du client suivant le circuit 9.4. Chaque entrée indique l'écran concerné et la spec où elle est aujourd'hui décrite (à titre de mémoire, pas comme une autorisation de développement).

| # | Élément | Écran | Description |
| --- | --- | --- | --- |
| 1 | Carte « À faire » | `docs/ecrans/club-accueil.md` | Liste des actions en attente pour le Président (parrainage refusé, signature en attente, dépenses à valider…), en plus des notifications |
| 2 | Raccourcis d'accueil | `docs/ecrans/club-accueil.md` | Accès rapides depuis la page d'accueil vers les actions fréquentes |
| 3 | « Retirer un pointage » | `docs/ecrans/sport-seance.md` | Annuler un pointage de présence saisi par erreur, en dehors du circuit standard de modification du jour même |
| 4 | Réapplication automatique de la répartition A/B | `docs/ecrans/sport-seance.md` | Recalcul en un clic de la répartition initiale après des ajustements manuels |
| 5 | Notification « Composition modifiée » | `docs/ecrans/sport-espace-coach.md` | Alerte aux joueurs convoqués si la composition change après publication |
| 6 | Ligne « Total du mois » | `docs/ecrans/tresorerie-grille-cotisations.md` | Total agrégé par mois dans la grille des cotisations |
| 7 | Raccourcis de montant en Caisse Terrain Express | `docs/ecrans/tresorerie-tableau-de-bord.md` | Boutons de saisie rapide (1, 2, 3 mois) pour le montant encaissé |
| 8 | Retrait d'une offre de mercato | `docs/ecrans/mercato-marche.md` | Permettre au club émetteur d'annuler une offre de transfert avant réponse du joueur |
| 9 | Indicateur « Anomalies » présenté comme une liste à traiter | `docs/ecrans/superuser-espace.md` | Le CDC et le schéma ne prévoient qu'un indicateur calculé en direct (voir `schema-donnees.md` §12.3) ; une file « à traiter » avec état stocké par anomalie est hors MVP |
| 10 | Indicateur « Demandes de réinitialisation » | `docs/ecrans/superuser-espace.md` | Vue dédiée aux demandes de mot de passe oublié en attente, au-delà du traitement au fil de l'eau déjà prévu |

**Accepté et intégré au cahier des charges** (pour mémoire — ne pas confondre avec les entrées ci-dessus, qui restent reportées) : `late_arrival_counts_absent` et `board_seats_per_role` configurables par club, versionnement des CGU, confirmation de résiliation par saisie du nom du club — voir `docs/cahier-des-charges.md` 10.2 n° 24 à 27.
