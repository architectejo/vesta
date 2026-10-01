"""Consentement au traitement des donnees de sante (CDC 4.12, 7.5) et
consentement d'acces du President (10.2 n15) -- medical.md §4.10, §4.11."""

from __future__ import annotations

import pytest

from apps.audit.models import AuditLog
from apps.medical import services

pytestmark = pytest.mark.django_db


def test_only_player_can_give_processing_consent(ctx):
    with pytest.raises(services.MedicalPermissionError):
        services.give_processing_consent(membership=ctx.player, actor=ctx.doctor.user)


def test_give_processing_consent_is_journalized(ctx):
    record = services.give_processing_consent(membership=ctx.player, actor=ctx.player.user)
    assert record.consent_given_at is not None
    entry = AuditLog.objects.filter(action_type="medical.processing_consent.given").first()
    assert entry is not None
    assert entry.actor_id == ctx.player.user_id


def test_self_declaration_without_consent_requires_checkbox(ctx):
    with pytest.raises(services.ConsentMissingError):
        services.update_self_declaration(membership=ctx.player, actor=ctx.player.user, text="Je vais bien.")


def test_self_declaration_with_checkbox_grants_consent_and_saves(ctx):
    record = services.update_self_declaration(
        membership=ctx.player, actor=ctx.player.user, text="Je vais bien.", consent_given=True
    )
    assert record.consent_given_at is not None
    assert record.self_declaration == "Je vais bien."
    assert record.self_declaration_updated_at is not None


def test_self_declaration_log_never_contains_the_text_itself(ctx):
    services.update_self_declaration(
        membership=ctx.player, actor=ctx.player.user, text="Contenu clinique prive.", consent_given=True
    )
    entry = AuditLog.objects.filter(action_type="medical.self_declaration.updated").first()
    assert entry is not None
    assert entry.after == {"fields_changed": ["self_declaration"]}
    assert "Contenu clinique prive." not in str(entry.after)


def test_doctor_cannot_declare_on_behalf_of_player(ctx):
    with pytest.raises(services.MedicalPermissionError):
        services.update_self_declaration(membership=ctx.player, actor=ctx.doctor.user, text="x", consent_given=True)


# ---------------------------------------------------------------------------
# Acces du President (medical.md §4.11)
# ---------------------------------------------------------------------------


def test_only_player_can_grant_or_revoke_president_access(ctx):
    with pytest.raises(services.MedicalPermissionError):
        services.grant_president_access(membership=ctx.player, actor=ctx.president.user)
    with pytest.raises(services.MedicalPermissionError):
        services.revoke_president_access(membership=ctx.player, actor=ctx.president.user)


def test_grant_and_revoke_are_journalized_without_clinical_content(ctx):
    services.grant_president_access(membership=ctx.player, actor=ctx.player.user)
    services.revoke_president_access(membership=ctx.player, actor=ctx.player.user)

    granted = AuditLog.objects.filter(action_type="medical.president_access.granted").first()
    revoked = AuditLog.objects.filter(action_type="medical.president_access.revoked").first()
    assert granted is not None and revoked is not None
    assert granted.before is None and granted.after is None
    assert revoked.before is None and revoked.after is None
