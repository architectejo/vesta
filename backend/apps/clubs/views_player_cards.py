"""Vues des cartes de joueurs et de leurs statistiques (CDC 4.2 ; docs/ecrans/
club-cartes-joueurs.md §7). Lecture seule, ouverte à tout membre actif du
club : permission -> service (``apps.sport.player_stats``) -> réponse. Le
filtrage par rôle (suspension, aptitude, disponibilité) est fait dans le
service, jamais ici.

Étanchéité : le joueur demandé est lu par le manager tenant-aware
(``Membership.objects``) ; un joueur d'un autre club répond 404. La seule voie
vers un joueur d'un autre club est la comparaison, qui ne sert que ses données
publiques (CDC 6.3).
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clubs.models import Membership
from apps.clubs.permissions import IsActiveClubMember
from apps.core.permissions import HasAcceptedLatestTerms, HasCompletedPasswordSetup, HasUsableLicence
from apps.core.tenant import get_active_club
from apps.sport import player_stats
from apps.sport.services import SportValidationError

_CLUB_MEMBER_GATE = [IsAuthenticated, HasCompletedPasswordSetup, HasAcceptedLatestTerms, HasUsableLicence]


def _bad_request(exc: Exception) -> Response:
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class PlayerCardListView(APIView):
    """``GET /clubs/players/cards/`` : cartes paginées (``limit``/``offset``,
    « Voir plus »), recherche, poste, statut, disponibilité (staff), saison,
    tri."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def get(self, request):
        club = get_active_club()
        try:
            params = player_stats.parse_cards_params(request.query_params)
            payload = player_stats.list_player_cards(club=club, viewer=request.user, params=params, request=request)
        except SportValidationError as exc:
            return _bad_request(exc)
        return Response(payload)


class PlayerStatsView(APIView):
    """``GET /clubs/players/{id}/stats/`` : statistiques détaillées."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def get(self, request, membership_id: int):
        try:
            membership = Membership.objects.select_related("user", "club").get(pk=membership_id)
        except Membership.DoesNotExist:
            return Response({"detail": "Ce joueur n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        season_raw = request.query_params.get("season")
        try:
            season_id = int(season_raw) if season_raw not in (None, "") else None
        except ValueError:
            return _bad_request(player_stats.PlayerStatsError("Saison : saisissez un nombre entier."))
        try:
            payload = player_stats.get_player_stats(
                membership=membership, viewer=request.user, season_id=season_id, request=request
            )
        except SportValidationError as exc:
            return _bad_request(exc)
        return Response(payload)


class PlayerComparisonView(APIView):
    """``GET /clubs/players/compare/?ids=1,2,3`` : 2 à 4 joueurs. Joueurs du
    club : statistiques et radar ; joueurs d'un autre club : données
    publiques seulement (consentement, non mineur)."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def get(self, request):
        club = get_active_club()
        try:
            ids = player_stats.parse_compare_ids(request.query_params.get("ids"))
            payload = player_stats.compare_players(club=club, ids=ids, request=request)
        except SportValidationError as exc:
            return _bad_request(exc)
        return Response(payload)
