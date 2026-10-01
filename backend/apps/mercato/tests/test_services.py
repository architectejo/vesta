"""Tests unitaires des règles métier du mercato (CDC 4.14 ; tâche 4.4).

Règle non négociable n° 5 / 10.2 n° 30 : le blocage et le déblocage
automatique passent exclusivement par
``apps.treasury.services.is_in_good_standing``/``record_payment`` --
jamais de dette recalculée ici."""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.clubs.models import Membership
from apps.mercato import services
from apps.mercato.models import TransferOffer
from apps.mercato.tests.conftest import PIN, MercatoClubContext, make_debtor
from apps.treasury.models import Payment
from apps.treasury.services import record_payment

pytestmark = pytest.mark.django_db


def test_set_market_availability_only_by_the_player_himself(ctx: MercatoClubContext):
    services.set_market_availability(membership=ctx.player, actor=ctx.player.user, is_on_market=True)
    ctx.player.refresh_from_db()
    assert ctx.player.is_on_transfer_market is True

    with pytest.raises(services.MercatoError):
        services.set_market_availability(membership=ctx.player, actor=ctx.president.user, is_on_market=False)


def test_create_offer_requires_president_or_sports_director(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)

    with pytest.raises(services.MercatoError):
        services.create_transfer_offer(
            initiated_by=ctx.coach.user, target_club=ctx.club, target_membership=other_ctx.player, message="Rejoignez-nous"
        )

    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Rejoignez-nous"
    )
    assert offer.status == TransferOffer.Status.SENT
    assert offer.origin_club_id == other_ctx.club.id
    assert offer.target_club_id == ctx.club.id


def test_create_offer_refused_if_not_on_market(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    with pytest.raises(services.MercatoError, match="n'est plus sur le marché"):
        services.create_transfer_offer(
            initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
        )


def test_accept_offer_without_debt_completes_transfer_automatically(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )

    offer = services.respond_to_offer(offer=offer, actor=other_ctx.player.user, accept=True)

    assert offer.status == TransferOffer.Status.COMPLETED
    assert offer.quitus_file
    assert offer.completed_at is not None

    other_ctx.player.refresh_from_db()
    assert other_ctx.player.status == Membership.Status.DEPARTED
    assert other_ctx.player.left_reason == Membership.LeftReason.TRANSFER

    new_membership = Membership.all_objects.get(pk=offer.new_membership_id)
    assert new_membership.club_id == ctx.club.id
    assert new_membership.status == Membership.Status.PENDING
    assert new_membership.user_id == other_ctx.player.user_id
    assert new_membership.sponsor_id is None  # aucun parrainage requis (schema §8.1)


def test_decline_offer(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )
    offer = services.respond_to_offer(offer=offer, actor=other_ctx.player.user, accept=False)
    assert offer.status == TransferOffer.Status.DECLINED_BY_PLAYER


def test_accept_offer_with_debt_blocks_and_auto_unblocks_on_payment(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    ctype = make_debtor(other_ctx.club, other_ctx.player)

    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )
    offer = services.respond_to_offer(offer=offer, actor=other_ctx.player.user, accept=True)

    assert offer.status == TransferOffer.Status.BLOCKED_DEBT
    assert offer.debt_amount == Decimal("10.00")

    other_ctx.player.refresh_from_db()
    assert other_ctx.player.status == Membership.Status.ACTIVE  # pas encore transféré

    # Le paiement passe exclusivement par apps.treasury.services (jamais de
    # règle de dette dupliquée dans apps.mercato).
    record_payment(
        membership=other_ctx.player,
        contribution_type=ctype,
        amount=Decimal("10.00"),
        method=Payment.Method.CASH,
        paid_on=timezone.now().date(),
        recorded_by=other_ctx.treasurer.user,
        pin=PIN,
    )

    # 10.2 n° 30 : déblocage automatique, sans nouvelle acceptation du joueur.
    updated = services.recheck_transfers_for_membership(other_ctx.player)
    assert len(updated) == 1
    offer.refresh_from_db()
    assert offer.status == TransferOffer.Status.COMPLETED
    other_ctx.player.refresh_from_db()
    assert other_ctx.player.status == Membership.Status.DEPARTED


def test_recheck_all_blocked_transfers_cron_sweep(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    ctype = make_debtor(other_ctx.club, other_ctx.player)
    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )
    offer = services.respond_to_offer(offer=offer, actor=other_ctx.player.user, accept=True)
    assert offer.status == TransferOffer.Status.BLOCKED_DEBT

    # Toujours bloqué : le balayage ne débloque rien tant que la dette dure.
    assert services.recheck_all_blocked_transfers() == 0

    record_payment(
        membership=other_ctx.player,
        contribution_type=ctype,
        amount=Decimal("10.00"),
        method=Payment.Method.CASH,
        paid_on=timezone.now().date(),
        recorded_by=other_ctx.treasurer.user,
        pin=PIN,
    )
    assert services.recheck_all_blocked_transfers() == 1


def test_automatic_unblock_writes_no_audit_entry_without_a_real_actor(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    """Convention déjà établie ailleurs dans le projet (voir docstring de
    ``apps.mercato.services``) : une transition sans acteur humain réel
    n'écrit aucune entrée de journal."""

    from apps.audit.models import AuditLog

    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    ctype = make_debtor(other_ctx.club, other_ctx.player)
    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )
    offer = services.respond_to_offer(offer=offer, actor=other_ctx.player.user, accept=True)
    record_payment(
        membership=other_ctx.player,
        contribution_type=ctype,
        amount=Decimal("10.00"),
        method=Payment.Method.CASH,
        paid_on=timezone.now().date(),
        recorded_by=other_ctx.treasurer.user,
        pin=PIN,
    )
    count_before = AuditLog.objects.filter(action_type="mercato.transfer_offer.completed").count()
    services.recheck_transfers_for_membership(other_ctx.player)
    count_after = AuditLog.objects.filter(action_type="mercato.transfer_offer.completed").count()
    assert count_after == count_before


def _quitus_text(offer: TransferOffer) -> str:
    offer.quitus_file.open("rb")
    try:
        content = offer.quitus_file.read()
    finally:
        offer.quitus_file.close()
    assert content.startswith(b"%PDF")
    # Canevas sans compression (pageCompression=0) : permet une assertion
    # directe sur le flux de contenu (`apps.core.pdf.NumberedDocumentCanvas`).
    return content.decode("latin-1")


class TestQuitusPdfContent:
    """Gabarit valide docs/annexes/modeles-documents.md §2, §6.2 : aucune
    reference au cahier des charges, cadre d'attestation avec date de
    verification, date etablie dans le fuseau du club d'origine."""

    def test_quitus_never_contains_the_literal_cdc_reference(self, ctx, other_ctx):
        services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
        offer = services.create_transfer_offer(
            initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
        )
        offer = services.respond_to_offer(offer=offer, actor=other_ctx.player.user, accept=True)

        text = _quitus_text(offer)
        assert "CDC" not in text
        # L'objet meme du document : le badge « En ordre » (§2.3 ligne 11)
        # et la mention de verification automatique doivent y figurer.
        assert "En ordre" in text
        assert "Solde v" in text  # « Solde vérifié... » (« é » échappé en octal par reportlab)

    def test_debt_check_and_quitus_date_use_the_origin_clubs_local_date_not_utc(self, ctx, other_ctx):
        """CLAUDE.md §7 : ``_evaluate_debt_and_progress`` doit évaluer et
        imprimer la date du jour au club d'origine, pas la date UTC de
        ``now`` (docs/annexes/modeles-documents.md §6.2, remarque hors
        gabarit)."""

        services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
        offer = services.create_transfer_offer(
            initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
        )

        # 23h30 UTC un jour donne = 00h30 le lendemain a Kinshasa (UTC+1,
        # sans heure d'ete -- fuseau par defaut de `build_mercato_club_context`).
        utc_instant = datetime.datetime(2026, 9, 27, 23, 30, tzinfo=datetime.timezone.utc)
        expected_local_date = datetime.date(2026, 9, 28)
        assert expected_local_date != utc_instant.date()

        with patch("apps.treasury.services.is_in_good_standing") as mocked:
            mocked.return_value = (True, None, "")
            offer = services.respond_to_offer(offer=offer, actor=other_ctx.player.user, accept=True, now=utc_instant)

        called_kwargs = mocked.call_args.kwargs
        assert called_kwargs["at_date"] == expected_local_date

        assert offer.status == TransferOffer.Status.COMPLETED
        text = _quitus_text(offer)
        assert "28/09/2026" in text
        assert "27/09/2026" not in text
