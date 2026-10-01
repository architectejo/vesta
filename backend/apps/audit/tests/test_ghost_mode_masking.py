"""Tests du masquage Ghost Mode centralise (CDC 5.4 ; tache 1.8).

Sources : CDC 5.4 (« Systeme Vesta » cote club, identite reelle conservee
dans le journal) ; docs/lot0/schema-donnees.md §12.1.
"""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.audit.services import GHOST_ACTOR_DISPLAY_NAME, create_audit_log, get_actor_display_name
from apps.clubs.tests.factories import ClubFactory, MembershipFactory


@pytest.mark.django_db
class TestGetActorDisplayName:
    def test_action_normale_affiche_toujours_l_identite_reelle(self):
        membership = MembershipFactory(status="active")
        entry = create_audit_log(
            actor=membership.user,
            club=membership.club,
            action_type="role.appointed",
            object_type="MembershipRole",
            object_id=1,
            acted_as_ghost=False,
        )

        reader = UserFactory()
        display = get_actor_display_name(entry, reader=reader)

        assert display == f"{membership.user.first_name} {membership.user.last_name}".strip()
        assert display != GHOST_ACTOR_DISPLAY_NAME

    def test_ghost_mode_masque_l_identite_pour_un_lecteur_du_club(self):
        superuser = SuperuserFactory()
        club = ClubFactory()
        entry = create_audit_log(
            actor=superuser,
            club=club,
            action_type="treasury.payment.corrected",
            object_type="Payment",
            object_id=1,
            acted_as_ghost=True,
            support_session_id="42",
        )

        club_member = UserFactory()
        display = get_actor_display_name(entry, reader=club_member)

        assert display == GHOST_ACTOR_DISPLAY_NAME

    def test_ghost_mode_ne_masque_jamais_pour_un_superuser_lecteur(self):
        """CDC 5.4 : « Le journal conserve l'identite reelle du Superuser » --
        le masquage ne s'applique qu'a la vue cote club, jamais a la vue
        Superuser (CDC 5.5)."""

        superuser = SuperuserFactory()
        club = ClubFactory()
        entry = create_audit_log(
            actor=superuser,
            club=club,
            action_type="treasury.payment.corrected",
            object_type="Payment",
            object_id=1,
            acted_as_ghost=True,
            support_session_id="42",
        )

        other_superuser = SuperuserFactory()
        display = get_actor_display_name(entry, reader=other_superuser)

        assert display == f"{superuser.first_name} {superuser.last_name}".strip()

    def test_acteur_reel_toujours_conserve_en_base_meme_masque_a_l_affichage(self):
        """Le masquage n'est qu'un affichage : `AuditLog.actor_id` reste
        toujours l'identite reelle (CDC 5.4)."""

        superuser = SuperuserFactory()
        club = ClubFactory()
        entry = create_audit_log(
            actor=superuser,
            club=club,
            action_type="treasury.payment.corrected",
            object_type="Payment",
            object_id=1,
            acted_as_ghost=True,
            support_session_id="42",
        )

        assert entry.actor_id == superuser.id
