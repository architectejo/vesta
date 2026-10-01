"""Serializers DRF de l'app medical (Lot 4, tache 4.2).

Convention reprise de ``apps.sport.serializers``/``apps.treasury.serializers`` :
des fonctions ``serialize_*`` pour la sortie, des classes
``rest_framework.serializers.Serializer`` pour valider la forme des
entrees (les regles elles-memes vivent dans ``apps.medical.services``,
qui refait ses propres controles -- defense en profondeur).

Regle de visibilite (CLAUDE.md section 5, consigne explicite de la
tache) : chaque fonction ``serialize_*`` ne renvoie QUE ce que le
niveau N0/N1/N2 du lecteur autorise (medical.md §2, §5.1) -- jamais
reconstruit cote vue ou interface. Les fonctions qui exposent du
contenu N2 (:func:`serialize_health_record_full`,
:func:`serialize_injury_detail`) ne sont appelees par les vues
qu'APRES un controle d'acces reussi cote service
(``apps.medical.services.view_health_record_as_*``) : elles ne
refont pas ce controle elles-memes, mais ne sont jamais exposees a un
lecteur N0/N1 par construction des vues (``apps.medical.views``).
"""

from __future__ import annotations

from rest_framework import serializers

from apps.medical import services
from apps.medical.models import HealthRecord, Injury, InjuryFollowUp

__all__ = [
    "SelfDeclarationSerializer",
    "HealthRecordUpdateSerializer",
    "FitnessUpdateSerializer",
    "InjuryReportSerializer",
    "InjuryCompleteSerializer",
    "InjuryFollowUpCreateSerializer",
    "InjuryReturnSerializer",
    "serialize_membership_brief",
    "serialize_fitness_summary",
    "serialize_fitness_list_item",
    "serialize_health_record_full",
    "serialize_injury_list_item",
    "serialize_injury_detail",
    "serialize_followup",
    "serialize_consent_status",
]


def _user_name(user) -> str:
    return f"{user.first_name} {user.last_name}".strip()


def serialize_membership_brief(membership) -> dict:
    """Identite minimale d'un joueur (jamais de donnee medicale ici) --
    meme etroitesse volontaire que ``apps.sport.serializers.serialize_membership_brief``."""

    user = membership.user
    return {
        "membership_id": membership.pk,
        "name": _user_name(user),
        "jersey_number": membership.jersey_number,
    }


def serialize_fitness_summary(membership) -> dict:
    """N1 (medical.md §5.1 point 1) : ``fitness_status``/``fitness_return_date``
    UNIQUEMENT -- point d'entree unique deja consomme par
    ``apps.sport.services.get_unfitness_reason``. Reserve a un usage direct
    de l'API medicale par un lecteur N1 (VP/DS/Coach/President sans
    consentement) qui n'accede pas a la page Medical."""

    return services.get_fitness_summary(membership)


def serialize_fitness_list_item(record: HealthRecord, *, viewer_is_full_access: bool) -> dict:
    """Ligne « Inaptes et restrictions » (medical.md §3.2). ``badge_injured``
    (« Blessé ») n'est renvoye qu'aux lecteurs N2 (§3.2, §5.1 point 5)."""

    membership = record.membership
    data = {
        **serialize_membership_brief(membership),
        "fitness_status": record.fitness_status,
        "fitness_return_date": record.fitness_return_date,
        "fitness_return_date_label": (
            services.format_date_fr(record.fitness_return_date) if record.fitness_return_date else None
        ),
    }
    if viewer_is_full_access:
        data["badge_injured"] = Injury.all_objects.filter(
            club_id=record.club_id, membership_id=membership.pk, status=Injury.Status.OPEN
        ).exists()
    return data


def serialize_health_record_full(record: HealthRecord) -> dict:
    """N2 (medical.md §4.2, §4.10) : dossier complet. N'est appelee par les
    vues qu'apres un controle d'acces reussi (voir docstring du module)."""

    membership = record.membership
    open_injuries = Injury.all_objects.filter(
        club_id=record.club_id, membership_id=membership.pk, status=Injury.Status.OPEN
    ).order_by("-reported_at")
    resolved_injuries = Injury.all_objects.filter(
        club_id=record.club_id, membership_id=membership.pk, status=Injury.Status.RESOLVED
    ).order_by("-resolved_at")

    return {
        **serialize_membership_brief(membership),
        "fitness_status": record.fitness_status,
        "fitness_return_date": record.fitness_return_date,
        "fitness_set_by": _user_name(record.fitness_set_by) if record.fitness_set_by_id else None,
        "fitness_set_at": record.fitness_set_at,
        "blood_group": record.blood_group,
        "allergies": record.allergies,
        "medical_history": record.medical_history,
        "ongoing_treatments": record.ongoing_treatments,
        "emergency_contact_name": record.emergency_contact_name,
        "emergency_contact_phone": record.emergency_contact_phone,
        "self_declaration": record.self_declaration,
        "self_declaration_updated_at": record.self_declaration_updated_at,
        "consent_given_at": record.consent_given_at,
        "open_injuries": [serialize_injury_list_item(injury) for injury in open_injuries],
        "resolved_injuries": [serialize_injury_list_item(injury) for injury in resolved_injuries[:5]],
    }


def serialize_injury_list_item(injury: Injury) -> dict:
    return {
        "id": injury.pk,
        "membership_id": injury.membership_id,
        "reported_at": injury.reported_at,
        "status": injury.status,
        "location_on_body": injury.location_on_body,
        "event_id": injury.event_id,
        "doctor_completed": injury.doctor_completed_at is not None,
    }


def serialize_followup(followup: InjuryFollowUp) -> dict:
    return {
        "id": followup.pk,
        "entry_date": followup.entry_date,
        "note": followup.note,
        "created_by": _user_name(followup.created_by),
        "created_at": followup.created_at,
    }


def serialize_injury_detail(injury: Injury) -> dict:
    """N2 (medical.md §4.3) : detail complet d'une blessure."""

    return {
        "id": injury.pk,
        "membership_id": injury.membership_id,
        "status": injury.status,
        "reported_by": _user_name(injury.reported_by),
        "reported_at": injury.reported_at,
        "event_id": injury.event_id,
        "occurred_time": injury.occurred_time,
        "occurred_minute": injury.occurred_minute,
        "circumstances": injury.circumstances,
        "location_on_body": injury.location_on_body,
        "severity": injury.severity,
        "on_site_care": injury.on_site_care,
        "referral": injury.referral,
        "estimated_days_out": injury.estimated_days_out,
        "doctor_completed_by": _user_name(injury.doctor_completed_by) if injury.doctor_completed_by_id else None,
        "doctor_completed_at": injury.doctor_completed_at,
        "resolved_by": _user_name(injury.resolved_by) if injury.resolved_by_id else None,
        "resolved_at": injury.resolved_at,
        "followups": [serialize_followup(f) for f in injury.followups.order_by("-entry_date", "-created_at")[:5]],
    }


def serialize_consent_status(record: HealthRecord | None) -> dict:
    """medical.md §4.11 : etat EFFECTIF du consentement d'acces du
    President (``can_president_read_full_record``), pas seulement la
    presence brute de ``president_access_granted_at`` (regle de la
    passation, §4.11 « nouveau — etat effectif »)."""

    if record is None:
        return {"granted": False, "granted_at": None}
    return {
        "granted": services.can_president_read_full_record(record),
        "granted_at": record.president_access_granted_at,
    }


# ---------------------------------------------------------------------------
# Entrees
# ---------------------------------------------------------------------------


class SelfDeclarationSerializer(serializers.Serializer):
    self_declaration = serializers.CharField(required=False, allow_blank=True, default="")
    consent_given = serializers.BooleanField(required=False, default=False)


class HealthRecordUpdateSerializer(serializers.Serializer):
    blood_group = serializers.ChoiceField(choices=HealthRecord.BloodGroup.choices, required=False, allow_blank=True)
    allergies = serializers.CharField(required=False, allow_blank=True)
    medical_history = serializers.CharField(required=False, allow_blank=True)
    ongoing_treatments = serializers.CharField(required=False, allow_blank=True)
    emergency_contact_name = serializers.CharField(required=False, allow_blank=True, max_length=160)
    emergency_contact_phone = serializers.CharField(required=False, allow_blank=True, max_length=30)


class FitnessUpdateSerializer(serializers.Serializer):
    fitness_status = serializers.ChoiceField(choices=HealthRecord.FitnessStatus.choices)
    fitness_return_date = serializers.DateField(required=False, allow_null=True)


class InjuryReportSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    event_id = serializers.IntegerField(required=False, allow_null=True)
    occurred_time = serializers.TimeField(required=False, allow_null=True)
    occurred_minute = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=130)
    circumstances = serializers.CharField(allow_blank=False)


class InjuryCompleteSerializer(serializers.Serializer):
    location_on_body = serializers.CharField(required=False, allow_blank=True, max_length=160)
    severity = serializers.ChoiceField(choices=Injury.Severity.choices, required=False, allow_blank=True)
    on_site_care = serializers.CharField(required=False, allow_blank=True)
    referral = serializers.ChoiceField(choices=Injury.Referral.choices, required=False, allow_blank=True)
    estimated_days_out = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=365)
    fitness_return_date = serializers.DateField(required=False, allow_null=True)


class InjuryFollowUpCreateSerializer(serializers.Serializer):
    entry_date = serializers.DateField()
    note = serializers.CharField(allow_blank=False)
    fitness_return_date = serializers.DateField(required=False, allow_null=True)


class InjuryReturnSerializer(serializers.Serializer):
    return_date = serializers.DateField()
