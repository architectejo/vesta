"""Visibilite N2 (medical.md §2, schema §6) : ``can_president_read_full_record``,
``has_full_record_access``, et les consultations journalisees
(``view_health_record_as_*``)."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.clubs.tests.factories import PresidencyTransferFactory
from apps.medical import services

pytestmark = pytest.mark.django_db


def test_no_consent_means_no_access(ctx):
    assert services.has_full_record_access(viewer=ctx.president.user, membership=ctx.player) is False


def test_doctor_always_has_full_access(ctx):
    assert services.has_full_record_access(viewer=ctx.doctor.user, membership=ctx.player) is True


def test_player_has_full_access_to_self(ctx):
    assert services.has_full_record_access(viewer=ctx.player.user, membership=ctx.player) is True


def test_president_has_access_after_consent(ctx):
    services.grant_president_access(membership=ctx.player, actor=ctx.player.user)
    assert services.has_full_record_access(viewer=ctx.president.user, membership=ctx.player) is True


def test_president_access_is_scoped_to_one_player(ctx):
    services.grant_president_access(membership=ctx.player, actor=ctx.player.user)
    assert services.has_full_record_access(viewer=ctx.president.user, membership=ctx.other_player) is False


def test_revocation_cuts_access_immediately(ctx):
    services.grant_president_access(membership=ctx.player, actor=ctx.player.user)
    services.revoke_president_access(membership=ctx.player, actor=ctx.player.user)
    assert services.has_full_record_access(viewer=ctx.president.user, membership=ctx.player) is False


def test_re_grant_after_revocation_restores_access(ctx):
    services.grant_president_access(membership=ctx.player, actor=ctx.player.user)
    services.revoke_president_access(membership=ctx.player, actor=ctx.player.user)
    services.grant_president_access(membership=ctx.player, actor=ctx.player.user)
    assert services.has_full_record_access(viewer=ctx.president.user, membership=ctx.player) is True


def test_presidency_transfer_does_not_carry_consent_to_new_president(ctx):
    """CLAUDE.md regle n11, 10.2 n15 : le consentement est donne a la
    FONCTION de President, pas a la personne -- une passation ne le
    transfere jamais (schema §6)."""

    services.grant_president_access(membership=ctx.player, actor=ctx.player.user)
    assert services.has_full_record_access(viewer=ctx.president.user, membership=ctx.player) is True

    new_president = ctx.other_player  # simule un nouveau titulaire quelconque
    PresidencyTransferFactory(
        club=ctx.club,
        from_membership=ctx.president,
        to_membership=new_president,
        transferred_at=timezone.now(),
    )

    # L'ancien President n'a plus le role -- verifie surtout la regle de
    # DONNEES : le consentement existant ne s'applique plus apres la
    # passation, meme pour un acteur qui porterait a nouveau le role.
    record = services.get_health_record(ctx.player)
    assert services.can_president_read_full_record(record) is False


def test_new_consent_after_transfer_is_valid(ctx):
    PresidencyTransferFactory(
        club=ctx.club,
        from_membership=ctx.president,
        to_membership=ctx.other_player,
        transferred_at=timezone.now() - datetime.timedelta(days=1),
    )
    services.grant_president_access(membership=ctx.player, actor=ctx.player.user)
    record = services.get_health_record(ctx.player)
    assert services.can_president_read_full_record(record) is True


def test_view_health_record_as_doctor_logs_without_clinical_content(ctx):
    record = services.view_health_record_as_doctor(membership=ctx.player, actor=ctx.doctor.user)
    entry = AuditLog.objects.filter(action_type="medical.record.viewed", object_id=str(record.pk)).first()
    assert entry is not None
    assert entry.before is None
    assert entry.after is None


def test_view_health_record_as_doctor_forbidden_for_coach(ctx):
    with pytest.raises(services.MedicalPermissionError):
        services.view_health_record_as_doctor(membership=ctx.player, actor=ctx.coach.user)


def test_view_health_record_as_player_forbidden_for_other_player(ctx):
    with pytest.raises(services.MedicalPermissionError):
        services.view_health_record_as_player(membership=ctx.player, actor=ctx.other_player.user)


def test_view_health_record_as_president_forbidden_without_consent(ctx):
    with pytest.raises(services.MedicalPermissionError):
        services.view_health_record_as_president(membership=ctx.player, actor=ctx.president.user)


def test_view_health_record_as_president_logs_consultation(ctx):
    services.grant_president_access(membership=ctx.player, actor=ctx.player.user)
    record = services.view_health_record_as_president(membership=ctx.player, actor=ctx.president.user)
    entry = AuditLog.objects.filter(
        action_type="medical.record.viewed_by_president", object_id=str(record.pk)
    ).first()
    assert entry is not None


def test_fitness_summary_shape_is_identical_with_or_without_record(ctx):
    summary_without = services.get_fitness_summary(ctx.player)
    services.grant_president_access(membership=ctx.other_player, actor=ctx.other_player.user)
    summary_with = services.get_fitness_summary(ctx.other_player)

    assert set(summary_without.keys()) == set(summary_with.keys()) == {"fitness_status", "fitness_return_date"}
