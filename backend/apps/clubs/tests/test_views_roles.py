"""Tests HTTP des endpoints de roles (CDC 2.2-2.4 ; tache 1.5, 1.5t).

Verifie, endpoint par endpoint, que la classe de permission correspond a
la matrice 2.4, que le cumul de roles (CDC 2.2) est respecte, et que le
critere de fin de la tache 1.5 (plan-lots.md) est satisfait : « un club
configure a 2 titulaires pour un role accepte la seconde nomination ».
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import ClubFactory, ClubSettingsFactory, MembershipFactory, MembershipRoleFactory


@pytest.fixture
def api_client():
    return APIClient()


def _authenticated_client(user) -> APIClient:
    """Client authentifie par un jeton d'acces reel (pas ``force_authenticate``) :
    passe par ``TenantJWTAuthentication`` comme en production, pour que le
    club actif soit resolu depuis l'adhesion reelle (CLAUDE.md regle n9),
    exactement comme le ferait une requete de production."""

    client = APIClient()
    access_token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return client


@pytest.mark.django_db
class TestRoleAppointmentView:
    def test_le_president_nomme_un_role_du_bureau(self):
        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club)
        client = _authenticated_client(president.user)

        response = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": target.id, "role": MembershipRole.Role.TREASURER},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["role"] == MembershipRole.Role.TREASURER
        assert response.data["role_label"] == "Trésorier"

    def test_un_simple_joueur_est_refuse(self):
        club = ClubFactory()
        joueur = MembershipFactory(club=club)
        target = MembershipFactory(club=club)
        client = _authenticated_client(joueur.user)

        response = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": target.id, "role": MembershipRole.Role.TREASURER},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_le_coach_seul_ne_peut_pas_nommer_un_role_du_bureau(self):
        """Matrice 2.4 : « Nomination du bureau et du Medecin » est L pour
        le Coach, pas É."""

        club = ClubFactory()
        coach = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach, role=MembershipRole.Role.COACH)
        target = MembershipFactory(club=club)
        client = _authenticated_client(coach.user)

        response = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": target.id, "role": MembershipRole.Role.TREASURER},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cumul_de_roles_president_et_coach_peut_nommer(self):
        """CDC 2.2 : cumul de roles -- l'union des droits s'applique."""

        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.COACH)
        target = MembershipFactory(club=club)
        client = _authenticated_client(president.user)

        response = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": target.id, "role": MembershipRole.Role.TREASURER},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

    def test_le_capitaine_est_refuse_par_cet_endpoint(self):
        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club)
        client = _authenticated_client(president.user)

        response = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": target.id, "role": MembershipRole.Role.CAPTAIN},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_medecin_sans_qualification_precisee_est_refuse(self):
        """CDC 10.2 n17 : choix explicite obligatoire, jamais devine."""

        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club)
        client = _authenticated_client(president.user)

        response = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": target.id, "role": MembershipRole.Role.DOCTOR},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_medecin_non_qualifie_est_affiche_referent_sante(self):
        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club)
        client = _authenticated_client(president.user)

        response = client.post(
            reverse("clubs:role-appoint"),
            {
                "membership_id": target.id,
                "role": MembershipRole.Role.DOCTOR,
                "is_qualified_professional": False,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["effective_label"] == "Médecin / référent santé"

    def test_seconde_nomination_refusee_par_defaut(self):
        club = ClubFactory()
        ClubSettingsFactory(club=club)  # board_seats_per_role=1
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president.user)

        premier = MembershipFactory(club=club)
        second = MembershipFactory(club=club)

        r1 = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": premier.id, "role": MembershipRole.Role.TREASURER},
            format="json",
        )
        r2 = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": second.id, "role": MembershipRole.Role.TREASURER},
            format="json",
        )

        assert r1.status_code == status.HTTP_201_CREATED
        assert r2.status_code == status.HTTP_400_BAD_REQUEST

    def test_seconde_nomination_acceptee_si_club_configure_a_deux_titulaires(self):
        """Critere de fin de la tache 1.5 (plan-lots.md)."""

        club = ClubFactory()
        ClubSettingsFactory(club=club, board_seats_per_role=2)
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president.user)

        premier = MembershipFactory(club=club)
        second = MembershipFactory(club=club)

        r1 = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": premier.id, "role": MembershipRole.Role.TREASURER},
            format="json",
        )
        r2 = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": second.id, "role": MembershipRole.Role.TREASURER},
            format="json",
        )

        assert r1.status_code == status.HTTP_201_CREATED
        assert r2.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestRoleRevocationView:
    def test_le_president_revoque(self):
        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        role = MembershipRoleFactory(membership=MembershipFactory(club=club), role=MembershipRole.Role.STEWARD)
        client = _authenticated_client(president.user)

        response = client.post(
            reverse("clubs:role-revoke"), {"role_id": role.id, "reason": "Depart"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["revoked_at"] is not None

    def test_un_simple_joueur_est_refuse(self):
        club = ClubFactory()
        joueur = MembershipFactory(club=club)
        role = MembershipRoleFactory(membership=MembershipFactory(club=club), role=MembershipRole.Role.STEWARD)
        client = _authenticated_client(joueur.user)

        response = client.post(reverse("clubs:role-revoke"), {"role_id": role.id}, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestCaptainViews:
    def test_le_coach_choisit_le_capitaine(self):
        club = ClubFactory()
        coach = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach, role=MembershipRole.Role.COACH)
        target = MembershipFactory(club=club)
        client = _authenticated_client(coach.user)

        response = client.post(
            reverse("clubs:captain-appoint"), {"membership_id": target.id}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["role"] == MembershipRole.Role.CAPTAIN

    def test_le_president_seul_ne_peut_pas_choisir_le_capitaine(self):
        """Matrice 2.4 : « Choix du Capitaine » est L pour le President, É pour le Coach."""

        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club)
        client = _authenticated_client(president.user)

        response = client.post(
            reverse("clubs:captain-appoint"), {"membership_id": target.id}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_le_coach_retire_le_capitaine(self):
        club = ClubFactory()
        coach = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach, role=MembershipRole.Role.COACH)
        role = MembershipRoleFactory(membership=MembershipFactory(club=club), role=MembershipRole.Role.CAPTAIN)
        client = _authenticated_client(coach.user)

        response = client.post(reverse("clubs:captain-revoke"), {"role_id": role.id}, format="json")

        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestPresidencyTransferViews:
    def test_le_president_sortant_passe_la_main(self):
        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        entrant = MembershipFactory(club=club)
        client = _authenticated_client(sortant.user)

        response = client.post(
            reverse("clubs:presidency-handover"), {"to_membership_id": entrant.id}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["method"] == "handover"

    def test_un_joueur_quelconque_ne_peut_pas_forcer_la_passation(self):
        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        entrant = MembershipFactory(club=club)
        autre_joueur = MembershipFactory(club=club)
        client = _authenticated_client(autre_joueur.user)

        response = client.post(
            reverse("clubs:presidency-handover"), {"to_membership_id": entrant.id}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_le_superuser_force_la_passation_avec_motif(self):
        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        entrant = MembershipFactory(club=club)
        superuser = SuperuserFactory()
        client = _authenticated_client(superuser)

        response = client.post(
            reverse("clubs:presidency-superuser-override"),
            {
                "club_id": club.id,
                "from_membership_id": sortant.id,
                "to_membership_id": entrant.id,
                "reason": "Blocage de gouvernance signale par le club.",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["method"] == "superuser_override"

    def test_le_superuser_sans_motif_est_refuse(self):
        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        entrant = MembershipFactory(club=club)
        superuser = SuperuserFactory()
        client = _authenticated_client(superuser)

        response = client.post(
            reverse("clubs:presidency-superuser-override"),
            {
                "club_id": club.id,
                "from_membership_id": sortant.id,
                "to_membership_id": entrant.id,
                "reason": "   ",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_un_non_superuser_ne_peut_pas_utiliser_l_intervention_forcee(self):
        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        entrant = MembershipFactory(club=club)
        client = _authenticated_client(sortant.user)

        response = client.post(
            reverse("clubs:presidency-superuser-override"),
            {
                "club_id": club.id,
                "from_membership_id": sortant.id,
                "to_membership_id": entrant.id,
                "reason": "Motif.",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestBoardSeatsSettingsView:
    def test_lecture_ouverte_a_tout_membre_actif(self):
        club = ClubFactory()
        ClubSettingsFactory(club=club, board_seats_per_role=2)
        joueur = MembershipFactory(club=club)
        client = _authenticated_client(joueur.user)

        response = client.get(reverse("clubs:board-seats"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["board_seats_per_role"] == 2

    def test_ecriture_reservee_au_president(self):
        club = ClubFactory()
        ClubSettingsFactory(club=club)
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president.user)

        response = client.patch(
            reverse("clubs:board-seats"), {"board_seats_per_role": 3}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["board_seats_per_role"] == 3

    def test_un_simple_joueur_ne_peut_pas_ecrire(self):
        club = ClubFactory()
        ClubSettingsFactory(club=club)
        joueur = MembershipFactory(club=club)
        client = _authenticated_client(joueur.user)

        response = client.patch(
            reverse("clubs:board-seats"), {"board_seats_per_role": 3}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestRoleListView:
    def test_liste_ouverte_a_tout_membre_actif(self):
        club = ClubFactory()
        joueur = MembershipFactory(club=club)
        MembershipRoleFactory(membership=joueur, role=MembershipRole.Role.CAPTAIN)
        client = _authenticated_client(joueur.user)

        response = client.get(reverse("clubs:role-list"))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["role"] == MembershipRole.Role.CAPTAIN

    def test_hors_authentification_est_refuse(self, api_client):
        response = api_client.get(reverse("clubs:role-list"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
