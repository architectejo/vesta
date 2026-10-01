"""Outils de la revue indépendante des tests dépenses / assistance sociale.

Complète ``expense_helpers`` sans le modifier : membres portant les fonctions
absentes de la fixture ``ctx`` (DS, Intendant, Coach, Capitaine, Médecin,
recruteur, joueur parti), horloge simulée et contrôle du journal.
"""

from __future__ import annotations

import datetime
import io
import json
from dataclasses import dataclass

import pytest
from django.utils import timezone as django_timezone
from PIL import Image

from apps.audit.models import AuditLog
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import MembershipRoleFactory
from apps.treasury.tests.conftest import make_member

UTC = datetime.timezone.utc


@dataclass
class Staff:
    """Membres d'un club dont la fonction n'a AUCUN droit sur les dépenses."""

    coach: Membership
    captain: Membership
    doctor: Membership
    recruiter: Membership
    departed: Membership
    sports_director_and_steward: Membership

    def all(self) -> dict[str, Membership]:
        return dict(self.__dict__)


def _make_doctor(club) -> Membership:
    # La nomination du Médecin exige un choix explicite (CDC 10.2 n° 17).
    membership = make_member(club)
    MembershipRoleFactory(
        membership=membership,
        club=club,
        role=MembershipRole.Role.DOCTOR,
        appointed_at=django_timezone.now(),
        is_qualified_professional=True,
    )
    return membership


def build_staff(club) -> Staff:
    R = MembershipRole.Role
    return Staff(
        coach=make_member(club, roles=[R.COACH]),
        captain=make_member(club, roles=[R.CAPTAIN]),
        doctor=_make_doctor(club),
        recruiter=make_member(club, roles=[R.PLAYER_RECRUITER]),
        departed=make_member(club, status=Membership.Status.DEPARTED),
        # Cumul de deux fonctions sans droit sur les dépenses : les droits restent nuls (union vide).
        sports_director_and_steward=make_member(club, roles=[R.SPORTS_DIRECTOR, R.STEWARD]),
    )


@pytest.fixture
def staff(ctx) -> Staff:
    return build_staff(ctx.club)


@pytest.fixture
def other_staff(other_ctx) -> Staff:
    return build_staff(other_ctx.club)


@pytest.fixture
def set_now(monkeypatch):
    """Fige ``django.utils.timezone.now`` (pas de freezegun dans le projet)."""

    def _set(moment: datetime.datetime):
        assert moment.tzinfo is not None
        monkeypatch.setattr(django_timezone, "now", lambda: moment)

    return _set


def utc(year, month, day, hour=12, minute=0) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour, minute, tzinfo=UTC)


def revoke_role(membership: Membership, role: str) -> None:
    MembershipRole.all_objects.filter(membership=membership, role=role, revoked_at__isnull=True).update(
        revoked_at=django_timezone.now()
    )


def treasury_logs(club=None):
    queryset = AuditLog.objects.filter(action_type__startswith="treasury.")
    if club is not None:
        queryset = queryset.filter(club=club)
    return queryset.order_by("pk")


def walk_keys(value):
    """Toutes les clés (récursivement) d'un contenu JSON."""

    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from walk_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from walk_keys(item)


def dump(value) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def png_bytes(size=(20, 20), color=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_bytes(size=(20, 20)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()
