"""Tests HTTP de la liste/recherche des membres du club actif
(``PlayerListView``, route ``clubs:players-list``).

Comble le trou releve pendant l'implementation frontend de la tache 1.9
(club-comite-bureau.md §3.6 « Effectif » ; PlayerSearch pour le champ
Parrain §4.5 et le choix de titulaire de role/Capitaine/successeur a la
presidence ; CDC 2.4, 4.2 ; CLAUDE.md regle n15). Point le plus critique :
etancheite multi-tenant (CLAUDE.md regle n8) -- un membre du club A ne
doit jamais voir apparaitre un membre du club B dans cette liste, meme
avec une recherche texte qui correspondrait a son nom.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import ClubFactory, MembershipFactory, MembershipRoleFactory
from apps.licences.models import Licence
from apps.licences.tests.factories import LicenceFactory

pytestmark = pytest.mark.django_db


def _authenticated_client(user) -> APIClient:
    """Jeton d'acces reel (pas ``force_authenticate``) : passe par
    ``TenantJWTAuthentication`` comme en production, club actif resolu
    depuis l'adhesion reelle (CLAUDE.md regle n9)."""

    client = APIClient()
    access_token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return client


def _list(client: APIClient, **params):
    return client.get(reverse("clubs:players-list"), params)


class TestPlayerListView:
    def test_member_sees_all_teammates(self):
        club = ClubFactory()
        viewer = MembershipFactory(club=club)
        teammate_1 = MembershipFactory(club=club)
        teammate_2 = MembershipFactory(club=club)

        response = _list(_authenticated_client(viewer.user))

        assert response.status_code == status.HTTP_200_OK
        returned_ids = {row["membership_id"] for row in response.data}
        assert returned_ids == {viewer.id, teammate_1.id, teammate_2.id}

    def test_cross_club_isolation_never_leaks_another_clubs_member(self):
        """CLAUDE.md regle n8 : un membre du club A ne voit jamais un
        membre du club B, meme lorsque la recherche texte correspond au
        nom de ce dernier."""

        club_a = ClubFactory()
        club_b = ClubFactory(name="Club B Effectif", slug="club-b-effectif")
        member_a = MembershipFactory(club=club_a)
        member_b = MembershipFactory(
            club=club_b,
            user=UserFactory(first_name="Unique", last_name="Nomclubb"),
        )

        response = _list(_authenticated_client(member_a.user))
        response_search = _list(_authenticated_client(member_a.user), search="Unique")

        returned_ids = {row["membership_id"] for row in response.data}
        assert member_b.id not in returned_ids
        assert response_search.data == []
        body_text = str(response.data) + str(response_search.data)
        assert member_b.user.first_name not in body_text
        assert member_b.user.last_name not in body_text

    def test_search_matches_first_or_last_name_case_insensitively(self):
        club = ClubFactory()
        viewer = MembershipFactory(club=club)
        target = MembershipFactory(
            club=club, user=UserFactory(first_name="Jonathan", last_name="Mbala")
        )
        MembershipFactory(club=club, user=UserFactory(first_name="Autre", last_name="Joueur"))

        response = _list(_authenticated_client(viewer.user), search="mbala")

        returned_ids = {row["membership_id"] for row in response.data}
        assert returned_ids == {target.id}

    def test_search_result_limit_is_50(self):
        """Choix technique de securite/performance (pas une regle CDC),
        documente au compte rendu de la tache : 50 resultats max sur une
        recherche texte."""

        club = ClubFactory()
        viewer = MembershipFactory(
            club=club, user=UserFactory(first_name="Recherche", last_name="Zero")
        )
        for index in range(60):
            MembershipFactory(
                club=club, user=UserFactory(first_name="Recherche", last_name=f"Joueur{index}")
            )

        response = _list(_authenticated_client(viewer.user), search="Recherche")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 50

    def test_search_result_limit_keeps_the_alphabetically_first_50(self):
        """Revue independante (CLAUDE.md regle n8, point de vigilance signale
        au compte rendu) : la limite de 50 doit s'appliquer APRES le tri
        (`order_by("user__last_name", ...)`), pas sur un sous-ensemble
        arbitraire de la base -- les 50 lignes renvoyees doivent etre les 50
        premieres alphabetiquement (noms de famille `A00` a `A49`), jamais
        un echantillon qui saute `A50`..`A59` au profit d'un nom anterieur
        dans la base mais posterieur alphabetiquement."""

        club = ClubFactory()
        viewer = MembershipFactory(
            club=club, user=UserFactory(first_name="Recherche", last_name="Zero")
        )
        # Insere delibimplerement dans le desordre (le tri ne doit rien devoir
        # a l'ordre d'insertion/PK, CLAUDE.md regle « pas de test dependant
        # de l'ordre d'execution »).
        for index in reversed(range(60)):
            MembershipFactory(
                club=club, user=UserFactory(first_name="Recherche", last_name=f"A{index:02d}")
            )

        response = _list(_authenticated_client(viewer.user), search="Recherche")

        assert response.status_code == status.HTTP_200_OK
        returned_last_names = [row["last_name"] for row in response.data]
        expected_last_names = [f"A{index:02d}" for index in range(50)]
        assert returned_last_names == expected_last_names


class TestPlayerListViewLicenceGate:
    """Non-regression HTTP (audit securite tache 1.13, ecart bloquant B1) :
    ``HasUsableLicence`` doit figurer dans ``_CLUB_MEMBER_GATE``
    (apps/clubs/views.py), sinon un membre d'un club dont la licence est
    suspendue continuerait a acceder aux vues protegees par ce garde
    (CDC 1.4 ; 10.2 n19). Ce test verifie le CABLAGE HTTP reel de cette
    vue precise, pas ``HasUsableLicence`` elle-meme (deja testee en
    isolation dans apps/core/tests/test_permissions.py)."""

    def test_licence_suspendue_refuse_meme_la_lecture_de_la_liste_des_joueurs(self):
        club = ClubFactory()
        viewer = MembershipFactory(club=club, status=Membership.Status.ACTIVE)
        LicenceFactory(club=club, status=Licence.Status.SUSPENDED)

        response = _list(_authenticated_client(viewer.user))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_no_limit_applied_without_text_search(self):
        club = ClubFactory()
        viewer = MembershipFactory(club=club)
        for _ in range(55):
            MembershipFactory(club=club)

        response = _list(_authenticated_client(viewer.user))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 56

    def test_filter_by_position(self):
        club = ClubFactory()
        viewer = MembershipFactory(club=club, position=Membership.Position.GOALKEEPER)
        forward = MembershipFactory(club=club, position=Membership.Position.FORWARD)

        response = _list(_authenticated_client(viewer.user), position=Membership.Position.FORWARD)

        returned_ids = {row["membership_id"] for row in response.data}
        assert returned_ids == {forward.id}

    def test_filter_by_status(self):
        """CDC 10.2 n16 : le filtre "En attente" reste disponible pour un
        role autorise a voir ce motif (ici le President)."""

        club = ClubFactory()
        president = MembershipFactory(club=club, status=Membership.Status.ACTIVE)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        pending = MembershipFactory(club=club, status=Membership.Status.PENDING)

        response = _list(_authenticated_client(president.user), status=Membership.Status.PENDING)

        returned_ids = {row["membership_id"] for row in response.data}
        assert returned_ids == {pending.id}

    def test_filter_by_pending_status_returns_nothing_to_an_unauthorised_teammate(self):
        """CDC 10.2 n16 (precise en 4.12) : un coequipier sans role
        autorise ne doit ni voir le motif "En attente" ni pouvoir le
        retrouver via le filtre -- resultat vide, jamais une fuite."""

        club = ClubFactory()
        viewer = MembershipFactory(club=club, status=Membership.Status.ACTIVE)
        MembershipFactory(club=club, status=Membership.Status.PENDING)

        response = _list(_authenticated_client(viewer.user), status=Membership.Status.PENDING)

        assert response.data == []

    def test_general_listing_masks_pending_status_for_an_unauthorised_teammate(self):
        """CDC 4.12 : "un joueur [...] en attente d'adhesion [leur]
        apparait simplement « Indisponible », sans distinction"."""

        club = ClubFactory()
        viewer = MembershipFactory(club=club, status=Membership.Status.ACTIVE)
        pending = MembershipFactory(club=club, status=Membership.Status.PENDING)

        response = _list(_authenticated_client(viewer.user))

        row = next(row for row in response.data if row["membership_id"] == pending.id)
        assert row["membership_status"] != Membership.Status.PENDING
        assert row["membership_status_label"] == "Indisponible"

    # Note : le joueur PENDING lui-meme ne peut pas atteindre cet endpoint
    # (``IsActiveClubMember``/``resolve_active_membership`` n'accepte
    # qu'une adhesion ``ACTIVE`` -- CDC 2.4) : la visibilite "self" de
    # ``can_view_pending_membership_status`` est donc verifiee au niveau
    # du service (voir ``apps.clubs.tests.test_services_roles``), pas ici.

    def test_filter_by_role(self):
        club = ClubFactory()
        viewer = MembershipFactory(club=club)
        coach = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach, role=MembershipRole.Role.COACH)

        response = _list(_authenticated_client(viewer.user), role=MembershipRole.Role.COACH)

        returned_ids = {row["membership_id"] for row in response.data}
        assert returned_ids == {coach.id}

    def test_filter_by_role_excludes_revoked_role_holders(self):
        club = ClubFactory()
        viewer = MembershipFactory(club=club)
        former_coach = MembershipFactory(club=club)
        MembershipRoleFactory(
            membership=former_coach,
            role=MembershipRole.Role.COACH,
            revoked_at=timezone.now(),
        )

        response = _list(_authenticated_client(viewer.user), role=MembershipRole.Role.COACH)

        returned_ids = {row["membership_id"] for row in response.data}
        assert former_coach.id not in returned_ids

    def test_role_filter_does_not_duplicate_rows(self):
        """Un joueur avec plusieurs roles actifs ne doit apparaitre
        qu'une seule fois (jointure sur `roles`, `.distinct()` requis)."""

        club = ClubFactory()
        viewer = MembershipFactory(club=club)
        multi_role = MembershipFactory(club=club)
        MembershipRoleFactory(membership=multi_role, role=MembershipRole.Role.VICE_PRESIDENT)
        MembershipRoleFactory(membership=multi_role, role=MembershipRole.Role.PLAYER_RECRUITER)

        response = _list(_authenticated_client(viewer.user))

        ids = [row["membership_id"] for row in response.data]
        assert ids.count(multi_role.id) == 1

    def test_multi_role_holder_keeps_both_roles_in_payload_without_a_role_filter(self):
        """Revue independante du `.distinct()` (CLAUDE.md regle n8, point de
        vigilance signale au compte rendu) : un joueur qui cumule DEUX roles
        actifs (ex. Capitaine + Tresorier) ne doit apparaitre qu'une seule
        fois -- meme SANS filtre `role` -- et son champ `roles` doit lister
        les DEUX roles, pas un seul rogne par un `.distinct()` mal place.
        Le `.distinct()` de la vue porte sur le queryset des `Membership`
        (une jointure `roles__role` qui n'existe que si le parametre `role`
        est fourni) : la liste `roles` de chaque ligne vient d'une requete
        separee (`PlayerPublicCardSerializer.to_representation`), jamais
        impactee par ce `.distinct()`."""

        club = ClubFactory()
        viewer = MembershipFactory(club=club)
        multi_role = MembershipFactory(club=club)
        MembershipRoleFactory(membership=multi_role, role=MembershipRole.Role.CAPTAIN)
        MembershipRoleFactory(membership=multi_role, role=MembershipRole.Role.TREASURER)

        response = _list(_authenticated_client(viewer.user))

        matching_rows = [row for row in response.data if row["membership_id"] == multi_role.id]
        assert len(matching_rows) == 1
        returned_roles = {entry["role"] for entry in matching_rows[0]["roles"]}
        assert returned_roles == {MembershipRole.Role.CAPTAIN, MembershipRole.Role.TREASURER}

    def test_general_listing_never_leaks_a_revoked_role_alongside_an_active_one(self):
        """Un joueur ayant eu un role revoque, puis un autre role toujours
        actif, ne doit jamais voir le role revoque reapparaitre dans
        `roles` (CDC -- confidentialite du parcours de role, coherence avec
        `test_filter_by_role_excludes_revoked_role_holders` qui ne couvre
        que le filtre `role`, pas la fiche generale)."""

        club = ClubFactory()
        viewer = MembershipFactory(club=club)
        member = MembershipFactory(club=club)
        MembershipRoleFactory(
            membership=member,
            role=MembershipRole.Role.COACH,
            revoked_at=timezone.now(),
        )
        MembershipRoleFactory(membership=member, role=MembershipRole.Role.CAPTAIN)

        response = _list(_authenticated_client(viewer.user))

        row = next(row for row in response.data if row["membership_id"] == member.id)
        returned_roles = {entry["role"] for entry in row["roles"]}
        assert returned_roles == {MembershipRole.Role.CAPTAIN}

    def test_response_never_contains_financial_or_medical_fields(self):
        club = ClubFactory()
        viewer = MembershipFactory(club=club)
        MembershipFactory(club=club)

        response = _list(_authenticated_client(viewer.user))

        assert response.status_code == status.HTTP_200_OK
        expected_keys = {
            "membership_id",
            "first_name",
            "last_name",
            "photo",
            "position",
            "position_label",
            "position_detail",
            "jersey_number",
            "membership_status",
            "membership_status_label",
            "joined_on",
            "roles",
            # Booléen « bloqué » du pointage groupé, sans motif (10.2 n° 16).
            "is_unavailable",
        }
        for row in response.data:
            assert set(row.keys()) == expected_keys

    def test_invalid_filter_value_returns_400_in_french(self):
        club = ClubFactory()
        viewer = MembershipFactory(club=club)

        response = _list(_authenticated_client(viewer.user), position="gardien-de-but-invalide")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_anonymous_user_is_rejected(self):
        club = ClubFactory()
        MembershipFactory(club=club)

        response = APIClient().get(reverse("clubs:players-list"))

        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def _card(client: APIClient, membership_id: int):
    return client.get(reverse("clubs:player-card", args=[membership_id]))


class TestPlayerCardPendingStatusForTreasury:
    """Demande dev-b (B6, 27/11/2026) : la carte joueur montre « En attente »
    au Tresorier et a son adjoint (CDC 4.3, matrice 2.4 « Enregistrement des
    paiements ») ; le masquage du 10.2 n16 reste en place pour les
    coequipiers."""

    @pytest.mark.parametrize("role", [MembershipRole.Role.TREASURER, MembershipRole.Role.ASSISTANT_TREASURER])
    def test_le_tresorier_voit_en_attente_sur_la_carte(self, role):
        club = ClubFactory()
        treasurer = MembershipFactory(club=club, status=Membership.Status.ACTIVE)
        MembershipRoleFactory(membership=treasurer, role=role)
        pending = MembershipFactory(club=club, status=Membership.Status.PENDING)

        response = _card(_authenticated_client(treasurer.user), pending.id)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["membership_status"] == Membership.Status.PENDING
        assert response.data["membership_status_label"] == "En attente"

    def test_le_tresorier_retrouve_les_joueurs_en_attente_par_le_filtre(self):
        club = ClubFactory()
        treasurer = MembershipFactory(club=club, status=Membership.Status.ACTIVE)
        MembershipRoleFactory(membership=treasurer, role=MembershipRole.Role.TREASURER)
        pending = MembershipFactory(club=club, status=Membership.Status.PENDING)

        response = _list(_authenticated_client(treasurer.user), status=Membership.Status.PENDING)

        assert {row["membership_id"] for row in response.data} == {pending.id}

    @pytest.mark.parametrize("role", [None, MembershipRole.Role.SECRETARY, MembershipRole.Role.CAPTAIN])
    def test_un_coequipier_voit_toujours_le_statut_masque(self, role):
        club = ClubFactory()
        viewer = MembershipFactory(club=club, status=Membership.Status.ACTIVE)
        if role:
            MembershipRoleFactory(membership=viewer, role=role)
        pending = MembershipFactory(club=club, status=Membership.Status.PENDING)

        response = _card(_authenticated_client(viewer.user), pending.id)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["membership_status"] == "unavailable"
        assert response.data["membership_status_label"] == "Indisponible"

    def test_un_tresorier_revoque_ne_voit_plus_le_statut(self):
        club = ClubFactory()
        treasurer = MembershipFactory(club=club, status=Membership.Status.ACTIVE)
        role = MembershipRoleFactory(membership=treasurer, role=MembershipRole.Role.TREASURER)
        pending = MembershipFactory(club=club, status=Membership.Status.PENDING)
        role.revoked_at = timezone.now()
        role.revoked_by = treasurer.user
        role.save()

        response = _card(_authenticated_client(treasurer.user), pending.id)

        assert response.data["membership_status"] == "unavailable"

    def test_le_tresorier_d_un_autre_club_recoit_404(self):
        club = ClubFactory()
        pending = MembershipFactory(club=club, status=Membership.Status.PENDING)
        other_treasurer = MembershipFactory(club=ClubFactory(), status=Membership.Status.ACTIVE)
        MembershipRoleFactory(membership=other_treasurer, role=MembershipRole.Role.TREASURER)

        response = _card(_authenticated_client(other_treasurer.user), pending.id)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "membership_status" not in response.data
