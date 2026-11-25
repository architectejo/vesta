"""Regles metier de l'app assemblies (CDC 4.15 ; tache 4.5).

Sources : docs/lot0/schema-donnees.md §9 ; docs/ecrans/assemblees-page-ag.md ;
10.2 n° 18 (quorum, 50 % par defaut), n° 24 (plusieurs titulaires par role),
n° 28 (President seul si VP vacant) ; CLAUDE.md regles n° 6, n° 7, n° 9.

Decisions par defaut appliquees ici (signalees au compte rendu) :

- **Quorum jamais bloquant** (assemblees-page-ag.md §4.2, revision 29/09) :
  ce module calcule toujours le quorum (present/total, seuil, atteint ou
  non) mais ne refuse JAMAIS une saisie de presence ou de vote pour ce seul
  motif -- l'interface affiche un avertissement, rien de plus (4.15 impose
  le calcul, pas la consequence, point ouvert §7).
- **Total des votes superieur au nombre de presents** : meme logique,
  jamais bloquant (§4.3 de l'ecran, revision 29/09) -- le service enregistre
  la decision telle quelle, sans comparer aux presences.
- **Seuil de quorum toujours lu en direct** sur ``ClubSettings`` au moment
  du calcul (jamais fige a la convocation ni a la cloture) : point ouvert
  §7 de l'ecran, position la plus simple retenue, a confirmer.
- **Signature du Vice-president** : un seul champ ``Minutes.vp_signed_by``
  existe dans le schema (§9.5) -- un seul titulaire du role Vice-president
  suffit donc a signer, quel que soit le nombre de titulaires actifs
  (10.2 n° 24). Point ouvert non tranche, voir docstring de
  ``apps.assemblies.models``.
- **Vacance du Vice-president appreciee a CHAQUE evenement de signature**
  (schema §9.5 ``vp_vacant_at_signature``, pas a la date de l'AG) : re-
  evaluee a chaque appel de :func:`sign_minutes` tant que le PV n'est pas
  complet, pour couvrir le cas d'un VP revoque entre la signature du
  President et celle attendue du Vice-president.
- **Presences ouvertes uniquement le jour de l'AG** (fuseau du club,
  meme mecanisme que ``apps.sport.services`` pour le verrouillage a
  minuit des evenements sportifs) : President et VP ne peuvent pointer
  une presence qu'a la date de l'assemblee -- pas de derogation Superuser
  au Lot 4 (le CDC ne le prevoit pas pour l'AG, contrairement aux seances
  sportives, 4.7).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from apps.core.private_files import rename_upload_to_real_type
from apps.assemblies.models import (
    AgendaItem,
    ArchivedDocument,
    Assembly,
    AssemblyAttendance,
    Decision,
    Minutes,
)
from apps.clubs.models import ClubSettings, Membership, MembershipRole
from apps.core.roles import get_active_roles, has_any_role
from apps.core.services import log_action

__all__ = [
    "AssemblyError",
    "AssemblyValidationError",
    "AssemblyPermissionError",
    "AssemblyLockedError",
    "QuorumResult",
    "get_club_today",
    "convene_assembly",
    "get_active_membership_count",
    "get_quorum",
    "mark_attendance",
    "remove_attendance",
    "record_decision",
    "draft_minutes",
    "sign_minutes",
    "update_quorum_threshold",
    "send_assembly_reminders",
    "archive_document",
    "replace_archived_document",
    "withdraw_archived_document",
    "record_archived_document_access",
    "filter_archived_documents",
]


class AssemblyError(Exception):
    """Racine des erreurs metier de l'app assemblies."""


class AssemblyValidationError(AssemblyError):
    """Donnee ou etat invalide (traduite en 400 par les vues)."""


class AssemblyPermissionError(AssemblyError, PermissionError):
    """Action refusee malgre un role a priori suffisant (ex. VP qui tente de
    signer au titre du President, President-VP qui a deja signe une fois)."""


class AssemblyLockedError(AssemblyError):
    """Presences hors du jour de l'AG, ou PV deja signe/complet (traduite en
    409 par les vues)."""


# ---------------------------------------------------------------------------
# Fuseau horaire du club (meme convention que apps.sport.services)
# ---------------------------------------------------------------------------


def _club_settings(club) -> ClubSettings:
    club_settings = ClubSettings.objects.filter(club_id=club.id).first()
    if club_settings is None:
        raise AssemblyValidationError("Les paramètres du club (fuseau horaire, quorum) ne sont pas configurés.")
    return club_settings


def _club_tz(club_settings: ClubSettings) -> ZoneInfo:
    try:
        return ZoneInfo(club_settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise AssemblyValidationError("Le fuseau horaire du club est invalide.") from None


def _club_today(club, *, now: Optional[datetime] = None) -> date:
    now = now or timezone.now()
    return now.astimezone(_club_tz(_club_settings(club))).date()


def get_club_today(club, *, now: Optional[datetime] = None) -> date:
    """Date du jour dans le fuseau du club (CDC 4.15)."""

    return _club_today(club, now=now)


# ---------------------------------------------------------------------------
# Convocation (assemblees-page-ag.md §4.1)
# ---------------------------------------------------------------------------


def convene_assembly(
    *,
    club,
    actor,
    assembly_type: str,
    scheduled_date: date,
    scheduled_time,
    location: str = "",
    agenda_items: list[dict],
    now=None,
) -> Assembly:
    """Convoque une AG (President, VP, Secretaire -- verifie par la vue). Exige au
    moins un point a l'ordre du jour et une date future (fuseau du club).
    Notifie tous les joueurs actifs (convocation, in-app + email -- CDC
    4.17) et journalise (assemblees-page-ag.md §4.7)."""

    now = now or timezone.now()

    if scheduled_date <= _club_today(club, now=now):
        raise AssemblyValidationError("La date doit être dans le futur.")
    if not agenda_items:
        raise AssemblyValidationError("Ajoutez au moins un point à l'ordre du jour.")

    assembly = Assembly(
        club=club,
        assembly_type=assembly_type,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        location=location or "",
        status=Assembly.Status.SCHEDULED,
        created_by=actor,
    )
    assembly.save()

    for index, item in enumerate(agenda_items, start=1):
        title = (item.get("title") or "").strip()
        if not title:
            raise AssemblyValidationError("Ajoutez au moins un point à l'ordre du jour.")
        AgendaItem.all_objects.create(
            club=club,
            assembly=assembly,
            order=index,
            title=title,
            description=item.get("description") or "",
        )

    log_action(
        actor=actor,
        club=club,
        action_type="assemblies.assembly.convened",
        obj=assembly,
        after={
            "assembly_type": assembly.assembly_type,
            "scheduled_date": str(assembly.scheduled_date),
            "scheduled_time": str(assembly.scheduled_time),
            "location": assembly.location,
            "agenda_items": len(agenda_items),
        },
    )

    _notify_all_active_members_of_convocation(club, assembly, now=now)

    return assembly


def _notify_all_active_members_of_convocation(club, assembly: Assembly, *, now) -> None:
    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    type_label = "ordinaire" if assembly.assembly_type == Assembly.AssemblyType.ORDINARY else "extraordinaire"
    message = (
        f"Assemblée générale {type_label} le {assembly.scheduled_date.strftime('%d/%m/%Y')} "
        f"à {assembly.scheduled_time.strftime('%H:%M')}, {assembly.location or 'lieu à confirmer'}."
    )
    memberships = Membership.all_objects.filter(club=club, status=Membership.Status.ACTIVE).select_related("user")
    for membership in memberships:
        create_notification(
            recipient=membership.user,
            event_type=Notification.EventType.ASSEMBLY_CONVENED,
            message=message,
            club=club,
            target=assembly,
            now=now,
        )


# ---------------------------------------------------------------------------
# Effectif actif / quorum (assemblees-page-ag.md §4.2, 10.2 n° 18)
# ---------------------------------------------------------------------------


def get_active_membership_count(club, *, at_date: date) -> int:
    """Nombre de joueurs « actifs a la date de l'AG » (denominateur du
    quorum). Simplification assumee (signalee au compte rendu) : le
    schema ne conserve pas l'historique des changements de statut d'une
    adhesion -- ce compte utilise le statut ACTUEL (``Membership.Status.ACTIVE``)
    plutot qu'une reconstruction retroactive a ``at_date``, avec une seule
    verification simple (``joined_on <= at_date``) pour exclure un joueur
    ajoute apres l'AG."""

    return Membership.all_objects.filter(
        club=club, status=Membership.Status.ACTIVE, joined_on__lte=at_date
    ).count()


@dataclass(frozen=True)
class QuorumResult:
    present: int
    total: int
    percentage: Decimal
    threshold: Decimal
    reached: bool


def get_quorum(assembly: Assembly) -> QuorumResult:
    """Quorum calcule par l'API, jamais par l'interface (assemblees-page-ag.md
    §4.2). Ne bloque jamais rien : purement informatif."""

    club_settings = _club_settings(assembly.club)
    total = get_active_membership_count(assembly.club, at_date=assembly.scheduled_date)
    present = AssemblyAttendance.all_objects.filter(club=assembly.club, assembly=assembly, present=True).count()
    if total > 0:
        percentage = (Decimal(present) * Decimal(100) / Decimal(total)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        percentage = Decimal("0.00")
    threshold = club_settings.assembly_quorum_percentage
    return QuorumResult(
        present=present, total=total, percentage=percentage, threshold=threshold, reached=percentage >= threshold
    )


# ---------------------------------------------------------------------------
# Presences (assemblees-page-ag.md §4.2 onglet « Presences »)
# ---------------------------------------------------------------------------


def _ensure_assembly_day(assembly: Assembly, *, now) -> None:
    if _club_today(assembly.club, now=now) != assembly.scheduled_date:
        raise AssemblyLockedError(
            "Les présences ne peuvent être pointées que le jour de l'assemblée."
        )


def mark_attendance(*, assembly: Assembly, actor, membership: Membership, now=None) -> AssemblyAttendance:
    now = now or timezone.now()
    _ensure_assembly_day(assembly, now=now)
    if membership.club_id != assembly.club_id:
        raise AssemblyValidationError("Ce joueur n'appartient pas à ce club.")

    attendance, _created = AssemblyAttendance.all_objects.get_or_create(
        club=assembly.club,
        assembly=assembly,
        membership=membership,
        defaults={"present": True, "checked_in_at": now},
    )
    if not attendance.present:
        attendance.present = True
        attendance.checked_in_at = now
        attendance.save()

    log_action(
        actor=actor,
        club=assembly.club,
        action_type="assemblies.attendance.marked",
        obj=attendance,
        after={"present": True, "membership_id": membership.id},
    )
    return attendance


def remove_attendance(*, assembly: Assembly, actor, membership: Membership, now=None) -> None:
    now = now or timezone.now()
    _ensure_assembly_day(assembly, now=now)

    try:
        attendance = AssemblyAttendance.all_objects.get(club=assembly.club, assembly=assembly, membership=membership)
    except AssemblyAttendance.DoesNotExist:
        raise AssemblyValidationError("Ce joueur n'a pas été pointé présent.") from None

    log_action(
        actor=actor,
        club=assembly.club,
        action_type="assemblies.attendance.removed",
        obj=attendance,
        before={"present": attendance.present},
        after={"present": False},
    )
    attendance.delete()


# ---------------------------------------------------------------------------
# Decisions et votes (assemblees-page-ag.md §4.3) -- jamais bloquant
# ---------------------------------------------------------------------------


def record_decision(
    *,
    assembly: Assembly,
    agenda_item: AgendaItem,
    actor,
    votes_for: int,
    votes_against: int,
    votes_abstain: int,
    outcome: str,
    linked_object_type: str = "",
    linked_object_id: Optional[int] = None,
    now=None,
) -> Decision:
    now = now or timezone.now()
    if agenda_item.assembly_id != assembly.id:
        raise AssemblyValidationError("Ce point n'appartient pas à cette assemblée.")
    outcome = (outcome or "").strip()
    if not outcome:
        raise AssemblyValidationError("Ce champ est obligatoire.")
    for label, value in (("Pour", votes_for), ("Contre", votes_against), ("Abstention", votes_abstain)):
        if value is None or value < 0:
            raise AssemblyValidationError(f"« {label} » doit être supérieur ou égal à 0.")

    decision = Decision.all_objects.filter(club=assembly.club, agenda_item=agenda_item).first()
    before = None
    if decision is not None:
        before = {
            "votes_for": decision.votes_for,
            "votes_against": decision.votes_against,
            "votes_abstain": decision.votes_abstain,
            "outcome": decision.outcome,
        }
        decision.votes_for = votes_for
        decision.votes_against = votes_against
        decision.votes_abstain = votes_abstain
        decision.outcome = outcome
        decision.linked_object_type = linked_object_type or ""
        decision.linked_object_id = linked_object_id
        decision.recorded_by = actor
        decision.recorded_at = now
        decision.save()
        action_type = "assemblies.decision.updated"
    else:
        decision = Decision.all_objects.create(
            club=assembly.club,
            assembly=assembly,
            agenda_item=agenda_item,
            votes_for=votes_for,
            votes_against=votes_against,
            votes_abstain=votes_abstain,
            outcome=outcome,
            linked_object_type=linked_object_type or "",
            linked_object_id=linked_object_id,
            recorded_by=actor,
            recorded_at=now,
        )
        action_type = "assemblies.decision.recorded"

    log_action(
        actor=actor,
        club=assembly.club,
        action_type=action_type,
        obj=decision,
        before=before,
        after={
            "votes_for": decision.votes_for,
            "votes_against": decision.votes_against,
            "votes_abstain": decision.votes_abstain,
            "outcome": decision.outcome,
        },
    )
    return decision


# ---------------------------------------------------------------------------
# Proces-verbal (assemblees-page-ag.md §4.2 onglet « Proces-verbal », §4.4)
# ---------------------------------------------------------------------------


def _get_or_init_minutes(assembly: Assembly) -> Minutes:
    """Renvoie le PV de l'AG, verrouille en ecriture (``select_for_update``),
    en le creant s'il n'existe pas encore (get_or_create verrouille : deux
    appels concurrents convergent sur la meme ligne, cle primaire = AG).

    A appeler DANS une transaction (``transaction.atomic``) : le verrou
    n'est tenu que jusqu'a sa fin."""

    queryset = Minutes.all_objects.select_for_update().filter(club=assembly.club, assembly=assembly)
    minutes = queryset.first()
    if minutes is None:
        try:
            with transaction.atomic():
                Minutes(club=assembly.club, assembly=assembly, content="").save(force_insert=True)
        except IntegrityError:
            pass  # cree entre-temps par un appel concurrent
        minutes = queryset.get()
    return minutes


def draft_minutes(*, assembly: Assembly, actor, content: str, now=None) -> Minutes:
    now = now or timezone.now()
    with transaction.atomic():
        minutes = _get_or_init_minutes(assembly)
        if minutes.president_signed_by_id is not None:
            raise AssemblyLockedError("Le PV ne peut plus être modifié après une signature.")

        before = {"content": minutes.content}
        minutes.content = content or ""
        minutes.save()

        log_action(
            actor=actor,
            club=assembly.club,
            action_type="assemblies.minutes.drafted",
            obj=minutes,
            before=before,
            after={"content": minutes.content},
        )
    return minutes


def _active_vice_presidents(club):
    return MembershipRole.all_objects.filter(
        club=club, role=MembershipRole.Role.VICE_PRESIDENT, revoked_at__isnull=True
    ).select_related("membership__user")


def sign_minutes(*, assembly: Assembly, actor, now=None) -> Minutes:
    """Signature du PV (sans code PIN ; décision client du 11/10/2026).

    Determine le role de signature a partir des roles REELS de l'acteur
    dans le club (jamais transmis par le client) : President en priorite
    (« un joueur qui cumule President et un autre role signe une seule
    fois, au titre de President »), sinon Vice-president. Genere le PDF
    des que le PV est complet (President seul si le poste de VP est
    vacant, sinon les deux signatures)."""

    now = now or timezone.now()
    club = assembly.club
    roles = get_active_roles(actor, club=club)

    if MembershipRole.Role.PRESIDENT in roles:
        signing_role = "president"
    elif MembershipRole.Role.VICE_PRESIDENT in roles:
        signing_role = "vice_president"
    else:
        raise AssemblyPermissionError("Réservé au Président et au Vice-président.")

    with transaction.atomic():
        # PV verrouille (get_or_create verrouille) : `is_complete` et les
        # `*_signed_by_id` sont lus APRES le verrou, donc deux signatures
        # concurrentes se serialisent sans perdre celle de l'autre.
        minutes = _get_or_init_minutes(assembly)
        if minutes.is_complete:
            raise AssemblyLockedError("Le procès-verbal est déjà complet.")

        before = {
            "president_signed": minutes.president_signed_by_id is not None,
            "vp_signed": minutes.vp_signed_by_id is not None,
            "vp_vacant_at_signature": minutes.vp_vacant_at_signature,
            "vp_role_held_by_president": minutes.vp_role_held_by_president,
        }

        if signing_role == "president":
            if minutes.president_signed_by_id is not None:
                raise AssemblyValidationError("Le Président a déjà signé ce procès-verbal.")
            minutes.president_signed_by = actor
            minutes.president_signed_at = now
        else:
            if minutes.vp_signed_by_id is not None:
                raise AssemblyValidationError("Le Vice-président a déjà signé ce procès-verbal.")
            minutes.vp_signed_by = actor
            minutes.vp_signed_at = now
            minutes.vp_vacant_at_signature = False

        # Vacance du VP appreciee a CHAQUE evenement de signature tant que le
        # PV n'est pas complet (schema §9.5 : `vp_vacant_at_signature`, pas la
        # date de l'AG -- voir docstring du module). Si le seul titulaire actif
        # du role Vice-president est la personne qui vient de signer au titre
        # de President (cumul de roles), sa signature de President couvre deja
        # les deux -- « signe une seule fois » (assemblees-page-ag.md §2) :
        # on l'exclut du calcul de vacance pour ne pas attendre une seconde
        # signature qu'elle ne pourra jamais donner. On distingue ce cas d'une
        # vacance reelle via `vp_role_held_by_president` : le PV n'a pas le
        # droit d'afficher « poste vacant » quand le poste est occupe (voir
        # docs/annexes/modeles-documents.md §8 point 5, point ouvert non tranche
        # par le client -- seul le cas objectivement faux est corrige ici).
        if minutes.vp_signed_by_id is None:
            active_vps = _active_vice_presidents(club)
            president_holds_vp = (
                minutes.president_signed_by_id is not None
                and active_vps.filter(membership__user_id=minutes.president_signed_by_id).exists()
            )
            other_active_vps = active_vps
            if minutes.president_signed_by_id is not None:
                other_active_vps = other_active_vps.exclude(membership__user_id=minutes.president_signed_by_id)
            minutes.vp_vacant_at_signature = not other_active_vps.exists()
            minutes.vp_role_held_by_president = minutes.vp_vacant_at_signature and president_holds_vp

        minutes.save()

        log_action(
            actor=actor,
            club=club,
            action_type="assemblies.minutes.signed",
            obj=minutes,
            before=before,
            after={
                "president_signed": minutes.president_signed_by_id is not None,
                "vp_signed": minutes.vp_signed_by_id is not None,
                "vp_vacant_at_signature": minutes.vp_vacant_at_signature,
                "vp_role_held_by_president": minutes.vp_role_held_by_president,
            },
        )

    if minutes.is_complete:
        _generate_minutes_pdf(minutes)
    else:
        _notify_pending_signatory(minutes, now=now)

    return minutes


def _notify_pending_signatory(minutes: Minutes, *, now) -> None:
    """Proposition (assemblees-page-ag.md §4.7, non dans le tableau CDC
    4.17, a valider) : le second signataire attendu est prevenu."""

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    club = minutes.club
    assembly = minutes.assembly
    message = (
        f"Le PV de l'AG du {assembly.scheduled_date.strftime('%d/%m/%Y')} attend votre signature."
    )

    if minutes.president_signed_by_id is not None and minutes.vp_signed_by_id is None:
        for role in _active_vice_presidents(club):
            create_notification(
                recipient=role.membership.user,
                event_type=Notification.EventType.ASSEMBLY_PV_SIGNATURE_PENDING,
                message=message,
                club=club,
                target=assembly,
                now=now,
            )
    elif minutes.vp_signed_by_id is not None and minutes.president_signed_by_id is None:
        president_role = MembershipRole.all_objects.filter(
            club=club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
        ).select_related("membership__user").first()
        if president_role is not None:
            create_notification(
                recipient=president_role.membership.user,
                event_type=Notification.EventType.ASSEMBLY_PV_SIGNATURE_PENDING,
                message=message,
                club=club,
                target=assembly,
                now=now,
            )


def _role_label(role: str) -> str:
    return "Président" if role == "president" else "Vice-président"


def _pv_reference(assembly: Assembly) -> str:
    reference = f"AG-{assembly.scheduled_date.strftime('%Y-%m-%d')}"
    if Assembly.all_objects.filter(club=assembly.club, scheduled_date=assembly.scheduled_date).count() > 1:
        reference = f"{reference}-{assembly.pk}"
    return reference


def _user_full_name(user) -> str:
    if user is None:
        return "—"
    return f"{user.first_name} {user.last_name}"


def _build_minutes_pdf(minutes: Minutes) -> bytes:
    """Genere le PV en PDF (assemblees-page-ag.md §4.6 ; gabarit valide
    docs/annexes/modeles-documents.md §3). Canevas bas niveau (hors
    perimetre `ui-designer`), aucune mention de l'Editeur ni de « Vesta »
    (CLAUDE.md regle n19), aucune donnee financiere individuelle ni
    medicale (§3.6 du gabarit). Aucune troncature de texte (§3.5) : tout
    depasse sur autant de lignes que necessaire, avec repli automatique de
    page et en-tete reduit (§1.4)."""

    from apps.core.pdf import (
        DARK_TEXT_RGB,
        MARGIN,
        MUTED_TEXT_RGB,
        NumberedDocumentCanvas,
        club_stripe_colors,
        draw_continuation_header,
        draw_header,
        draw_status_badge,
        format_date_longue,
        format_percentage,
        make_footer_drawer,
        wrap_text,
    )

    assembly = minutes.assembly
    club = assembly.club
    quorum = get_quorum(assembly)
    club_settings = _club_settings(club)
    tz = _club_tz(club_settings)

    doc_type_label = "Procès-verbal d'AG"
    reference = _pv_reference(assembly)
    now_local = timezone.now().astimezone(tz)
    generated_at_text = f"{now_local.strftime('%d/%m/%Y')} à {now_local.strftime('%H:%M')}"

    width, height = A4
    content_width = width - 2 * MARGIN

    buffer = io.BytesIO()
    footer_fn = make_footer_drawer(
        club_name=club.name,
        doc_type_label=doc_type_label,
        reference=reference,
        generated_at_text=generated_at_text,
        width=width,
    )
    pdf = NumberedDocumentCanvas(buffer, pagesize=A4, pageCompression=0, footer_fn=footer_fn)
    pdf.setTitle(doc_type_label)
    pdf.setAuthor(club.name)
    pdf.setCreator(club.name)
    pdf.setSubject(doc_type_label)

    y = draw_header(pdf, club=club, doc_type_label=doc_type_label, reference=reference, width=width, height=height)

    def new_page() -> None:
        nonlocal y
        pdf.showPage()
        y = draw_continuation_header(
            pdf, club=club, doc_type_label=doc_type_label, reference=reference, width=width, height=height
        )

    def ensure_space(needed: float = 26 * mm) -> None:
        if y < needed:
            new_page()

    def write_lines(text: str, *, font: str = "Helvetica", size: float = 10, indent: float = 0.0) -> None:
        nonlocal y
        max_width = content_width - indent
        for raw_line in (text or "").split("\n"):
            for wline in wrap_text(raw_line, font=font, size=size, max_width=max_width):
                ensure_space()
                pdf.setFillColorRGB(*DARK_TEXT_RGB)
                pdf.setFont(font, size)
                pdf.drawString(MARGIN + indent, y, wline)
                y -= size * 1.35

    def section_title(text: str) -> None:
        nonlocal y
        ensure_space(30 * mm)
        pdf.setFillColorRGB(*DARK_TEXT_RGB)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(MARGIN, y, text)
        y -= 3 * mm
        primary, _secondary = club_stripe_colors(club)
        pdf.setStrokeColorRGB(*primary)
        pdf.setLineWidth(0.5)
        pdf.line(MARGIN, y, MARGIN + content_width, y)
        y -= 6 * mm

    # -- Titre et sous-titre (§3.3 lignes 2-3) --------------------------
    type_label = "ordinaire" if assembly.assembly_type == Assembly.AssemblyType.ORDINARY else "extraordinaire"
    title_text = (
        f"Procès-verbal de l'assemblée générale {type_label} du {format_date_longue(assembly.scheduled_date)}"
    )
    for wline in wrap_text(title_text, font="Helvetica-Bold", size=16, max_width=content_width):
        ensure_space()
        pdf.setFillColorRGB(*DARK_TEXT_RGB)
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(MARGIN, y, wline)
        y -= 16 * 1.2
    location_text = (assembly.location or "").strip()
    subtitle = (
        f"{assembly.scheduled_time.strftime('%H:%M')} · {location_text}"
        if location_text
        else assembly.scheduled_time.strftime("%H:%M")
    )
    pdf.setFillColorRGB(*MUTED_TEXT_RGB)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(MARGIN, y, subtitle)
    y -= 10 * mm

    # -- Présences et quorum (§3.3 lignes 4-5) --------------------------
    section_title("Présences et quorum")
    badge_label = "Quorum atteint" if quorum.reached else "Quorum non atteint"
    badge_family = "green" if quorum.reached else "orange"
    draw_status_badge(pdf, MARGIN, y - 1.5 * mm, label=badge_label, family=badge_family)
    y -= 9 * mm
    write_lines(
        f"{quorum.present} présents sur {quorum.total} joueurs actifs — quorum de "
        f"{format_percentage(quorum.threshold)} {'atteint' if quorum.reached else 'non atteint'}"
    )
    y -= 4 * mm

    # -- Ordre du jour et décisions (§3.3 lignes 6-10) -------------------
    section_title("Ordre du jour et décisions")
    decisions_by_item = {
        decision.agenda_item_id: decision
        for decision in Decision.all_objects.filter(club=club, assembly=assembly).select_related("agenda_item")
    }
    for item in AgendaItem.all_objects.filter(club=club, assembly=assembly).order_by("order"):
        ensure_space(30 * mm)
        write_lines(f"{item.order}. {item.title}", font="Helvetica-Bold", size=10)
        if item.description:
            write_lines(item.description, size=9, indent=6 * mm)
        decision = decisions_by_item.get(item.id)
        if decision is None:
            write_lines("Aucune décision saisie.", font="Helvetica-Oblique", size=9, indent=6 * mm)
        else:
            write_lines(
                f"Pour {decision.votes_for} · Contre {decision.votes_against} · Abstention {decision.votes_abstain}",
                size=9,
                indent=6 * mm,
            )
            write_lines(f"Décision retenue : {decision.outcome}", size=9, indent=6 * mm)
        y -= 3 * mm

    # -- Texte du procès-verbal (§3.3 ligne 11) --------------------------
    y -= 3 * mm
    section_title("Texte du procès-verbal")
    for raw_line in (minutes.content or "").splitlines() or [""]:
        stripped = raw_line.strip()
        if not stripped:
            y -= 4
            continue
        if stripped.startswith("- ") or stripped.startswith("• "):
            write_lines(f"• {stripped[2:].strip()}", indent=4 * mm)
        else:
            write_lines(raw_line)

    # -- Signatures (§3.3 lignes 12-16, §3.4) ----------------------------
    y -= 4 * mm
    section_title("Signatures")

    if minutes.vp_vacant_at_signature:
        if minutes.vp_role_held_by_president:
            # Cas objectivement faux corrige (point ouvert
            # modeles-documents.md §8 n. 5) : le poste n'est pas vacant, il
            # est occupe par le President signataire. Libelle neutre
            # propose, non tranche par le client -- voir compte rendu.
            vacancy_text = (
                "Le Président exerçant aussi la fonction de Vice-président, le procès-verbal "
                "est signé par lui seul."
            )
        else:
            vacancy_text = (
                "Le poste de Vice-président étant vacant à la date de la signature, le procès-verbal "
                "est signé par le Président seul."
            )
        write_lines(vacancy_text, font="Helvetica-Oblique", size=9)
        y -= 3 * mm

    box_height = 24 * mm
    ensure_space(box_height + 14 * mm)
    box_top = y
    gap = 3 * mm
    box_width = (content_width - gap) / 2

    def draw_signature_box(x: float, role_label: str, lines: list[str]) -> None:
        pdf.setStrokeColorRGB(*MUTED_TEXT_RGB)
        pdf.setLineWidth(0.5)
        pdf.rect(x, box_top - box_height, box_width, box_height, fill=0, stroke=1)
        inner_y = box_top - 5 * mm
        pdf.setFillColorRGB(*MUTED_TEXT_RGB)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(x + 3 * mm, inner_y, role_label)
        inner_y -= 5 * mm
        for text, font, size, color in lines:
            pdf.setFillColorRGB(*color)
            for wline in wrap_text(text, font=font, size=size, max_width=box_width - 6 * mm):
                pdf.setFont(font, size)
                pdf.drawString(x + 3 * mm, inner_y, wline)
                inner_y -= size * 1.35

    president_name = _user_full_name(minutes.president_signed_by)
    president_lines = [(president_name, "Helvetica-Bold", 10, DARK_TEXT_RGB)]
    if minutes.president_signed_by_id is not None:
        signed_local = minutes.president_signed_at.astimezone(tz)
        president_lines.append(
            (
                f"Signé électroniquement par {president_name}, Président, le "
                f"{signed_local.strftime('%d/%m/%Y')} à {signed_local.strftime('%H:%M')}",
                "Helvetica",
                9,
                MUTED_TEXT_RGB,
            )
        )
    draw_signature_box(MARGIN, "Président", president_lines)

    vp_x = MARGIN + box_width + gap
    if minutes.vp_signed_by_id is not None:
        vp_name = _user_full_name(minutes.vp_signed_by)
        signed_local = minutes.vp_signed_at.astimezone(tz)
        vp_lines = [
            (vp_name, "Helvetica-Bold", 10, DARK_TEXT_RGB),
            (
                f"Signé électroniquement par {vp_name}, Vice-président, le "
                f"{signed_local.strftime('%d/%m/%Y')} à {signed_local.strftime('%H:%M')}",
                "Helvetica",
                9,
                MUTED_TEXT_RGB,
            ),
        ]
        draw_signature_box(vp_x, "Vice-président", vp_lines)
    else:
        pdf.setStrokeColorRGB(*MUTED_TEXT_RGB)
        pdf.setLineWidth(0.5)
        pdf.rect(vp_x, box_top - box_height, box_width, box_height, fill=0, stroke=1)
        pdf.setFillColorRGB(*MUTED_TEXT_RGB)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(vp_x + 3 * mm, box_top - 5 * mm, "Vice-président")
        vacant_label = "Fonction exercée par le Président" if minutes.vp_role_held_by_president else "Poste vacant"
        draw_status_badge(pdf, vp_x + 3 * mm, box_top - 11 * mm, label=vacant_label, family="gray")
        pdf.setFillColorRGB(*DARK_TEXT_RGB)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(vp_x + 3 * mm, box_top - 17 * mm, "Signature non requise.")

    y = box_top - box_height - 6 * mm
    write_lines(
        "Signatures électroniques, enregistrées dans le journal d'activité du club.",
        font="Helvetica-Oblique",
        size=9,
    )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _generate_minutes_pdf(minutes: Minutes, *, now=None) -> Minutes:
    if minutes.generated_at is not None:
        return minutes
    now = now or timezone.now()
    pdf_bytes = _build_minutes_pdf(minutes)
    assembly = minutes.assembly
    type_slug = "ordinaire" if assembly.assembly_type == Assembly.AssemblyType.ORDINARY else "extraordinaire"
    filename = f"pv-ag-{type_slug}-{assembly.scheduled_date.isoformat()}.pdf"
    minutes.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
    minutes.generated_at = now
    minutes.save()
    if assembly.status != Assembly.Status.HELD:
        assembly.status = Assembly.Status.HELD
        assembly.save()
    return minutes


# ---------------------------------------------------------------------------
# Seuil de quorum (assemblees-page-ag.md §4.5, 10.2 n° 18)
# ---------------------------------------------------------------------------


def update_quorum_threshold(*, club, actor, percentage: Decimal, now=None) -> ClubSettings:
    if percentage is None or percentage < 1 or percentage > 100:
        raise AssemblyValidationError("Saisissez une valeur entre 1 et 100.")

    club_settings = _club_settings(club)
    before = {"assembly_quorum_percentage": str(club_settings.assembly_quorum_percentage)}
    club_settings.assembly_quorum_percentage = Decimal(percentage).quantize(Decimal("0.01"))
    club_settings.updated_by = actor
    club_settings.save()

    log_action(
        actor=actor,
        club=club,
        action_type="assemblies.quorum_threshold.updated",
        obj=club_settings,
        before=before,
        after={"assembly_quorum_percentage": str(club_settings.assembly_quorum_percentage)},
    )
    return club_settings


# ---------------------------------------------------------------------------
# Rappel la veille (cron, assemblees-page-ag.md §4.7)
# ---------------------------------------------------------------------------


def send_assembly_reminders(*, now=None) -> dict[str, int]:
    """Rappel la veille de l'AG (CDC 4.17), commande de gestion appelee par
    cron (CLAUDE.md section 4). Idempotent via ``Assembly.reminder_sent_at``."""

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    now = now or timezone.now()
    sent = 0

    assemblies = Assembly.all_objects.filter(
        status=Assembly.Status.SCHEDULED, reminder_sent_at__isnull=True
    ).select_related("club", "club__settings")

    for assembly in assemblies:
        club_settings = ClubSettings.objects.filter(club_id=assembly.club_id).first()
        if club_settings is None:
            continue
        try:
            today = now.astimezone(_club_tz(club_settings)).date()
        except AssemblyValidationError:
            continue
        if assembly.scheduled_date != today + timedelta(days=1):
            continue

        message = (
            f"Rappel : assemblée générale demain à {assembly.scheduled_time.strftime('%H:%M')}, "
            f"{assembly.location or 'lieu à confirmer'}."
        )
        memberships = Membership.all_objects.filter(
            club=assembly.club, status=Membership.Status.ACTIVE
        ).select_related("user")
        for membership in memberships:
            create_notification(
                recipient=membership.user,
                event_type=Notification.EventType.ASSEMBLY_REMINDER,
                message=message,
                club=assembly.club,
                target=assembly,
                now=now,
            )
        assembly.reminder_sent_at = now
        assembly.save(update_fields=["reminder_sent_at"])
        sent += 1

    return {"reminders_sent": sent}


# ---------------------------------------------------------------------------
# Archive des documents officiels (CDC 4.15.1 ; 10.3 n 169 et suivants)
# ---------------------------------------------------------------------------
#
# Les droits (ecriture : Secretaire, President, VP ; lecture : Bureau) sont
# verifies par les classes de permission des vues. Jamais de suppression en
# dur : retrait ou remplacement traces, journal a chaque depot, consultation,
# telechargement, remplacement et retrait (regle n 6). Aucun contenu du
# fichier n'est copie dans le journal (titre, categorie, date seulement).


def _archive_snapshot(document: ArchivedDocument) -> dict:
    return {
        "category": document.category,
        "title": document.title,
        "document_date": str(document.document_date),
        "status": document.status,
    }


def _create_archived_document(*, club, actor, category, title, document_date, file, replaces=None):
    title = (title or "").strip()
    if not title:
        raise AssemblyValidationError("Le titre du document est obligatoire.")
    if category not in ArchivedDocument.Category.values:
        raise AssemblyValidationError("Cette catégorie de document n'existe pas.")
    # Nom de stockage aleatoire a extension reelle (jamais celle du client).
    rename_upload_to_real_type(file)
    document = ArchivedDocument(
        club=club,
        category=category,
        title=title,
        document_date=document_date,
        file=file,
        uploaded_by=actor,
        replaces=replaces,
    )
    try:
        document.save()  # full_clean() : type reel et taille du fichier
    except DjangoValidationError as exc:
        raise AssemblyValidationError(" ".join(exc.messages)) from None
    return document


@transaction.atomic
def archive_document(*, club, actor, category: str, title: str, document_date: date, file) -> ArchivedDocument:
    """Depose un document dans l'archive du club, de facon atomique avec son
    entree de journal : si le journal echoue, la ligne est annulee et le
    fichier physique supprime."""

    document = _create_archived_document(
        club=club, actor=actor, category=category, title=title, document_date=document_date, file=file
    )
    try:
        log_action(
            actor=actor,
            club=club,
            action_type="assemblies.archived_document.created",
            obj=document,
            after=_archive_snapshot(document),
        )
    except Exception:
        document.file.delete(save=False)
        raise
    return document


@transaction.atomic
def replace_archived_document(
    *, document: ArchivedDocument, actor, category: str, title: str, document_date: date, file, now=None
) -> ArchivedDocument:
    """Remplace un document en vigueur : l'ancien est retire (motif
    « Remplace ») et conserve ; le nouveau le reference (``replaces``)."""

    now = now or timezone.now()
    document = _lock_archived_document(document)  # statut relu apres le verrou
    if document.status != ArchivedDocument.Status.ACTIVE:
        raise AssemblyValidationError("Ce document est déjà retiré ou remplacé : il ne peut pas être remplacé.")
    before = _archive_snapshot(document)
    new_document = _create_archived_document(
        club=document.club,
        actor=actor,
        category=category,
        title=title,
        document_date=document_date,
        file=file,
        replaces=document,
    )
    document.status = ArchivedDocument.Status.WITHDRAWN
    document.withdrawn_by = actor
    document.withdrawn_at = now
    document.withdrawn_reason = "Remplacé par un nouveau document."
    document.save()
    log_action(
        actor=actor,
        club=document.club,
        action_type="assemblies.archived_document.replaced",
        obj=document,
        before=before,
        after={**_archive_snapshot(document), "replaced_by": new_document.pk},
    )
    log_action(
        actor=actor,
        club=document.club,
        action_type="assemblies.archived_document.created",
        obj=new_document,
        after={**_archive_snapshot(new_document), "replaces": document.pk},
    )
    return new_document


def _lock_archived_document(document: ArchivedDocument) -> ArchivedDocument:
    """Verrouille la ligne du document (a appeler dans une transaction) et
    la relit : deux retraits/remplacements simultanes se serialisent et le
    second voit le statut deja modifie."""

    return ArchivedDocument.all_objects.select_for_update().get(pk=document.pk, club_id=document.club_id)


@transaction.atomic
def withdraw_archived_document(*, document: ArchivedDocument, actor, reason: str, now=None) -> ArchivedDocument:
    """Retire un document de l'archive (motif obligatoire, fichier conserve)."""

    reason = (reason or "").strip()
    if not reason:
        raise AssemblyValidationError("Indiquez le motif du retrait.")
    document = _lock_archived_document(document)  # statut relu apres le verrou
    if document.status != ArchivedDocument.Status.ACTIVE:
        raise AssemblyValidationError("Ce document est déjà retiré.")
    before = _archive_snapshot(document)
    document.status = ArchivedDocument.Status.WITHDRAWN
    document.withdrawn_by = actor
    document.withdrawn_at = now or timezone.now()
    document.withdrawn_reason = reason
    document.save()
    log_action(
        actor=actor,
        club=document.club,
        action_type="assemblies.archived_document.withdrawn",
        obj=document,
        before=before,
        after={**_archive_snapshot(document), "reason": reason},
    )
    return document


def record_archived_document_access(*, document: ArchivedDocument, actor, downloaded: bool) -> None:
    """Journalise la consultation (detail) ou le telechargement (regle n 6)."""

    log_action(
        actor=actor,
        club=document.club,
        action_type=(
            "assemblies.archived_document.downloaded" if downloaded else "assemblies.archived_document.viewed"
        ),
        obj=document,
        after={"title": document.title, "category": document.category},
    )


def filter_archived_documents(queryset, *, category: str = "", year: str = "", include_withdrawn: bool = False):
    """Filtres de la liste (categorie, annee du document, retires)."""

    if category:
        if category not in ArchivedDocument.Category.values:
            raise AssemblyValidationError("Cette catégorie de document n'existe pas.")
        queryset = queryset.filter(category=category)
    if year:
        if not year.isdigit() or len(year) != 4:
            raise AssemblyValidationError("L'année doit comporter 4 chiffres.")
        queryset = queryset.filter(document_date__year=int(year))
    if not include_withdrawn:
        queryset = queryset.filter(status=ArchivedDocument.Status.ACTIVE)
    return queryset
