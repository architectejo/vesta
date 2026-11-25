"""Service d'audit : ecriture d'entrees `AuditLog` (CLAUDE.md regle n6 ; CDC 5).

C'est l'unique point d'entree ecrivant dans `apps.audit.models.AuditLog` :
`apps.core.services.log_action` (l'interface stable utilisee par les
autres apps, deja posee tache 1.2) delegue a `create_audit_log`
ci-dessous.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timezone as dt_timezone
from typing import Any, Iterable, Mapping, Optional

from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.audit.models import AuditLog

__all__ = [
    "MEDICAL_ACTION_PREFIX",
    "CLINICAL_FIELD_BLACKLIST",
    "GHOST_ACTOR_DISPLAY_NAME",
    "MedicalContentInLogError",
    "assert_no_clinical_content",
    "create_audit_log",
    "get_actor_display_name",
    "ALERT_ACTION_TYPES",
    "filter_audit_logs",
    "is_medical_entry",
    "export_audit_logs_csv",
]

# CDC 5.4 : « Toute action faite par un Superuser dans un club s'affiche
# cote club comme "Action effectuee par le Systeme Vesta". »
GHOST_ACTOR_DISPLAY_NAME = "Systeme Vesta"


# CDC 5.2 « Medical » : « le contenu medical n'est pas copie dans le
# journal ». `medical.*` regroupe toutes les actions du domaine medical
# (consultation/modification de fiche de sante, octroi/revocation d'acces
# Président -- schema-donnees.md §6, §12.1).
MEDICAL_ACTION_PREFIX = "medical."

# Champs cliniques qui ne doivent jamais apparaitre dans `before`/`after`
# d'une entree `medical.*` (docs/lot0/schema-donnees.md §6.1 `HealthRecord`,
# §6.2 `Injury`, §6.3 `InjuryFollowUp`). Liste volontairement large et
# incluant des noms generiques (`diagnosis`, `notes`, `symptoms`...) : ce
# garde-fou reste utile meme si l'app `medical` (Lot 4) ajoute un jour un
# champ clinique non liste ici mot pour mot -- mieux vaut qu'un appel
# legitime soit rejete a tort (et corrige) que de laisser passer un
# contenu clinique par inadvertance.
CLINICAL_FIELD_BLACKLIST = frozenset(
    {
        # HealthRecord (schema §6.1)
        "blood_group",
        "allergies",
        "medical_history",
        "ongoing_treatments",
        "emergency_contact_name",
        "emergency_contact_phone",
        "self_declaration",
        # Injury (schema §6.2)
        "circumstances",
        "location_on_body",
        "severity",
        "on_site_care",
        "referral",
        "estimated_days_out",
        # InjuryFollowUp (schema §6.3)
        "note",
        # Noms generiques frequemment utilises pour du contenu clinique,
        # non lies a un nom de champ precis du schema actuel.
        "notes",
        "diagnosis",
        "symptoms",
        "treatment",
        "prescription",
    }
)


class MedicalContentInLogError(ValidationError):
    """Levee si un appel journalise du domaine medical contient du contenu clinique.

    CLAUDE.md regle n11 ; CDC 5.2 « Medical ». Rejette plutot que de
    filtrer silencieusement : un filtrage silencieux masquerait une
    erreur d'appel (l'appelant doit ne jamais construire `before`/`after`
    avec ces champs pour une action `medical.*`, pas s'en remettre a ce
    garde-fou pour les retirer a sa place).
    """


def _find_clinical_keys(value: Any) -> set[str]:
    """Cles cliniques presentes a n'importe quelle profondeur (dicts et
    listes imbriques), comparees sans tenir compte de la casse : un
    contenu medical glisse dans ``{"details": {"diagnosis": ...}}`` ne doit
    pas echapper au garde-fou."""

    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in CLINICAL_FIELD_BLACKLIST:
                found.add(key.lower())
            found |= _find_clinical_keys(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            found |= _find_clinical_keys(item)
    return found


def assert_no_clinical_content(
    action_type: str, payload: Optional[Mapping[str, Any]], *, field_label: str
) -> None:
    """Leve :class:`MedicalContentInLogError` si `payload` contient une cle cliniques.

    Ne s'applique qu'aux actions `medical.*` (:data:`MEDICAL_ACTION_PREFIX`) :
    un champ nomme par exemple ``notes`` n'a rien d'anormal en dehors de
    ce domaine (CDC 5.2, autres modules).
    """

    if not payload:
        return
    if not action_type or not action_type.startswith(MEDICAL_ACTION_PREFIX):
        return

    leaked = _find_clinical_keys(payload)
    if leaked:
        raise MedicalContentInLogError(
            "Contenu medical detecte dans le champ '{field}' d'une entree de "
            "journal '{action_type}' : les cles {leaked} ne doivent jamais "
            "etre copiees dans le journal (CLAUDE.md regle n11, CDC 5.2 "
            "« Medical »).".format(
                field=field_label, action_type=action_type, leaked=sorted(leaked)
            )
        )


def create_audit_log(
    *,
    actor,
    club=None,
    action_type: str,
    object_type: str,
    object_id: Any,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
    ip_address: str = "",
    user_agent: str = "",
    device: str = "",
    acted_as_ghost: bool = False,
    support_session_id: str = "",
) -> AuditLog:
    """Cree et enregistre une entree `AuditLog` (CDC 5.1).

    Applique les garde-fous non negociables avant toute ecriture :
    - un acteur reel est obligatoire, meme en Ghost Mode (CDC 5.4) ;
    - un type d'action et un objet concerne sont obligatoires (CDC 5.1) ;
    - aucun contenu medical n'est copie pour une action `medical.*`
      (:func:`assert_no_clinical_content`).

    Leve `django.core.exceptions.ValidationError` (ou une sous-classe) si
    l'un de ces garde-fous echoue : l'appel echoue explicitement plutot
    que d'ecrire une entree partielle ou incorrecte.
    """

    if actor is None:
        raise ValidationError(
            "Une entree de journal doit toujours porter un acteur reel, y "
            "compris en Ghost Mode (CDC 5.1, 5.4)."
        )
    if not action_type:
        raise ValidationError("Une entrée de journal doit porter un type d'action.")
    if not object_type or object_id in (None, ""):
        raise ValidationError(
            "Une entree de journal doit identifier l'objet concerne (type et identifiant, CDC 5.1)."
        )

    assert_no_clinical_content(action_type, before, field_label="before")
    assert_no_clinical_content(action_type, after, field_label="after")

    entry = AuditLog(
        club=club,
        actor=actor,
        acted_as_ghost=acted_as_ghost,
        support_session_id=support_session_id or "",
        action_type=action_type,
        object_type=object_type,
        object_id=str(object_id),
        before=before,
        after=after,
        ip_address=ip_address or "",
        user_agent=user_agent or "",
        device=device or "",
    )
    entry.save()
    return entry


def get_actor_display_name(entry: AuditLog, *, reader) -> str:
    """Nom d'acteur a afficher pour ``entry``, du point de vue de ``reader``
    (CDC 5.4 ; tache 1.8).

    Point de MASQUAGE CENTRALISE du Ghost Mode : toute vue/serializer qui
    expose un jour l'acteur d'une action a un club (journal, historique
    d'une adhesion, futur ecran de support...) doit passer par cette
    fonction plutot que de reimplementer la regle -- evite qu'un futur
    module l'oublie ou l'implemente differemment.

    - ``entry.acted_as_ghost`` faux : renvoie toujours l'identite reelle de
      ``entry.actor`` (prenom + nom), quel que soit ``reader`` -- rien a
      masquer.
    - ``entry.acted_as_ghost`` vrai ET ``reader`` n'est PAS un Superuser :
      renvoie ``"Systeme Vesta"`` (CDC 5.4) -- l'identite reelle du
      Superuser ne doit jamais transpirer cote club.
    - ``entry.acted_as_ghost`` vrai ET ``reader`` EST un Superuser (l'ecran
      de surveillance du journal, CDC 5.5, reserve aux Superusers) :
      renvoie l'identite reelle -- « Le journal conserve l'identite reelle
      du Superuser » (CDC 5.4) ; le masquage ne s'applique qu'a la vue
      "cote club", jamais a la vue Superuser elle-meme.
    """

    if entry.acted_as_ghost and not getattr(reader, "is_superuser", False):
        return GHOST_ACTOR_DISPLAY_NAME

    actor = entry.actor
    full_name = f"{getattr(actor, 'first_name', '')} {getattr(actor, 'last_name', '')}".strip()
    return full_name or getattr(actor, "email", "")


# ---------------------------------------------------------------------------
# Consultation Superuser (CDC 5.5 ; docs/ecrans/superuser-espace.md §3.4, §4.6)
# ---------------------------------------------------------------------------

# Interrupteur « Alertes seulement » (ecran §3.4) : le CDC 5.5 nomme quatre
# familles d'alertes sans fixer les identifiants d'action. Correspondance
# retenue par defaut (types reellement emis par le code a ce jour) :
# echecs de connexion repetes, annulations de paiements, derogations,
# rupture de la chaine financiere.
ALERT_ACTION_TYPES = frozenset(
    {
        "auth.login_failed",
        "auth.account_locked",
        "treasury.payment_reversal.approved",
        "treasury.expense.derogation_granted",
        "treasury.ledger.frozen",
    }
)


def is_medical_entry(entry: AuditLog) -> bool:
    return (entry.action_type or "").startswith(MEDICAL_ACTION_PREFIX)


def filter_audit_logs(
    queryset,
    *,
    club_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    action_types: Optional[Iterable[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    alerts_only: bool = False,
):
    """Applique les filtres de l'ecran Journal (CDC 5.5). Bornes de dates
    inclusives, interpretees en UTC (decision par defaut)."""

    if club_id is not None:
        queryset = queryset.filter(club_id=club_id)
    if actor_id is not None:
        queryset = queryset.filter(actor_id=actor_id)
    types = [t for t in (action_types or []) if t]
    if types:
        # Un element se terminant par « . » ou « * » filtre par prefixe.
        query = Q()
        for t in types:
            if t.endswith("*") or t.endswith("."):
                query |= Q(action_type__startswith=t.rstrip("*"))
            else:
                query |= Q(action_type=t)
        queryset = queryset.filter(query)
    if date_from is not None:
        queryset = queryset.filter(created_at__gte=datetime.combine(date_from, time.min, tzinfo=dt_timezone.utc))
    if date_to is not None:
        queryset = queryset.filter(created_at__lte=datetime.combine(date_to, time.max, tzinfo=dt_timezone.utc))
    if alerts_only:
        queryset = queryset.filter(action_type__in=ALERT_ACTION_TYPES)
    return queryset


def _csv_safe(text: Any) -> str:
    text = "" if text is None else str(text)
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def export_audit_logs_csv(entries: Iterable[AuditLog], *, reader) -> tuple[str, bytes]:
    """Export CSV (CDC 5.5). Separateur « ; », BOM UTF-8 (meme convention
    que la grille des cotisations). Colonnes : metadonnees uniquement ;
    ``before``/``after`` ne sont JAMAIS exportes (position prudente, 10.2
    n137 : aucun contenu medical dans l'export)."""

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        ["Horodatage (UTC)", "Club", "Acteur", "Session de support", "Action", "Type d'objet", "Identifiant de l'objet", "Adresse IP"]
    )
    for entry in entries:
        writer.writerow(
            [
                entry.created_at.astimezone(dt_timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                _csv_safe(entry.club.name if entry.club_id else ""),
                _csv_safe(get_actor_display_name(entry, reader=reader)),
                _csv_safe(entry.support_session_id),
                _csv_safe(entry.action_type),
                _csv_safe(entry.object_type),
                _csv_safe(entry.object_id),
                _csv_safe(entry.ip_address),
            ]
        )
    stamp = datetime.now(dt_timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"journal-{stamp}.csv", ("\ufeff" + buffer.getvalue()).encode("utf-8")
