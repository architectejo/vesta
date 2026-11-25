"""Emission d'une session de recette (Playwright) sans mot de passe.

Tache 5.2 du plan des lots (`docs/lot0/plan-lots.md`) : le parcours de
recette bout en bout (CDC 9.3) doit piloter un VRAI navigateur, avec des
comptes REELS du jeu de simulation (`seed_simulation`, tache 5.1) dont le
mot de passe n'est pas connu du test (les comptes reels du club pilote
ont pu changer leur mot de passe initial -- CLAUDE.md regle n1, CDC 4.1).

Cette commande reproduit EXACTEMENT la forme de reponse de
`apps.accounts.views.LoginView` (memes cles : `access`, `refresh`,
`user`, `club`) pour un utilisateur donne par email, sans verifier de
mot de passe -- c'est une porte de test, jamais un point d'acces reseau :
elle n'existe qu'en ligne de commande, cote serveur, et refuse de
s'executer si `settings.DEBUG` est faux (meme garde-fou que
`seed_simulation`, CLAUDE.md : jamais de contournement d'authentification
en production).

Le jeton d'acces est un vrai jeton SimpleJWT (`RefreshToken.for_user`,
CLAUDE.md regle n9 : le club actif n'est JAMAIS encode dans le jeton,
seulement deduit de l'adhesion en cours par
`apps.core.services.resolve_active_membership`, exactement comme une
vraie connexion) : le test ne fait donc que sauter la case "saisir le
mot de passe", tout le reste du comportement serveur (isolation
multi-tenant, permissions par role) reste reel.

Usage :
    python manage.py issue_e2e_session --email president@example.com
    python manage.py issue_e2e_session --email joueur@example.com --api-base-url http://127.0.0.1:8000

Sortie : une seule ligne JSON sur stdout (le reste des messages va sur
stderr), pour etre consommee telle quelle par le script Node du parcours
Playwright.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from ._guards import refuse_outside_development
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.accounts.serializers import UserSummarySerializer
from apps.core.services import NoActiveClubError, resolve_active_membership


class Command(BaseCommand):
    help = (
        "Emet un acces/refresh JWT + identite (memes cles que LoginView) pour un "
        "utilisateur existant, SANS mot de passe -- reserve au parcours de recette "
        "Playwright (CDC 9.3, tache 5.2). Refuse si settings.DEBUG=False."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Email du compte (President, Coach, joueur...).")
        parser.add_argument(
            "--api-base-url",
            default="http://127.0.0.1:8000",
            help="Origine de l'API, pour construire l'URL absolue du logo du club (defaut : http://127.0.0.1:8000).",
        )

    def handle(self, *args, **options):
        refuse_outside_development("issue_e2e_session")

        email = options["email"]
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise CommandError(f"Aucun utilisateur avec l'email « {email} ».") from None

        club = None
        if not user.is_superuser:
            try:
                membership = resolve_active_membership(user)
            except NoActiveClubError:
                membership = None
            else:
                club = membership.club

        refresh = RefreshToken.for_user(user)

        club_payload = None
        if club is not None:
            api_base_url = options["api_base_url"].rstrip("/")
            club_payload = {
                "id": club.id,
                "slug": club.slug,
                "name": club.name,
                "logo": f"{api_base_url}{club.logo.url}" if club.logo else None,
                "primary_color": club.primary_color,
                "secondary_color": club.secondary_color,
            }

        payload = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSummarySerializer(user).data,
            "club": club_payload,
        }

        # Une seule ligne, sur stdout exclusivement (les `self.stdout.write`
        # habituels de Django ajoutent un saut de ligne final : sans
        # consequence, le script Node ne lit que la premiere ligne JSON).
        self.stdout.write(json.dumps(payload))
