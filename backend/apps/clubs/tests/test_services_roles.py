"""Tests des services de nomination/revocation de roles (tache 1.5).

Sources : CDC 2.2-2.4, 10.2 n17 (Medecin/referent sante), 10.2 n24
(titulaires par role configurable par club).
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import SuperuserFactory
from apps.clubs import services
from apps.clubs.models import Membership, MembershipRole, PresidencyTransfer
from apps.clubs.tests.factories import (
    ClubFactory,
    ClubSettingsFactory,
    MembershipFactory,
    MembershipRoleFactory,
)


@pytest.mark.django_db
class TestAppointPresidentNominatedRole:
    def test_le_president_nomme_un_membre_du_bureau(self):
        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club)

        role = services.appoint_president_nominated_role(
            president_user=president_membership.user,
            target_membership=target,
            role=MembershipRole.Role.TREASURER,
        )

        assert role.membership_id == target.id
        assert role.role == MembershipRole.Role.TREASURER
        assert role.appointed_by_id == president_membership.user_id
        assert role.revoked_at is None

    def test_refuse_si_l_acteur_n_est_pas_president(self):
        club = ClubFactory()
        non_president = MembershipFactory(club=club)
        target = MembershipFactory(club=club)

        with pytest.raises(PermissionError):
            services.appoint_president_nominated_role(
                president_user=non_president.user,
                target_membership=target,
                role=MembershipRole.Role.TREASURER,
            )

    def test_refuse_pour_un_role_non_nomme_par_le_president(self):
        """Le Capitaine (Coach) et le President (passation) ne se nomment
        jamais par cette fonction (CDC 2.3)."""

        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club)

        with pytest.raises(services.RoleManagementError):
            services.appoint_president_nominated_role(
                president_user=president_membership.user,
                target_membership=target,
                role=MembershipRole.Role.CAPTAIN,
            )
        with pytest.raises(services.RoleManagementError):
            services.appoint_president_nominated_role(
                president_user=president_membership.user,
                target_membership=target,
                role=MembershipRole.Role.PRESIDENT,
            )

    def test_medecin_exige_le_choix_explicite_de_qualification(self):
        """CDC 10.2 n17 : « choix explicite du President [...] jamais devine »."""

        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club)

        with pytest.raises(services.RoleManagementError):
            services.appoint_president_nominated_role(
                president_user=president_membership.user,
                target_membership=target,
                role=MembershipRole.Role.DOCTOR,
                is_qualified_professional=None,
            )

    def test_qualification_non_applicable_hors_medecin(self):
        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club)

        with pytest.raises(services.RoleManagementError):
            services.appoint_president_nominated_role(
                president_user=president_membership.user,
                target_membership=target,
                role=MembershipRole.Role.TREASURER,
                is_qualified_professional=True,
            )

    def test_medecin_qualifie_garde_le_libelle_standard(self):
        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club)

        role = services.appoint_president_nominated_role(
            president_user=president_membership.user,
            target_membership=target,
            role=MembershipRole.Role.DOCTOR,
            is_qualified_professional=True,
        )

        assert services.get_effective_role_label(role) == "Médecin"

    def test_medecin_non_qualifie_porte_le_libelle_referent_sante(self):
        """CDC 10.2 n17 : « affiche « Medecin / referent sante » dans ce cas [...]
        avec exactement les memes droits que le role Medecin »."""

        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club)

        role = services.appoint_president_nominated_role(
            president_user=president_membership.user,
            target_membership=target,
            role=MembershipRole.Role.DOCTOR,
            is_qualified_professional=False,
        )

        assert role.is_qualified_professional is False
        assert services.get_effective_role_label(role) == "Médecin / référent santé"

    def test_libelle_special_jamais_fabrique_pour_un_autre_role(self):
        role = MembershipRoleFactory(role=MembershipRole.Role.TREASURER)
        assert services.get_effective_role_label(role) == "Trésorier"

    def test_refuse_la_nomination_d_un_joueur_parti(self):
        """CDC 2.3 : le President nomme « parmi les joueurs du club » --
        une adhesion DEPARTED n'en fait plus partie (revue de conformite,
        ecart B3)."""

        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club, status=Membership.Status.DEPARTED)

        with pytest.raises(services.RoleManagementError):
            services.appoint_president_nominated_role(
                president_user=president_membership.user,
                target_membership=target,
                role=MembershipRole.Role.TREASURER,
            )

    def test_refuse_la_nomination_d_un_joueur_en_attente(self):
        """Meme regle pour une adhesion PENDING (parrainage non finalise,
        ecart B3)."""

        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club, status=Membership.Status.PENDING)

        with pytest.raises(services.RoleManagementError):
            services.appoint_president_nominated_role(
                president_user=president_membership.user,
                target_membership=target,
                role=MembershipRole.Role.TREASURER,
            )


@pytest.mark.django_db
class TestCardinaliteParRole:
    def test_un_seul_titulaire_par_defaut_refuse_le_second(self):
        """10.2 n24 : « configurable par club, un seul par defaut »."""

        club = ClubFactory()
        ClubSettingsFactory(club=club)  # board_seats_per_role=1 par defaut
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        premier = MembershipFactory(club=club)
        second = MembershipFactory(club=club)

        services.appoint_president_nominated_role(
            president_user=president_membership.user, target_membership=premier, role=MembershipRole.Role.TREASURER
        )

        with pytest.raises(ValidationError):
            services.appoint_president_nominated_role(
                president_user=president_membership.user,
                target_membership=second,
                role=MembershipRole.Role.TREASURER,
            )

    def test_club_configure_a_deux_titulaires_accepte_la_seconde_nomination(self):
        """Critere de fin de la tache 1.5 (plan-lots.md) : « un club
        configure a 2 titulaires pour un role accepte la seconde
        nomination »."""

        club = ClubFactory()
        ClubSettingsFactory(club=club, board_seats_per_role=2)
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        premier = MembershipFactory(club=club)
        second = MembershipFactory(club=club)

        services.appoint_president_nominated_role(
            president_user=president_membership.user, target_membership=premier, role=MembershipRole.Role.TREASURER
        )
        role = services.appoint_president_nominated_role(
            president_user=president_membership.user, target_membership=second, role=MembershipRole.Role.TREASURER
        )

        assert role.pk is not None
        actifs = MembershipRole.all_objects.filter(
            club=club, role=MembershipRole.Role.TREASURER, revoked_at__isnull=True
        ).count()
        assert actifs == 2

    def test_recruteur_jamais_plafonne(self):
        """CDC 2.3 : le recruteur n'est jamais soumis au plafond (10.2 n24)."""

        club = ClubFactory()
        ClubSettingsFactory(club=club)  # board_seats_per_role=1
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)

        for _ in range(3):
            target = MembershipFactory(club=club)
            services.appoint_president_nominated_role(
                president_user=president_membership.user,
                target_membership=target,
                role=MembershipRole.Role.PLAYER_RECRUITER,
            )

        actifs = MembershipRole.all_objects.filter(
            club=club, role=MembershipRole.Role.PLAYER_RECRUITER, revoked_at__isnull=True
        ).count()
        assert actifs == 3

    def test_un_role_revoque_ne_compte_plus_dans_le_plafond(self):
        club = ClubFactory()
        ClubSettingsFactory(club=club)  # board_seats_per_role=1
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        premier = MembershipFactory(club=club)
        second = MembershipFactory(club=club)

        role = services.appoint_president_nominated_role(
            president_user=president_membership.user, target_membership=premier, role=MembershipRole.Role.STEWARD
        )
        services.revoke_president_nominated_role(president_user=president_membership.user, role=role)

        # Le titulaire precedent est revoque : la nomination d'un nouveau
        # titulaire pour ce meme role redevient possible.
        nouveau = services.appoint_president_nominated_role(
            president_user=president_membership.user, target_membership=second, role=MembershipRole.Role.STEWARD
        )
        assert nouveau.pk is not None


@pytest.mark.django_db
class TestRevokePresidentNominatedRole:
    def test_le_president_revoque_un_role(self):
        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        role = MembershipRoleFactory(membership=MembershipFactory(club=club), role=MembershipRole.Role.STEWARD)

        revoked = services.revoke_president_nominated_role(
            president_user=president_membership.user, role=role, reason="Depart du club"
        )

        assert revoked.revoked_at is not None
        assert revoked.revoked_by_id == president_membership.user_id
        assert revoked.revoked_reason == "Depart du club"

    def test_refuse_si_deja_revoque(self):
        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        role = MembershipRoleFactory(membership=MembershipFactory(club=club), role=MembershipRole.Role.STEWARD)
        services.revoke_president_nominated_role(president_user=president_membership.user, role=role)

        with pytest.raises(services.RoleManagementError):
            services.revoke_president_nominated_role(president_user=president_membership.user, role=role)

    def test_refuse_si_l_acteur_n_est_pas_president(self):
        club = ClubFactory()
        non_president = MembershipFactory(club=club)
        role = MembershipRoleFactory(membership=MembershipFactory(club=club), role=MembershipRole.Role.STEWARD)

        with pytest.raises(PermissionError):
            services.revoke_president_nominated_role(president_user=non_president.user, role=role)

    def test_refuse_pour_le_capitaine(self):
        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        role = MembershipRoleFactory(membership=MembershipFactory(club=club), role=MembershipRole.Role.CAPTAIN)

        with pytest.raises(services.RoleManagementError):
            services.revoke_president_nominated_role(president_user=president_membership.user, role=role)


@pytest.mark.django_db
class TestCapitaine:
    def test_le_coach_choisit_le_capitaine(self):
        club = ClubFactory()
        coach_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach_membership, role=MembershipRole.Role.COACH)
        target = MembershipFactory(club=club)

        role = services.appoint_captain(coach_user=coach_membership.user, target_membership=target)

        assert role.role == MembershipRole.Role.CAPTAIN
        assert role.appointed_by_id == coach_membership.user_id

    def test_refuse_si_l_acteur_n_est_pas_coach(self):
        """Matrice 2.4 : « Choix du Capitaine » est L pour le President, pas É."""

        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        target = MembershipFactory(club=club)

        with pytest.raises(PermissionError):
            services.appoint_captain(coach_user=president_membership.user, target_membership=target)

    def test_cumul_de_roles_coach_et_tresorier_adjoint_donne_droit_de_coach(self):
        """CDC 2.2 : cumul de roles -- l'union des droits s'applique."""

        club = ClubFactory()
        coach_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach_membership, role=MembershipRole.Role.COACH)
        MembershipRoleFactory(membership=coach_membership, role=MembershipRole.Role.ASSISTANT_TREASURER)
        target = MembershipFactory(club=club)

        role = services.appoint_captain(coach_user=coach_membership.user, target_membership=target)
        assert role.pk is not None

    def test_changer_le_capitaine_revoque_puis_nomme(self):
        club = ClubFactory()
        ClubSettingsFactory(club=club)  # un seul Capitaine par defaut
        coach_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach_membership, role=MembershipRole.Role.COACH)
        ancien_capitaine = MembershipFactory(club=club)
        nouveau_capitaine = MembershipFactory(club=club)

        ancien_role = services.appoint_captain(coach_user=coach_membership.user, target_membership=ancien_capitaine)

        with pytest.raises(ValidationError):
            # Le plafond (1 par defaut) refuse un second Capitaine actif
            # tant que l'ancien n'est pas revoque.
            services.appoint_captain(coach_user=coach_membership.user, target_membership=nouveau_capitaine)

        services.revoke_captain(coach_user=coach_membership.user, role=ancien_role)
        nouveau_role = services.appoint_captain(coach_user=coach_membership.user, target_membership=nouveau_capitaine)

        assert nouveau_role.pk is not None
        assert MembershipRole.all_objects.get(pk=ancien_role.pk).revoked_at is not None

    def test_refuse_de_designer_capitaine_un_joueur_parti(self):
        """CDC 2.3 (ecart B3) : le Capitaine se choisit « parmi les
        joueurs » -- un joueur DEPARTED n'en fait plus partie."""

        club = ClubFactory()
        coach_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach_membership, role=MembershipRole.Role.COACH)
        target = MembershipFactory(club=club, status=Membership.Status.DEPARTED)

        with pytest.raises(services.RoleManagementError):
            services.appoint_captain(coach_user=coach_membership.user, target_membership=target)


@pytest.mark.django_db
class TestTransfertDePresidenceParPassationDirecte:
    def test_passation_directe_est_atomique(self):
        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        entrant = MembershipFactory(club=club)

        transfer = services.transfer_presidency_by_handover(outgoing_user=sortant.user, to_membership=entrant)

        assert transfer.method == PresidencyTransfer.Method.HANDOVER
        actifs = MembershipRole.all_objects.filter(
            club=club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
        )
        # Jamais zero, jamais deux : exactement un President actif apres la passation.
        assert actifs.count() == 1
        assert actifs.first().membership_id == entrant.id

    def test_refuse_si_l_acteur_n_est_pas_le_president_sortant(self):
        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        entrant = MembershipFactory(club=club)
        autre_joueur = MembershipFactory(club=club)

        with pytest.raises(PermissionError):
            services.transfer_presidency_by_handover(outgoing_user=autre_joueur.user, to_membership=entrant)

    def test_refuse_si_aucun_president_actif(self):
        club = ClubFactory()
        membre = MembershipFactory(club=club)
        entrant = MembershipFactory(club=club)

        with pytest.raises(services.RoleManagementError):
            services.transfer_presidency_by_handover(outgoing_user=membre.user, to_membership=entrant)

    def test_refuse_si_le_successeur_n_est_plus_inscrit(self):
        """CDC 2.3 (ecart B3) : le successeur doit etre « parmi les
        joueurs du club » -- une adhesion DEPARTED n'en fait plus partie."""

        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        entrant = MembershipFactory(club=club, status=Membership.Status.DEPARTED)

        with pytest.raises(services.RoleManagementError):
            services.transfer_presidency_by_handover(outgoing_user=sortant.user, to_membership=entrant)


@pytest.mark.django_db
class TestTransfertDePresidenceParSuperuser:
    def test_exige_un_motif_ecrit(self):
        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        entrant = MembershipFactory(club=club)
        superuser = SuperuserFactory()

        with pytest.raises(services.RoleManagementError):
            services.transfer_presidency_by_superuser(
                superuser=superuser, from_membership=sortant, to_membership=entrant, reason=""
            )

    def test_refuse_si_l_acteur_n_est_pas_superuser(self):
        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        entrant = MembershipFactory(club=club)

        with pytest.raises(PermissionError):
            services.transfer_presidency_by_superuser(
                superuser=entrant.user, from_membership=sortant, to_membership=entrant, reason="Motif"
            )

    def test_intervention_reussie_est_atomique_et_journalisee_en_ghost_mode(self):
        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        entrant = MembershipFactory(club=club)
        superuser = SuperuserFactory()

        transfer = services.transfer_presidency_by_superuser(
            superuser=superuser,
            from_membership=sortant,
            to_membership=entrant,
            reason="Blocage de gouvernance signale par le club (CDC 2.3).",
        )

        assert transfer.method == PresidencyTransfer.Method.SUPERUSER_OVERRIDE
        assert transfer.superuser_id == superuser.id
        actifs = MembershipRole.all_objects.filter(
            club=club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
        )
        assert actifs.count() == 1
        assert actifs.first().membership_id == entrant.id

        from apps.audit.models import AuditLog

        entry = AuditLog.objects.get(
            action_type="clubs.presidency_transfer.completed", object_id=str(transfer.pk)
        )
        assert entry.actor_id == superuser.id
        assert entry.acted_as_ghost is True

    def test_refuse_si_le_successeur_n_est_plus_inscrit(self):
        """Meme regle que la passation directe (CDC 2.3, ecart B3)."""

        club = ClubFactory()
        sortant = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sortant, role=MembershipRole.Role.PRESIDENT)
        entrant = MembershipFactory(club=club, status=Membership.Status.PENDING)
        superuser = SuperuserFactory()

        with pytest.raises(services.RoleManagementError):
            services.transfer_presidency_by_superuser(
                superuser=superuser, from_membership=sortant, to_membership=entrant, reason="Motif"
            )


@pytest.mark.django_db
class TestBoardSeatsPerRole:
    def test_le_president_modifie_le_nombre_de_titulaires(self):
        club = ClubFactory()
        club_settings = ClubSettingsFactory(club=club)
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)

        updated = services.update_board_seats_per_role(
            president_user=president_membership.user, club_settings=club_settings, seats=2
        )

        assert updated.board_seats_per_role == 2
        from apps.audit.models import AuditLog

        entry = AuditLog.objects.get(
            action_type="clubs.settings.board_seats_updated", object_id=str(club.pk)
        )
        assert entry.after["board_seats_per_role"] == 2

    def test_refuse_pour_un_non_president(self):
        club = ClubFactory()
        club_settings = ClubSettingsFactory(club=club)
        membre = MembershipFactory(club=club)

        with pytest.raises(PermissionError):
            services.update_board_seats_per_role(
                president_user=membre.user, club_settings=club_settings, seats=2
            )


@pytest.mark.django_db
def test_notify_role_change_cree_une_notification_au_joueur_concerne():
    """Le point d'accroche de la tache 1.5 est reellement cable par la
    tache 1.7 (CDC 2.3 : « notification au joueur concerne » ; CDC 4.17,
    ligne « Nomination ou revocation »). Remplace l'ancien test qui ne
    verifiait qu'un no-op deliberement provisoire (voir docstring de
    ``notify_role_change`` avant la tache 1.7) : ce point d'accroche a
    desormais un comportement reel a verifier."""

    from apps.notifications.models import Notification

    membership = MembershipFactory()
    role_instance = MembershipRoleFactory(membership=membership, role=MembershipRole.Role.COACH)

    result = services.notify_role_change(role_instance=role_instance, event="appointed")

    assert result is None  # toujours pas de valeur de retour utile (effet de bord uniquement)
    notification = Notification.objects.get(recipient=membership.user)
    assert notification.event_type == Notification.EventType.ROLE_APPOINTED_OR_REVOKED
    assert notification.title == "Nouveau rôle"
    assert notification.body == f"Vous avez désormais le rôle « Coach » au sein de {membership.club.name}."
    assert notification.club_id == membership.club_id


@pytest.mark.django_db
def test_notify_role_change_revocation_message_different_de_la_nomination():
    from apps.notifications.models import Notification

    membership = MembershipFactory()
    role_instance = MembershipRoleFactory(membership=membership, role=MembershipRole.Role.COACH)

    services.notify_role_change(role_instance=role_instance, event="revoked")

    notification = Notification.objects.get(recipient=membership.user)
    assert notification.title == "Fin de rôle"
    assert notification.body == f"Vous n'avez plus le rôle « Coach » au sein de {membership.club.name}."


@pytest.mark.django_db
class TestCanViewPendingMembershipStatus:
    """Ecart B6 : CDC 10.2 n16 (precise en 4.12) -- qui voit qu'une
    adhesion est « En attente »."""

    @pytest.mark.parametrize(
        "role",
        [
            MembershipRole.Role.PRESIDENT,
            MembershipRole.Role.VICE_PRESIDENT,
            MembershipRole.Role.SPORTS_DIRECTOR,
            MembershipRole.Role.COACH,
            MembershipRole.Role.DOCTOR,
        ],
    )
    def test_les_roles_autorises_voient_le_statut(self, role):
        club = ClubFactory()
        viewer_membership = MembershipFactory(club=club)
        extra = {"is_qualified_professional": True} if role == MembershipRole.Role.DOCTOR else {}
        MembershipRoleFactory(membership=viewer_membership, role=role, **extra)
        target = MembershipFactory(club=club, status=Membership.Status.PENDING)

        assert services.can_view_pending_membership_status(
            viewer_user=viewer_membership.user, target_membership=target
        )

    def test_un_coequipier_sans_role_autorise_ne_voit_pas_le_statut(self):
        club = ClubFactory()
        viewer_membership = MembershipFactory(club=club)
        target = MembershipFactory(club=club, status=Membership.Status.PENDING)

        assert not services.can_view_pending_membership_status(
            viewer_user=viewer_membership.user, target_membership=target
        )

    def test_le_capitaine_ne_fait_pas_partie_des_roles_autorises(self):
        """Seul Pdt/VP/DS/Coach/Medecin -- le Capitaine n'est pas dans la
        liste du 10.2 n16, meme s'il occupe un role de terrain proche du
        Coach."""

        club = ClubFactory()
        viewer_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=viewer_membership, role=MembershipRole.Role.CAPTAIN)
        target = MembershipFactory(club=club, status=Membership.Status.PENDING)

        assert not services.can_view_pending_membership_status(
            viewer_user=viewer_membership.user, target_membership=target
        )

    def test_le_joueur_concerne_voit_toujours_son_propre_statut(self):
        club = ClubFactory()
        target = MembershipFactory(club=club, status=Membership.Status.PENDING)

        assert services.can_view_pending_membership_status(
            viewer_user=target.user, target_membership=target
        )
