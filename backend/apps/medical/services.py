"""Regles metier de l'app medical (Lot 4, tache 4.2).

Sources : CDC 4.12 (en entier), 2.4 (matrice), 6.7, 7.5, 10.2 n15/n16/n17 ;
docs/lot0/schema-donnees.md §6 ; docs/ecrans/medical.md (fait reference
pour tous les textes et regles d'affichage, §0). CLAUDE.md regles n1, n5,
n6, n8, n9, n11.

Convention (meme principe que ``apps.sport.services``/``apps.treasury.services``) :
toute lecture/ecriture passe par ``all_objects`` avec un filtre explicite
sur ``club_id`` -- ces services sont appeles aussi bien depuis une
requete HTTP (club actif positionne) que depuis un test ou une future
commande cron.

Contrat consomme par le Lot 3 (``apps.sport.services._get_medical_unfitness``,
deja en attente) : :func:`get_unfitness_reason`. Voir docs/ecrans/medical.md
§2.4 pour le contrat exact -- NE JAMAIS reformuler ce texte ailleurs
(l'interface l'affiche tel quel, comme ``describe_reason_for_viewer``
cote sport).

Points ouverts (docs/ecrans/medical.md §11) appliques ici a titre
provisoire, signales au compte rendu :
- n1 : cumul Coach+Medecin -> union des droits UNIQUEMENT dans ce module.
- n3 : une blessure « En cours » rend inapte DES SA DECLARATION.
- n4 : consentement au traitement manquant -> declaration/aptitude
  restent possibles ; bilan/suivi/fiche bloques.
- n5 : « Apte avec restriction » reste selectionnable (CLAUDE.md §2.5).
- n7 : une entree de suivi n'est jamais modifiee ni supprimee.
- n9 : consultation de la page Medical (Coach/President) journalisee
  (``medical.fitness_list.viewed``).
- n10 : le Superuser n'a pas d'acces au contenu medical en session de
  support (Ghost Mode) -- aucune fonction de ce module ne contourne les
  controles de role pour un Superuser.
"""

from __future__ import annotations

from datetime import date, time
from typing import Any, Optional

from django.utils import timezone

from apps.clubs.models import COACHING_STAFF_ROLES, Membership, MembershipRole, PresidencyTransfer
from apps.core.private_files import rename_upload_to_real_type
from apps.core.roles import get_active_roles, has_any_role
from apps.core.services import log_action
from apps.medical.models import HealthRecord, Injury, InjuryFollowUp, MedicalDocument

__all__ = [
    "MedicalError",
    "MedicalValidationError",
    "MedicalPermissionError",
    "ConsentMissingError",
    "get_unfitness_reason",
    "get_fitness_summary",
    "format_date_fr",
    "get_health_record",
    "get_or_create_health_record",
    "can_president_read_full_record",
    "has_full_record_access",
    "view_health_record_as_doctor",
    "view_health_record_as_player",
    "view_health_record_as_president",
    "give_processing_consent",
    "update_self_declaration",
    "update_health_record",
    "update_fitness",
    "grant_president_access",
    "revoke_president_access",
    "report_injury",
    "complete_injury_report",
    "add_injury_followup",
    "declare_injury_return",
    "list_injuries_to_complete",
    "list_recent_injuries",
    "list_unfit_and_restricted",
    "log_fitness_list_viewed",
    "log_injury_viewed",
    "attach_document",
    "can_access_document",
    "log_document_viewed",
]


class MedicalError(Exception):
    """Racine des erreurs metier de l'app medical."""


class MedicalValidationError(MedicalError):
    """Donnee ou etat invalide (traduite en 400 par les vues)."""


class MedicalPermissionError(MedicalError, PermissionError):
    """Action refusee malgre un role a priori suffisant."""


class ConsentMissingError(MedicalValidationError):
    """Le consentement au traitement des données de santé du joueur manque
    (CDC 4.12, 7.5 ; medical.md §4.2, point ouvert 4) : bloque le bilan, le
    suivi et la fiche -- pas la declaration ni l'aptitude (CLAUDE.md
    regle n5, priorite a la securite du joueur)."""


# ---------------------------------------------------------------------------
# Formatage de date (design-system §4 : « dim. 12 oct. 2026 »)
# ---------------------------------------------------------------------------

_FR_WEEKDAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
_FR_MONTHS = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
]


def format_date_fr(value: date) -> str:
    """« dim. 12 oct. 2026 » (design-system §4), utilise par les textes
    d'aptitude renvoyes par l'API (medical.md §2.4 : jamais recompose par
    l'interface)."""

    weekday = _FR_WEEKDAYS[value.weekday()]
    month = _FR_MONTHS[value.month - 1]
    return f"{weekday} {value.day} {month} {value.year}"


# ---------------------------------------------------------------------------
# Lecture de base
# ---------------------------------------------------------------------------


def get_health_record(membership: Membership) -> Optional[HealthRecord]:
    """Fiche de ``membership``, ou ``None`` si jamais creee (joueur apte par
    defaut, aucune donnee saisie -- HealthRecord.FitnessStatus.FIT est le
    defaut du modele, coherent avec l'absence de fiche)."""

    return HealthRecord.all_objects.filter(club_id=membership.club_id, membership_id=membership.pk).first()


def get_or_create_health_record(membership: Membership) -> HealthRecord:
    """Cree la fiche a la premiere lecture/ecriture utile (creation
    paresseuse -- voir la deviation documentee sur ``fitness_set_by`` dans
    ``apps.medical.models.HealthRecord``)."""

    record = get_health_record(membership)
    if record is not None:
        return record
    record = HealthRecord(club_id=membership.club_id, membership=membership)
    record.save()
    return record


# ---------------------------------------------------------------------------
# Contrat avec apps.sport (medical.md §2.4)
# ---------------------------------------------------------------------------


def get_unfitness_reason(membership: Membership, *, at_date: Optional[date] = None):
    """Contrat attendu par ``apps.sport.services._get_medical_unfitness``
    (medical.md §2.4). Renvoie ``None`` si le joueur est selectionnable
    (apte ou apte avec restriction -- point ouvert 5, CLAUDE.md §2.5 : seule
    l'inaptitude bloque), ou un tuple ``(raison_lisible, date_de_retour_ou_None)``.

    ``at_date`` : accepte pour la stabilite du contrat, mais VOLONTAIREMENT
    ignore au-dela de sa validation de type -- ``HealthRecord`` ne modelise
    aucun historique d'aptitude (un seul etat courant, jamais date par
    seance/match) : la question « etait-il inapte a telle date passee/future »
    n'a pas de reponse distincte de « est-il inapte maintenant ». C'est aussi
    coherent avec la regle explicite du §2.4 : « une date de retour depassee
    ne rend pas le joueur apte ». Signale au compte rendu comme limite
    connue, a lever si le Lot 4 doit un jour reconstituer l'eligibilite
    a une date passee (ex. replanification d'un evenement)."""

    record = get_health_record(membership)
    if record is None:
        return None
    if record.fitness_status in (HealthRecord.FitnessStatus.FIT, HealthRecord.FitnessStatus.FIT_WITH_RESTRICTION):
        return None

    if record.fitness_return_date is not None:
        return (f"Inapte · retour prévu le {format_date_fr(record.fitness_return_date)}", record.fitness_return_date)
    return ("Inapte · date de retour non fixée", None)


def get_unfit_membership_dates(club, membership_ids) -> dict[int, Optional[date]]:
    """Version groupée (une requête) de :func:`get_unfitness_reason` : renvoie
    ``{adhésion: date de retour ou None}`` pour les seuls joueurs INAPTES
    parmi ``membership_ids``. Même règle (seule l'inaptitude bloque), jamais
    de diagnostic ni de contenu de la fiche."""

    ids = list(membership_ids)
    if not ids:
        return {}
    rows = HealthRecord.all_objects.filter(
        club_id=club.pk, membership_id__in=ids, fitness_status=HealthRecord.FitnessStatus.UNFIT
    ).values_list("membership_id", "fitness_return_date")
    return dict(rows)


def get_fitness_summary(membership: Membership) -> dict[str, Any]:
    """Contrat N1 (medical.md §5.1 point 1) : ``fitness_status`` +
    ``fitness_return_date`` UNIQUEMENT -- jamais ``has_open_injury``, un
    compteur, ``fitness_set_at``/``fitness_set_by``, ni le statut de
    consentement. Meme forme pour tout joueur, avec ou sans fiche
    (medical.md §5.1 point 2)."""

    record = get_health_record(membership)
    if record is None:
        return {"fitness_status": HealthRecord.FitnessStatus.FIT, "fitness_return_date": None}
    return {"fitness_status": record.fitness_status, "fitness_return_date": record.fitness_return_date}


# ---------------------------------------------------------------------------
# Visibilite N2 (medical.md §2, schema §6)
# ---------------------------------------------------------------------------


def can_president_read_full_record(record: HealthRecord, *, now=None) -> bool:
    """``can_president_read_full_record`` (schema §6) : vrai SSI le
    consentement est accorde, non revoque (ou revoque avant le dernier
    octroi), ET l'octroi est posterieur a la derniere passation de
    presidence du club. Ne verifie PAS l'identite du President : c'est le
    role du (des) appelant(s) ci-dessous (``view_health_record_as_president``,
    ``has_full_record_access``)."""

    if record is None or record.president_access_granted_at is None:
        return False
    if (
        record.president_access_revoked_at is not None
        and record.president_access_revoked_at >= record.president_access_granted_at
    ):
        return False

    last_transfer = (
        PresidencyTransfer.all_objects.filter(club_id=record.club_id)
        .order_by("-transferred_at")
        .first()
    )
    if last_transfer is not None and record.president_access_granted_at <= last_transfer.transferred_at:
        return False
    return True


def has_full_record_access(*, viewer, membership: Membership) -> bool:
    """N2 (medical.md §2.2) : le Medecin (pour tout joueur du club), le
    joueur lui-meme, ou le President avec un consentement actif POUR CE
    JOUEUR. Le Superuser n'a jamais d'acces au contenu medical (point
    ouvert 10, position prudente retenue)."""

    if getattr(viewer, "is_superuser", False):
        return False
    if getattr(viewer, "id", None) == membership.user_id:
        return True
    if has_any_role(viewer, {MembershipRole.Role.DOCTOR}, club=membership.club):
        return True
    if has_any_role(viewer, {MembershipRole.Role.PRESIDENT}, club=membership.club):
        record = get_health_record(membership)
        return record is not None and can_president_read_full_record(record)
    return False


def _require_full_record_access(*, viewer, membership: Membership) -> None:
    if not has_full_record_access(viewer=viewer, membership=membership):
        raise MedicalPermissionError("Vous n'avez pas accès au dossier médical complet de ce joueur.")


# ---------------------------------------------------------------------------
# Consultations journalisees (CDC 5.2, 7.5 ; schema §6, §12.1)
# ---------------------------------------------------------------------------


def view_health_record_as_doctor(*, membership: Membership, actor) -> HealthRecord:
    if not has_any_role(actor, {MembershipRole.Role.DOCTOR}, club=membership.club):
        raise MedicalPermissionError("Réservé au Médecin / référent santé.")
    record = get_or_create_health_record(membership)
    log_action(actor=actor, club=membership.club, action_type="medical.record.viewed", obj=record)
    return record


def view_health_record_as_player(*, membership: Membership, actor) -> HealthRecord:
    if getattr(actor, "id", None) != membership.user_id:
        raise MedicalPermissionError("Réservé au joueur concerné.")
    record = get_or_create_health_record(membership)
    log_action(actor=actor, club=membership.club, action_type="medical.record.viewed", obj=record)
    return record


def view_health_record_as_president(*, membership: Membership, actor) -> HealthRecord:
    """« Consulter le dossier complet » (medical.md §4.6) : re-verifiee a
    CHAQUE appel (jamais mise en cache cote serveur non plus) -- l'interface
    redemande toutes les 30 s pendant la consultation (§4.6, revocation en
    cours de session)."""

    if not has_any_role(actor, {MembershipRole.Role.PRESIDENT}, club=membership.club):
        raise MedicalPermissionError("Réservé au Président du club.")
    record = get_health_record(membership)
    if record is None or not can_president_read_full_record(record):
        raise MedicalPermissionError("Ce dossier n'est plus accessible.")
    log_action(actor=actor, club=membership.club, action_type="medical.record.viewed_by_president", obj=record)
    return record


def log_injury_viewed(*, actor, injury: Injury) -> None:
    """Consultation du detail d'une blessure (medical.md §4.3 ; CDC 5.2, 7.5),
    journalisee comme celle de la fiche : ``medical.record.viewed_by_president``
    si le lecteur est le President (hors son propre dossier), sinon
    ``medical.injury.viewed`` (Medecin ou joueur concerne). Seule la
    reference a la blessure est journalisee, jamais son contenu."""

    is_president_reading_other = (
        has_any_role(actor, {MembershipRole.Role.PRESIDENT}, club=injury.club)
        and getattr(actor, "id", None) != injury.membership.user_id
    )
    action_type = "medical.record.viewed_by_president" if is_president_reading_other else "medical.injury.viewed"
    log_action(actor=actor, club=injury.club, action_type=action_type, obj=injury)


def log_fitness_list_viewed(*, club, actor) -> None:
    """Consultation de la page « Medical » (liste d'aptitudes) par le Coach
    ou le President (point ouvert 9, proposition retenue). Le Medecin n'est
    pas concerne : ses consultations sont deja journalisees fiche par fiche
    (``medical.record.viewed``). Aucun appel pour un simple texte
    d'inéligibilite affiche dans les ecrans sportifs (volume, §11 n9)."""

    log_action(actor=actor, club=club, action_type="medical.fitness_list.viewed", obj=club)


# ---------------------------------------------------------------------------
# Consentement au traitement des données de santé (CDC 4.12, 7.5)
# ---------------------------------------------------------------------------


def give_processing_consent(*, membership: Membership, actor, now=None) -> HealthRecord:
    if getattr(actor, "id", None) != membership.user_id:
        raise MedicalPermissionError("Seul le joueur concerné peut donner ce consentement.")
    now = now or timezone.now()
    record = get_or_create_health_record(membership)
    if record.consent_given_at is None:
        record.consent_given_at = now
        record.save(update_fields=["consent_given_at"])
        log_action(actor=actor, club=membership.club, action_type="medical.processing_consent.given", obj=record)
    return record


def update_self_declaration(*, membership: Membership, actor, text: str, consent_given: bool = False, now=None) -> HealthRecord:
    """« Mettre a jour ma declaration » (medical.md §4.10) : si le
    consentement au traitement manque, ``consent_given`` doit être vrai
    (case a cocher obligatoire cote interface) pour enregistrer."""

    if getattr(actor, "id", None) != membership.user_id:
        raise MedicalPermissionError("Seul le joueur concerné peut mettre à jour sa déclaration.")
    now = now or timezone.now()
    record = get_or_create_health_record(membership)
    if record.consent_given_at is None:
        if not consent_given:
            raise ConsentMissingError("Cochez la case pour enregistrer votre déclaration.")
        record.consent_given_at = now
        log_action(actor=actor, club=membership.club, action_type="medical.processing_consent.given", obj=record)

    record.self_declaration = text or ""
    record.self_declaration_updated_at = now
    record.save(update_fields=["self_declaration", "self_declaration_updated_at", "consent_given_at"])
    log_action(
        actor=actor,
        club=membership.club,
        action_type="medical.self_declaration.updated",
        obj=record,
        after={"fields_changed": ["self_declaration"]},
    )
    return record


# ---------------------------------------------------------------------------
# Fiche completee par le Medecin (medical.md §4.5)
# ---------------------------------------------------------------------------

_HEALTH_RECORD_DOCTOR_FIELDS = (
    "blood_group",
    "allergies",
    "medical_history",
    "ongoing_treatments",
    "emergency_contact_name",
    "emergency_contact_phone",
)


def update_health_record(*, membership: Membership, actor, data: dict[str, Any]) -> HealthRecord:
    """« Modifier la fiche » (medical.md §4.5) : reserve au Medecin, bloque
    si le consentement au traitement manque (bandeau §4.2, bouton masque
    cote interface -- reverifie ici, defense en profondeur)."""

    if not has_any_role(actor, {MembershipRole.Role.DOCTOR}, club=membership.club):
        raise MedicalPermissionError("Réservé au Médecin / référent santé.")
    record = get_or_create_health_record(membership)
    if record.consent_given_at is None:
        raise ConsentMissingError(
            "Vous pouvez fixer l'aptitude et suivre les blessures déclarées, mais pas compléter la fiche "
            "tant que le joueur n'a pas donné son consentement au traitement de ses données de santé."
        )

    changed_fields: list[str] = []
    for field in _HEALTH_RECORD_DOCTOR_FIELDS:
        if field in data and getattr(record, field) != data[field]:
            setattr(record, field, data[field])
            changed_fields.append(field)

    if changed_fields:
        record.save(update_fields=changed_fields + ["updated_at"])
        log_action(
            actor=actor,
            club=membership.club,
            action_type="medical.record.updated",
            obj=record,
            after={"fields_changed": changed_fields},
        )
    return record


# ---------------------------------------------------------------------------
# Aptitude (medical.md §4.4)
# ---------------------------------------------------------------------------


def update_fitness(
    *,
    membership: Membership,
    actor,
    status: str,
    return_date: Optional[date] = None,
    now=None,
) -> HealthRecord:
    if not has_any_role(actor, {MembershipRole.Role.DOCTOR}, club=membership.club):
        raise MedicalPermissionError("Réservé au Médecin / référent santé.")
    if status not in HealthRecord.FitnessStatus.values:
        raise MedicalValidationError("Choisissez une aptitude valide.")

    now = now or timezone.now()
    record = get_or_create_health_record(membership)

    has_open_injury = Injury.all_objects.filter(
        club_id=membership.club_id, membership_id=membership.pk, status=Injury.Status.OPEN
    ).exists()
    if has_open_injury and status in (
        HealthRecord.FitnessStatus.FIT,
        HealthRecord.FitnessStatus.FIT_WITH_RESTRICTION,
    ):
        raise MedicalValidationError(
            "Ce joueur a une blessure en cours. Déclarez son retour depuis la blessure pour le rendre apte."
        )

    if status != HealthRecord.FitnessStatus.UNFIT:
        return_date = None
    elif return_date is not None and return_date < timezone.localdate():
        raise MedicalValidationError("La date de retour ne peut pas être dans le passé.")

    record.fitness_status = status
    record.fitness_return_date = return_date
    record.fitness_set_by = actor
    record.fitness_set_at = now
    record.save(update_fields=["fitness_status", "fitness_return_date", "fitness_set_by", "fitness_set_at", "updated_at"])
    log_action(
        actor=actor,
        club=membership.club,
        action_type="medical.fitness.updated",
        obj=record,
        after={"fitness_status": record.fitness_status, "fitness_return_date": str(return_date) if return_date else None},
    )
    return record


# ---------------------------------------------------------------------------
# Consentement d'acces du President (CDC 4.12, 7.5 ; 10.2 n15)
# ---------------------------------------------------------------------------


def grant_president_access(*, membership: Membership, actor, now=None) -> HealthRecord:
    if getattr(actor, "id", None) != membership.user_id:
        raise MedicalPermissionError("Seul le joueur concerné peut accorder cet accès.")
    now = now or timezone.now()
    record = get_or_create_health_record(membership)
    record.president_access_granted_at = now
    record.save(update_fields=["president_access_granted_at"])
    log_action(actor=actor, club=membership.club, action_type="medical.president_access.granted", obj=record)
    return record


def revoke_president_access(*, membership: Membership, actor, now=None) -> HealthRecord:
    if getattr(actor, "id", None) != membership.user_id:
        raise MedicalPermissionError("Seul le joueur concerné peut révoquer cet accès.")
    now = now or timezone.now()
    record = get_or_create_health_record(membership)
    record.president_access_revoked_at = now
    record.save(update_fields=["president_access_revoked_at"])
    log_action(actor=actor, club=membership.club, action_type="medical.president_access.revoked", obj=record)
    return record


# ---------------------------------------------------------------------------
# Blessures (CDC 4.12 etapes 1-5 ; medical.md §4.1, §4.7-§4.9)
# ---------------------------------------------------------------------------

INJURY_REPORTER_ROLES = frozenset(
    {*COACHING_STAFF_ROLES, MembershipRole.Role.CAPTAIN, MembershipRole.Role.DOCTOR}
)


def report_injury(
    *,
    membership: Membership,
    actor,
    circumstances: str,
    event=None,
    occurred_time: Optional[time] = None,
    occurred_minute: Optional[int] = None,
    now=None,
) -> Injury:
    """Etape 1 (CDC 4.12) : Coach, Capitaine ou Medecin. Accepte meme si le
    consentement au traitement manque (point ouvert 4, position retenue :
    l'auteur n'en est pas informe). Le joueur devient inapte DES LA
    DECLARATION (point ouvert 3, position retenue -- schema §6.2)."""

    if not has_any_role(actor, INJURY_REPORTER_ROLES, club=membership.club):
        raise MedicalPermissionError("Réservé au Coach (ou son assistant), au Capitaine et au Médecin.")
    if not (circumstances or "").strip():
        raise MedicalValidationError("Décrivez brièvement les circonstances.")

    now = now or timezone.now()
    injury = Injury(
        club_id=membership.club_id,
        membership=membership,
        event=event,
        reported_by=actor,
        reported_at=now,
        occurred_time=occurred_time,
        occurred_minute=occurred_minute,
        circumstances=circumstances,
        status=Injury.Status.OPEN,
    )
    injury.save()

    record = get_or_create_health_record(membership)
    record.fitness_status = HealthRecord.FitnessStatus.UNFIT
    record.save(update_fields=["fitness_status"])

    log_action(
        actor=actor,
        club=membership.club,
        action_type="medical.injury.reported",
        obj=injury,
        after={"status": injury.status},
    )
    _notify_injury_reported(injury=injury, membership=membership)
    return injury


def _notify_injury_reported(*, injury: Injury, membership: Membership) -> None:
    """Notifications CDC 4.17 (medical.md §7) : Medecin(s) + Coach, jamais
    l'auteur de la declaration, jamais les circonstances/localisation/
    gravite."""

    from apps.notifications.services import create_notification
    from apps.notifications.models import Notification

    event_label = "hors séance ou match"
    if injury.event_id is not None:
        event = injury.event
        if event.kind == event.Kind.SESSION:
            event_label = f"Séance du {format_date_fr(event.event_date)}"
        else:
            match = getattr(event, "match", None)
            opponent = None
            if match is not None:
                opponent = match.opponent_club.name if match.opponent_club_id else match.opponent_name
            event_label = f"Match contre {opponent}" if opponent else "Match"

    doctor_memberships = Membership.all_objects.filter(
        club_id=membership.club_id,
        status=Membership.Status.ACTIVE,
        roles__role=MembershipRole.Role.DOCTOR,
        roles__revoked_at__isnull=True,
    ).distinct()
    coach_memberships = Membership.all_objects.filter(
        club_id=membership.club_id,
        status=Membership.Status.ACTIVE,
        roles__role__in=COACHING_STAFF_ROLES,
        roles__revoked_at__isnull=True,
    ).distinct()

    player_name = f"{membership.user.first_name} {membership.user.last_name}".strip()

    for doctor_membership in doctor_memberships:
        if doctor_membership.user_id == injury.reported_by_id:
            continue
        create_notification(
            recipient=doctor_membership.user,
            event_type=Notification.EventType.INJURY_DECLARED,
            message=f"Blessure déclarée : {player_name} ({event_label}). À compléter.",
            club=membership.club,
            target=injury,
        )
    for coach_membership in coach_memberships:
        if coach_membership.user_id == injury.reported_by_id:
            continue
        create_notification(
            recipient=coach_membership.user,
            event_type=Notification.EventType.INJURY_DECLARED,
            message=f"{player_name} est inapte : blessure déclarée le {format_date_fr(timezone.localdate())}.",
            club=membership.club,
            target=injury,
        )


def _get_injury_or_error(*, injury_id, club) -> Injury:
    injury = Injury.all_objects.filter(club_id=club.id, pk=injury_id).first()
    if injury is None:
        raise MedicalValidationError("Cet élément n'existe plus.")
    return injury


def complete_injury_report(
    *,
    injury: Injury,
    actor,
    location_on_body: str = "",
    severity: str = "",
    on_site_care: str = "",
    referral: str = "",
    estimated_days_out: Optional[int] = None,
    return_date: Optional[date] = None,
    now=None,
) -> Injury:
    """Etape 2 (CDC 4.12) : « Completer la blessure »/« Modifier le bilan »
    (medical.md §4.7), reserve au Medecin, bloque si le consentement
    manque (point ouvert 4)."""

    if not has_any_role(actor, {MembershipRole.Role.DOCTOR}, club=injury.club):
        raise MedicalPermissionError("Réservé au Médecin / référent santé.")
    record = get_or_create_health_record(injury.membership)
    if record.consent_given_at is None:
        raise ConsentMissingError(
            "Vous pouvez fixer l'aptitude et suivre les blessures déclarées, mais pas compléter la fiche "
            "tant que le joueur n'a pas donné son consentement au traitement de ses données de santé."
        )
    if return_date is not None and injury.reported_at is not None and return_date < injury.reported_at.date():
        raise MedicalValidationError("La date de retour ne peut pas être avant la blessure.")

    now = now or timezone.now()
    injury.location_on_body = location_on_body
    injury.severity = severity
    injury.on_site_care = on_site_care
    injury.referral = referral
    injury.estimated_days_out = estimated_days_out
    was_completed = injury.doctor_completed_by_id is not None
    injury.doctor_completed_by = actor
    injury.doctor_completed_at = now
    injury.save()

    if return_date is not None:
        record.fitness_return_date = return_date
        record.save(update_fields=["fitness_return_date"])

    action_type = "medical.injury.completed"
    log_action(
        actor=actor,
        club=injury.club,
        action_type=action_type,
        obj=injury,
        after={"fields_changed": ["location_on_body", "severity", "on_site_care", "referral", "estimated_days_out"], "was_update": was_completed},
    )
    return injury


def add_injury_followup(*, injury: Injury, actor, entry_date: date, note: str, new_return_date: Optional[date] = None, now=None) -> InjuryFollowUp:
    """Etape 4 (CDC 4.12) : « Ajouter un suivi » (medical.md §4.8), reserve
    au Medecin. Une entree n'est jamais modifiee ni supprimee (point ouvert
    7)."""

    if not has_any_role(actor, {MembershipRole.Role.DOCTOR}, club=injury.club):
        raise MedicalPermissionError("Réservé au Médecin / référent santé.")
    record = get_or_create_health_record(injury.membership)
    if record.consent_given_at is None:
        raise ConsentMissingError(
            "Vous pouvez fixer l'aptitude et suivre les blessures déclarées, mais pas ajouter de suivi "
            "tant que le joueur n'a pas donné son consentement au traitement de ses données de santé."
        )
    if not (note or "").strip():
        raise MedicalValidationError("Ce champ est obligatoire.")
    today = timezone.localdate()
    if entry_date > today:
        raise MedicalValidationError("La date ne peut pas être dans le futur.")
    if injury.reported_at is not None and entry_date < injury.reported_at.date():
        raise MedicalValidationError("La date ne peut pas être avant la blessure.")
    if new_return_date is not None and new_return_date < today:
        raise MedicalValidationError("La date de retour ne peut pas être dans le passé.")

    now = now or timezone.now()
    followup = InjuryFollowUp(
        club_id=injury.club_id, injury=injury, entry_date=entry_date, note=note, created_by=actor
    )
    followup.save()

    if new_return_date is not None:
        record.fitness_return_date = new_return_date
        record.save(update_fields=["fitness_return_date"])

    log_action(actor=actor, club=injury.club, action_type="medical.injury.followup_added", obj=followup)
    return followup


def declare_injury_return(*, injury: Injury, actor, return_date: date, now=None) -> Injury:
    """Etape 5 (CDC 4.12) : « Declarer le retour » (medical.md §4.9),
    reserve au Medecin. Le joueur redevient APTE (jamais « avec
    restriction » automatiquement -- §4.9 : « Pour mettre apte avec
    restriction ensuite : Modifier l'aptitude ») s'il n'a plus d'autre
    blessure en cours."""

    if not has_any_role(actor, {MembershipRole.Role.DOCTOR}, club=injury.club):
        raise MedicalPermissionError("Réservé au Médecin / référent santé.")
    if injury.status == Injury.Status.RESOLVED:
        raise MedicalValidationError("Cette blessure est déjà clôturée.")
    today = timezone.localdate()
    if return_date > today:
        raise MedicalValidationError("La date du retour ne peut pas être dans le futur.")
    if injury.reported_at is not None and return_date < injury.reported_at.date():
        raise MedicalValidationError("La date du retour ne peut pas être avant la blessure.")

    now = now or timezone.now()
    injury.status = Injury.Status.RESOLVED
    injury.resolved_by = actor
    injury.resolved_at = now
    injury.save()

    other_open = Injury.all_objects.filter(
        club_id=injury.club_id, membership_id=injury.membership_id, status=Injury.Status.OPEN
    ).exclude(pk=injury.pk).exists()

    record = get_or_create_health_record(injury.membership)
    if not other_open:
        record.fitness_status = HealthRecord.FitnessStatus.FIT
        record.fitness_return_date = None
        record.save(update_fields=["fitness_status", "fitness_return_date"])

    log_action(
        actor=actor,
        club=injury.club,
        action_type="medical.injury.resolved",
        obj=injury,
        after={"fitness_status": record.fitness_status},
    )
    return injury


# ---------------------------------------------------------------------------
# Listes de la page « Medical » (medical.md §3)
# ---------------------------------------------------------------------------


def list_injuries_to_complete(club):
    """§3.1 : blessures declarees, pas encore completees, les plus
    anciennes en premier."""

    return Injury.all_objects.filter(club_id=club.id, doctor_completed_at__isnull=True).order_by("reported_at")


def list_recent_injuries(club, *, limit: int = 5):
    """§3.4 : historique du club, toutes blessures confondues, les plus
    recentes en premier."""

    return Injury.all_objects.filter(club_id=club.id).order_by("-reported_at")[:limit]


def list_unfit_and_restricted(club):
    """§3.2 : joueurs dont l'aptitude n'est pas « Apte », inaptes d'abord
    par date de retour croissante (sans date en dernier), puis
    restrictions."""

    from django.db.models import Case, When, Value, IntegerField

    return (
        HealthRecord.all_objects.filter(club_id=club.id)
        .exclude(fitness_status=HealthRecord.FitnessStatus.FIT)
        .annotate(
            _status_rank=Case(
                When(fitness_status=HealthRecord.FitnessStatus.UNFIT, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            _has_return_date=Case(
                When(fitness_return_date__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            ),
        )
        .order_by("_status_rank", "_has_return_date", "fitness_return_date")
        .select_related("membership")
    )


# ---------------------------------------------------------------------------
# Documents medicaux (CDC 6.7 ; ajout hors schema -- voir models.py)
# ---------------------------------------------------------------------------


def attach_document(*, actor, file, original_filename: str = "", injury: Optional[Injury] = None, health_record: Optional[HealthRecord] = None) -> MedicalDocument:
    if bool(injury) == bool(health_record):
        raise MedicalValidationError("Un document doit être rattaché à une blessure ou à une fiche, jamais les deux.")
    club = injury.club if injury is not None else health_record.club
    if not has_any_role(actor, {MembershipRole.Role.DOCTOR}, club=club):
        raise MedicalPermissionError("Réservé au Médecin / référent santé.")
    # Nom de stockage aleatoire a extension reelle (jamais celle du client).
    rename_upload_to_real_type(file)
    document = MedicalDocument(
        club_id=club.id,
        injury=injury,
        health_record=health_record,
        file=file,
        original_filename=original_filename,
        uploaded_by=actor,
    )
    document.save()

    # CLAUDE.md regle n6 (toute creation ecrit une entree de journal) ;
    # regle n11 / CDC 5.2 « Medical » : jamais le contenu (ni le nom de
    # fichier, qui peut lui-meme reveler un element clinique -- ex.
    # « entorse_genou.pdf »). Seule la reference (type/id, deja portee par
    # `obj`) et le parent (blessure ou fiche) sont journalises -- jamais le
    # fichier lui-meme ni son nom original.
    log_action(
        actor=actor,
        club=club,
        action_type="medical.document.attached",
        obj=document,
        after={
            "injury_id": injury.pk if injury is not None else None,
            "health_record_id": health_record.pk if health_record is not None else None,
        },
    )
    return document


def can_access_document(*, viewer, document: MedicalDocument) -> bool:
    membership = document.injury.membership if document.injury_id else document.health_record.membership
    return has_full_record_access(viewer=viewer, membership=membership)


def log_document_viewed(*, actor, document: MedicalDocument) -> None:
    """Consultation journalisee d'un telechargement de document medical
    (CLAUDE.md regle n11 ; CDC 5.2 « Medical », 7.5 ; CDC 4.12 : « chaque
    consultation [du dossier par le President] est journalisee » --
    applique ici, par coherence, a toute consultation d'un document
    medical, quel que soit le role du lecteur, pas seulement le President,
    meme logique de tracabilite que le reste du module (``medical.record.viewed``,
    ``medical.record.viewed_by_president``). Jamais le contenu du document
    ni un diagnostic : seule la reference au document (type/id, portee par
    `obj`) est journalisee."""

    club = document.injury.club if document.injury_id else document.health_record.club
    owner_user_id = (
        document.injury.membership.user_id if document.injury_id else document.health_record.membership.user_id
    )
    is_president_reading_other = (
        has_any_role(actor, {MembershipRole.Role.PRESIDENT}, club=club)
        and getattr(actor, "id", None) != owner_user_id
    )
    action_type = "medical.record.viewed_by_president" if is_president_reading_other else "medical.document.viewed"
    log_action(actor=actor, club=club, action_type=action_type, obj=document)
