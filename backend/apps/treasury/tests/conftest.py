"""Fixtures communes aux tests de la tresorerie (tache 1.4b).

Chaque club de test dispose de ses parametres (`ClubSettings` : devise,
fuseau), d'un President, d'un Tresorier, d'un Tresorier adjoint, d'un
Vice-president et d'un simple joueur (plus aucun code PIN). Le nouveau joueur « En attente » (`pending_member`) a un parrain
inscrit (CDC 4.3, etape 1).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import ClubSettingsFactory, MembershipFactory, MembershipRoleFactory
from apps.treasury.tests.factories import MembershipFeeTypeFactory

# Valeurs « sentinelles » conservees : servent uniquement a verifier qu'un
# champ ``pin`` encore transmis est ignore et n'apparait jamais dans une
# reponse ni au journal. Depuis la decision client du 11/10/2026
# (CLAUDE.md regle 7), aucun compte n'a de PIN.
PIN = "2468"
WRONG_PIN = "1357"


def assert_logged_by(action_type: str, user, *, club=None, obj=None, count: int = 1):
    """L'action sensible est journalisee avec son AUTEUR (CLAUDE.md regles 6
    et 7) : c'est lui, et non plus un PIN, qui garantit la tracabilite.
    ``obj`` restreint aux entrees de cet objet."""

    from apps.audit.models import AuditLog

    entries = AuditLog.objects.filter(action_type=action_type)
    if club is not None:
        entries = entries.filter(club=club)
    if obj is not None:
        entries = entries.filter(object_type=type(obj).__name__, object_id=str(obj.pk))
    assert entries.count() == count, f"{action_type} : {entries.count()} entree(s) au lieu de {count}"
    assert set(entries.values_list("actor_id", flat=True)) == {user.pk}
    return entries


def past_day(days: int = 2) -> datetime.date:
    """Date de paiement passee, sans ambiguite de fuseau (marge de 2 jours)."""

    return timezone.now().date() - datetime.timedelta(days=days)


def make_member(club, *, roles=(), status=Membership.Status.ACTIVE, sponsor=None):
    user = UserFactory()
    membership = MembershipFactory(club=club, user=user, status=status, sponsor=sponsor)
    for role in roles:
        MembershipRoleFactory(membership=membership, club=club, role=role, appointed_at=timezone.now())
    return membership


@dataclass
class ClubContext:
    club: object
    president: Membership
    vice_president: Membership
    treasurer: Membership
    assistant_treasurer: Membership
    player: Membership
    pending_member: Membership


def build_club_context(currency="USD") -> ClubContext:
    club = ClubSettingsFactory(currency=currency, timezone="Africa/Kinshasa").club
    president = make_member(club, roles=[MembershipRole.Role.PRESIDENT])
    player = make_member(club)
    return ClubContext(
        club=club,
        president=president,
        vice_president=make_member(club, roles=[MembershipRole.Role.VICE_PRESIDENT]),
        treasurer=make_member(club, roles=[MembershipRole.Role.TREASURER]),
        assistant_treasurer=make_member(club, roles=[MembershipRole.Role.ASSISTANT_TREASURER]),
        player=player,
        pending_member=make_member(club, status=Membership.Status.PENDING, sponsor=player),
    )


@pytest.fixture
def ctx(db) -> ClubContext:
    return build_club_context()


@pytest.fixture
def other_ctx(db) -> ClubContext:
    return build_club_context(currency="CDF")


@pytest.fixture
def fee_type(ctx):
    return MembershipFeeTypeFactory(club=ctx.club, created_by=ctx.president.user)


@pytest.fixture
def other_fee_type(other_ctx):
    return MembershipFeeTypeFactory(club=other_ctx.club, created_by=other_ctx.president.user)
