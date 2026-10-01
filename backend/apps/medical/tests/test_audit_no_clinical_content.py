"""CLAUDE.md regle n6/n11 ; CDC 5.2 « Medical » : le contenu medical n'est
jamais copie dans le journal. Verifie a la fois le garde-fou generique
(``apps.audit.services``, deja teste ailleurs) et son application reelle
par chaque service metier de ce module."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import MedicalContentInLogError
from apps.medical import services
from apps.medical.models import Injury

pytestmark = pytest.mark.django_db


def test_log_action_rejects_clinical_keys_for_medical_actions(ctx):
    injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")
    with pytest.raises(MedicalContentInLogError):
        services.log_action(
            actor=ctx.doctor.user,
            club=ctx.club,
            action_type="medical.injury.completed",
            obj=injury,
            after={"circumstances": "Ne doit jamais etre journalise."},
        )


def test_injury_reported_log_has_no_circumstances(ctx):
    injury = services.report_injury(
        membership=ctx.player, actor=ctx.coach.user, circumstances="Contenu clinique tres prive."
    )
    entry = AuditLog.objects.get(action_type="medical.injury.reported", object_id=str(injury.pk))
    assert "circumstances" not in (entry.after or {})
    assert "Contenu clinique tres prive." not in str(entry.before) + str(entry.after)


def test_injury_completed_log_has_no_clinical_values_as_keys(ctx):
    injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")
    services.give_processing_consent(membership=ctx.player, actor=ctx.player.user)
    injury = services.complete_injury_report(
        injury=injury,
        actor=ctx.doctor.user,
        location_on_body="Genou gauche, ligament croise",
        severity=Injury.Severity.SEVERE,
    )
    entry = AuditLog.objects.get(action_type="medical.injury.completed", object_id=str(injury.pk))
    assert "location_on_body" not in (entry.after or {})
    assert "Genou gauche, ligament croise" not in str(entry.after)


def test_followup_note_is_never_logged(ctx):
    injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")
    services.give_processing_consent(membership=ctx.player, actor=ctx.player.user)
    followup = services.add_injury_followup(
        injury=injury, actor=ctx.doctor.user, entry_date=timezone.localdate(), note="Details cliniques confidentiels."
    )
    entry = AuditLog.objects.get(action_type="medical.injury.followup_added", object_id=str(followup.pk))
    assert entry.before is None
    assert entry.after is None


def test_health_record_update_log_only_lists_field_names(ctx):
    services.give_processing_consent(membership=ctx.player, actor=ctx.player.user)
    record = services.update_health_record(
        membership=ctx.player,
        actor=ctx.doctor.user,
        data={"allergies": "Penicilline", "blood_group": "O+"},
    )
    entry = AuditLog.objects.get(action_type="medical.record.updated", object_id=str(record.pk))
    assert set(entry.after["fields_changed"]) == {"allergies", "blood_group"}
    assert "Penicilline" not in str(entry.after)


def test_fitness_updated_log_only_contains_allowed_n1_fields(ctx):
    record = services.update_fitness(
        membership=ctx.player, actor=ctx.doctor.user, status="fit_with_restriction"
    )
    entry = AuditLog.objects.get(action_type="medical.fitness.updated", object_id=str(record.pk))
    assert set(entry.after.keys()) == {"fitness_status", "fitness_return_date"}
