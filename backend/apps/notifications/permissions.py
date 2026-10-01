"""Classes de permission DRF de l'app notifications (CDC 4.17 ; tache 1.7).

La matrice 2.4 ne reserve aucun endpoint de ce module a un role de club
particulier : chaque utilisateur authentifie (joueur ou Superuser) ne
voit jamais que SES PROPRES notifications et SA PROPRE preference email,
quels que soient ses roles. Le controle qui compte n'est donc jamais un
role de club (pas de classe de permission dediee ici), mais le filtrage
systematique par destinataire (``recipient=request.user``) applique par
``apps.notifications.views`` -- jamais par club, jamais par un autre
mecanisme (voir consigne explicite de la tache 1.7).

Les gardes-fous communs (``IsAuthenticated``, ``HasCompletedPasswordSetup``,
``HasAcceptedLatestTerms``, ``apps.core.permissions``) suffisent donc et
sont declares directement dans ``apps.notifications.views``, meme
principe que ``apps.clubs.views``.
"""
