"""Tests de la journalisation des actions metier de l'app clubs (tache 1.6, 1.6t).

Sources : CLAUDE.md regle n6 ; CDC 5.2 « Club et roles » -- « modification
du club, nomination, revocation, ajout et depart de joueur, import ».
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import SuperuserFactory
from apps.audit.models import AuditLog
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import (
    ImportBatchFactory,
    MembershipFactory,
    MembershipRoleFactory,
    PresidencyTransferFactory,
)


@pytest.mark.django_db
class TestJournalisationRoles:
    def test_nomination_dun_role_cree_une_entree_avec_avant_apres(self):
        role = MembershipRoleFactory(role=MembershipRole.Role.COACH)

        entry = AuditLog.objects.get(action_type="role.appointed", object_id=str(role.pk))
        assert entry.before is None
        assert entry.after["role"] == MembershipRole.Role.COACH
        assert entry.club_id == role.club_id
        assert entry.actor_id == role.appointed_by_id

    def test_revocation_dun_role_cree_une_entree_avec_etat_avant(self):
        superuser = SuperuserFactory()
        role = MembershipRoleFactory(role=MembershipRole.Role.CAPTAIN)

        role.revoked_by = superuser
        role.revoked_at = timezone.now()
        role.revoked_reason = "Depart du club"
        role.save()

        entry = AuditLog.objects.get(action_type="role.revoked", object_id=str(role.pk))
        assert entry.before["revoked_at"] is None
        assert entry.after["revoked_at"] is not None
        assert entry.actor_id == superuser.id


@pytest.mark.django_db
class TestJournalisationAdhesions:
    def test_ajout_dun_joueur_cree_une_entree(self):
        membership = MembershipFactory(status=Membership.Status.ACTIVE)

        entry = AuditLog.objects.get(action_type="membership.created", object_id=str(membership.pk))
        assert entry.after["status"] == Membership.Status.ACTIVE
        assert entry.actor_id == membership.added_by_id
        assert entry.club_id == membership.club_id

    def test_depart_dun_joueur_cree_une_entree_avec_etat_avant(self):
        membership = MembershipFactory(status=Membership.Status.ACTIVE)

        membership.status = Membership.Status.DEPARTED
        membership.left_on = timezone.now().date()
        membership.left_reason = Membership.LeftReason.RESIGNATION
        membership.left_by = membership.added_by
        membership.save()

        entry = AuditLog.objects.get(action_type="membership.departed", object_id=str(membership.pk))
        assert entry.before["status"] == Membership.Status.ACTIVE
        assert entry.after["status"] == Membership.Status.DEPARTED

    def test_depart_dun_joueur_journalise_le_bon_acteur(self):
        """Corrige un bug reel remonte par test-engineer pendant le Lot 1.

        CDC 5.1 : « Acteur : Identifiant reel de l'utilisateur [...] a
        l'origine de l'action. » `apps.clubs.signals._log_membership`
        journalisait auparavant systematiquement `membership.added_by`
        comme acteur du depart, quel que soit qui avait reellement
        constate/traite le depart -- une fausse attribution positive : le
        journal designait une personne reelle et identifiable (le
        recruteur d'origine, potentiellement parti du club depuis) comme
        ayant realise une action qu'elle n'avait probablement pas
        realisee. Un risque concret en cas d'enquete disciplinaire ou de
        controle du journal (CDC 5.5).

        Correction : `Membership.left_by` porte desormais l'acteur reel
        du depart (distinct de `added_by`, qui reste le recruteur
        d'origine). `services.log_membership_departed` exige cet acteur
        explicitement -- aucun repli silencieux sur `added_by`.
        """

        recruteur_dorigine = MembershipFactory(status=Membership.Status.ACTIVE).user
        membre_du_bureau = MembershipFactory(status=Membership.Status.ACTIVE).user

        # Sans acteur explicite (`left_by` non renseigne), le passage en
        # DEPARTED doit echouer clairement plutot que de retomber sur
        # `added_by`.
        membership_sans_acteur = MembershipFactory(
            status=Membership.Status.ACTIVE, added_by=recruteur_dorigine
        )
        membership_sans_acteur.status = Membership.Status.DEPARTED
        membership_sans_acteur.left_on = timezone.now().date()
        membership_sans_acteur.left_reason = Membership.LeftReason.RESIGNATION
        with pytest.raises(ValueError):
            membership_sans_acteur.save()

        # Avec un acteur explicite (un membre du bureau totalement
        # distinct du recruteur d'origine), le journal doit attribuer le
        # depart a cette personne, jamais a `added_by`.
        membership = MembershipFactory(
            status=Membership.Status.ACTIVE, added_by=recruteur_dorigine
        )
        membership.status = Membership.Status.DEPARTED
        membership.left_on = timezone.now().date()
        membership.left_reason = Membership.LeftReason.RESIGNATION
        membership.left_by = membre_du_bureau
        membership.save()

        entry = AuditLog.objects.get(action_type="membership.departed", object_id=str(membership.pk))
        assert entry.actor_id == membre_du_bureau.id
        assert entry.actor_id != recruteur_dorigine.id


@pytest.mark.django_db
def test_import_batch_cree_une_entree():
    batch = ImportBatchFactory()

    entry = AuditLog.objects.get(action_type="clubs.import.created", object_id=str(batch.pk))
    assert entry.actor_id == batch.imported_by_id
    assert entry.club_id == batch.club_id


@pytest.mark.django_db
def test_passation_de_presidence_cree_une_entree():
    transfer = PresidencyTransferFactory()

    entry = AuditLog.objects.get(
        action_type="clubs.presidency_transfer.completed", object_id=str(transfer.pk)
    )
    assert entry.actor_id == transfer.from_membership.user_id
    assert entry.acted_as_ghost is False


@pytest.mark.django_db
def test_passation_de_presidence_par_superuser_est_journalisee_en_ghost_mode():
    """`reason` explicite depuis la tache 1.5 (CDC 2.5, Ghost Mode) :
    une intervention Superuser exige desormais un motif ecrit
    (`PresidencyTransfer.clean()`), au meme titre que toute intervention
    Ghost Mode (« bouton Intervenir sur ce club avec un motif obligatoire »).
    Ce test, ecrit avant cette regle (tache 1.6), doit fournir ce motif
    pour continuer a passer -- comportement volontairement plus strict,
    pas une regression."""

    superuser = SuperuserFactory()
    transfer = PresidencyTransferFactory(
        method="superuser_override",
        superuser=superuser,
        reason="Blocage de gouvernance signale par le club (CDC 2.3).",
    )

    entry = AuditLog.objects.get(
        action_type="clubs.presidency_transfer.completed", object_id=str(transfer.pk)
    )
    # Ghost Mode (CDC 5.4) : le journal conserve l'identite reelle du Superuser.
    assert entry.actor_id == superuser.id
    assert entry.acted_as_ghost is True
