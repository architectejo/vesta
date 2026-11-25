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
from apps.mercato.tests.conftest import MercatoClubContext, make_debtor
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
    )
    assert services.recheck_all_blocked_transfers() == 1


def test_automatic_unblock_writes_audit_entry_with_system_actor_and_auto_post(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    """D16 (règle 6) : le déblocage automatique est journalisé avec l'acteur Système ;
    D7 (CDC 4.14 étape 6) : une publication automatique apparaît sur le fil du nouveau club."""

    from apps.audit.models import AuditLog
    from apps.core.reserved_accounts import SYSTEM_ACTOR_EMAIL
    from apps.social.models import Post

    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    ctype = make_debtor(other_ctx.club, other_ctx.player)
    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )
    offer = services.respond_to_offer(offer=offer, actor=other_ctx.player.user, accept=True)
    assert offer.status == TransferOffer.Status.BLOCKED_DEBT
    record_payment(
        membership=other_ctx.player,
        contribution_type=ctype,
        amount=Decimal("10.00"),
        method=Payment.Method.CASH,
        paid_on=timezone.now().date(),
        recorded_by=other_ctx.treasurer.user,
    )
    services.recheck_transfers_for_membership(other_ctx.player)
    entries = AuditLog.objects.filter(action_type="mercato.transfer_offer.completed")
    assert entries.count() == 1
    assert entries.first().actor.email == SYSTEM_ACTOR_EMAIL
    posts = Post.all_objects.filter(club=ctx.club, post_kind=Post.PostKind.AUTO_TRANSFER)
    assert posts.count() == 1
    assert other_ctx.player.user.last_name in posts.first().body


def test_manual_transfer_publishes_auto_post_once(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    from apps.social.models import Post

    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )
    services.respond_to_offer(offer=offer, actor=other_ctx.player.user, accept=True)
    assert Post.all_objects.filter(club=ctx.club, post_kind=Post.PostKind.AUTO_TRANSFER).count() == 1
