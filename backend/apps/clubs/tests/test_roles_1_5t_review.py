"""Revue independante de la tache 1.5 (tache 1.5t, plan-lots.md).

Complements de couverture apportes par test-engineer en plus des tests
deja livres par backend-dev (`test_services_roles.py`, `test_views_roles.py`).
Sources : CDC 2.2-2.4, 9.2 Lot 1 ; CLAUDE.md regle n8 (etancheite
multi-tenant), regle n6 (journal).

Ce module ne modifie ni n'affaiblit aucun test existant : il ajoute des
cas non couverts, et documente explicitement (docstring « BUG » ou
« ECART ») tout comportement observe qui contredit le cahier des
charges, sans le corriger (regle du projet : un test qui echoue revele
un bug, jamais une raison de le desactiver).
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.clubs import services
from apps.clubs.models import ClubSettings, Membership, MembershipRole, PresidencyTransfer
from apps.clubs.tests.factories import ClubFactory, ClubSettingsFactory, MembershipFactory, MembershipRoleFactory
from apps.core.roles import get_active_roles, has_any_role
from apps.core.tenant import active_club


def _authenticated_client(user) -> APIClient:
    """Meme helper que `test_views_roles.py` : jeton d'acces reel, pour
    que le club actif soit resolu depuis l'adhesion reelle (regle n9)."""

    client = APIClient()
    access_token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return client


# ---------------------------------------------------------------------------
# 1. Cumul de roles (CDC 2.2) : le role qui autorise n'est jamais le premier
#    role attribue, et un role revoque ne doit jamais compter, meme cumule
#    avec un role actif.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCumulDeRolesRevocationEtOrdreDattribution:
    def test_get_active_roles_ignore_un_role_revoque_meme_cumule_avec_un_role_actif(self):
        """Cumul CDC 2.2 : le role revoque ne doit jamais compter dans
        l'union des droits, meme si un AUTRE role reste actif en meme
        temps sur la meme adhesion."""

        membership = MembershipFactory()
        role_actif = MembershipRoleFactory(membership=membership, role=MembershipRole.Role.ASSISTANT_TREASURER)
        role_revoque = MembershipRoleFactory(membership=membership, role=MembershipRole.Role.COACH)
        role_revoque.revoked_by = membership.added_by
        role_revoque.revoked_at = timezone.now()
        role_revoque.save()

        with active_club(membership.club):
            actifs = get_active_roles(membership.user, club=membership.club)
            assert actifs == {MembershipRole.Role.ASSISTANT_TREASURER}
            assert has_any_role(membership.user, {MembershipRole.Role.COACH}, club=membership.club) is False
            assert has_any_role(membership.user, {MembershipRole.Role.ASSISTANT_TREASURER}, club=membership.club) is True

    def test_role_reappointe_apres_revocation_compte_de_nouveau_comme_actif(self):
        """Un role revoque puis re-attribue (nouvelle ligne) doit de
        nouveau compter, meme si une PREMIERE ligne pour ce meme role sur
        la meme adhesion reste revoquee en base."""

        membership = MembershipFactory()
        premiere = MembershipRoleFactory(membership=membership, role=MembershipRole.Role.STEWARD)
        premiere.revoked_by = membership.added_by
        premiere.revoked_at = timezone.now()
        premiere.save()
        MembershipRoleFactory(membership=membership, role=MembershipRole.Role.STEWARD)

        with active_club(membership.club):
            assert has_any_role(membership.user, {MembershipRole.Role.STEWARD}, club=membership.club) is True

    def test_endpoint_capitaine_accessible_via_le_role_coach_detenu_en_second(self):
        """CDC 2.2 : l'union des droits s'applique, y compris quand le role
        qui autorise l'action n'est pas le premier role attribue au joueur
        (ordre d'attribution non pertinent)."""

        club = ClubFactory()
        membre = MembershipFactory(club=club)
        # Premier role attribue : ne donne aucun droit sur cet endpoint.
        MembershipRoleFactory(membership=membre, role=MembershipRole.Role.ASSISTANT_TREASURER)
        # Second role attribue : c'est lui qui doit autoriser l'action.
        MembershipRoleFactory(membership=membre, role=MembershipRole.Role.COACH)
        target = MembershipFactory(club=club)
        client = _authenticated_client(membre.user)

        response = client.post(reverse("clubs:captain-appoint"), {"membership_id": target.id}, format="json")

        assert response.status_code == status.HTTP_201_CREATED

    def test_endpoint_bureau_refuse_si_le_seul_role_actif_restant_nest_pas_president(self):
        """Symmetrique : un joueur qui a PERDU son role President (revoque)
        mais garde un autre role actif ne doit plus pouvoir nommer le
        bureau, meme si ce role President a ete detenu en premier."""

        club = ClubFactory()
        membre = MembershipFactory(club=club)
        president_role = MembershipRoleFactory(membership=membre, role=MembershipRole.Role.PRESIDENT)
        MembershipRoleFactory(membership=membre, role=MembershipRole.Role.STEWARD)
        president_role.revoked_by = membre.added_by
        president_role.revoked_at = timezone.now()
        president_role.save()
        target = MembershipFactory(club=club)
        client = _authenticated_client(membre.user)

        response = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": target.id, "role": MembershipRole.Role.TREASURER},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# 2. Plafond `board_seats_per_role` : par ROLE et par CLUB (CDC 10.2 n24).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPlafondParRoleEtParClub:
    def test_le_plafond_dun_role_natteint_pas_un_autre_role_du_meme_club(self):
        """Le plafond se verifie role par role : un plafond atteint pour
        le Tresorier ne bloque pas une nomination Tresorier adjoint dans
        le meme club."""

        club = ClubFactory()
        ClubSettingsFactory(club=club, board_seats_per_role=1)
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        tresorier = MembershipFactory(club=club)
        adjoint = MembershipFactory(club=club)

        services.appoint_president_nominated_role(
            president_user=president.user, target_membership=tresorier, role=MembershipRole.Role.TREASURER
        )
        role = services.appoint_president_nominated_role(
            president_user=president.user,
            target_membership=adjoint,
            role=MembershipRole.Role.ASSISTANT_TREASURER,
        )

        assert role.pk is not None

    def test_le_plafond_atteint_dans_le_club_a_ne_bloque_pas_le_meme_role_dans_le_club_b(self):
        """Etancheite multi-tenant du plafond (regle n8) : le compte des
        titulaires actifs d'un role est filtre par club, jamais global a
        la plateforme."""

        club_a = ClubFactory()
        club_b = ClubFactory()
        ClubSettingsFactory(club=club_a, board_seats_per_role=1)
        ClubSettingsFactory(club=club_b, board_seats_per_role=1)

        president_a = MembershipFactory(club=club_a)
        MembershipRoleFactory(membership=president_a, role=MembershipRole.Role.PRESIDENT)
        president_b = MembershipFactory(club=club_b)
        MembershipRoleFactory(membership=president_b, role=MembershipRole.Role.PRESIDENT)

        services.appoint_president_nominated_role(
            president_user=president_a.user,
            target_membership=MembershipFactory(club=club_a),
            role=MembershipRole.Role.TREASURER,
        )
        # Le plafond du club A (1, deja atteint) ne doit avoir aucun effet
        # sur le club B : la nomination doit reussir independamment.
        role_b = services.appoint_president_nominated_role(
            president_user=president_b.user,
            target_membership=MembershipFactory(club=club_b),
            role=MembershipRole.Role.TREASURER,
        )

        assert role_b.pk is not None
        actifs_b = MembershipRole.all_objects.filter(
            club=club_b, role=MembershipRole.Role.TREASURER, revoked_at__isnull=True
        ).count()
        assert actifs_b == 1


# ---------------------------------------------------------------------------
# 3. Cardinalite du President : la garantie repose UNIQUEMENT sur la
#    conception des services (docstring de `MembershipRole`) -- ce bloc
#    verifie si un autre chemin d'ecriture peut la contourner.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCardinaliteDuPresidentHorsServices:
    def test_une_creation_directe_de_membershiprole_ne_cree_pas_de_second_president_actif(self):
        """CDC 2.3 : « Un club a toujours un et un seul President. » C'est
        un invariant de donnees, pas seulement une garantie procedurale :
        cette assertion doit tenir MEME pour un chemin d'ecriture qui ne
        passe pas par `transfer_presidency_by_handover`/
        `transfer_presidency_by_superuser` (ex. un futur correctif Superuser
        en Ghost Mode, un script de migration de donnees, un bug dans un
        autre service qui appellerait `MembershipRole.objects.create()`
        directement).

        BUG POTENTIEL (a signaler, ne pas corriger ici) : la docstring de
        `MembershipRole` (apps/clubs/models.py) affirme explicitement qu'il
        n'existe volontairement AUCUNE contrainte d'unicite dediee pour le
        President -- la garantie « un seul President » ne vient QUE de la
        conception atomique des deux fonctions de passation. `clean()`
        exclut explicitement `Role.PRESIDENT` de son controle de plafond
        (`role not in (self.Role.PRESIDENT, self.Role.PLAYER_RECRUITER)`).
        Si ce test echoue, c'est la preuve qu'un deuxieme President actif
        peut etre cree dans le meme club par un chemin autre que les deux
        services dedies, ce qui contredit CDC 2.3."""

        club = ClubFactory()
        premier_president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=premier_president, role=MembershipRole.Role.PRESIDENT)
        autre_joueur = MembershipFactory(club=club)

        second_role = MembershipRole(
            club=club,
            membership=autre_joueur,
            role=MembershipRole.Role.PRESIDENT,
            appointed_by=premier_president.user,
            appointed_at=timezone.now(),
        )
        with active_club(club):
            with pytest.raises(ValidationError):
                second_role.save()

        actifs = MembershipRole.all_objects.filter(
            club=club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
        )
        assert actifs.count() == 1, (
            "Deux Presidents actifs coexistent dans le meme club : "
            "invariant CDC 2.3 viole par un chemin d'ecriture direct."
        )


# ---------------------------------------------------------------------------
# 4. Etancheite multi-tenant sur chaque endpoint de roles (regle n8).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEtancheiteMultiTenantEndpointsRoles:
    def test_le_president_du_club_a_ne_peut_pas_nommer_un_role_pour_une_adhesion_du_club_b(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        president_a = MembershipFactory(club=club_a)
        MembershipRoleFactory(membership=president_a, role=MembershipRole.Role.PRESIDENT)
        cible_b = MembershipFactory(club=club_b)
        client = _authenticated_client(president_a.user)

        response = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": cible_b.id, "role": MembershipRole.Role.TREASURER},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert not MembershipRole.all_objects.filter(membership=cible_b, role=MembershipRole.Role.TREASURER).exists()

    def test_le_president_du_club_a_ne_peut_pas_revoquer_un_role_du_club_b(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        president_a = MembershipFactory(club=club_a)
        MembershipRoleFactory(membership=president_a, role=MembershipRole.Role.PRESIDENT)
        role_b = MembershipRoleFactory(membership=MembershipFactory(club=club_b), role=MembershipRole.Role.STEWARD)
        client = _authenticated_client(president_a.user)

        response = client.post(reverse("clubs:role-revoke"), {"role_id": role_b.id}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        role_b.refresh_from_db()
        assert role_b.revoked_at is None

    def test_le_coach_du_club_a_ne_peut_pas_choisir_un_capitaine_du_club_b(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        coach_a = MembershipFactory(club=club_a)
        MembershipRoleFactory(membership=coach_a, role=MembershipRole.Role.COACH)
        cible_b = MembershipFactory(club=club_b)
        client = _authenticated_client(coach_a.user)

        response = client.post(reverse("clubs:captain-appoint"), {"membership_id": cible_b.id}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert not MembershipRole.all_objects.filter(membership=cible_b, role=MembershipRole.Role.CAPTAIN).exists()

    def test_le_coach_du_club_a_ne_peut_pas_revoquer_un_capitaine_du_club_b(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        coach_a = MembershipFactory(club=club_a)
        MembershipRoleFactory(membership=coach_a, role=MembershipRole.Role.COACH)
        capitaine_b = MembershipFactory(club=club_b)
        role_b = MembershipRoleFactory(membership=capitaine_b, role=MembershipRole.Role.CAPTAIN)
        client = _authenticated_client(coach_a.user)

        response = client.post(reverse("clubs:captain-revoke"), {"role_id": role_b.id}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        role_b.refresh_from_db()
        assert role_b.revoked_at is None

    def test_le_president_du_club_a_ne_peut_pas_passer_la_main_a_une_adhesion_du_club_b(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        sortant_a = MembershipFactory(club=club_a)
        MembershipRoleFactory(membership=sortant_a, role=MembershipRole.Role.PRESIDENT)
        cible_b = MembershipFactory(club=club_b)
        client = _authenticated_client(sortant_a.user)

        response = client.post(
            reverse("clubs:presidency-handover"), {"to_membership_id": cible_b.id}, format="json"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        actifs_a = MembershipRole.all_objects.filter(
            club=club_a, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
        )
        assert actifs_a.count() == 1
        assert actifs_a.first().membership_id == sortant_a.id

    def test_intervention_superuser_avec_from_membership_dun_autre_club_que_club_id_est_refusee(self):
        """Le Superuser designe explicitement `club_id` : une adhesion
        d'un AUTRE club que celui indique ne doit jamais etre resolue
        (pas de fuite entre clubs, regle n8), meme depuis l'espace
        Superuser qui utilise `all_objects`."""

        club_a = ClubFactory()
        club_b = ClubFactory()
        sortant_a = MembershipFactory(club=club_a)
        MembershipRoleFactory(membership=sortant_a, role=MembershipRole.Role.PRESIDENT)
        cible_b = MembershipFactory(club=club_b)
        superuser = SuperuserFactory()
        client = _authenticated_client(superuser)

        response = client.post(
            reverse("clubs:presidency-superuser-override"),
            {
                "club_id": club_a.id,
                "from_membership_id": sortant_a.id,
                "to_membership_id": cible_b.id,
                "reason": "Motif ecrit.",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        actifs_a = MembershipRole.all_objects.filter(
            club=club_a, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
        )
        assert actifs_a.count() == 1
        assert actifs_a.first().membership_id == sortant_a.id

    def test_la_liste_des_roles_du_club_a_ne_contient_aucun_role_du_club_b(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        membre_a = MembershipFactory(club=club_a)
        role_a = MembershipRoleFactory(membership=membre_a, role=MembershipRole.Role.CAPTAIN)
        role_b = MembershipRoleFactory(membership=MembershipFactory(club=club_b), role=MembershipRole.Role.CAPTAIN)
        client = _authenticated_client(membre_a.user)

        response = client.get(reverse("clubs:role-list"))

        assert response.status_code == status.HTTP_200_OK
        ids = {entry["id"] for entry in response.data}
        assert role_a.id in ids
        assert role_b.id not in ids


# ---------------------------------------------------------------------------
# 5. Permissions par endpoint : refus explicite pour chaque role qui n'est
#    pas dans la matrice 2.4, au-dela du seul « simple joueur ».
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRefusExpliciteParRoleNonAutorise:
    def test_le_capitaine_ne_peut_pas_revoquer_un_role_du_bureau(self):
        """Matrice 2.4 : la revocation du bureau est reservee au President."""

        club = ClubFactory()
        capitaine = MembershipFactory(club=club)
        MembershipRoleFactory(membership=capitaine, role=MembershipRole.Role.CAPTAIN)
        role = MembershipRoleFactory(membership=MembershipFactory(club=club), role=MembershipRole.Role.STEWARD)
        client = _authenticated_client(capitaine.user)

        response = client.post(reverse("clubs:role-revoke"), {"role_id": role.id}, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_le_president_seul_ne_peut_pas_retirer_le_capitaine(self):
        """Matrice 2.4 : « Choix du Capitaine » est É pour le Coach
        uniquement -- le retrait suit la meme regle que la nomination."""

        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        role = MembershipRoleFactory(membership=MembershipFactory(club=club), role=MembershipRole.Role.CAPTAIN)
        client = _authenticated_client(president.user)

        response = client.post(reverse("clubs:captain-revoke"), {"role_id": role.id}, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_le_vice_president_ne_peut_pas_nommer_le_bureau(self):
        """Matrice 2.4 : « Nomination du bureau et du Medecin » est L pour
        le Vice-president, É pour le President seul."""

        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        vice_president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=vice_president, role=MembershipRole.Role.VICE_PRESIDENT)
        target = MembershipFactory(club=club)
        client = _authenticated_client(vice_president.user)

        response = client.post(
            reverse("clubs:role-appoint"),
            {"membership_id": target.id, "role": MembershipRole.Role.TREASURER},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# 6. Message clair pour le Medecin sans qualification precisee (10.2 n17).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_message_de_refus_medecin_sans_qualification_est_en_francais_clair():
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
    detail = " ".join(response.data.get("detail", []) if isinstance(response.data.get("detail"), list) else [response.data.get("detail", "")])
    assert "qualifi" in detail.lower()
    assert "Traceback" not in detail
    assert "Exception" not in detail


# ---------------------------------------------------------------------------
# 7. Passation de presidence : cas limites (CDC 2.3).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPassationDePresidenceCasLimites:
    def test_le_president_sortant_ne_peut_pas_se_designer_lui_meme_comme_successeur(self):
        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)

        with pytest.raises(services.RoleManagementError):
            services.transfer_presidency_by_handover(outgoing_user=sortant.user, to_membership=sortant)

        actifs = MembershipRole.all_objects.filter(
            club=club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
        )
        assert actifs.count() == 1
        assert actifs.first().membership_id == sortant.id

    def test_http_le_president_sortant_ne_peut_pas_se_designer_lui_meme(self):
        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(sortant.user)

        response = client.post(
            reverse("clubs:presidency-handover"), {"to_membership_id": sortant.id}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_intervention_superuser_avec_from_membership_qui_ne_detient_plus_le_role_president(self):
        """Le President a change entre-temps (passation directe) : la
        demande Superuser qui vise l'ANCIEN titulaire comme sortant doit
        echouer avec un message clair, pas un crash technique."""

        club = ClubFactory()
        ancien_president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=ancien_president, role=MembershipRole.Role.PRESIDENT)
        nouveau_president = MembershipFactory(club=club)
        services.transfer_presidency_by_handover(
            outgoing_user=ancien_president.user, to_membership=nouveau_president
        )
        troisieme = MembershipFactory(club=club)
        superuser = SuperuserFactory()

        with pytest.raises(services.RoleManagementError):
            services.transfer_presidency_by_superuser(
                superuser=superuser,
                from_membership=ancien_president,  # plus President actuellement
                to_membership=troisieme,
                reason="Motif ecrit valable.",
            )

        actifs = MembershipRole.all_objects.filter(
            club=club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
        )
        assert actifs.count() == 1
        assert actifs.first().membership_id == nouveau_president.id

    def test_http_intervention_superuser_avec_from_membership_perime_renvoie_400_pas_500(self):
        club = ClubFactory()
        ancien_president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=ancien_president, role=MembershipRole.Role.PRESIDENT)
        nouveau_president = MembershipFactory(club=club)
        services.transfer_presidency_by_handover(
            outgoing_user=ancien_president.user, to_membership=nouveau_president
        )
        troisieme = MembershipFactory(club=club)
        superuser = SuperuserFactory()
        client = _authenticated_client(superuser)

        response = client.post(
            reverse("clubs:presidency-superuser-override"),
            {
                "club_id": club.id,
                "from_membership_id": ancien_president.id,
                "to_membership_id": troisieme.id,
                "reason": "Motif ecrit valable.",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# 8. `update_board_seats_per_role` : reduction en dessous du nombre de
#    titulaires actifs (comportement non precise par le CDC -- documente
#    ici, a confirmer avec le client).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReductionDuPlafondSousLeNombreDeTitulairesActifs:
    def test_reduire_le_plafond_sous_le_nombre_de_titulaires_actifs_ne_les_revoque_pas(self):
        """Comportement observe (a confirmer, non tranche par le CDC) :
        `update_board_seats_per_role` ne fait AUCUN controle par rapport
        aux titulaires actifs existants -- reduire le plafond en dessous
        de leur nombre reussit silencieusement, sans revoquer personne.
        Le club se retrouve alors « en depassement » : toute NOUVELLE
        nomination pour ce role sera bloquee par `clean()` tant que des
        titulaires ne sont pas revoques manuellement, mais les titulaires
        actuels restent actifs sans aucune alerte ni notification.

        Ce test documente ce comportement observe ; il n'affirme pas qu'il
        s'agit d'une violation du CDC (aucune regle 10.2 n24 ne precise le
        cas), mais le signale explicitement dans le compte rendu pour
        decision du client."""

        club = ClubFactory()
        club_settings = ClubSettingsFactory(club=club, board_seats_per_role=2)
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        premier = MembershipFactory(club=club)
        second = MembershipFactory(club=club)
        services.appoint_president_nominated_role(
            president_user=president.user, target_membership=premier, role=MembershipRole.Role.TREASURER
        )
        services.appoint_president_nominated_role(
            president_user=president.user, target_membership=second, role=MembershipRole.Role.TREASURER
        )

        updated = services.update_board_seats_per_role(
            president_user=president.user, club_settings=club_settings, seats=1
        )

        assert updated.board_seats_per_role == 1
        actifs = MembershipRole.all_objects.filter(
            club=club, role=MembershipRole.Role.TREASURER, revoked_at__isnull=True
        )
        assert actifs.count() == 2, "Les titulaires existants ne sont pas revoques par la reduction du plafond."

        # Le depassement bloque bien toute NOUVELLE nomination pour ce role.
        troisieme = MembershipFactory(club=club)
        with pytest.raises(ValidationError):
            services.appoint_president_nominated_role(
                president_user=president.user, target_membership=troisieme, role=MembershipRole.Role.TREASURER
            )
