"""Règles métier de l'app mercato (CDC 4.14 ; tâche 4.4).

Sources : docs/ecrans/mercato.md (spec validée) ; docs/lot0/schema-donnees.md
§8 ; règle non négociable n° 5 (« transfert bloqué si dette dans le club
d'origine, sinon quitus automatique ») ; CLAUDE.md section 5.

**Quitus et déblocage** : ce module appelle exclusivement
``apps.treasury.services.is_in_good_standing`` pour toute question
financière (CLAUDE.md : la trésorerie relève de ``finance-engine``) --
aucune règle de dette n'est dupliquée ici.

Décisions par défaut appliquées (à ne pas re-décider, signalées au compte
rendu) :

- **10.2 n° 30** : déblocage automatique dès que le solde redevient bon,
  sans nouvelle acceptation du joueur -- voir :func:`recheck_transfer_offer`,
  point d'entrée exposé pour un déclenchement à chaque paiement validé
  (``finance-engine``) et pour une commande cron de secours.
- **10.2 n° 34** : aucun champ ni logique de frais de sortie.
- **Convention déjà établie ailleurs dans le projet** (``apps.treasury.
  services.run_unjustified_expenses``, ``generate_monthly_dues``) : une
  transition purement automatique, sans acteur humain réel (cron, ou
  déblocage déclenché par un paiement validé par un tiers), n'écrit
  **aucune** entrée de journal -- ``AuditLog.actor`` est obligatoire et il
  n'existe aucun acteur réel à lui attribuer honnêtement. Une transition
  décidée par un humain (acceptation du joueur) journalise, elle,
  normalement avec cet acteur réel.
- **Messagerie inter-clubs** : lecture et écriture restreintes au
  Président et au Directeur sportif de chaque club (voir docstring de
  ``apps.mercato.models``, contradiction schéma/CDC non définitivement
  tranchée par le client).
- **Publication automatique sur le fil public** (CDC 4.14 étape 6, 4.16) :
  **non câblée** ici -- ``apps.social`` n'a encore aucun modèle `Post`
  (scaffolding vide à ce jour). Point ouvert signalé au compte rendu,
  à câbler par une migration additive quand `apps.social` existera.
"""

from __future__ import annotations

import datetime
import io
import re
import unicodedata
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from apps.clubs.models import ClubSettings, Membership, MembershipRole
from apps.core.roles import has_any_role
from apps.core.services import log_action
from apps.core.tenant import active_club
from apps.mercato.models import MercatoMessage, MercatoThread, TransferOffer

__all__ = [
    "MercatoError",
    "OFFER_INITIATOR_ROLES",
    "MESSAGING_ROLES",
    "set_market_availability",
    "transfer_offers_visible_to_club",
    "create_transfer_offer",
    "respond_to_offer",
    "recheck_transfer_offer",
    "recheck_transfers_for_membership",
    "recheck_all_blocked_transfers",
    "can_read_thread",
    "get_or_create_thread",
    "threads_visible_to",
    "send_message",
    "mark_thread_read",
]


class MercatoError(Exception):
    """Erreur métier de l'app mercato : refus renvoyé tel quel à l'API."""


# Matrice 2.4 : « Faire une offre » et « Messagerie entre clubs » -- É pour
# Président et Directeur sportif seulement (VP/Trés/Coach : L ou —).
OFFER_INITIATOR_ROLES = frozenset({MembershipRole.Role.PRESIDENT, MembershipRole.Role.SPORTS_DIRECTOR})
MESSAGING_ROLES = OFFER_INITIATOR_ROLES


def _officers(club) -> list:
    """Président et Directeur sportif en fonction de ``club`` (destinataires
    des notifications de suivi, fiche d'écran §8)."""

    roles = MembershipRole.all_objects.filter(
        club=club, role__in=OFFER_INITIATOR_ROLES, revoked_at__isnull=True
    ).select_related("membership__user")
    return [r.membership.user for r in roles]


# ---------------------------------------------------------------------------
# Fuseau horaire du club (meme convention que apps.assemblies.services et
# apps.sport.services ; CLAUDE.md §7 -- jamais l'heure UTC affichee ou
# evaluee telle quelle). Necessaire ici pour dater le quitus et pour
# evaluer la dette « au jour du club », pas au jour UTC (voir
# docs/annexes/modeles-documents.md §6.2, remarque hors gabarit).
# ---------------------------------------------------------------------------


def _club_settings(club) -> ClubSettings:
    club_settings = ClubSettings.objects.filter(club_id=club.id).first()
    if club_settings is None:
        raise MercatoError("Les paramètres du club (fuseau horaire) ne sont pas configurés.")
    return club_settings


def _club_tz(club_settings: ClubSettings) -> ZoneInfo:
    try:
        return ZoneInfo(club_settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise MercatoError("Le fuseau horaire du club est invalide.") from None


def _club_today(club, *, now: Optional[datetime.datetime] = None) -> datetime.date:
    now = now or timezone.now()
    return now.astimezone(_club_tz(_club_settings(club))).date()


_ASCII_FOLD = {
    "œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE", "ß": "ss",
}


def _ascii_slug(value: str) -> str:
    """ASCII, sans accents ni espaces (gabarit §2.1 : nom de fichier
    telecharge)."""

    value = "".join(_ASCII_FOLD.get(ch, ch) for ch in (value or ""))
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_only).strip("-")
    return slug or "document"


# ---------------------------------------------------------------------------
# Disponibilité (CDC 4.14 ; « Ma disponibilité »)
# ---------------------------------------------------------------------------


def set_market_availability(*, membership: Membership, actor, is_on_market: bool, now: Optional[datetime.datetime] = None) -> Membership:
    if getattr(actor, "id", None) != membership.user_id:
        raise MercatoError("Seul le joueur concerné peut changer sa propre disponibilité.")
    now = now or timezone.now()
    before = membership.is_on_transfer_market
    membership.is_on_transfer_market = bool(is_on_market)
    membership.market_status_changed_at = now
    membership.save()
    if before != membership.is_on_transfer_market:
        log_action(
            actor=actor,
            club=membership.club,
            action_type="mercato.availability.changed",
            obj=membership,
            before={"is_on_transfer_market": before},
            after={"is_on_transfer_market": membership.is_on_transfer_market},
        )
    return membership


# ---------------------------------------------------------------------------
# Offres de transfert
# ---------------------------------------------------------------------------


def transfer_offers_visible_to_club(club):
    """Offres où ``club`` est origine OU destinataire (étanchéité §2.1)."""

    from django.db.models import Q

    return TransferOffer.objects.filter(Q(origin_club=club) | Q(target_club=club)).select_related(
        "origin_club", "target_club", "target_membership__user", "initiated_by"
    )


def create_transfer_offer(
    *, initiated_by, target_club, target_membership: Membership, message: str, conditions: str = "", now: Optional[datetime.datetime] = None
) -> TransferOffer:
    if not has_any_role(initiated_by, OFFER_INITIATOR_ROLES, club=target_club):
        raise MercatoError("Réservé au Président et au Directeur sportif (CDC 2.4, 4.14).")
    if target_membership.club_id == target_club.id:
        raise MercatoError("Ce joueur appartient déjà à votre club.")
    if target_membership.status != Membership.Status.ACTIVE:
        raise MercatoError("Ce joueur n'est plus disponible.")
    if not target_membership.is_on_transfer_market:
        raise MercatoError(f"{target_membership.user.first_name} n'est plus sur le marché.")
    if not (message or "").strip():
        raise MercatoError("Le message est obligatoire.")

    now = now or timezone.now()
    offer = TransferOffer(
        origin_club=target_membership.club,
        target_club=target_club,
        target_membership=target_membership,
        initiated_by=initiated_by,
        message=message,
        conditions=conditions or "",
        created_at=now,
    )
    offer.save()

    log_action(
        actor=initiated_by,
        club=target_club,
        action_type="mercato.transfer_offer.created",
        obj=offer,
        after={"target_membership_id": target_membership.pk, "origin_club_id": offer.origin_club_id},
    )

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    create_notification(
        recipient=target_membership.user,
        event_type=Notification.EventType.TRANSFER_OFFER,
        title=f"Offre de transfert de {target_club.name}",
        message=f"{target_club.name} vous propose de le rejoindre. Ouvrez l'offre pour l'accepter ou la refuser.",
        club=offer.origin_club,
        target=offer,
        now=now,
    )
    for officer in _officers(offer.origin_club):
        create_notification(
            recipient=officer,
            event_type=Notification.EventType.TRANSFER_OFFER,
            title=f"Offre de {target_club.name} pour {target_membership.user.first_name}",
            message=(
                f"{target_club.name} a fait une offre de transfert à "
                f"{target_membership.user.first_name} {target_membership.user.last_name}. Le joueur décide seul ; "
                "aucune action n'est attendue de votre part."
            ),
            club=offer.origin_club,
            target=offer,
            now=now,
        )
    for officer in _officers(target_club):
        if officer.id == getattr(initiated_by, "id", None):
            continue
        create_notification(
            recipient=officer,
            event_type=Notification.EventType.TRANSFER_OFFER,
            title=f"Offre envoyée à {target_membership.user.first_name}",
            message=f"Une offre a été envoyée à {target_membership.user.first_name} ({offer.origin_club.name}).",
            club=target_club,
            target=offer,
            now=now,
        )
    return offer


def respond_to_offer(*, offer: TransferOffer, actor, accept: bool, now: Optional[datetime.datetime] = None) -> TransferOffer:
    if offer.target_membership.user_id != getattr(actor, "id", None):
        raise MercatoError("Seul le joueur visé peut répondre à cette offre.")
    if offer.status != TransferOffer.Status.SENT:
        raise MercatoError("Cette offre n'est plus en attente.")

    now = now or timezone.now()

    if not accept:
        offer.status = TransferOffer.Status.DECLINED_BY_PLAYER
        offer.player_decision_by = actor
        offer.player_decision_at = now
        offer.save()
        log_action(
            actor=actor,
            club=offer.target_club,
            action_type="mercato.transfer_offer.declined",
            obj=offer,
            after={"status": offer.status},
        )
        from apps.notifications.models import Notification
        from apps.notifications.services import create_notification

        name = f"{offer.target_membership.user.first_name} {offer.target_membership.user.last_name}"
        for officer in _officers(offer.target_club):
            create_notification(
                recipient=officer,
                event_type=Notification.EventType.TRANSFER_OFFER,
                title=f"{name} a refusé votre offre",
                message=f"{name} a refusé l'offre de {offer.target_club.name}.",
                club=offer.target_club,
                target=offer,
                now=now,
            )
        return offer

    offer.player_decision_by = actor
    offer.player_decision_at = now
    offer.status = TransferOffer.Status.ACCEPTED_BY_PLAYER
    offer.save()
    log_action(
        actor=actor,
        club=offer.target_club,
        action_type="mercato.transfer_offer.accepted",
        obj=offer,
        after={"status": offer.status},
    )
    return _evaluate_debt_and_progress(offer, actor=actor, now=now)


def _evaluate_debt_and_progress(offer: TransferOffer, *, actor=None, now: Optional[datetime.datetime] = None) -> TransferOffer:
    """Vérifie le solde du joueur dans le club d'origine et fait progresser
    l'offre (règle non négociable n° 5, 10.2 n° 30). ``actor`` est ``None``
    pour une évaluation automatique (cron, relecture, déblocage déclenché
    par un paiement) -- voir convention documentée en tête de module."""

    from apps.treasury.services import is_in_good_standing

    now = now or timezone.now()
    # Date du jour dans le fuseau du club d'origine, pas la date UTC de
    # ``now`` (CLAUDE.md §7) : autour de minuit, la date UTC et la date au
    # club peuvent differer d'un jour et faire compter ou non l'echeance du
    # jour (docs/annexes/modeles-documents.md §6.2, remarque hors gabarit).
    today = _club_today(offer.origin_club, now=now)
    in_order, amount_due, _reason = is_in_good_standing(offer.target_membership, at_date=today)
    offer.debt_checked_at = now

    if in_order:
        offer.debt_amount = None
        return complete_transfer(offer, actor=actor, now=now)

    was_blocked = offer.status == TransferOffer.Status.BLOCKED_DEBT
    offer.status = TransferOffer.Status.BLOCKED_DEBT
    offer.debt_amount = amount_due
    offer.save()

    if actor is not None:
        log_action(
            actor=actor,
            club=offer.target_club,
            action_type="mercato.transfer_offer.blocked",
            obj=offer,
            after={"status": offer.status, "debt_amount": str(amount_due)},
        )

    if not was_blocked:
        from apps.notifications.models import Notification
        from apps.notifications.services import create_notification

        create_notification(
            recipient=offer.target_membership.user,
            event_type=Notification.EventType.TRANSFER_OFFER,
            title=f"Transfert bloqué : {amount_due} à régulariser",
            message=(
                f"Votre transfert vers {offer.target_club.name} se fera automatiquement dès que votre solde "
                f"auprès de {offer.origin_club.name} sera à jour."
            ),
            club=offer.origin_club,
            target=offer,
            now=now,
        )
        for officer in _officers(offer.target_club):
            create_notification(
                recipient=officer,
                event_type=Notification.EventType.TRANSFER_OFFER,
                title=f"Quitus en attente pour {offer.target_membership.user.first_name}",
                message=(
                    f"{offer.target_membership.user.first_name} a accepté votre offre. Le transfert se fera "
                    "dès que son club actuel pourra établir le quitus."
                ),
                club=offer.target_club,
                target=offer,
                now=now,
            )
    return offer


def recheck_transfer_offer(offer: TransferOffer, *, now: Optional[datetime.datetime] = None) -> TransferOffer:
    """Relit l'état financier d'une offre ``blocked_debt`` et la débloque
    automatiquement si le solde est redevenu bon (10.2 n° 30). Point
    d'entrée SANS acteur humain : utilisé par la relecture régulière de
    l'interface (à chaque ouverture de page/modale), par
    :func:`recheck_transfers_for_membership` (hook pour finance-engine,
    déclenché à chaque paiement validé) et par la commande cron de
    secours. Idempotent et sans effet si l'offre n'est pas bloquée."""

    if offer.status != TransferOffer.Status.BLOCKED_DEBT:
        return offer
    with active_club(None):
        return _evaluate_debt_and_progress(offer, actor=None, now=now)


def recheck_transfers_for_membership(membership: Membership, *, now: Optional[datetime.datetime] = None) -> list[TransferOffer]:
    """Hook exposé pour ``finance-engine`` : à appeler après la validation
    d'un paiement du joueur ``membership`` (CDC 4.14 §5.1 étape 5 : « cette
    vérification est déclenchée à chaque paiement validé du joueur »)."""

    offers = TransferOffer.objects.filter(target_membership=membership, status=TransferOffer.Status.BLOCKED_DEBT)
    return [recheck_transfer_offer(offer, now=now) for offer in offers]


def recheck_all_blocked_transfers(*, now: Optional[datetime.datetime] = None) -> int:
    """Balayage périodique de secours (commande cron) : le 4.14 §5.1 précise
    que la vérification n'est « pas seulement » déclenchée par un cron
    périodique -- ce balayage reste un filet de sécurité, idempotent."""

    count = 0
    for offer in TransferOffer.objects.filter(status=TransferOffer.Status.BLOCKED_DEBT):
        result = recheck_transfer_offer(offer, now=now)
        if result.status == TransferOffer.Status.COMPLETED:
            count += 1
    return count


def _quitus_reference(offer: TransferOffer) -> str:
    return f"Q-{offer.pk}"


def _build_quitus_pdf(offer: TransferOffer, *, now: datetime.datetime) -> bytes:
    """Quitus numérique aux couleurs du club A (émetteur), gabarit validé
    docs/annexes/modeles-documents.md §2. Une seule page, aucun montant,
    aucune référence au cahier des charges sur le document remis à un
    autre club (§2.3) -- seul le fait attesté (« en ordre ») y figure."""

    from apps.core.pdf import (
        DARK_TEXT_RGB,
        MARGIN,
        MUTED_TEXT_RGB,
        STATUS_COLORS,
        NumberedDocumentCanvas,
        club_stripe_colors,
        draw_header,
        draw_status_badge,
        format_date_longue,
        make_footer_drawer,
        wrap_text,
    )

    club = offer.origin_club
    membership = offer.target_membership
    player = membership.user
    club_settings = _club_settings(club)
    tz = _club_tz(club_settings)

    established_at = (offer.quitus_generated_at or now).astimezone(tz)
    checked_at = (offer.debt_checked_at or now).astimezone(tz)

    doc_type_label = "Quitus de transfert"
    reference = _quitus_reference(offer)
    generated_at_text = f"{established_at.strftime('%d/%m/%Y')} à {established_at.strftime('%H:%M')}"

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

    def write_lines(text: str, *, font: str = "Helvetica", size: float = 10, color=DARK_TEXT_RGB) -> None:
        nonlocal y
        pdf.setFillColorRGB(*color)
        for raw_line in (text or "").split("\n"):
            for wline in wrap_text(raw_line, font=font, size=size, max_width=content_width):
                pdf.setFont(font, size)
                pdf.drawString(MARGIN, y, wline)
                y -= size * 1.35

    def section_title(text: str) -> None:
        nonlocal y
        pdf.setFillColorRGB(*DARK_TEXT_RGB)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(MARGIN, y, text)
        y -= 3 * mm
        primary, _secondary = club_stripe_colors(club)
        pdf.setStrokeColorRGB(*primary)
        pdf.setLineWidth(0.5)
        pdf.line(MARGIN, y, MARGIN + content_width, y)
        y -= 6 * mm

    label_col = 42 * mm

    def field_row(label: str, value: str) -> None:
        nonlocal y
        pdf.setFillColorRGB(*MUTED_TEXT_RGB)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(MARGIN, y, label)
        lines = wrap_text(value, font="Helvetica", size=10, max_width=content_width - label_col)
        pdf.setFillColorRGB(*DARK_TEXT_RGB)
        for line in lines:
            pdf.setFont("Helvetica", 10)
            pdf.drawString(MARGIN + label_col, y, line)
            y -= 10 * 1.35

    # -- Titre et sous-titre (§2.3 lignes 2-3) --------------------------
    pdf.setFillColorRGB(*DARK_TEXT_RGB)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(MARGIN, y, doc_type_label)
    y -= 16 * 1.2
    write_lines(
        f"Établi le {format_date_longue(established_at.date())} à {established_at.strftime('%H:%M')}",
        size=10,
        color=MUTED_TEXT_RGB,
    )
    y -= 6 * mm

    # -- Joueur (§2.3 lignes 4-6) ----------------------------------------
    section_title("Joueur")
    field_row("Nom", f"{player.first_name} {player.last_name}")
    position_label = membership.get_position_display() if membership.position else ""
    if position_label:
        field_row("Poste", position_label)
    if membership.joined_on and membership.left_on:
        field_row(
            f"Membre de {club.name}",
            f"du {membership.joined_on.strftime('%d/%m/%Y')} au {membership.left_on.strftime('%d/%m/%Y')}",
        )
    y -= 3 * mm

    # -- Transfert (§2.3 lignes 7-10) -------------------------------------
    section_title("Transfert")
    field_row("Club quitté", f"{offer.origin_club.name} ({offer.origin_club.city})")
    field_row("Club rejoint", f"{offer.target_club.name} ({offer.target_club.city})")
    if offer.player_decision_at:
        field_row("Offre acceptée le", offer.player_decision_at.astimezone(tz).strftime("%d/%m/%Y"))
    if offer.completed_at:
        field_row("Transfert effectué le", offer.completed_at.astimezone(tz).strftime("%d/%m/%Y"))
    y -= 5 * mm

    # -- Cadre « Attestation » (§2.3 lignes 11-14) : c'est l'objet meme du
    # document -- badge « En ordre » et date/heure de verification.
    frame_padding = 4 * mm
    frame_top = y
    inner_x = MARGIN + frame_padding
    inner_width = content_width - 2 * frame_padding
    inner_y = frame_top - frame_padding

    draw_status_badge(pdf, inner_x, inner_y - 1.5 * mm, label="En ordre", family="green")
    inner_y -= 9 * mm

    attestation_lines = [
        (
            f"{club.name} atteste que {player.first_name} {player.last_name} n'a aucune dette envers le club "
            f"à la date du {format_date_longue(checked_at.date())}.",
            "Helvetica",
            10,
        ),
        (
            f"Solde vérifié automatiquement le {checked_at.strftime('%d/%m/%Y')} à {checked_at.strftime('%H:%M')}.",
            "Helvetica",
            9,
        ),
        (f"Aucun frais de sortie n'est dû à {club.name}.", "Helvetica", 9),
    ]
    for text, font, size in attestation_lines:
        pdf.setFillColorRGB(*DARK_TEXT_RGB)
        for wline in wrap_text(text, font=font, size=size, max_width=inner_width):
            pdf.setFont(font, size)
            pdf.drawString(inner_x, inner_y, wline)
            inner_y -= size * 1.35

    inner_y -= frame_padding
    frame_bottom = inner_y
    pdf.setStrokeColorRGB(*STATUS_COLORS["green"]["dot"])
    pdf.setLineWidth(0.75)
    pdf.rect(MARGIN, frame_bottom, content_width, frame_top - frame_bottom, fill=0, stroke=1)
    y = frame_bottom - 8 * mm

    # -- Mention finale (§2.3 ligne 15) -----------------------------------
    write_lines(
        "Ce quitus est établi automatiquement après vérification du solde du joueur. Il ne comporte pas de "
        "signature manuscrite. Il atteste la situation du joueur à la date de vérification.",
        font="Helvetica-Oblique",
        size=9,
        color=MUTED_TEXT_RGB,
    )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def complete_transfer(offer: TransferOffer, *, actor=None, now: Optional[datetime.datetime] = None) -> TransferOffer:
    """Finalise le transfert : quitus, clôture de l'adhésion au club A,
    ouverture d'une adhésion « En attente » au club B (règle non négociable
    n° 5, 10.2 n° 30). ``actor`` est ``None`` pour un déblocage automatique
    (voir convention documentée en tête de module)."""

    now = now or timezone.now()
    origin_membership = offer.target_membership

    with transaction.atomic():
        with active_club(None):
            # Date du jour dans le fuseau de chaque club (CLAUDE.md §7),
            # pas la date UTC de ``now`` -- meme correction que le controle
            # de dette (voir docstring de :func:`_evaluate_debt_and_progress`).
            origin_membership.status = Membership.Status.DEPARTED
            origin_membership.left_on = _club_today(offer.origin_club, now=now)
            origin_membership.left_reason = Membership.LeftReason.TRANSFER
            origin_membership.left_by = actor or origin_membership.user
            origin_membership.is_on_transfer_market = False
            origin_membership.save()

            new_membership = Membership(
                club=offer.target_club,
                user=origin_membership.user,
                status=Membership.Status.PENDING,
                position=origin_membership.position,
                joined_on=_club_today(offer.target_club, now=now),
                added_by=offer.initiated_by,
            )
            new_membership.save()

        quitus_bytes = _build_quitus_pdf(offer, now=now)
        player = origin_membership.user
        quitus_date = _club_today(offer.origin_club, now=now)
        filename = f"quitus-{_ascii_slug(player.last_name)}-{_ascii_slug(player.first_name)}-{quitus_date.isoformat()}.pdf"
        offer.quitus_file.save(filename, ContentFile(quitus_bytes), save=False)
        offer.quitus_generated_at = now
        offer.status = TransferOffer.Status.COMPLETED
        offer.completed_at = now
        offer.new_membership = new_membership
        offer.debt_amount = None
        offer.save()

    if actor is not None:
        log_action(
            actor=actor,
            club=offer.target_club,
            action_type="mercato.transfer_offer.completed",
            obj=offer,
            after={"status": offer.status, "new_membership_id": new_membership.pk},
        )

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    create_notification(
        recipient=origin_membership.user,
        event_type=Notification.EventType.TRANSFER_OFFER,
        title=f"Transfert effectué : bienvenue à {offer.target_club.name}",
        message=(
            f"Votre solde auprès de {offer.origin_club.name} est à jour. Votre quitus a été établi et vous êtes "
            f"maintenant membre de {offer.target_club.name}."
        ),
        club=offer.target_club,
        target=offer,
        now=now,
    )
    for officer in _officers(offer.origin_club):
        create_notification(
            recipient=officer,
            event_type=Notification.EventType.TRANSFER_OFFER,
            title=f"Transfert effectué : {origin_membership.user.first_name} rejoint {offer.target_club.name}",
            message=f"{origin_membership.user.first_name} {origin_membership.user.last_name} a rejoint {offer.target_club.name}.",
            club=offer.origin_club,
            target=offer,
            now=now,
        )
    for officer in _officers(offer.target_club):
        create_notification(
            recipient=officer,
            event_type=Notification.EventType.TRANSFER_OFFER,
            title=f"{origin_membership.user.first_name} a rejoint {offer.target_club.name}",
            message="Son quitus a été établi. Son adhésion est en attente du paiement des frais d'adhésion.",
            club=offer.target_club,
            target=offer,
            now=now,
        )
    return offer


# ---------------------------------------------------------------------------
# Messagerie inter-clubs (CDC 4.14 ; §2.1 point 5, position provisoire)
# ---------------------------------------------------------------------------


def can_read_thread(user, thread: MercatoThread) -> bool:
    return has_any_role(user, MESSAGING_ROLES, club=thread.club_a) or has_any_role(
        user, MESSAGING_ROLES, club=thread.club_b
    )


def threads_visible_to(user, club) -> "list[MercatoThread]":
    """Fils où ``club`` est l'une des deux parties ET où ``user`` porte le
    rôle Président/DS de ``club`` (position provisoire, la plus prudente,
    appliquée à la contradiction schéma §8.2 / CDC 4.14)."""

    from django.db.models import Q

    if not has_any_role(user, MESSAGING_ROLES, club=club):
        return MercatoThread.objects.none()
    return MercatoThread.objects.filter(Q(club_a=club) | Q(club_b=club)).order_by("-created_at")


def get_or_create_thread(*, club_a, club_b, subject: str = "", transfer_offer: TransferOffer = None, now=None) -> MercatoThread:
    now = now or timezone.now()
    a, b = (club_a, club_b) if club_a.pk < club_b.pk else (club_b, club_a)
    thread = MercatoThread.objects.filter(club_a=a, club_b=b).first()
    if thread is not None:
        return thread
    thread = MercatoThread(club_a=a, club_b=b, subject=subject or "", transfer_offer=transfer_offer, created_at=now)
    thread.save()
    return thread


def send_message(*, thread: MercatoThread, actor, club, body: str, now=None) -> MercatoMessage:
    if not has_any_role(actor, MESSAGING_ROLES, club=club):
        raise MercatoError("Réservé au Président et au Directeur sportif (CDC 4.14).")
    if club.id not in (thread.club_a_id, thread.club_b_id):
        raise MercatoError("Ce fil ne concerne pas votre club.")
    if not (body or "").strip():
        raise MercatoError("Le message est obligatoire.")
    now = now or timezone.now()
    message = MercatoMessage(club=club, thread=thread, sender=actor, body=body, sent_at=now)
    message.save()
    log_action(actor=actor, club=club, action_type="mercato.message.sent", obj=message, after={"thread_id": thread.pk})

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    other_club_id = thread.other_club_id(club.id)
    other_club = thread.club_a if other_club_id == thread.club_a_id else thread.club_b
    for officer in _officers(other_club):
        create_notification(
            recipient=officer,
            event_type=Notification.EventType.TRANSFER_OFFER,
            title=f"Nouveau message de {club.name}",
            message=(message.body[:140]),
            club=other_club,
            target=thread,
            now=now,
        )
    return message


def mark_thread_read(*, thread: MercatoThread, user, club, now=None) -> int:
    now = now or timezone.now()
    return MercatoMessage.objects.filter(thread=thread, read_at__isnull=True).exclude(club=club).update(read_at=now)
