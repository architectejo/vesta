"""Etancheite entre clubs (CLAUDE.md regles n8/n9 ; CDC 6.3 ; schema-treasury.md §1.2)."""

from __future__ import annotations

import pytest

from apps.clubs.models import MembershipApplication
from apps.clubs.tests.factories import MembershipApplicationFactory
from apps.core.tenant import NoActiveClubError, TenantMismatchError, active_club
from apps.treasury import services
from apps.treasury.models import ContributionType, ContributionTypeRate, Payment, PaymentReversal, Transaction
from apps.treasury.tests.conftest import PIN, past_day

pytestmark = pytest.mark.django_db


def pay(ctx, membership=None, validated_by=None):
    return services.record_membership_fee_payment(
        membership=membership or ctx.pending_member,
        amount="5",
        method="cash",
        paid_on=past_day(),
        validated_by=(validated_by or ctx.treasurer).user,
        pin=PIN,
    )


def test_lecture_sans_club_actif_refusee(ctx, fee_type):
    pay(ctx)
    for model in (ContributionType, Payment, Transaction, PaymentReversal):
        with pytest.raises(NoActiveClubError):
            list(model.objects.all())


def test_lecture_scopee_au_club_actif(ctx, fee_type, other_ctx, other_fee_type):
    pa = pay(ctx)
    pb = pay(other_ctx)
    with active_club(ctx.club):
        assert list(Payment.objects.all()) == [pa]
        assert list(Transaction.objects.all()) == [pa.transaction]
        assert list(ContributionType.objects.all()) == [fee_type]
    with active_club(other_ctx.club):
        assert list(Payment.objects.all()) == [pb]


def test_tresorier_du_club_a_ne_peut_encaisser_pour_un_joueur_du_club_b(ctx, fee_type, other_ctx, other_fee_type):
    with pytest.raises(services.TreasuryPermissionError):
        pay(other_ctx, validated_by=ctx.treasurer)
    assert not Payment.all_objects.exists()


def test_ecriture_dans_un_autre_club_que_le_club_actif_refusee(ctx, fee_type, other_ctx, other_fee_type):
    with active_club(ctx.club):
        with pytest.raises(TenantMismatchError):
            pay(other_ctx)
    assert not Payment.all_objects.exists()
    assert not Transaction.all_objects.exists()


def test_suppression_type_hors_du_club_actif_refusee(ctx, other_ctx):
    foreign_type = services.create_contribution_type(
        club=other_ctx.club,
        created_by=other_ctx.president.user,
        name="Adhesion autre club",
        nature=ContributionType.Nature.MANDATORY,
        periodicity=ContributionType.Periodicity.ONE_OFF,
        amount="5",
        is_membership_fee=True,
    )

    with active_club(ctx.club):
        with pytest.raises(TenantMismatchError):
            services.delete_contribution_type(
                contribution_type=foreign_type, deleted_by=other_ctx.president.user
            )

    assert ContributionType.all_objects.filter(pk=foreign_type.pk).exists()
    assert ContributionTypeRate.all_objects.filter(contribution_type=foreign_type).exists()


def test_ecriture_dans_le_club_actif_acceptee(ctx, fee_type):
    with active_club(ctx.club):
        payment = pay(ctx)
    assert payment.pk


def test_president_d_un_autre_club_ne_peut_approuver_une_annulation(ctx, fee_type, other_ctx):
    reversal = services.request_payment_reversal(
        payment=pay(ctx), reason="Erreur", requested_by=ctx.treasurer.user
    )
    with pytest.raises(services.TreasuryPermissionError):
        services.approve_payment_reversal(reversal=reversal, approved_by=other_ctx.president.user, pin=PIN)


def test_type_de_cotisation_d_un_autre_club_refuse_par_le_modele(ctx, other_ctx, other_fee_type):
    from django.core.exceptions import ValidationError
    from django.utils import timezone

    payment = Payment(
        club=ctx.club, membership=ctx.pending_member, contribution_type=other_fee_type,
        amount="5.00", currency="USD", method=Payment.Method.CASH, paid_on=past_day(),
        source=Payment.Source.TREASURER_ENTRY, submitted_by=ctx.treasurer.user, submitted_at=timezone.now(),
    )
    with pytest.raises(ValidationError):
        payment.save()


class TestLienDossierAdhesion:
    """Champ `MembershipApplication.membership_fee_payment` (migration additive 1.4b)."""

    def test_le_dossier_reference_le_paiement(self, ctx, fee_type):
        payment = pay(ctx)
        application = MembershipApplicationFactory(membership=ctx.pending_member, club=ctx.club)
        application.membership_fee_payment = payment
        application.save()
        application.refresh_from_db()
        assert application.membership_fee_payment_id == payment.pk

    def test_paiement_d_un_autre_club_refuse(self, ctx, fee_type, other_ctx, other_fee_type):
        from django.core.exceptions import ValidationError

        foreign = pay(other_ctx)
        application = MembershipApplicationFactory(membership=ctx.pending_member, club=ctx.club)
        application.membership_fee_payment = foreign
        with pytest.raises(ValidationError):
            application.save()

    def test_paiement_d_un_autre_joueur_refuse(self, ctx, fee_type):
        from django.core.exceptions import ValidationError

        someone_else = pay(ctx, membership=ctx.player)
        application = MembershipApplicationFactory(membership=ctx.pending_member, club=ctx.club)
        application.membership_fee_payment = someone_else
        with pytest.raises(ValidationError):
            application.save()

    def test_paiement_reference_par_un_dossier_ne_peut_etre_supprime(self, ctx, fee_type):
        payment = pay(ctx)
        MembershipApplicationFactory(membership=ctx.pending_member, club=ctx.club, membership_fee_payment=payment)
        assert MembershipApplication.all_objects.filter(membership_fee_payment=payment).exists()
