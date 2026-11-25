"""Regles metier de l'app treasury (tache 1.4b -- forme definitive).

Sources : CDC 4.3, 4.4.1, 4.4.4, 4.6, 5.3, 7.2 ; 10.2 n° 36 ;
docs/lot0/schema-treasury.md §4.1, §5.1, §5.3, §6.1-6.4, §9, §10, §13.

Perimetre construit a ce stade
------------------------------
- Types de cotisation : creation, archivage, suppression d'un type jamais
  utilise (CDC 4.4.1 ; invariant 7, partie « archiver seulement »).
- Paiement des frais d'adhesion saisi par le Tresorier ou l'adjoint, valide
  apres confirmation dans l'interface (source ``treasurer_entry``) -- **point d'entree pour
  `backend-dev`** : :func:`record_membership_fee_payment` et
  :func:`has_paid_membership_fee`.
- Grand livre chaine (CDC 5.3) : scellement atomique HMAC-SHA256,
  immuabilite, gel du club, fonction de verification :func:`verify_chain`
  (la commande cron quotidienne et l'alerte Superuser qui l'appelleront
  sont une tache ulterieure).
- Annulations (CDC 4.4.4) et remboursement des frais d'adhesion apres refus
  du parrain (CDC 4.3 ; decision D9, a confirmer).

Tache 2.2 (Lot 2) : montants dus, solde et « En ordre », repartition
mensuelle, puis depenses (categories, circuit, blocage, derogation, caisse
disponible) et assistance sociale (bareme, eligibilite, demandes) -- voir
la section « Depenses et assistance sociale » en fin de module.

Tache 2.3 (Lot 2) : traitements periodiques appeles par les commandes cron
(generation des montants dus, verification quotidienne de la chaine,
depenses non justifiees) -- section « Traitements periodiques » en fin de
module.

Tache 2.4 (Lot 2) : enregistrement general d'un paiement (apercu de la
repartition sans ecriture, validation confirmee par une modale) et Caisse
Terrain Express (session de caisse, encaissements y compris hors connexion,
recherche de joueurs) -- sections du meme nom.

Tache 2.5 (Lot 2) : paiement en ligne phase 1 (CDC 4.6) -- lien de
paiement du club, declaration « J'ai paye » par le joueur, validation par
confirmation en modale ou refus motive par le Tresorier ou l'adjoint -- section « Paiement en
ligne ». Aucun modele nouveau : ``Transaction.provider``/``external_ref``/
``status`` preparent deja FlexPaie (phase 2).

Tache 2.6 (Lot 2) : grille des cotisations (CDC 4.4.7, calculee, export
CSV) et import des cotisations historiques CSV (CDC 4.4.8, apercu puis
import definitif) -- sections du meme nom en fin de module.

Hors perimetre : FlexPaie (phase 2).

Recu PDF (CDC 4.4.4) : numero attribue au scellement (:func:`_seal`), PDF
emis apres validation effective en base -- section « Recu de paiement »
en fin de module (:func:`issue_payment_receipt`).

Conventions
-----------
- Le club vient **toujours** de l'adhesion concernee (CLAUDE.md regle n9),
  jamais d'un parametre transmis par le client.
- Lectures/ecritures via ``all_objects`` **avec un filtre explicite par
  club** : ces services sont appeles aussi bien depuis une requete HTTP
  (club actif positionne) que depuis une commande ou un test. Une ecriture
  dans un autre club que le club actif reste refusee par
  ``TenantModel.save()`` (``TenantMismatchError``).
- Plus aucun code PIN (decision du 11/10/2026, CLAUDE.md regle 7) : les
  actions sensibles sont confirmees par une modale cote interface ; l'auteur
  est ecrit au journal.
- Toute creation ou changement d'etat est journalise (CLAUDE.md regle n6).
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import logging
import re
import unicodedata
import uuid
import time as _time
from dataclasses import dataclass
from functools import partial, wraps
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from datetime import timezone as dt_timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Iterable, NamedTuple, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, OperationalError
from django.db import transaction as db_transaction
from django.db.models import Count, Max, Min, Q, Sum
from django.utils import timezone
from django.utils.text import slugify

from apps.clubs.models import ClubSettings, ImportBatch, Membership, MembershipRole
from apps.core.private_files import rename_upload_to_real_type
from apps.core.roles import get_active_roles
from apps.core.services import log_action
from apps.core.tenant import TenantMismatchError, get_active_club
from apps.core.tenant import active_club as _active_club_context
from apps.core.validators import validate_csv_file, validate_image_or_pdf, validate_upload_size
from apps.treasury.models import (
    CashSession,
    ContributionType,
    ContributionTypeRate,
    ContributionAssignment,
    ContributionSuspension,
    DebtDueNotice,
    Due,
    DueCancellation,
    Expense,
    ExpenseAttachment,
    ExpenseCategory,
    ExpenseDerogation,
    LedgerChainState,
    Payment,
    PaymentAllocation,
    PaymentReversal,
    SocialAssistanceEvent,
    SocialAssistanceRequest,
    SocialAssistanceScale,
    Transaction,
    approved_reversal_exists,
    reversal_prefetch,
)

__all__ = [
    # Erreurs
    "TreasuryError",
    "TreasuryValidationError",
    "TreasuryPermissionError",
    "InvalidAmountError",
    "LedgerFrozenError",
    "LedgerKeyError",
    # Montants
    "to_money",
    # Types de cotisation
    "create_contribution_type",
    "update_contribution_type",
    "archive_contribution_type",
    "delete_contribution_type",
    "get_active_membership_fee_type",
    "create_contribution_assignment",
    "end_contribution_assignment",
    "create_contribution_suspension",
    "end_contribution_suspension",
    "generate_dues_for_period",
    "get_balance",
    "get_balances",
    "is_in_good_standing",
    "BalanceSummary",
    "get_balance_summary",
    "allocate_payment",
    "refresh_member_allocations",
    # Frais d'adhesion (interface backend-dev)
    "record_membership_fee_payment",
    "has_paid_membership_fee",
    "refund_membership_fee",
    "ensure_membership_fee_due",
    "cancel_membership_fee_due",
    "rebalance_membership_fee_dues",
    # Enregistrement d'un paiement (tache 2.4)
    "AllocationPreviewLine",
    "PaymentPreview",
    "preview_payment_allocation",
    "record_payment",
    # Caisse Terrain Express (tache 2.4)
    "CashSessionNotFoundError",
    "CashSessionNotValidError",
    "ClientUuidConflictError",
    "CashPlayerResult",
    "cash_session_expiry",
    "cash_session_state",
    "cash_session_totals",
    "get_current_cash_session",
    "get_owned_cash_session",
    "open_cash_session",
    "close_cash_session",
    "get_default_contribution_type",
    "get_default_contribution_type_ids",
    "search_cash_session_players",
    "preview_cash_payment",
    "record_cash_payment",
    # Paiement en ligne, phase 1 : lien externe et « J'ai paye » (tache 2.5)
    "PaymentLinkNotConfiguredError",
    "DeclarationAlreadyProcessedError",
    "ContributeInfo",
    "get_payment_link",
    "get_declarable_contribution_types",
    "get_contribute_info",
    "declare_payment",
    "preview_declared_payment",
    "validate_declared_payment",
    "reject_declared_payment",
    "payment_status_key",
    "PAYMENT_STATUS_LABELS",
    # Annulations
    "request_payment_reversal",
    "approve_payment_reversal",
    "reject_payment_reversal",
    # Grand livre
    "LEDGER_GENESIS_HASH",
    "open_payment_transaction",
    "advance_transaction",
    "transaction_canonical_payload",
    "compute_transaction_hash",
    "freeze_ledger",
    "verify_chain",
    "ChainVerificationResult",
    # Depenses (tache 2.2)
    "ExpenseReleaseBlockedError",
    "ExpenseReleaseCheck",
    "create_expense_category",
    "update_expense_category",
    "archive_expense_category",
    "create_expense",
    "refuse_expense",
    "can_release_expense",
    "release_expense",
    "release_expense_with_derogation",
    "justify_expense",
    "mark_overdue_expenses_unjustified",
    "is_expense_overdue",
    "get_available_cash",
    # Assistance sociale (tache 2.2)
    "SocialAssistanceEligibility",
    "SocialAssistancePreview",
    "create_social_assistance_scale",
    "update_social_assistance_scale",
    "archive_social_assistance_scale",
    "get_social_assistance_eligibility",
    "get_social_assistance_preview",
    "submit_social_assistance_request",
    "approve_social_assistance_request",
    "reject_social_assistance_request",
    # Capacites et parametres exposes a l'interface
    "get_treasury_capabilities",
    "get_club_currency",
    "get_club_today",
    # Traitements periodiques (cron, tache 2.3)
    "MonthlyDuesRun",
    "LedgerVerificationOutcome",
    "get_club_current_period",
    "run_monthly_dues",
    "run_ledger_verification",
    "run_unjustified_expenses",
    # Grille des cotisations et import historique (tache 2.6)
    "GRID_READERS",
    "CONTRIBUTION_IMPORTERS",
    "GRID_STATE_LABELS",
    "GridCell",
    "GridRow",
    "ContributionGrid",
    "GridMonthDetail",
    "build_contribution_grid",
    "filter_grid_rows",
    "get_balance_summaries",
    "get_grid_month_detail",
    "get_grid_contribution_types",
    "export_contribution_grid_csv",
    "ContributionImportError",
    "ContributionImportReport",
    "preview_contribution_import",
    "import_contributions",
    # Recu de paiement PDF (CDC 4.4.4)
    "RECEIPT_DOC_TYPE_LABEL",
    "format_receipt_amount",
    "issue_payment_receipt",
    "payments_missing_receipt",
    "ReceiptJournalError",
    # Dette constatee a l'echeance (CDC 4.17)
    "DEBT_NOTICE_LOOKBACK_DAYS",
    "DebtDueRun",
    "run_debt_due_notifications",
]


# ---------------------------------------------------------------------------
# Erreurs (messages en francais clair, CLAUDE.md regle n20)
# ---------------------------------------------------------------------------


class TreasuryError(Exception):
    """Base de toutes les erreurs metier de la tresorerie."""


class TreasuryValidationError(TreasuryError):
    """Donnee invalide ou etat incompatible avec l'action demandee."""


class TreasuryPermissionError(TreasuryError, PermissionError):
    """L'acteur n'a pas le role requis dans le club concerne (CDC 2.4)."""


class InvalidAmountError(TreasuryValidationError):
    """Montant illisible, en `float`, nul ou negatif (invariant 12)."""


class LedgerFrozenError(TreasuryError):
    """Ecritures financieres du club gelees apres une rupture de chaine (CDC 5.3)."""


class LedgerKeyError(TreasuryError):
    """Cle de chainage absente ou invalide dans l'environnement (CDC 5.3, regle n12)."""


# ---------------------------------------------------------------------------
# Outils internes
# ---------------------------------------------------------------------------

MONEY_QUANTUM = Decimal("0.01")
MONEY_MAX = Decimal("9999999999.99")  # DecimalField(max_digits=12, decimal_places=2)
LEDGER_GENESIS_HASH = "0" * 64
MIN_LEDGER_KEY_LENGTH = 32
# Version du format canonique hache (``Transaction.payload_version``).
# v1 : format d'origine (jamais modifie : les empreintes deja en base restent
# verifiables). v2 : ajoute le numero de version et les champs du paiement
# lie (mode, reference, source, numero de recu, valideur, piece jointe).
# Toute nouvelle transaction est scellee dans la version courante.
LEDGER_PAYLOAD_VERSION = 2
SUPPORTED_LEDGER_PAYLOAD_VERSIONS = frozenset({1, 2})

TREASURY_MANAGERS = frozenset({MembershipRole.Role.PRESIDENT, MembershipRole.Role.TREASURER})
PAYMENT_RECORDERS = frozenset({MembershipRole.Role.TREASURER, MembershipRole.Role.ASSISTANT_TREASURER})
REVERSAL_REQUESTERS = frozenset(
    {MembershipRole.Role.PRESIDENT, MembershipRole.Role.TREASURER, MembershipRole.Role.ASSISTANT_TREASURER}
)
PRESIDENT_ONLY = frozenset({MembershipRole.Role.PRESIDENT})
# Valider ou refuser une annulation de paiement (CDC 4.4.4) : President
# seul. Source unique pour :func:`approve_payment_reversal`,
# :func:`reject_payment_reversal`, la permission ``CanDecidePaymentReversal``
# et la capacite ``can_decide_payment_reversal``.
REVERSAL_DECIDERS = PRESIDENT_ONLY

# Modes proposes dans la modale d'enregistrement (CDC 4.4.4) ; `card` est
# reserve a la phase 2 FlexPaie (CDC 4.6 ; schema §5.1).
TREASURER_ENTRY_METHODS = frozenset(
    {Payment.Method.CASH, Payment.Method.MOBILE_MONEY, Payment.Method.PAYMENT_LINK}
)

ALLOWED_TRANSITIONS = {
    Transaction.Status.INITIATED: {
        Transaction.Status.PENDING,
        Transaction.Status.SUCCEEDED,
        Transaction.Status.FAILED,
    },
    Transaction.Status.PENDING: {Transaction.Status.SUCCEEDED, Transaction.Status.FAILED},
}


_AMOUNT_INVALID_MESSAGE = "Montant invalide : saisissez un nombre, par exemple 5, 5,50 ou 5.50."
_AMOUNT_TOO_PRECISE_MESSAGE = (
    "Montant invalide : 2 chiffres après la virgule au plus (par exemple 5,50 ou 5.50)."
)
# Saisie d'un montant (correctif D-A7) : chiffres, puis au plus une virgule
# ou un point decimal suivi de chiffres. Ni exposant (« 1e3 »), ni
# separateur de milliers, ni espace interne.
_AMOUNT_INPUT_RE = re.compile(r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)")


def _parse_amount_text(text: str) -> Decimal:
    cleaned = text.strip()
    if not _AMOUNT_INPUT_RE.fullmatch(cleaned):
        raise InvalidAmountError(_AMOUNT_INVALID_MESSAGE)
    normalized = cleaned.replace(",", ".")
    _, _, decimals = normalized.partition(".")
    if len(decimals) > 2:
        raise InvalidAmountError(_AMOUNT_TOO_PRECISE_MESSAGE)
    return Decimal(normalized)


def to_money(value: Any) -> Decimal:
    """Convertit un montant en ``Decimal`` a 2 decimales.

    - Chaine (saisie de l'utilisateur, correctif D-A7 du 13/11/2026) :
      virgule ou point decimal acceptes (« 10,50 », « 10.50 ») ; plus de 2
      decimales (« 10.555 ») et notation scientifique (« 1e3 ») refusees,
      jamais arrondies en silence.
    - ``Decimal`` ou ``int`` (valeurs calculees ou deja validees) : arrondi
      a 2 decimales ``ROUND_HALF_UP`` (D7).

    Refuse ``float`` (jamais de flottant pour un montant, CLAUDE.md 7),
    booleens, ``None``, valeurs illisibles ou non finies, et montants hors
    capacite du stockage.
    """

    if value is None or isinstance(value, (bool, float)) or not isinstance(value, (Decimal, int, str)):
        raise InvalidAmountError(_AMOUNT_INVALID_MESSAGE)
    if isinstance(value, str):
        decimal_value = _parse_amount_text(value)
    else:
        decimal_value = value if isinstance(value, Decimal) else Decimal(value)
    if not decimal_value.is_finite():
        raise InvalidAmountError(_AMOUNT_INVALID_MESSAGE)
    # Borne verifiee AVANT l'arrondi : ``quantize`` leve
    # ``decimal.InvalidOperation`` quand le resultat depasse la precision du
    # contexte (ex. 1e30), ce qui produirait une erreur 500 non traduite.
    if abs(decimal_value) > MONEY_MAX + MONEY_QUANTUM:
        raise InvalidAmountError("Montant trop élevé.")
    try:
        rounded = decimal_value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise InvalidAmountError("Montant trop élevé.") from None
    if abs(rounded) > MONEY_MAX:
        raise InvalidAmountError("Montant trop élevé.")
    return rounded


def _money_str(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return str(Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP))


def _save(instance) -> None:
    """Enregistre en traduisant les erreurs de validation du modele."""

    try:
        instance.save()
    except DjangoValidationError as exc:
        raise TreasuryValidationError(" ".join(exc.messages)) from exc


# Rejeu PARALLELE d'une meme saisie (correctif D-A11 du 13/11/2026) : sous
# plusieurs envois simultanes du meme ``client_uuid``, la base peut refuser
# temporairement un acces (« database is locked » sous SQLite, « Deadlock
# found » ou « Lock wait timeout » sous MySQL/MariaDB). L'appel complet est
# alors rejoue : chaque tentative est atomique (rien n'est ecrit en cas
# d'echec) et commence par chercher la saisie deja enregistree, donc le
# premier envoi cree (201) et les suivants la renvoient (200). Jamais
# applique sans ``client_uuid`` (pas de cle d'idempotence) ni a l'interieur
# d'une transaction englobante (elle serait deja compromise).
_LOCK_RETRY_ATTEMPTS = 8
_LOCK_RETRY_BASE_DELAY = 0.05


def _is_lock_error(exc: OperationalError) -> bool:
    return "lock" in str(exc).lower()


def _retry_idempotent_when_locked(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if kwargs.get("client_uuid") is None:
            return func(*args, **kwargs)
        for attempt in range(_LOCK_RETRY_ATTEMPTS):
            try:
                return func(*args, **kwargs)
            except OperationalError as exc:
                last_attempt = attempt == _LOCK_RETRY_ATTEMPTS - 1
                if last_attempt or not _is_lock_error(exc) or db_transaction.get_connection().in_atomic_block:
                    raise
                _time.sleep(_LOCK_RETRY_BASE_DELAY * (attempt + 1))
        raise AssertionError("unreachable")  # pragma: no cover

    return wrapper


def _require_roles(user, club, roles: Iterable[str], message: str) -> None:
    if not get_active_roles(user, club=club).intersection(roles):
        raise TreasuryPermissionError(message)


def _club_settings(club) -> ClubSettings:
    club_settings = ClubSettings.objects.filter(club_id=club.id).first()
    if club_settings is None:
        raise TreasuryValidationError(
            "Les paramètres du club (devise, fuseau horaire) ne sont pas configurés : "
            "aucune opération financière n'est possible."
        )
    return club_settings


def _club_today(club_settings: ClubSettings, now: datetime) -> date:
    try:
        tz = ZoneInfo(club_settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise TreasuryValidationError("Le fuseau horaire du club est invalide.") from None
    return now.astimezone(tz).date()


def _require_reason(reason: str, message: str) -> str:
    cleaned = (reason or "").strip()
    if not cleaned:
        raise TreasuryValidationError(message)
    return cleaned


def _contribution_type_snapshot(ctype: ContributionType) -> dict[str, Any]:
    return {
        "name": ctype.name,
        "nature": ctype.nature,
        "amount": _money_str(ctype.amount),
        "periodicity": ctype.periodicity,
        "due_day": ctype.due_day,
        "due_month": ctype.due_month,
        "deadline": ctype.deadline,
        "is_membership_fee": ctype.is_membership_fee,
        "scope": ctype.scope,
        "status": ctype.status,
        "archived_at": ctype.archived_at,
        "archived_by_id": ctype.archived_by_id,
    }


def _transaction_snapshot(txn: Optional[Transaction]) -> dict[str, Any]:
    if txn is None:
        return {}
    return {
        "transaction_id": txn.pk,
        "transaction_kind": txn.kind,
        "transaction_amount": _money_str(txn.amount),
        "transaction_status": txn.status,
        "transaction_provider": txn.provider,
        "transaction_external_ref": txn.external_ref,
        "transaction_sequence": txn.sequence,
        "transaction_hash": txn.hash,
    }


def _payment_snapshot(payment: Payment, txn: Optional[Transaction] = None) -> dict[str, Any]:
    snapshot = {
        "membership_id": payment.membership_id,
        "contribution_type_id": payment.contribution_type_id,
        "amount": _money_str(payment.amount),
        "currency": payment.currency,
        "method": payment.method,
        "reference": payment.reference,
        "paid_on": payment.paid_on,
        "source": payment.source,
        "submitted_by_id": payment.submitted_by_id,
        "validated_by_id": payment.validated_by_id,
        "validated_at": payment.validated_at,
        "receipt_number": payment.receipt_number,
        "has_attachment": bool(payment.attachment),
    }
    if payment.rejected_at is not None:
        # Refus motive d'une declaration « J'ai paye » (CDC 4.6).
        snapshot.update(
            {
                "rejected_by_id": payment.rejected_by_id,
                "rejected_at": payment.rejected_at,
                "rejection_reason": payment.rejection_reason,
            }
        )
    if payment.cash_session_id is not None:
        # Encaissement de la Caisse Terrain Express : journalise avec
        # l'identifiant de la session (CDC 4.4.5 ; 10.2 n° 22).
        snapshot.update(
            {
                "cash_session_id": str(payment.cash_session.public_id),
                "client_uuid": str(payment.client_uuid) if payment.client_uuid else None,
                "client_recorded_at": payment.client_recorded_at,
            }
        )
    elif payment.client_uuid is not None:
        # Saisie en ligne idempotente (correctif M4) : cle de la modale.
        snapshot["client_uuid"] = str(payment.client_uuid)
    if payment.import_batch_id is not None:
        # Import des cotisations historiques (CDC 4.4.8) : lot d'origine.
        snapshot["import_batch_id"] = payment.import_batch_id
    snapshot.update(_transaction_snapshot(txn))
    return snapshot


def _reversal_snapshot(reversal: PaymentReversal, txn: Optional[Transaction] = None) -> dict[str, Any]:
    snapshot = {
        "payment_id": reversal.payment_id,
        "reason": reversal.reason,
        "reason_kind": reversal.reason_kind,
        "status": reversal.status,
        "requested_by_id": reversal.requested_by_id,
        "approved_by_id": reversal.approved_by_id,
        "rejected_by_id": reversal.rejected_by_id,
        "rejection_reason": reversal.rejection_reason,
    }
    snapshot.update(_transaction_snapshot(txn))
    return snapshot


def _require_service_club(club) -> None:
    active = get_active_club()
    if active is not None and active.pk != club.pk:
        raise TenantMismatchError("Le club actif ne correspond pas au club de l'opération financière.")


def _period_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _next_period(value: date) -> date:
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)


def _due_date_for_month(ctype: ContributionType, period: date) -> date:
    return date(period.year, period.month, ctype.due_day or DEFAULT_DUE_DAY)


def _arrival_due_date(ctype: ContributionType, period: date, joined_on: date) -> date:
    """Echeance du montant du du **mois d'arrivee** d'un joueur.

    PROPOSITION PAR DEFAUT 10.2 n° 5 APPLIQUEE -- NON TRANCHEE PAR LE CLIENT
    (CDC 4.4.2 : « joueur arrive en cours de mois (mois entier du ou non) »
    est un cas « a trancher par le club ») : le mois d'arrivee est du en
    entier. Son echeance suit la meme regle que les autres mois :

    - arrivee au plus tard le jour d'echeance du type (le 10 par defaut,
      10.2 n° 4) : echeance normale du mois ;
    - arrivee apres ce jour : l'echeance est reportee pour laisser au joueur
      le meme delai qu'un montant du genere le 1er du mois (jour d'echeance
      - 1 jours, soit 9 jours par defaut) a compter de son arrivee -- personne
      n'est bloque des son arrivee.

    Dans les deux cas, la tolerance du club s'ajoute ensuite
    (:func:`_matured_mandatory_dues`), comme pour tout montant du."""

    regular = _due_date_for_month(ctype, period)
    if joined_on <= regular:
        return regular
    return joined_on + timedelta(days=(ctype.due_day or DEFAULT_DUE_DAY) - 1)


def _assignment_snapshot(assignment: ContributionAssignment) -> dict[str, Any]:
    return {
        "membership_id": assignment.membership_id,
        "contribution_type_id": assignment.contribution_type_id,
        "starts_on": assignment.starts_on,
        "ends_on": assignment.ends_on,
    }


def _suspension_snapshot(suspension: ContributionSuspension) -> dict[str, Any]:
    return {
        "membership_id": suspension.membership_id,
        "starts_on": suspension.starts_on,
        "ends_on": suspension.ends_on,
        "reason": suspension.reason,
        "decided_by_id": suspension.decided_by_id,
        "decided_at": suspension.decided_at,
        "ended_by_id": suspension.ended_by_id,
        "ended_at": suspension.ended_at,
    }


def _due_snapshot(due: Due) -> dict[str, Any]:
    return {
        "membership_id": due.membership_id,
        "contribution_type_id": due.contribution_type_id,
        "period": due.period,
        "amount": _money_str(due.amount),
        "due_date": due.due_date,
        "source": due.source,
    }


def _allocation_snapshot(allocation: PaymentAllocation) -> dict[str, Any]:
    return {
        "payment_id": allocation.payment_id,
        "membership_id": allocation.membership_id,
        "contribution_type_id": allocation.contribution_type_id,
        "period": allocation.period,
        "amount": _money_str(allocation.amount),
    }


def create_contribution_assignment(
    *, membership: Membership, contribution_type: ContributionType, starts_on: date,
    created_by, ends_on: Optional[date] = None, now: Optional[datetime] = None,
) -> ContributionAssignment:
    """Cree un rattachement pour un type `selected` ou `attached`, sans chevauchement."""

    club = membership.club
    _require_service_club(club)
    _require_roles(created_by, club, TREASURY_MANAGERS, "Seuls le Président et le Trésorier gèrent les rattachements.")
    if contribution_type.club_id != club.pk:
        raise TreasuryValidationError("Le type de cotisation doit appartenir au club du joueur.")
    if contribution_type.scope not in (ContributionType.Scope.SELECTED, ContributionType.Scope.ATTACHED):
        raise TreasuryValidationError("Ce type ne demande pas de rattachement individuel.")
    now = now or timezone.now()
    with db_transaction.atomic():
        assignment = ContributionAssignment(
            club=club,
            membership=membership,
            contribution_type=contribution_type,
            starts_on=starts_on,
            ends_on=ends_on,
            created_at=now,
            created_by=created_by,
        )
        _save(assignment)
        log_action(
            actor=created_by,
            club=club,
            action_type="treasury.contribution_assignment.created",
            obj=assignment,
            before=None,
            after=_assignment_snapshot(assignment),
        )
        _recompute_allocations_for_pairs(
            club=club, pairs={(membership.pk, contribution_type.pk)}, actor=created_by, now=now
        )
    return assignment


def end_contribution_assignment(*, assignment: ContributionAssignment, ends_on: date, ended_by) -> ContributionAssignment:
    """Clot un rattachement sans supprimer son historique financier."""

    club = assignment.club
    _require_service_club(club)
    _require_roles(ended_by, club, TREASURY_MANAGERS, "Seuls le Président et le Trésorier gèrent les rattachements.")
    with db_transaction.atomic():
        stored = ContributionAssignment.all_objects.get(pk=assignment.pk, club=club)
        before = _assignment_snapshot(stored)
        stored.ends_on = ends_on
        _save(stored)
        log_action(
            actor=ended_by,
            club=club,
            action_type="treasury.contribution_assignment.ended",
            obj=stored,
            before=before,
            after=_assignment_snapshot(stored),
        )
        _recompute_allocations_for_pairs(
            club=club, pairs={(stored.membership_id, stored.contribution_type_id)}, actor=ended_by, now=None
        )
    return stored


def create_contribution_suspension(
    *, membership: Membership, starts_on: date, reason: str, decided_by,
    ends_on: Optional[date] = None, now: Optional[datetime] = None,
) -> ContributionSuspension:
    """Suspend les cotisations futures, sur decision tracee du President."""

    club = membership.club
    _require_service_club(club)
    _require_roles(decided_by, club, PRESIDENT_ONLY, "Seul le Président peut suspendre les cotisations.")
    cleaned = _require_reason(reason, "Le motif de suspension est obligatoire.")
    now = now or timezone.now()
    with db_transaction.atomic():
        suspension = ContributionSuspension(
            club=club,
            membership=membership,
            starts_on=starts_on,
            ends_on=ends_on,
            reason=cleaned,
            decided_by=decided_by,
            decided_at=now,
        )
        _save(suspension)
        log_action(
            actor=decided_by,
            club=club,
            action_type="treasury.contribution_suspension.created",
            obj=suspension,
            before=None,
            after=_suspension_snapshot(suspension),
        )
        # B8 : les mois suspendus n'ont plus de capacite -- un paiement
        # d'avance qui les couvrait est reporte sur les mois suivants.
        _recompute_member_allocations(membership=membership, actor=decided_by, now=now)
    return suspension


def end_contribution_suspension(
    *, suspension: ContributionSuspension, ends_on: date, ended_by, now: Optional[datetime] = None,
) -> ContributionSuspension:
    """Met fin a une suspension a la fin d'un mois, en conservant la trace."""

    club = suspension.club
    _require_service_club(club)
    _require_roles(ended_by, club, PRESIDENT_ONLY, "Seul le Président peut lever une suspension de cotisations.")
    with db_transaction.atomic():
        stored = ContributionSuspension.all_objects.get(pk=suspension.pk, club=club)
        if stored.ended_at is not None:
            raise TreasuryValidationError("Cette suspension est déjà levée.")
        before = _suspension_snapshot(stored)
        stored.ends_on = ends_on
        stored.ended_by = ended_by
        stored.ended_at = now or timezone.now()
        _save(stored)
        log_action(
            actor=ended_by,
            club=club,
            action_type="treasury.contribution_suspension.ended",
            obj=stored,
            before=before,
            after=_suspension_snapshot(stored),
        )
        _recompute_member_allocations(membership=stored.membership, actor=ended_by, now=stored.ended_at)
    return stored


def generate_dues_for_period(
    *, club, period: date, actor, arrival_due_date: Optional[date] = None,
    now: Optional[datetime] = None,
) -> list[Due]:
    """Genere les dus mensuels d'une periode, de facon idempotente.

    Pour le mois d'arrivee, le montant plein est cree (proposition par
    defaut 10.2 n° 5, non tranchee par le client) ; son echeance est
    ``arrival_due_date`` si fourni, sinon :func:`_arrival_due_date` (meme
    regle que les autres mois). La repartition 4.4.3 des joueurs concernes
    ayant deja des paiements est recalculee (grille jamais perimee). La
    fonction ne constitue pas une commande cron et traite uniquement le
    mois demande (la commande ``generate_monthly_dues`` passe par
    :func:`run_monthly_dues`).

    ``actor`` : utilisateur inscrit au journal. ``None`` pour une tache
    cron sans acteur reel : aucune entree `AuditLog` n'est alors ecrite (le
    journal exige un acteur reel, CDC 5.1), la creation reste tracee par
    ``Due.created_at`` et ``Due.source`` -- meme convention que
    ``apps.licences.services.process_licence_expirations`` (point ouvert).
    """

    return _generate_dues(club=club, period=period, actor=actor, arrival_due_date=arrival_due_date, now=now)


def _generate_dues(
    *, club, period: date, actor, arrival_due_date: Optional[date], now: Optional[datetime],
) -> list[Due]:
    """Noyau de :func:`generate_dues_for_period` et de la tache cron
    (:func:`run_monthly_dues`).

    Montants dus **mensuels** uniquement (``periodicity=MONTHLY``). POINT
    OUVERT (Q3, a trancher par le client -- non resolu ici) : le CDC 4.4.2
    ne prevoit de generation automatique que pour le type mensuel (« le
    montant du du mois ... selon son type mensuel ») ; ni le CDC ni le 10.2
    ne disent a quelle date creer le montant du d'une cotisation
    obligatoire **annuelle** (jour/mois d'echeance, mais pour quelle
    saison, quel joueur arrive en cours d'annee ?) ou **ponctuelle** (date
    limite, mais pour quels joueurs, crees quand ?). Aucune regle n'est
    inventee : ces types ne generent aucun montant du tant que la decision
    n'est pas prise.
    """

    _require_service_club(club)
    if period.day != 1:
        raise TreasuryValidationError("La période d'un montant mensuel doit commencer le premier jour du mois.")
    _club_settings(club)
    now = now or timezone.now()
    types = list(
        ContributionType.all_objects.filter(
            club=club,
            nature=ContributionType.Nature.MANDATORY,
            periodicity=ContributionType.Periodicity.MONTHLY,
            status=ContributionType.Status.ACTIVE,
        ).order_by("pk")
    )
    memberships = list(
        Membership.all_objects.filter(club=club, status=Membership.Status.ACTIVE, joined_on__lte=_next_period(period) - timedelta(days=1))
        .exclude(left_on__lt=period)
        .order_by("pk")
    )
    created = []
    with db_transaction.atomic():
        for ctype in types:
            rates = ContributionTypeRate.all_objects.filter(
                club=club, contribution_type=ctype, effective_from__lte=period
            ).order_by("-effective_from")
            rate = rates.first()
            if rate is None:
                raise TreasuryValidationError(f"Aucun tarif n'est défini pour le type « {ctype.name} » à cette période.")
            for membership in memberships:
                is_arrival_month = membership.joined_on.year == period.year and membership.joined_on.month == period.month
                matching_assignment = None
                if ctype.scope == ContributionType.Scope.ALL:
                    applicable = True
                else:
                    assignments = ContributionAssignment.all_objects.filter(
                        club=club,
                        contribution_type=ctype,
                        membership=membership,
                        starts_on__lte=period,
                    ).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=period))
                    matching_assignment = assignments.order_by("starts_on").first()
                    applicable = matching_assignment is not None
                if not applicable:
                    continue
                suspended = ContributionSuspension.all_objects.filter(
                    club=club,
                    membership=membership,
                    starts_on__lte=_next_period(period) - timedelta(days=1),
                ).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=period)).exists()
                if suspended:
                    continue
                source = Due.Source.ARRIVAL if is_arrival_month else Due.Source.SCHEDULER
                due_date = _due_date_for_month(ctype, period)
                if is_arrival_month:
                    # Proposition par defaut 10.2 n° 5 (non tranchee) : mois
                    # entier du, echeance selon la regle normale.
                    due_date = arrival_due_date or _arrival_due_date(ctype, period, membership.joined_on)
                elif matching_assignment and matching_assignment.starts_on == period:
                    source = Due.Source.ASSIGNMENT
                if Due.all_objects.filter(
                    club=club, membership=membership, contribution_type=ctype, period=period
                ).exists():
                    continue
                due = Due(
                    club=club,
                    membership=membership,
                    contribution_type=ctype,
                    period=period,
                    amount=rate.amount,
                    due_date=due_date,
                    source=source,
                    created_at=now,
                )
                _save(due)
                if actor is not None:
                    log_action(
                        actor=actor,
                        club=club,
                        action_type="treasury.due.generated",
                        obj=due,
                        before=None,
                        after=_due_snapshot(due),
                    )
                created.append(due)
        # Revue de conformite B8 : un nouveau montant du peut changer la
        # repartition 4.4.3 (mois impayes les plus anciens d'abord) -- la
        # projection des joueurs ayant deja des paiements est recalculee.
        if created:
            _recompute_allocations_for_pairs(
                club=club,
                pairs={(due.membership_id, due.contribution_type_id) for due in created},
                actor=actor,
                now=now,
            )
    return created


def _balance_date(club, at_date: Optional[date]) -> date:
    if at_date is not None:
        if not isinstance(at_date, date) or isinstance(at_date, datetime):
            raise TreasuryValidationError("La date de calcul du solde est invalide.")
        return at_date
    settings_obj = _club_settings(club)
    return _club_today(settings_obj, timezone.now())


def _validated_mandatory_transactions(club, at_date: date):
    """Transactions scellees reussies des types obligatoires jusqu'a ``at_date``
    (premier terme de la formule du solde, CDC 4.4.2). Seule definition du
    domaine : solde, eligibilite a l'assistance sociale et commandes cron
    s'appuient dessus."""

    return Transaction.all_objects.filter(
        club=club,
        membership__isnull=False,
        contribution_type__nature=ContributionType.Nature.MANDATORY,
        status=Transaction.Status.SUCCEEDED,
        sealed_at__isnull=False,
        value_date__lte=at_date,
    )


def _matured_mandatory_dues(club, at_date: date):
    """Montants dus devenus **dette** a ``at_date`` (CDC 4.4.2 ; 10.2 n° 4).

    **Regle unique du passage en dette** : un montant du d'un type
    obligatoire devient une dette quand ``due_date + tolerance du club <
    at_date``. Rien n'est stocke ni « bascule » par une tache : le passage
    en dette est **calcule** a chaque lecture (invariant 1, 3), ce qui
    explique l'absence de commande cron « passage en dette » (tache 2.3).
    Le 1er du mois, un montant du fraichement genere n'est donc jamais une
    dette (echeance le 10 par defaut).

    **Frais d'adhesion** (decision du client du 17/11/2026, 10.3 n° 100 :
    « echeance a la date d'entree ») : le du d'adhesion est exigible des la
    date d'entree (``due_date <= at_date``), sans tolerance -- le joueur
    « paie d'abord l'adhesion » (CDC 4.3) et reste « En attente » tant qu'il
    ne l'a pas reglee ; son paiement ramene donc le solde a 0 le jour meme,
    sans credit transitoire. Interpretation signalee au compte rendu.

    Un montant du annule (:class:`DueCancellation`) ne compte jamais."""

    tolerance = _club_settings(club).debt_tolerance_days
    return Due.all_objects.filter(
        club=club,
        contribution_type__nature=ContributionType.Nature.MANDATORY,
        cancellation__isnull=True,
    ).filter(
        Q(due_date__lt=at_date - timedelta(days=tolerance))
        | Q(source=Due.Source.MEMBERSHIP_FEE, due_date__lte=at_date)
    )


def _balance_aggregates(*, club, at_date: date, membership_ids: Optional[Iterable[int]] = None):
    """Deux agregations SQL (paye, du echu) par adhesion. ``membership_ids``
    restreint le calcul a quelques joueurs (recherche de la caisse) sans
    changer la formule."""

    paid_qs = _validated_mandatory_transactions(club, at_date)
    owed_qs = _matured_mandatory_dues(club, at_date)
    if membership_ids is not None:
        ids = list(membership_ids)
        paid_qs = paid_qs.filter(membership_id__in=ids)
        owed_qs = owed_qs.filter(membership_id__in=ids)
    paid = dict(
        paid_qs.values("membership_id").annotate(total=Sum("amount")).values_list("membership_id", "total")
    )
    owed = dict(
        owed_qs.values("membership_id").annotate(total=Sum("amount")).values_list("membership_id", "total")
    )
    return paid, owed


def get_balance(membership: Membership, at_date: Optional[date] = None) -> Decimal:
    """Calcule le solde avec deux agregations SQL, sans consulter les allocations."""

    club = membership.club
    _require_service_club(club)
    at_date = _balance_date(club, at_date)
    paid, owed = _balance_aggregates(club=club, at_date=at_date)
    return (paid.get(membership.pk) or Decimal("0.00")) - (owed.get(membership.pk) or Decimal("0.00"))


def get_balances(club, at_date: Optional[date] = None) -> dict[int, Decimal]:
    """Renvoie les soldes par identifiant d'adhesion, en deux agregations SQL."""

    _require_service_club(club)
    at_date = _balance_date(club, at_date)
    paid, owed = _balance_aggregates(club=club, at_date=at_date)
    membership_ids = Membership.all_objects.filter(club=club).values_list("pk", flat=True)
    return {
        membership_id: (paid.get(membership_id) or Decimal("0.00"))
        - (owed.get(membership_id) or Decimal("0.00"))
        for membership_id in membership_ids
    }


@dataclass(frozen=True)
class BalanceSummary:
    """Situation financiere calculee d'une adhesion (jamais stockee, CDC 4.4.2).

    Seule source du statut « En ordre » / « En dette » et de sa raison
    lisible : :func:`is_in_good_standing` et les vues s'appuient dessus, sans
    jamais recalculer le solde eux-memes.
    """

    balance: Decimal
    amount_due: Decimal
    is_in_good_standing: bool
    reason: str
    currency: str


def get_balance_summary(membership: Membership, at_date: Optional[date] = None) -> BalanceSummary:
    """Renvoie solde, montant a regulariser, statut et raison en francais."""

    balance = get_balance(membership, at_date=at_date)
    return _membership_summary(membership, balance, _club_settings(membership.club).currency)


def _membership_summary(membership: Membership, balance: Decimal, currency: str) -> BalanceSummary:
    """:func:`_summary_from_balance` avec la raison propre a une adhesion
    « En attente » (frais d'adhesion a regler, jamais « en dette »)."""

    summary = _summary_from_balance(balance, currency)
    if not summary.is_in_good_standing and membership.status == Membership.Status.PENDING:
        # CDC 4.3 : le joueur « En attente » paie d'abord son adhesion ; il
        # n'est jamais presente « En dette » (CDC 4.1, diagramme des statuts).
        return BalanceSummary(
            summary.balance,
            summary.amount_due,
            False,
            f"Adhésion en attente : {summary.amount_due:.2f} {summary.currency} à régler.",
            summary.currency,
        )
    return summary


def _summary_from_balance(balance: Decimal, currency: str) -> BalanceSummary:
    """Statut « En ordre » / « En dette » et raison lisible d'un solde deja
    calcule (CDC 4.4.2). Seule formulation du statut, partagee par
    :func:`get_balance_summary`, l'apercu d'un paiement et la recherche de
    la Caisse Terrain Express."""

    balance = Decimal(balance).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    amount_due = max(-balance, Decimal("0.00"))
    if amount_due == 0:
        return BalanceSummary(balance, Decimal("0.00"), True, "Le joueur est en ordre.", currency)
    return BalanceSummary(
        balance,
        amount_due,
        False,
        f"Le joueur est en dette : {amount_due:.2f} {currency} à régulariser.",
        currency,
    )


def is_in_good_standing(membership: Membership, at_date: Optional[date] = None) -> tuple[bool, Decimal, str]:
    """Renvoie (eligibilite, montant a regulariser, raison en francais)."""

    summary = get_balance_summary(membership, at_date=at_date)
    return summary.is_in_good_standing, summary.amount_due, summary.reason


def _month_range(start: date, count: int):
    current = _period_start(start)
    for _ in range(count):
        yield current
        current = _next_period(current)


def _rate_for_period(ctype: ContributionType, period: date) -> Optional[Decimal]:
    rate = ContributionTypeRate.all_objects.filter(
        club_id=ctype.club_id, contribution_type_id=ctype.pk, effective_from__lte=period
    ).order_by("-effective_from").values_list("amount", flat=True).first()
    return rate


def _covered_by_assignment(*, club, membership, ctype, period: date) -> bool:
    if ctype.scope == ContributionType.Scope.ALL:
        return membership.joined_on <= _next_period(period) - timedelta(days=1) and (
            membership.left_on is None or membership.left_on >= period
        )
    return ContributionAssignment.all_objects.filter(
        club=club,
        membership=membership,
        contribution_type=ctype,
        starts_on__lte=period,
    ).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=period)).exists()


def _validated_payments_for(*, club, membership, ctype) -> list[Payment]:
    """Paiements valides et non annules d'un couple (joueur, type), dans
    l'ordre de la repartition 4.4.3 : ``paid_on`` puis sequence de chaine."""

    return list(
        Payment.all_objects.filter(
            club=club,
            membership=membership,
            contribution_type=ctype,
            transaction__kind=Transaction.Kind.PAYMENT,
            transaction__status=Transaction.Status.SUCCEEDED,
            transaction__sealed_at__isnull=False,
        )
        .exclude(reversal__status=PaymentReversal.Status.APPROVED)
        .select_related("transaction")
        .order_by("paid_on", "transaction__sequence")
    )


def _plan_allocations(
    *, club, membership, ctype, payments: list, extra_dues: Optional[dict[date, Decimal]] = None
) -> tuple[list[tuple[Any, date, Decimal]], dict]:
    """Calcule la repartition 4.4.3 **sans rien ecrire** (schema §5.2).

    ``payments`` : objets portant ``amount`` et ``paid_on``, deja ordonnes
    (paiements valides, plus eventuellement un paiement projete pour un
    apercu). Renvoie ``(lignes, capacites)`` : ``lignes`` = liste de
    ``(paiement, periode, montant)`` dans l'ordre d'affectation ;
    ``capacites`` = montant attendu par periode (vide pour un type libre).
    Seule definition de l'algorithme : la projection enregistree
    (:func:`_recompute_allocations`), l'apercu avant validation
    (:func:`preview_payment_allocation`) et l'apercu d'un import historique
    (:func:`preview_contribution_import`) s'appuient dessus.

    ``extra_dues`` : montants dus **projetes** (periode -> montant), traites
    exactement comme des `Due` existants ; sert uniquement a l'apercu d'un
    import qui creera ces montants dus (CDC 4.4.8). Un `Due` existant de la
    meme periode l'emporte (contrainte d'unicite, aucun doublon possible).
    """

    if ctype.nature == ContributionType.Nature.FREE:
        return [(payment, _period_start(payment.paid_on), payment.amount) for payment in payments], {}

    dues = list(
        Due.all_objects.filter(
            club=club, membership=membership, contribution_type=ctype, cancellation__isnull=True
        ).order_by("period")
    )
    if extra_dues:
        existing_periods = {due.period for due in dues}
        dues.extend(
            _ProjectedDue(period, amount) for period, amount in extra_dues.items() if period not in existing_periods
        )
        dues.sort(key=lambda due: due.period)
    lines: list[tuple[Any, date, Decimal]] = []
    if ctype.periodicity != ContributionType.Periodicity.MONTHLY:
        capacities = {due.period: due.amount for due in dues}
        remaining_by_period = dict(capacities)
        for payment in payments:
            remaining_payment = payment.amount
            for period in sorted(remaining_by_period):
                available = remaining_by_period[period]
                if available <= 0:
                    continue
                allocated = min(available, remaining_payment)
                lines.append((payment, period, allocated))
                remaining_by_period[period] -= allocated
                remaining_payment -= allocated
                if remaining_payment <= 0:
                    break
        return lines, capacities

    dues_by_period = {due.period: due.amount for due in dues}
    first_period = min([_period_start(payment.paid_on) for payment in payments] + list(dues_by_period))
    target_total = sum((payment.amount for payment in payments), Decimal("0.00"))
    monthly_periods = []
    capacity_total = Decimal("0.00")
    for period in _month_range(first_period, 1200):
        existing_due = dues_by_period.get(period)
        if existing_due is not None:
            capacity = existing_due
        elif period >= _period_start(payments[0].paid_on) and _covered_by_assignment(
            club=club, membership=membership, ctype=ctype, period=period
        ):
            if ctype.status != ContributionType.Status.ACTIVE:
                break
            is_suspended = ContributionSuspension.all_objects.filter(
                club=club,
                membership=membership,
                starts_on__lte=_next_period(period) - timedelta(days=1),
            ).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=period)).exists()
            capacity = Decimal("0.00") if is_suspended else (_rate_for_period(ctype, period) or Decimal("0.00"))
        else:
            capacity = Decimal("0.00")
        monthly_periods.append((period, capacity))
        capacity_total += capacity
        if capacity_total >= target_total and period >= _period_start(payments[-1].paid_on):
            break

    capacities = {period: amount for period, amount in monthly_periods}
    remaining_by_period = dict(capacities)
    for payment in payments:
        remaining_payment = payment.amount
        for period, _ in monthly_periods:
            available = remaining_by_period[period]
            if available <= 0:
                continue
            allocated = min(available, remaining_payment)
            if allocated <= 0:
                break
            lines.append((payment, period, allocated))
            remaining_by_period[period] -= allocated
            remaining_payment -= allocated
            if remaining_payment <= 0:
                break
    return lines, capacities


def _recompute_allocations(*, membership, ctype, actor, now: datetime) -> list[tuple[date, Decimal]]:
    """Reconstruit la projection 4.4.3 d'un couple (joueur, type).

    ``actor`` : auteur inscrit au journal ; ``None`` pour une tache cron
    sans acteur reel (aucune entree `AuditLog`, meme convention que la
    generation des montants dus)."""

    club = membership.club
    payments = _validated_payments_for(club=club, membership=membership, ctype=ctype)
    old_allocations = list(
        PaymentAllocation.all_objects.filter(club=club, membership=membership, contribution_type=ctype)
    )
    PaymentAllocation.all_objects.filter(club=club, membership=membership, contribution_type=ctype).delete()
    for allocation in old_allocations if actor is not None else ():
        log_action(
            actor=actor,
            club=club,
            action_type="treasury.payment_allocation.recomputed",
            obj=allocation,
            before=_allocation_snapshot(allocation),
            after=None,
        )
    if not payments:
        return []

    currency = _club_settings(club).currency
    if any(payment.currency != currency for payment in payments):
        raise TreasuryValidationError("La devise du paiement ne correspond plus à celle du club.")
    lines, _ = _plan_allocations(club=club, membership=membership, ctype=ctype, payments=payments)
    results = []
    for payment, period, allocated in lines:
        allocation = PaymentAllocation(
            club=club,
            payment=payment,
            membership=membership,
            contribution_type=ctype,
            period=period,
            amount=allocated,
            computed_at=now,
        )
        _save(allocation)
        if actor is not None:
            log_action(
                actor=actor,
                club=club,
                action_type="treasury.payment_allocation.recomputed",
                obj=allocation,
                before=None,
                after=_allocation_snapshot(allocation),
            )
        results.append((period, allocated))
    if ctype.nature == ContributionType.Nature.FREE:
        return []
    return results


def _paid_pairs(club, *, membership_ids=None, ctype_ids=None) -> set[tuple[int, int]]:
    """Couples (adhesion, type) ayant au moins un paiement valide (une
    requete SQL) : seuls ceux-la ont une projection 4.4.3 a recalculer."""

    queryset = Payment.all_objects.filter(
        club=club,
        transaction__kind=Transaction.Kind.PAYMENT,
        transaction__status=Transaction.Status.SUCCEEDED,
        transaction__sealed_at__isnull=False,
    )
    if membership_ids is not None:
        queryset = queryset.filter(membership_id__in=list(membership_ids))
    if ctype_ids is not None:
        queryset = queryset.filter(contribution_type_id__in=list(ctype_ids))
    return set(queryset.order_by().values_list("membership_id", "contribution_type_id").distinct())


def _recompute_allocations_for_pairs(*, club, pairs, actor, now: Optional[datetime]) -> int:
    """Recalcule la projection 4.4.3 des couples (adhesion, type) donnes qui
    ont des paiements valides (les autres n'ont aucune repartition).

    Revue de conformite B8 : la projection (`PaymentAllocation`) doit etre
    recalculee a **chaque** evenement qui change la capacite des mois --
    paiement, annulation, validation d'une declaration (deja le cas), mais
    aussi generation de montants dus, suspension (creation, levee),
    rattachement (creation, fin), changement de tarif ou de perimetre d'un
    type. L'archivage d'un type ne declenche volontairement PAS de recalcul
    (le moteur ne projette plus de mois sans montant du pour un type
    archive : recalculer effacerait la couverture d'avance deja affichee --
    point ouvert signale). Choix documente : recalcul a l'ecriture (et non a
    la lecture de la grille), coherent avec l'architecture existante ou la
    grille lit la projection stockee sans rien recalculer.

    Renvoie le nombre de couples recalcules."""

    pairs = set(pairs)
    if not pairs:
        return 0
    paid = _paid_pairs(
        club,
        membership_ids={membership_id for membership_id, _ in pairs},
        ctype_ids={ctype_id for _, ctype_id in pairs},
    )
    todo = sorted(pairs & paid)
    if not todo:
        return 0
    now = now or timezone.now()
    memberships = Membership.all_objects.select_related("club").in_bulk({m for m, _ in todo})
    ctypes = ContributionType.all_objects.in_bulk({c for _, c in todo})
    for membership_id, ctype_id in todo:
        _recompute_allocations(
            membership=memberships[membership_id], ctype=ctypes[ctype_id], actor=actor, now=now
        )
    return len(todo)


def _recompute_member_allocations(*, membership, actor, now: Optional[datetime]) -> int:
    """Recalcule la projection de tous les types payes par ce joueur."""

    pairs = _paid_pairs(membership.club, membership_ids=[membership.pk])
    return _recompute_allocations_for_pairs(club=membership.club, pairs=pairs, actor=actor, now=now)


def _recompute_type_allocations(*, ctype, actor, now: Optional[datetime]) -> int:
    """Recalcule la projection de tous les joueurs ayant paye ce type."""

    pairs = _paid_pairs(ctype.club, ctype_ids=[ctype.pk])
    return _recompute_allocations_for_pairs(club=ctype.club, pairs=pairs, actor=actor, now=now)


def refresh_member_allocations(membership: Membership, *, actor=None, now: Optional[datetime] = None) -> int:
    """INTERFACE EXPOSEE (revue de conformite B8) : recalcule la repartition
    4.4.3 d'un joueur apres un evenement geree hors tresorerie qui change
    les mois dont il est redevable -- en particulier son **depart** du club
    (``Membership.left_on``, app ``clubs``) ou la correction de sa date
    d'entree. ``actor`` : auteur de l'evenement (journal) ou ``None``.
    Renvoie le nombre de couples (joueur, type) recalcules."""

    _require_service_club(membership.club)
    with db_transaction.atomic():
        return _recompute_member_allocations(membership=membership, actor=actor, now=now)


def allocate_payment(payment: Payment) -> list[tuple[date, Decimal]]:
    """Reconstruit la projection des paiements valides du joueur et du type."""

    club = payment.club
    _require_service_club(club)
    if payment.currency != _club_settings(club).currency:
        raise TreasuryValidationError("La devise du paiement ne correspond pas à celle du club.")
    txn = Transaction.all_objects.filter(club=club, payment=payment).first()
    if txn is None or txn.status != Transaction.Status.SUCCEEDED or txn.sealed_at is None:
        raise TreasuryValidationError("Seul un paiement validé peut être réparti.")
    actor = payment.validated_by or payment.submitted_by
    with db_transaction.atomic():
        result = _recompute_allocations(
            membership=payment.membership,
            ctype=payment.contribution_type,
            actor=actor,
            now=timezone.now(),
        )
    return list(
        PaymentAllocation.all_objects.filter(club=club, payment=payment)
        .order_by("period")
        .values_list("period", "amount")
    )


# ---------------------------------------------------------------------------
# Types de cotisation (CDC 4.4.1 ; schema-treasury.md §4.1)
# ---------------------------------------------------------------------------

DEFAULT_DUE_DAY = 10  # 10.2 n° 4 (proposition par defaut)


def create_contribution_type(
    *,
    club,
    created_by,
    name: str,
    nature: str,
    periodicity: str,
    amount: Any = None,
    scope: str = ContributionType.Scope.ALL,
    due_day: Optional[int] = None,
    due_month: Optional[int] = None,
    deadline: Optional[date] = None,
    is_membership_fee: bool = False,
    now: Optional[datetime] = None,
) -> ContributionType:
    """Cree un type de cotisation (President ou Tresorier, matrice 2.4).

    ``due_day`` vaut 10 par defaut pour une mensuelle ou annuelle (10.2 n° 4).
    Au plus un type « adhesion » actif par club. Journalise
    ``treasury.contribution_type.created``.

    Cree egalement le tarif courant lorsqu'un montant est defini.
    """

    _require_roles(
        created_by,
        club,
        TREASURY_MANAGERS,
        "Seuls le Président et le Trésorier peuvent créer un type de cotisation.",
    )
    cleaned_name = _require_reason(name, "Le nom du type de cotisation est obligatoire.")
    if nature not in ContributionType.Nature.values:
        raise TreasuryValidationError("Nature de cotisation inconnue (obligatoire ou libre).")
    if periodicity not in ContributionType.Periodicity.values:
        raise TreasuryValidationError("Périodicité inconnue (mensuelle, annuelle ou ponctuelle).")
    if scope not in ContributionType.Scope.values:
        raise TreasuryValidationError("Périmètre des joueurs concernés inconnu.")
    money = None if amount is None else to_money(amount)
    if periodicity in (ContributionType.Periodicity.MONTHLY, ContributionType.Periodicity.ANNUAL) and due_day is None:
        due_day = DEFAULT_DUE_DAY
    if ContributionType.all_objects.filter(club=club, name=cleaned_name).exists():
        raise TreasuryValidationError("Un type de cotisation porte déjà ce nom dans ce club.")

    now = now or timezone.now()
    effective_from = None
    if money is not None:
        local_today = _club_today(_club_settings(club), now)
        effective_from = date(local_today.year, local_today.month, 1)
    ctype = ContributionType(
        club=club,
        name=cleaned_name,
        nature=nature,
        amount=money,
        periodicity=periodicity,
        due_day=due_day,
        due_month=due_month,
        deadline=deadline,
        is_membership_fee=bool(is_membership_fee),
        scope=scope,
        created_by=created_by,
        created_at=now,
    )
    with db_transaction.atomic():
        _save(ctype)
        if money is not None:
            _save(
                ContributionTypeRate(
                    club=club,
                    contribution_type=ctype,
                    amount=money,
                    effective_from=effective_from,
                    created_by=created_by,
                    created_at=now,
                )
            )
        log_action(
            actor=created_by,
            club=club,
            action_type="treasury.contribution_type.created",
            obj=ctype,
            before=None,
            after=_contribution_type_snapshot(ctype),
        )
    return ctype


def archive_contribution_type(
    *, contribution_type: ContributionType, archived_by, now: Optional[datetime] = None
) -> ContributionType:
    """Archive un type (President ou Tresorier). Il n'est plus propose a
    l'enregistrement d'un paiement ; les paiements passes restent acquis."""

    club = contribution_type.club
    _require_roles(
        archived_by,
        club,
        TREASURY_MANAGERS,
        "Seuls le Président et le Trésorier peuvent archiver un type de cotisation.",
    )
    with db_transaction.atomic():
        ctype = ContributionType.all_objects.select_for_update().get(pk=contribution_type.pk, club=club)
        if ctype.status == ContributionType.Status.ARCHIVED:
            raise TreasuryValidationError("Ce type de cotisation est déjà archivé.")
        before = _contribution_type_snapshot(ctype)
        ctype.status = ContributionType.Status.ARCHIVED
        ctype.archived_at = now or timezone.now()
        ctype.archived_by = archived_by
        _save(ctype)
        log_action(
            actor=archived_by,
            club=club,
            action_type="treasury.contribution_type.archived",
            obj=ctype,
            before=before,
            after=_contribution_type_snapshot(ctype),
        )
    contribution_type.refresh_from_db()
    return ctype


def update_contribution_type(
    *, contribution_type: ContributionType, updated_by, now: Optional[datetime] = None, **changes
) -> ContributionType:
    """Modifie un type et programme tout nouveau tarif au premier du mois suivant."""

    club = contribution_type.club
    _require_roles(
        updated_by,
        club,
        TREASURY_MANAGERS,
        "Seuls le Président et le Trésorier peuvent modifier un type de cotisation.",
    )
    allowed = {
        "name", "nature", "periodicity", "amount", "scope", "due_day", "due_month",
        "deadline", "is_membership_fee",
    }
    unknown = set(changes) - allowed
    if unknown:
        raise TreasuryValidationError("Champ de modification inconnu pour ce type de cotisation.")
    requested_amount = to_money(changes["amount"]) if changes.get("amount") is not None else changes.get("amount")
    with db_transaction.atomic():
        ctype = ContributionType.all_objects.select_for_update().get(pk=contribution_type.pk, club=club)
        if ctype.status == ContributionType.Status.ARCHIVED:
            raise TreasuryValidationError("Un type archivé ne peut plus être modifié.")
        before = _contribution_type_snapshot(ctype)
        requested_nature = changes.get("nature", ctype.nature)
        if requested_nature != ctype.nature and (
            Payment.all_objects.filter(club=club, contribution_type=ctype).exists()
            or Transaction.all_objects.filter(club=club, contribution_type=ctype).exists()
        ):
            raise TreasuryValidationError(
                "La nature d'un type de cotisation ne peut plus être modifiée après un paiement."
            )
        # Revue de conformite B9 : passer un type obligatoire en libre
        # effacerait silencieusement les dettes deja generees (invariants 1
        # et 2). Refuse des qu'un montant du existe pour ce type.
        if requested_nature != ctype.nature and Due.all_objects.filter(club=club, contribution_type=ctype).exists():
            raise TreasuryValidationError(
                "La nature d'un type de cotisation ne peut plus être modifiée : des montants dus ont déjà "
                "été générés pour ce type. Archivez-le et créez-en un nouveau."
            )
        amount_changed = "amount" in changes and requested_amount != ctype.amount
        for field, value in changes.items():
            if field == "amount":
                value = requested_amount
            if field == "name":
                value = _require_reason(value, "Le nom du type de cotisation est obligatoire.")
                if ContributionType.all_objects.filter(club=club, name=value).exclude(pk=ctype.pk).exists():
                    raise TreasuryValidationError("Un type de cotisation porte déjà ce nom dans ce club.")
            setattr(ctype, field, value)
        now = now or timezone.now()
        if amount_changed and ctype.amount is not None:
            local_today = _club_today(_club_settings(club), now)
            next_month = date(local_today.year + (local_today.month == 12), local_today.month % 12 + 1, 1)
            effective_from = next_month
            rate = (
                ContributionTypeRate.all_objects.select_for_update()
                .filter(contribution_type=ctype, effective_from=effective_from)
                .first()
            )
            if rate is None:
                rate = ContributionTypeRate(
                    club=club,
                    contribution_type=ctype,
                    effective_from=effective_from,
                    created_by=updated_by,
                    created_at=now,
                )
            rate.amount = ctype.amount
            rate.created_by = updated_by
            rate.created_at = now
            _save(rate)
        try:
            _save(ctype)
        except IntegrityError:
            raise TreasuryValidationError("Un type de cotisation porte déjà ce nom dans ce club.") from None
        log_action(
            actor=updated_by,
            club=club,
            action_type="treasury.contribution_type.updated",
            obj=ctype,
            before=before,
            after=_contribution_type_snapshot(ctype),
        )
        # B8 : un nouveau tarif (mois suivants) ou un nouveau perimetre change
        # la capacite des mois projetes par les paiements d'avance.
        if amount_changed or before.get("scope") != ctype.scope:
            _recompute_type_allocations(ctype=ctype, actor=updated_by, now=now)
    contribution_type.refresh_from_db()
    return contribution_type


def delete_contribution_type(*, contribution_type: ContributionType, deleted_by) -> None:
    """Supprime un type **jamais utilise** (CDC 4.4.1 ; invariant 7).

    Un type ayant recu un paiement (ou une transaction) ne peut qu'etre
    archive. Au Lot 2, le meme refus s'etendra aux types ayant genere un
    montant du (decision D6, a confirmer).
    """

    club = contribution_type.club
    active_club = get_active_club()
    if active_club is None:
        raise TreasuryValidationError(
            "Aucun club actif dans le contexte de la requête : suppression refusée."
        )
    if active_club.id != club.id:
        raise TenantMismatchError(
            "Suppression refusée : le type de cotisation n'appartient pas au club actif."
        )
    _require_roles(
        deleted_by,
        club,
        TREASURY_MANAGERS,
        "Seuls le Président et le Trésorier peuvent supprimer un type de cotisation.",
    )
    used = (
        Payment.all_objects.filter(club=club, contribution_type=contribution_type).exists()
        or Transaction.all_objects.filter(club=club, contribution_type=contribution_type).exists()
    )
    if used:
        raise TreasuryValidationError(
            "Ce type de cotisation a déjà reçu des paiements : il ne peut pas être supprimé, "
            "seulement archivé."
        )
    with db_transaction.atomic():
        log_action(
            actor=deleted_by,
            club=club,
            action_type="treasury.contribution_type.deleted",
            obj=contribution_type,
            before=_contribution_type_snapshot(contribution_type),
            after=None,
        )
        ContributionTypeRate.all_objects.filter(
            club=club, contribution_type=contribution_type
        ).delete()
        contribution_type.delete()


def get_active_membership_fee_type(club) -> Optional[ContributionType]:
    """Type « adhesion » actif du club, ou ``None`` (au plus un par club)."""

    return ContributionType.all_objects.filter(
        club=club, is_membership_fee=True, status=ContributionType.Status.ACTIVE
    ).first()


# ---------------------------------------------------------------------------
# Montant du des frais d'adhesion (decision du client du 17/11/2026 ;
# CDC 4.3, 4.4.2 ; 10.3 n° 100 confirmee)
# ---------------------------------------------------------------------------
#
# Les frais d'adhesion sont « une somme a payer » : un montant du UNIQUE par
# adhesion, au tarif des frais d'adhesion du club a la date d'entree,
# echeance a la date d'entree. Le paiement des frais s'alloue a ce du (moteur
# 4.4.3, branche « non mensuelle ») ; un surplus reste un credit. Points de
# creation (tous idempotents, jamais deux dus d'adhesion pour une adhesion) :
#
# - ouverture du dossier d'adhesion par le President ou le recruteur
#   (``apps.clubs.services.add_player_with_sponsor``, meme transaction) ;
# - premier paiement valide sur un type « adhesion » si le du manque encore
#   (adhesion ouverte avant la decision, ou registre gele a l'ouverture) ;
# - commande ``rebalance_membership_fee_dues`` pour les donnees existantes.
#
# L'import CSV des joueurs historiques (CDC 4.1, « Inscrit » d'office) ne
# cree PAS de du d'adhesion : position prudente provisoire (question au
# client), sinon tous les membres importes seraient « En dette » des l'import.


def _membership_fee_rate(fee_type: ContributionType, joined_on: date) -> Optional[Decimal]:
    """Tarif des frais d'adhesion en vigueur a la date d'entree (historique
    des tarifs, CDC 4.4.1), a defaut le montant courant du type."""

    rate = _rate_for_period(fee_type, _period_start(joined_on))
    return rate if rate is not None else fee_type.amount


def _existing_membership_fee_due(membership: Membership) -> Optional[Due]:
    """Du d'adhesion deja cree pour cette adhesion (annule ou non), tous
    types « adhesion » confondus (un type archive puis remplace ne cree
    jamais un second du)."""

    return (
        Due.all_objects.filter(
            club_id=membership.club_id, membership=membership, contribution_type__is_membership_fee=True
        )
        .order_by("pk")
        .first()
    )


def _create_membership_fee_due(
    membership: Membership, *, fee_type: ContributionType, actor, now: datetime
) -> Optional[Due]:
    """Cree le du d'adhesion s'il manque (a appeler dans ``atomic()``).
    Renvoie le du existant ou cree, ou ``None`` si aucun du n'est exigible
    (type libre : une cotisation libre ne cree jamais de dette, CLAUDE.md
    regle 3)."""

    existing = _existing_membership_fee_due(membership)
    if existing is not None:
        return existing
    if fee_type.nature != ContributionType.Nature.MANDATORY or fee_type.club_id != membership.club_id:
        return None
    amount = _membership_fee_rate(fee_type, membership.joined_on)
    if amount is None or amount <= 0:
        return None
    club = membership.club
    due = Due(
        club=club,
        membership=membership,
        contribution_type=fee_type,
        period=_period_start(membership.joined_on),
        amount=amount,
        due_date=membership.joined_on,
        source=Due.Source.MEMBERSHIP_FEE,
        created_at=now,
    )
    try:
        with db_transaction.atomic():
            _save(due)
    except IntegrityError:
        # Creation concurrente pour la meme adhesion (contrainte d'unicite
        # adhesion/type/periode) : la premiere fait foi.
        return _existing_membership_fee_due(membership)
    if actor is not None:
        log_action(
            actor=actor,
            club=club,
            action_type="treasury.due.generated",
            obj=due,
            before=None,
            after=_due_snapshot(due),
        )
    _recompute_allocations_for_pairs(club=club, pairs={(membership.pk, fee_type.pk)}, actor=actor, now=now)
    return due


def ensure_membership_fee_due(
    membership: Membership, *, actor, now: Optional[datetime] = None
) -> Optional[Due]:
    """INTERFACE EXPOSEE (app ``clubs``) : cree, a l'ouverture du dossier
    d'adhesion, le montant du unique des frais d'adhesion (CDC 4.3, 4.4.2 ;
    10.3 n° 100). Idempotente : renvoie le du deja cree s'il existe.

    Aucun du (``None``) si le club n'a pas de type « adhesion » actif (le
    paiement des frais reste alors refuse avec un message clair), si ce type
    est libre, ou si le club ne peut pas encaisser (licence suspendue,
    lecture seule, registre gele -- 10.2 n° 108 : aucune dette tant que les
    joueurs ne peuvent pas payer) ; le du sera alors cree au premier
    paiement des frais.

    ``actor`` : auteur journalise (``treasury.due.generated``) ou ``None``
    (aucune entree, convention des taches sans acteur). Aucun controle de
    role : l'appelant a deja verifie le droit d'ajouter un joueur."""

    club = membership.club
    _require_service_club(club)
    existing = _existing_membership_fee_due(membership)
    if existing is not None:
        return existing
    fee_type = get_active_membership_fee_type(club)
    if fee_type is None or _dues_generation_blocked_reason(club):
        return None
    with db_transaction.atomic():
        return _create_membership_fee_due(membership, fee_type=fee_type, actor=actor, now=now or timezone.now())


def _ensure_fee_due_for_payment(*, membership: Membership, ctype: ContributionType, actor, now: datetime) -> None:
    """Avant la repartition d'un paiement valide sur un type « adhesion » :
    cree le du d'adhesion s'il manque, pour que le paiement s'y alloue au
    lieu de devenir un credit (decision du client du 17/11/2026)."""

    if ctype.is_membership_fee:
        _create_membership_fee_due(membership, fee_type=ctype, actor=actor, now=now)


def cancel_membership_fee_due(
    *, membership: Membership, reason: str, cancelled_by, now: Optional[datetime] = None
) -> Optional[DueCancellation]:
    """INTERFACE EXPOSEE (app ``clubs``) : neutralise le du d'adhesion d'une
    adhesion annulee (CDC 4.3, refus du parrain) par une ecriture
    d'annulation motivee -- le du n'est jamais supprime (CLAUDE.md regle 4).
    President uniquement (meme droit que l'annulation de l'adhesion et le
    remboursement). Idempotente : ``None`` s'il n'y a aucun du d'adhesion
    actif. Journalise ``treasury.due.cancelled`` et recalcule la
    repartition 4.4.3 du joueur."""

    club = membership.club
    _require_service_club(club)
    _require_roles(cancelled_by, club, PRESIDENT_ONLY, "Seul le Président peut annuler les frais d'adhésion dus.")
    cleaned = _require_reason(reason, "Le motif de l'annulation est obligatoire.")
    now = now or timezone.now()
    with db_transaction.atomic():
        due = (
            Due.all_objects.select_for_update()
            .filter(
                club=club,
                membership=membership,
                contribution_type__is_membership_fee=True,
                cancellation__isnull=True,
            )
            .order_by("pk")
            .first()
        )
        if due is None:
            return None
        cancellation = DueCancellation(
            club=club, due=due, reason=cleaned, cancelled_by=cancelled_by, cancelled_at=now
        )
        try:
            with db_transaction.atomic():
                _save(cancellation)
        except IntegrityError:
            return None
        log_action(
            actor=cancelled_by,
            club=club,
            action_type="treasury.due.cancelled",
            obj=cancellation,
            before=None,
            after={**_due_snapshot(due), "due_id": due.pk, "reason": cleaned},
        )
        _recompute_allocations_for_pairs(
            club=club, pairs={(membership.pk, due.contribution_type_id)}, actor=cancelled_by, now=now
        )
    return cancellation


@dataclass(frozen=True)
class MembershipFeeRebalanceLine:
    """Une adhesion concernee par :func:`rebalance_membership_fee_dues`."""

    membership_id: int
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal


def _legacy_fee_credit_memberships(club) -> list[tuple[Membership, ContributionType]]:
    """Adhesions dont les frais ont ete payes (net > 0, annulations
    deduites) sans du d'adhesion : (adhesion, type « adhesion » paye)."""

    rows = (
        Transaction.all_objects.filter(
            club=club,
            membership__isnull=False,
            contribution_type__is_membership_fee=True,
            status=Transaction.Status.SUCCEEDED,
            sealed_at__isnull=False,
        )
        .values("membership_id")
        .annotate(net=Sum("amount"), fee_type_id=Min("contribution_type_id"))
        .filter(net__gt=0)
        .order_by("membership_id")
    )
    candidates = {row["membership_id"]: row["fee_type_id"] for row in rows}
    with_due = set(
        Due.all_objects.filter(
            club=club, membership_id__in=list(candidates), contribution_type__is_membership_fee=True
        ).values_list("membership_id", flat=True)
    )
    todo = {pk: type_id for pk, type_id in candidates.items() if pk not in with_due}
    memberships = Membership.all_objects.select_related("club").in_bulk(list(todo))
    types = ContributionType.all_objects.in_bulk(set(todo.values()))
    return [(memberships[pk], types[todo[pk]]) for pk in sorted(todo)]


def rebalance_membership_fee_dues(
    club, *, apply: bool = False, now: Optional[datetime] = None
) -> list[MembershipFeeRebalanceLine]:
    """Donnees existantes (decision du client du 17/11/2026) : pour chaque
    adhesion dont les frais d'adhesion ont ete payes AVANT la decision (le
    paiement etait alors un credit), cree le du d'adhesion manquant (tarif a
    la date d'entree, echeance a la date d'entree) et recalcule la
    repartition. Idempotente. ``apply=False`` (defaut) : simulation complete
    puis annulation, aucune ecriture. Journal : acteur « Systeme ».

    Renvoie les adhesions concernees avec leur solde avant/apres (a la date
    du jour du club) : un joueur dont le credit d'adhesion masquait une
    dette mensuelle repasse « En dette »."""

    _require_service_club(club)
    now = now or timezone.now()
    today = _club_today(_club_settings(club), now)
    lines: list[MembershipFeeRebalanceLine] = []

    class _DryRun(Exception):
        pass

    try:
        with db_transaction.atomic():
            actor = get_system_actor()
            for membership, fee_type in _legacy_fee_credit_memberships(club):
                before = get_balance(membership, at_date=today)
                due = _create_membership_fee_due(membership, fee_type=fee_type, actor=actor, now=now)
                if due is None:
                    continue
                lines.append(
                    MembershipFeeRebalanceLine(
                        membership_id=membership.pk,
                        amount=due.amount,
                        balance_before=before,
                        balance_after=get_balance(membership, at_date=today),
                    )
                )
            if not apply:
                raise _DryRun
    except _DryRun:
        pass
    return lines


# ---------------------------------------------------------------------------
# Grand livre chaine (CDC 5.3 ; schema-treasury.md §6)
# ---------------------------------------------------------------------------


def _ledger_key(key_id: str) -> bytes:
    keys = getattr(settings, "LEDGER_HMAC_KEYS", None) or {}
    secret = keys.get(key_id) if key_id else None
    if not secret or len(secret) < MIN_LEDGER_KEY_LENGTH or secret.lower().startswith("changeme"):
        raise LedgerKeyError(
            "La clé de sécurisation des écritures financières est absente ou invalide : "
            "aucune opération financière n'est possible pour le moment. Contactez l'équipe Vesta."
        )
    return secret.encode("utf-8")


def _any_valid_ledger_key() -> bool:
    """Vrai si au moins une cle de chainage valide est configuree.

    Sert a distinguer, a la verification, une erreur de configuration
    globale (aucune cle : verification impossible, sans gel) d'une ligne
    portant un ``key_id`` inconnu alors que des cles existent : les
    anciennes cles ne sont jamais retirees (regle d'exploitation), donc
    une telle ligne est un indice d'alteration (rupture, CDC 5.3)."""

    keys = getattr(settings, "LEDGER_HMAC_KEYS", None) or {}
    for key_id in keys:
        try:
            _ledger_key(key_id)
        except LedgerKeyError:
            continue
        return True
    return False


def _active_key_id() -> str:
    key_id = getattr(settings, "LEDGER_HMAC_ACTIVE_KEY_ID", "") or ""
    if not key_id or len(key_id) > 16:
        raise LedgerKeyError(
            "La clé de sécurisation des écritures financières n'est pas configurée : "
            "aucune opération financière n'est possible pour le moment. Contactez l'équipe Vesta."
        )
    _ledger_key(key_id)
    return key_id


def _utc_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def transaction_canonical_payload(txn: Transaction) -> str:
    """Serialisation canonique du contenu hache (schema-treasury.md §6.4).

    JSON a cles triees, sans espaces, montant en chaine a 2 decimales, dates
    ISO 8601, horodatage UTC. Uniquement des identifiants : aucune donnee
    personnelle (l'anonymisation d'un compte ne casse pas la chaine). La cle
    ``expense`` est deja presente (``null`` tant que les depenses n'existent
    pas, Lot 2) pour qu'aucune empreinte existante ne change a leur arrivee.

    Format versionne par ``txn.payload_version`` :

    - **v1** (transactions scellees avant l'audit de securite) : exactement
      les cles d'origine, sans cle ``v`` -- inchange, pour que toute
      empreinte deja en base reste verifiable ;
    - **v2** : cle ``"v": 2`` plus les champs du `Payment` lie qui n'etaient
      pas couverts (``payment_method``, ``payment_reference``,
      ``payment_source``, ``payment_receipt_number``,
      ``payment_validated_by``, ``payment_attachment`` ; ``null`` sans
      paiement lie). Retrograder une ligne en v1 change le contenu hache :
      la rupture est detectee.
    """

    version = txn.payload_version
    if version not in SUPPORTED_LEDGER_PAYLOAD_VERSIONS:
        raise TreasuryValidationError(f"Version de format de transaction inconnue : {version}.")
    payload = {
        "club": txn.club_id,
        "sequence": txn.sequence,
        "kind": txn.kind,
        "payment": txn.payment_id,
        "reversal": txn.reversal_id,
        "expense": getattr(txn, "expense_id", None),
        "membership": txn.membership_id,
        "contribution_type": txn.contribution_type_id,
        "amount": _money_str(txn.amount),
        "currency": txn.currency,
        "value_date": txn.value_date.isoformat() if txn.value_date else None,
        "provider": txn.provider,
        "external_ref": txn.external_ref or None,
        "status": txn.status,
        "sealed_at": _utc_iso(txn.sealed_at),
        "key_id": txn.key_id,
    }
    if version >= 2:
        payment = txn.payment if txn.payment_id else None
        payload.update(
            {
                "v": version,
                "payment_method": payment.method if payment else None,
                "payment_reference": (payment.reference or None) if payment else None,
                "payment_source": payment.source if payment else None,
                "payment_receipt_number": payment.receipt_number if payment else None,
                "payment_validated_by": payment.validated_by_id if payment else None,
                "payment_attachment": (payment.attachment.name or None) if payment else None,
            }
        )
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_transaction_hash(txn: Transaction, *, previous_hash: str, key_id: str) -> str:
    """HMAC-SHA256(cle[key_id], contenu canonique + empreinte precedente)."""

    message = (transaction_canonical_payload(txn) + previous_hash).encode("utf-8")
    return hmac.new(_ledger_key(key_id), message, hashlib.sha256).hexdigest()


def _lock_chain_state(club) -> LedgerChainState:
    """Verrouille (``select_for_update``) la tete de chaine du club, en la
    creant a la premiere ecriture. A appeler dans ``transaction.atomic()``.

    Sous SQLite (developpement), ``select_for_update`` est sans effet : la
    serialisation reelle des scellements concurrents n'est garantie que sur
    MySQL/MariaDB (a rejouer avant la fin du lot, CLAUDE.md §9). La
    contrainte d'unicite ``(club, sequence)`` reste un dernier rempart.
    """

    queryset = LedgerChainState.all_objects.select_for_update()
    state = queryset.filter(club=club).first()
    if state is None:
        try:
            with db_transaction.atomic():
                LedgerChainState(club=club, last_hash=LEDGER_GENESIS_HASH).save(force_insert=True)
        except (IntegrityError, DjangoValidationError):
            pass  # Creee au meme instant par une ecriture concurrente.
        state = queryset.get(club=club)
    return state


def _frozen_message(state: LedgerChainState) -> str:
    return (
        "Les écritures financières de ce club sont temporairement gelées pour vérification "
        f"({state.frozen_reason}). Aucun joueur n'est pénalisé ; l'équipe Vesta a été alertée."
    )


def _precheck_ledger_writable(club) -> None:
    """Controle rapide, sans verrou, avant les ecritures (le controle qui
    fait foi est refait sous verrou au scellement)."""

    state = LedgerChainState.all_objects.filter(club=club).first()
    if state is not None and state.is_frozen:
        raise LedgerFrozenError(_frozen_message(state))
    _active_key_id()


def _seal(txn: Transaction, status: str, now: datetime) -> Transaction:
    """Scelle ``txn`` dans la chaine de son club (a appeler dans ``atomic()``).

    Attribue ``sequence``, ``previous_hash``, ``key_id``, ``sealed_at`` et
    ``hash``, attribue le numero de recu d'un paiement reussi, puis avance la
    tete de chaine -- le tout dans la meme transaction de base de donnees.
    """

    state = _lock_chain_state(txn.club)
    if state.is_frozen:
        raise LedgerFrozenError(_frozen_message(state))
    key_id = _active_key_id()

    if txn.kind == Transaction.Kind.PAYMENT and status == Transaction.Status.SUCCEEDED:
        payment = txn.payment
        if payment.receipt_number is None:
            state.last_receipt_number += 1
            payment.receipt_number = state.last_receipt_number
            _save(payment)
            # Reçu PDF (CDC 4.4.4) : généré une fois la validation réellement
            # enregistrée, jamais avant (voir section « Reçu de paiement »).
            _schedule_payment_receipt(payment.pk)
            # Notification « Paiement validé » (CDC 4.17) : ici et nulle part
            # ailleurs, car le numéro de reçu n'est attribué qu'une fois par
            # paiement -- un seul événement, quel que soit le chemin
            # (saisie, caisse, adhésion, « J'ai payé », passerelle). Dans la
            # même transaction : rien n'est notifié si la validation échoue.
            _notify_payment_validated(payment, now)

    sealed_at = now.replace(microsecond=0)
    txn.status = status
    txn.status_changed_at = sealed_at
    txn.sequence = state.last_sequence + 1
    txn.previous_hash = state.last_hash
    txn.key_id = key_id
    txn.sealed_at = sealed_at
    txn.payload_version = LEDGER_PAYLOAD_VERSION
    txn.hash = compute_transaction_hash(txn, previous_hash=txn.previous_hash, key_id=key_id)
    _save(txn)

    state.last_sequence = txn.sequence
    state.last_hash = txn.hash
    _save(state)
    return txn


PAYMENT_VALIDATED_TITLE = "Paiement validé"


def _notify_payment_validated(payment: Payment, now: datetime) -> None:
    """Notification « Paiement validé » au joueur (CDC 4.17 : in-app + email
    selon sa préférence, l'email étant mis en file, jamais envoyé ici).

    Appelée par :func:`_seal` au moment où le paiement reçoit son numéro de
    reçu, donc une seule fois par paiement. Montant au format du reçu
    (:func:`format_receipt_amount`).

    **Import historique CSV exclu** (position prudente, signalée au compte
    rendu) : des paiements anciens ne déclenchent ni notification ni email
    en masse. Aucun lien ni pièce jointe du reçu dans le texte : la pièce
    jointe du reçu à l'email reste une question ouverte au client ; la
    notification mène au paiement (``target``), comme auparavant."""

    if payment.source == Payment.Source.CSV_IMPORT:
        return

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    create_notification(
        recipient=payment.membership.user,
        event_type=Notification.EventType.PAYMENT_VALIDATED,
        title=PAYMENT_VALIDATED_TITLE,
        message=(
            f"Votre paiement de {format_receipt_amount(payment.amount, payment.currency)} "
            f"({payment.contribution_type.name}) a été validé. Reçu n° {payment.receipt_number}."
        ),
        club=payment.club,
        target=payment,
        now=now,
    )


def open_payment_transaction(
    *,
    payment: Payment,
    provider: str,
    status: str = Transaction.Status.PENDING,
    external_ref: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Transaction:
    """Ouvre la transaction **non scellee** d'un paiement (``initiated`` ou
    ``pending``). Primitive du grand livre pour les circuits du Lot 2
    (« J'ai paye », passerelle) ; le chemin ``treasurer_entry`` n'en a pas
    besoin (transaction creee directement scellee)."""

    if status not in (Transaction.Status.INITIATED, Transaction.Status.PENDING):
        raise TreasuryValidationError("Une transaction s'ouvre à l'état « initié » ou « en attente ».")
    if provider not in Transaction.Provider.values:
        raise TreasuryValidationError("Fournisseur de paiement inconnu.")
    club = payment.club
    if Transaction.all_objects.filter(club=club, payment=payment).exists():
        raise TreasuryValidationError("Ce paiement a déjà une transaction.")
    external_ref = (external_ref or "").strip() or None
    if external_ref and Transaction.all_objects.filter(
        club=club, provider=provider, external_ref=external_ref
    ).exists():
        raise TreasuryValidationError("Cette référence externe est déjà utilisée pour ce fournisseur.")

    now = now or timezone.now()
    txn = Transaction(
        club=club,
        kind=Transaction.Kind.PAYMENT,
        payment=payment,
        membership=payment.membership,
        contribution_type=payment.contribution_type,
        amount=payment.amount,
        currency=payment.currency,
        value_date=payment.paid_on,
        provider=provider,
        external_ref=external_ref,
        status=status,
        status_changed_at=now,
        created_at=now,
    )
    with db_transaction.atomic():
        _save(txn)
        log_action(
            actor=payment.submitted_by,
            club=club,
            action_type="treasury.transaction.opened",
            obj=txn,
            before=None,
            after=_transaction_snapshot(txn),
        )
    return txn


def advance_transaction(
    *,
    transaction_obj: Transaction,
    status: str,
    external_ref: Optional[str] = None,
    now: Optional[datetime] = None,
    actor=None,
) -> Transaction:
    """Fait avancer une transaction non scellee :
    ``initiated -> pending -> succeeded | failed`` (``initiated`` peut aller
    directement a l'etat final). Atteindre ``succeeded``/``failed`` la scelle
    atomiquement ; elle devient alors immuable.

    Un paiement hors passerelle ne peut reussir que s'il porte son valideur
    (``validated_by``, confirme par l'appelant ; schema §5.1).

    ``actor`` (facultatif) : auteur reel du changement d'etat pour le
    journal (ex. le Tresorier qui refuse une declaration « J'ai paye ») ;
    a defaut, le valideur du paiement, sinon son auteur.
    """

    now = now or timezone.now()
    with db_transaction.atomic():
        txn = Transaction.all_objects.select_for_update().get(pk=transaction_obj.pk)
        if txn.is_sealed:
            raise TreasuryValidationError("Cette transaction est déjà scellée : elle ne peut plus changer d'état.")
        if status not in ALLOWED_TRANSITIONS.get(txn.status, set()):
            raise TreasuryValidationError("Changement d'état de transaction non autorisé.")
        before = _transaction_snapshot(txn)

        external_ref = (external_ref or "").strip() or None
        if external_ref and external_ref != txn.external_ref:
            if Transaction.all_objects.filter(
                club=txn.club, provider=txn.provider, external_ref=external_ref
            ).exclude(pk=txn.pk).exists():
                raise TreasuryValidationError("Cette référence externe est déjà utilisée pour ce fournisseur.")
            txn.external_ref = external_ref

        if status in Transaction.TERMINAL_STATUSES:
            if (
                txn.kind == Transaction.Kind.PAYMENT
                and status == Transaction.Status.SUCCEEDED
                and txn.payment.source != Payment.Source.GATEWAY
                and txn.payment.validated_by_id is None
            ):
                raise TreasuryValidationError(
                    "Ce paiement doit d'abord être validé par le Trésorier avant d'être réussi."
                )
            _seal(txn, status, now)
        else:
            txn.status = status
            txn.status_changed_at = now
            _save(txn)

        payment = txn.payment
        if actor is None and payment is not None:
            actor = payment.validated_by or payment.submitted_by
        if actor is not None and payment is not None:
            log_action(
                actor=actor,
                club=txn.club,
                action_type="treasury.transaction.status_changed",
                obj=txn,
                before=before,
                after=_transaction_snapshot(txn),
            )
            if txn.kind == Transaction.Kind.PAYMENT and status == Transaction.Status.SUCCEEDED:
                _ensure_fee_due_for_payment(
                    membership=payment.membership, ctype=payment.contribution_type, actor=actor, now=now
                )
                _recompute_allocations(
                    membership=payment.membership,
                    ctype=payment.contribution_type,
                    actor=actor,
                    now=now,
                )
    return txn


def freeze_ledger(*, club, reason: str, actor, now: Optional[datetime] = None) -> LedgerChainState:
    """Gele les ecritures financieres du club (CDC 5.3). Aucun scellement
    n'est plus possible ; les lectures restent possibles et aucun joueur
    n'est penalise. Appele par la verification quotidienne
    (:func:`run_ledger_verification`) ; la levee du gel est un point ouvert
    (Q8 de schema-treasury.md).

    ``actor`` : ``None`` pour la tache cron (aucun acteur reel) -- aucune
    entree `AuditLog` n'est alors ecrite, le gel reste trace par
    ``frozen_at``/``frozen_reason`` (meme convention que les commandes de
    licences, point ouvert)."""

    cleaned = _require_reason(reason, "Le motif du gel est obligatoire.")
    now = now or timezone.now()
    with db_transaction.atomic():
        state = _lock_chain_state(club)
        if state.is_frozen:
            return state
        before = {"is_frozen": False}
        state.is_frozen = True
        state.frozen_at = now
        state.frozen_reason = cleaned
        _save(state)
        if actor is not None:
            log_action(
                actor=actor,
                club=club,
                action_type="treasury.ledger.frozen",
                obj=state,
                before=before,
                after={"is_frozen": True, "frozen_at": now, "frozen_reason": cleaned},
            )
    return state


@dataclass(frozen=True)
class ChainVerificationResult:
    """Resultat de :func:`verify_chain`. ``details`` : diagnostic technique
    en francais, sans donnee personnelle."""

    ok: bool
    checked_count: int
    first_broken_sequence: Optional[int] = None
    details: str = ""
    # Vrai si la verification n'a pas pu etre menee parce qu'AUCUNE cle
    # valide n'est configuree : incident de configuration global, pas une
    # preuve d'alteration -- la tache cron ne gele pas le club dans ce cas.
    # Une ligne portant un ``key_id`` inconnu alors que des cles existent est
    # au contraire une rupture (``key_unavailable`` reste faux).
    key_unavailable: bool = False


def verify_chain(club) -> ChainVerificationResult:
    """Recalcule la chaine du club et la compare aux empreintes stockees
    (CDC 5.3 ; schema-treasury.md §6.4). Lecture seule : ne gele rien et ne
    modifie aucune donnee (la commande cron decidera de l'alerte et du gel).

    Controles : sequence continue a partir de 1 sans trou, ``previous_hash``
    egal a l'empreinte de la ligne precedente (genese pour la premiere),
    empreinte recalculee egale a l'empreinte stockee (avec la cle
    ``key_id`` de chaque ligne), tete de chaine coherente avec la derniere
    ligne (detecte la suppression des dernieres lignes), aucune transaction
    a l'etat final sans scellement, et, pour une transaction de paiement,
    concordance du `Payment` lie (montant, devise, joueur, type) avec la
    transaction.

    Cle absente : si aucune cle valide n'est configuree, resultat
    ``key_unavailable`` (sans gel) ; si des cles existent mais que la ligne
    porte un ``key_id`` inconnu ou invalide, **rupture** (les anciennes cles
    ne sont jamais retirees : c'est un indice d'alteration).

    Parcourt les transactions scellees une a une (``iterator()``) : c'est le
    seul traitement du domaine qui le fait, par nature ; il est quotidien.
    """

    def broken(count: int, sequence: Optional[int], details: str) -> ChainVerificationResult:
        return ChainVerificationResult(ok=False, checked_count=count, first_broken_sequence=sequence, details=details)

    expected_sequence = 1
    expected_previous = LEDGER_GENESIS_HASH
    count = 0
    rows = (
        Transaction.all_objects.filter(club=club, sealed_at__isnull=False)
        .select_related("payment")
        .order_by("sequence")
        .iterator()
    )
    for txn in rows:
        count += 1
        if txn.sequence != expected_sequence:
            return broken(count, expected_sequence, f"Ligne manquante : séquence {expected_sequence} attendue, {txn.sequence} trouvée.")
        if txn.previous_hash != expected_previous:
            return broken(count, txn.sequence, "L'empreinte précédente ne correspond pas à la ligne précédente.")
        if txn.payload_version not in SUPPORTED_LEDGER_PAYLOAD_VERSIONS:
            return broken(count, txn.sequence, "Version de format inconnue : ligne altérée.")
        try:
            recomputed = compute_transaction_hash(txn, previous_hash=txn.previous_hash, key_id=txn.key_id)
        except LedgerKeyError:
            if not _any_valid_ledger_key():
                return ChainVerificationResult(
                    ok=False,
                    checked_count=count,
                    first_broken_sequence=txn.sequence,
                    details="Aucune clé de chaînage valide n'est configurée : vérification impossible.",
                    key_unavailable=True,
                )
            return broken(
                count,
                txn.sequence,
                f"Clé de chaînage « {txn.key_id} » inconnue alors que des clés sont configurées : "
                "les anciennes clés ne sont jamais retirées, la ligne est considérée comme altérée.",
            )
        if not hmac.compare_digest(recomputed, txn.hash or ""):
            return broken(count, txn.sequence, "Contenu modifié : l'empreinte recalculée diffère de l'empreinte stockée.")
        payment = txn.payment if txn.payment_id else None
        if payment is not None and (
            payment.amount != txn.amount
            or payment.currency != txn.currency
            or payment.membership_id != txn.membership_id
            or payment.contribution_type_id != txn.contribution_type_id
        ):
            return broken(
                count,
                txn.sequence,
                "Paiement lié modifié : son montant, sa devise, son joueur ou son type ne correspond plus à la transaction.",
            )
        expected_previous = txn.hash
        expected_sequence += 1

    last_sequence = expected_sequence - 1
    state = LedgerChainState.all_objects.filter(club=club).first()
    if state is None:
        if count:
            return broken(count, 1, "Tête de chaîne absente alors que des transactions scellées existent.")
    elif state.last_sequence != last_sequence or state.last_hash != expected_previous:
        return broken(
            count,
            last_sequence + 1,
            f"Tête de chaîne incohérente : {state.last_sequence} ligne(s) attendue(s), {last_sequence} trouvée(s).",
        )

    if Transaction.all_objects.filter(
        club=club, sealed_at__isnull=True, status__in=Transaction.TERMINAL_STATUSES
    ).exists():
        return broken(count, None, "Transaction à l'état final sans scellement.")

    return ChainVerificationResult(ok=True, checked_count=count)


# ---------------------------------------------------------------------------
# Frais d'adhesion -- INTERFACE EXPOSEE A `backend-dev` (CDC 4.3)
# ---------------------------------------------------------------------------


@_retry_idempotent_when_locked
def record_membership_fee_payment(
    *,
    membership: Membership,
    amount: Any,
    method: str,
    paid_on: date,
    validated_by,
    reference: str = "",
    attachment=None,
    client_uuid=None,
    now: Optional[datetime] = None,
) -> Payment:
    """Enregistre et valide le paiement des frais d'adhesion d'un joueur
    (CDC 4.3 etape 2 ; 4.4.4 ; 7.2). Forme definitive : c'est exactement le
    meme `Payment` + `Transaction` chainee qu'au Lot 2.

    Parametres :

    - ``membership`` : adhesion du joueur qui paie (« En attente » en
      general ; « Inscrit » accepte ; « Parti » refuse). Le club est
      **deduit de cette adhesion**, jamais transmis a part.
    - ``amount`` : ``Decimal``, ``int`` ou chaine (``"5"``, ``"5.50"``) ;
      **jamais** ``float``. Arrondi a 2 decimales (ROUND_HALF_UP). Un
      paiement partiel est accepte ; les paiements s'additionnent.
    - ``method`` : ``"cash"``, ``"mobile_money"`` ou ``"payment_link"``
      (``Payment.Method``). ``"card"`` est reserve a la phase 2 (refuse).
    - ``paid_on`` : ``datetime.date`` de valeur, au plus aujourd'hui dans le
      fuseau du club.
    - ``validated_by`` : ``User`` qui saisit et valide ; doit etre
      **Tresorier ou Tresorier adjoint** actif de ce club (CDC 2.4, 4.4.4).
    - ``reference`` (facultatif) : reference mobile money / lien.
    - ``attachment`` (facultatif) : fichier justificatif (``File``).
    - ``client_uuid`` (facultatif, correctif M4) : cle d'idempotence unique
      par club (voir :func:`record_payment`). Un rejeu de la meme saisie
      renvoie le paiement existant sans aucune ecriture, marque
      ``idempotent_replay = True`` (``False`` pour une creation) ; une cle
      deja utilisee pour une autre saisie leve :class:`ClientUuidConflictError`.
      L'appelant (app ``clubs``) doit alors s'abstenir de ses propres
      ecritures (journal du dossier, etc.).

    Le type de cotisation n'est pas un parametre : c'est le type « adhesion »
    actif du club (:func:`get_active_membership_fee_type`).

    Renvoie le `Payment` cree ; sa transaction scellee est
    ``payment.transaction`` et son numero de recu ``payment.receipt_number``.
    Journalise ``treasury.payment.validated``. Ne modifie **ni**
    ``Membership.status`` **ni** le dossier d'adhesion : le passage
    « Inscrit » (paiement + signature du parrain) appartient a l'app
    ``clubs``, qui interroge :func:`has_paid_membership_fee` et peut
    referencer ce paiement dans ``MembershipApplication.membership_fee_payment``.

    Exceptions (toutes avec un message francais pret a afficher) :

    - :class:`TreasuryPermissionError` : ``validated_by`` n'est pas
      Tresorier/adjoint actif du club du joueur ;
    - :class:`TreasuryValidationError` (dont :class:`InvalidAmountError`) :
      aucun type « adhesion » actif, joueur parti, montant invalide ou <= 0,
      mode inconnu ou ``card``, date future, parametres du club absents ;
    - :class:`LedgerFrozenError` : ecritures du club gelees (CDC 5.3) ;
    - :class:`LedgerKeyError` : cle de chainage absente de l'environnement ;
    - ``apps.core.tenant.TenantMismatchError`` : appel dans le contexte d'un
      autre club actif que celui du joueur.

    Rien n'est ecrit si une exception est levee.
    """

    now = now or timezone.now()
    club = membership.club
    _require_service_club(club)
    _require_roles(
        validated_by,
        club,
        PAYMENT_RECORDERS,
        "Seuls le Trésorier et le Trésorier adjoint peuvent enregistrer un paiement.",
    )
    parsed_uuid = None if client_uuid is None else _parse_client_uuid(client_uuid)

    def replay(existing: Payment) -> Payment:
        return _replayed_entry_payment(
            existing,
            membership=membership,
            contribution_type=None,
            amount=amount,
            method=method,
            reference=reference,
            paid_on=paid_on,
            actor=validated_by,
        )

    if parsed_uuid is not None:
        existing = _existing_client_uuid_payment(club, parsed_uuid)
        if existing is not None:
            return replay(existing)

    current_status = Membership.all_objects.filter(pk=membership.pk).values_list("status", flat=True).first()
    if current_status is None or current_status == Membership.Status.DEPARTED:
        raise TreasuryValidationError("Ce joueur a quitté le club : aucun paiement ne peut être enregistré.")
    fee_type = get_active_membership_fee_type(club)
    if fee_type is None:
        raise TreasuryValidationError(
            "Aucun type de cotisation « adhésion » actif dans ce club : le Président ou le "
            "Trésorier doit d'abord le créer."
        )
    money = to_money(amount)
    if money <= 0:
        raise InvalidAmountError("Le montant doit être strictement positif.")
    if method not in TREASURER_ENTRY_METHODS:
        raise TreasuryValidationError("Mode de paiement invalide : espèces, mobile money ou lien de paiement.")
    if not isinstance(paid_on, date) or isinstance(paid_on, datetime):
        raise TreasuryValidationError("La date du paiement est invalide.")
    club_settings = _club_settings(club)
    if paid_on > _club_today(club_settings, now):
        raise TreasuryValidationError("La date du paiement ne peut pas être dans le futur.")
    cleaned_reference = (reference or "").strip()
    if len(cleaned_reference) > 120:
        raise TreasuryValidationError("La référence ne doit pas dépasser 120 caractères.")
    _validate_attachment(attachment)
    _precheck_ledger_writable(club)

    def create() -> Payment:
        payment = Payment(
            club=club,
            membership=membership,
            contribution_type=fee_type,
            amount=money,
            currency=club_settings.currency,
            method=method,
            reference=cleaned_reference,
            paid_on=paid_on,
            source=Payment.Source.TREASURER_ENTRY,
            submitted_by=validated_by,
            submitted_at=now,
            validated_by=validated_by,
            validated_at=now,
            client_uuid=parsed_uuid,
        )
        if attachment is not None:
            rename_upload_to_real_type(attachment)
            payment.attachment = attachment
        _save(payment)
        txn = Transaction(
            club=club,
            kind=Transaction.Kind.PAYMENT,
            payment=payment,
            membership=membership,
            contribution_type=fee_type,
            amount=money,
            currency=payment.currency,
            value_date=paid_on,
            provider=Transaction.Provider.MANUAL,
            external_ref=None,
            status=Transaction.Status.SUCCEEDED,
            status_changed_at=now,
            created_at=now,
        )
        _seal(txn, Transaction.Status.SUCCEEDED, now)
        log_action(
            actor=validated_by,
            club=club,
            action_type="treasury.payment.validated",
            obj=payment,
            before=None,
            after=_payment_snapshot(payment, txn),
        )
        # Decision du client du 17/11/2026 : les frais s'allouent au du
        # d'adhesion (cree ici s'il manque), jamais en credit.
        _ensure_fee_due_for_payment(membership=membership, ctype=fee_type, actor=validated_by, now=now)
        _recompute_allocations(membership=membership, ctype=fee_type, actor=validated_by, now=now)
        return payment

    return _create_idempotent(club=club, parsed_uuid=parsed_uuid, create=create, replay=replay)


def has_paid_membership_fee(membership: Membership) -> bool:
    """Vrai si les frais d'adhesion de ce joueur sont **entierement** payes
    (CDC 4.3 ; invariant 10, partie tresorerie).

    Calcul (agregation SQL, aucun champ stocke) : pour chaque type
    « adhesion » du club (actif ou archive), somme des transactions scellees
    ``succeeded`` du joueur -- paiements moins annulations approuvees. Vrai
    des qu'un type atteint son montant. Les transactions en attente, echouees
    ou non scellees ne comptent jamais. Lecture seule, possible meme si le
    club est gele.

    Ne regarde ni la signature du parrain ni ``Membership.status`` : le
    passage « Inscrit » est compose par l'app ``clubs``.

    Depuis la decision du client du 17/11/2026, si l'adhesion porte un du
    d'adhesion actif (non annule), la reference est **ce du** (tarif a la
    date d'entree) : frais payes des que le net verse sur les types
    « adhesion » l'atteint.
    """

    due_amount = (
        Due.all_objects.filter(
            club_id=membership.club_id,
            membership=membership,
            contribution_type__is_membership_fee=True,
            cancellation__isnull=True,
        )
        .order_by("pk")
        .values_list("amount", flat=True)
        .first()
    )
    if due_amount is not None:
        net = Transaction.all_objects.filter(
            club_id=membership.club_id,
            membership=membership,
            contribution_type__is_membership_fee=True,
            status=Transaction.Status.SUCCEEDED,
            sealed_at__isnull=False,
        ).aggregate(net=Sum("amount"))["net"]
        return (net or Decimal("0.00")) >= due_amount

    rows = (
        Transaction.all_objects.filter(
            club_id=membership.club_id,
            membership=membership,
            contribution_type__is_membership_fee=True,
            status=Transaction.Status.SUCCEEDED,
            sealed_at__isnull=False,
        )
        .values("contribution_type_id", "contribution_type__amount")
        .annotate(net=Sum("amount"))
    )
    return any(
        row["contribution_type__amount"] is not None and row["net"] >= row["contribution_type__amount"]
        for row in rows
    )


_REVERSAL_ALREADY_EXISTS_MESSAGE = (
    "Ce paiement fait déjà l'objet d'une annulation : un paiement ne s'annule qu'une fois."
)


def refund_membership_fee(
    *, membership: Membership, reason: str, president, now: Optional[datetime] = None
) -> list[PaymentReversal]:
    """Rembourse les frais d'adhesion apres refus du parrain et annulation de
    l'adhesion (CDC 4.3 : « le sort du paiement (remboursement ou
    conservation) est enregistre »).

    Decision D9 de schema-treasury.md (**a confirmer par le client**) : le
    remboursement s'enregistre comme une annulation ``reason_kind=refund``
    validee par le President, apres confirmation en modale (plus de PIN,
    decision du 11/10/2026). En une seule action, chaque paiement d'adhesion valide et non encore
    annule du joueur recoit une `PaymentReversal` approuvee et une
    transaction negative chainee. Apres l'appel,
    :func:`has_paid_membership_fee` renvoie ``False``.

    La **conservation** du paiement ne passe pas par la tresorerie (aucune
    ecriture financiere) : l'app ``clubs`` l'enregistre dans le dossier.

    Exceptions : :class:`TreasuryPermissionError` (pas President du club),
    :class:`TreasuryValidationError` (motif vide, aucun paiement a
    rembourser, annulation deja en cours ou rejetee sur un paiement),
    :class:`LedgerFrozenError`, :class:`LedgerKeyError`.
    """

    now = now or timezone.now()
    club = membership.club
    _require_service_club(club)
    _require_roles(
        president, club, PRESIDENT_ONLY, "Seul le Président peut décider du remboursement des frais d'adhésion."
    )
    cleaned = _require_reason(reason, "Le motif du remboursement est obligatoire.")
    payments = list(
        Payment.all_objects.filter(
            club=club,
            membership=membership,
            contribution_type__is_membership_fee=True,
            transaction__status=Transaction.Status.SUCCEEDED,
            transaction__sealed_at__isnull=False,
        ).order_by("pk")
    )
    # Une demande refusee ne bloque pas (correctif D-A4) : seule une demande
    # en attente doit d'abord etre traitee par le President.
    blocking = PaymentReversal.all_objects.filter(
        club=club, payment__in=payments, status=PaymentReversal.Status.PENDING_APPROVAL
    )
    if blocking.exists():
        raise TreasuryValidationError(
            "Une annulation est déjà en attente pour un paiement d'adhésion de ce joueur : "
            "traitez-la avant de rembourser."
        )
    already_reversed = set(
        PaymentReversal.all_objects.filter(
            club=club, payment__in=payments, status=PaymentReversal.Status.APPROVED
        ).values_list("payment_id", flat=True)
    )
    to_refund = [p for p in payments if p.pk not in already_reversed]
    if not to_refund:
        raise TreasuryValidationError("Aucun paiement de frais d'adhésion à rembourser pour ce joueur.")
    _precheck_ledger_writable(club)

    reversals = []
    try:
        with db_transaction.atomic():
            for payment in to_refund:
                reversal = _create_reversal(
                    payment=payment,
                    reason=cleaned,
                    reason_kind=PaymentReversal.ReasonKind.REFUND,
                    requested_by=president,
                    now=now,
                )
                reversals.append(_approve_locked(reversal=reversal, approved_by=president, now=now))
    except IntegrityError:
        raise TreasuryValidationError(_REVERSAL_ALREADY_EXISTS_MESSAGE) from None
    return reversals


# ---------------------------------------------------------------------------
# Annulations (CDC 4.4.4, 7.2 ; schema-treasury.md §5.3)
# ---------------------------------------------------------------------------


def _raise_if_open_reversal(club, payment: Payment) -> None:
    """Refuse une nouvelle demande si une demande est en attente ou si le
    paiement est deja annule ; une demande refusee ne bloque pas (D-A4)."""

    statuses = set(
        PaymentReversal.all_objects.filter(
            club=club, payment=payment, status__in=PaymentReversal.OPEN_STATUSES
        ).values_list("status", flat=True)
    )
    if PaymentReversal.Status.APPROVED in statuses:
        raise TreasuryValidationError("Ce paiement a déjà été annulé : un paiement ne s'annule qu'une fois.")
    if PaymentReversal.Status.PENDING_APPROVAL in statuses:
        raise TreasuryValidationError(
            "Une demande d'annulation est déjà en attente pour ce paiement : le Président doit d'abord la traiter."
        )


def _create_reversal(*, payment: Payment, reason: str, reason_kind: str, requested_by, now: datetime) -> PaymentReversal:
    reversal = PaymentReversal(
        club=payment.club,
        payment=payment,
        reason=reason,
        reason_kind=reason_kind,
        status=PaymentReversal.Status.PENDING_APPROVAL,
        requested_by=requested_by,
        requested_at=now,
    )
    _save(reversal)
    log_action(
        actor=requested_by,
        club=payment.club,
        action_type="treasury.payment_reversal.requested",
        obj=reversal,
        before=None,
        after=_reversal_snapshot(reversal),
    )
    return reversal


def _approve_locked(*, reversal: PaymentReversal, approved_by, now: datetime) -> PaymentReversal:
    """Approuve et scelle l'annulation (a appeler dans ``atomic()``, droits
    deja verifies). D11 : annulation totale ; D10 : date de valeur du paiement
    d'origine (decisions a confirmer)."""

    locked = PaymentReversal.all_objects.select_for_update().get(pk=reversal.pk)
    if locked.status != PaymentReversal.Status.PENDING_APPROVAL:
        raise TreasuryValidationError("Cette annulation a déjà été traitée.")
    before = _reversal_snapshot(locked)
    payment = locked.payment
    locked.status = PaymentReversal.Status.APPROVED
    locked.approved_by = approved_by
    locked.approved_at = now
    _save(locked)
    txn = Transaction(
        club=payment.club,
        kind=Transaction.Kind.PAYMENT_REVERSAL,
        reversal=locked,
        membership=payment.membership,
        contribution_type=payment.contribution_type,
        amount=-payment.amount,
        currency=payment.currency,
        value_date=payment.paid_on,
        provider=Transaction.Provider.MANUAL,
        external_ref=None,
        status=Transaction.Status.SUCCEEDED,
        status_changed_at=now,
        created_at=now,
    )
    _seal(txn, Transaction.Status.SUCCEEDED, now)
    _recompute_allocations(
        membership=payment.membership,
        ctype=payment.contribution_type,
        actor=approved_by,
        now=now,
    )
    log_action(
        actor=approved_by,
        club=payment.club,
        action_type="treasury.payment_reversal.approved",
        obj=locked,
        before=before,
        after=_reversal_snapshot(locked, txn),
    )
    return locked


def request_payment_reversal(
    *,
    payment: Payment,
    reason: str,
    requested_by,
    reason_kind: str = PaymentReversal.ReasonKind.ERROR,
    now: Optional[datetime] = None,
) -> PaymentReversal:
    """Demande l'annulation d'un paiement valide (Tresorier, adjoint ou
    President). Aucune ecriture financiere tant que le President n'a pas
    approuve (:func:`approve_payment_reversal`). Un paiement ne s'annule
    qu'une fois (schema §5.3). ``reason_kind=refund`` est reserve aux frais
    d'adhesion (D9).

    Correctif D-A4 (13/11/2026) : apres le REFUS d'une demande, une nouvelle
    demande est possible (CDC 4.4.4 : une erreur se corrige par une ecriture
    d'annulation) ; la demande refusee reste conservee telle quelle et
    journalisee. Refus si une demande est deja en attente ou si le paiement
    est deja annule. Garde-fou en base : ``open_for_payment`` unique."""

    club = payment.club
    _require_service_club(club)
    _require_roles(
        requested_by,
        club,
        REVERSAL_REQUESTERS,
        "Seuls le Trésorier, son adjoint et le Président peuvent demander une annulation.",
    )
    cleaned = _require_reason(reason, "Le motif de l'annulation est obligatoire.")
    if reason_kind not in PaymentReversal.ReasonKind.values:
        raise TreasuryValidationError("Type d'annulation inconnu.")
    txn = Transaction.all_objects.filter(club=club, payment=payment).first()
    if txn is None or not txn.is_sealed or txn.status != Transaction.Status.SUCCEEDED:
        raise TreasuryValidationError("Seul un paiement validé peut être annulé.")
    _raise_if_open_reversal(club, payment)
    if reason_kind == PaymentReversal.ReasonKind.REFUND and not payment.contribution_type.is_membership_fee:
        raise TreasuryValidationError("Le remboursement ne concerne que les frais d'adhésion.")

    try:
        with db_transaction.atomic():
            # Verrou du paiement (MySQL/MariaDB, PostgreSQL) : deux demandes
            # simultanees se succedent, la seconde voit la premiere.
            Payment.all_objects.select_for_update().filter(club=club, pk=payment.pk).first()
            _raise_if_open_reversal(club, payment)
            return _create_reversal(
                payment=payment,
                reason=cleaned,
                reason_kind=reason_kind,
                requested_by=requested_by,
                now=now or timezone.now(),
            )
    except IntegrityError:
        # Demande concurrente sur le meme paiement (contrainte d'unicite).
        raise TreasuryValidationError(_REVERSAL_ALREADY_EXISTS_MESSAGE) from None


def approve_payment_reversal(
    *, reversal: PaymentReversal, approved_by, now: Optional[datetime] = None
) -> PaymentReversal:
    """Approuve une annulation : President uniquement, apres confirmation
    dans l'interface (CDC 4.4.4, 7.2). Cree une transaction negative egale au paiement, chainee ;
    le paiement d'origine reste intact."""

    club = reversal.club
    _require_service_club(club)
    _require_roles(
        approved_by, club, REVERSAL_DECIDERS, "Seul le Président peut valider une annulation de paiement."
    )
    stored_status = PaymentReversal.all_objects.filter(pk=reversal.pk).values_list("status", flat=True).first()
    if stored_status != PaymentReversal.Status.PENDING_APPROVAL:
        raise TreasuryValidationError("Cette annulation a déjà été traitée.")
    _precheck_ledger_writable(club)

    with db_transaction.atomic():
        return _approve_locked(reversal=reversal, approved_by=approved_by, now=now or timezone.now())


def reject_payment_reversal(
    *, reversal: PaymentReversal, rejected_by, rejection_reason: str, now: Optional[datetime] = None
) -> PaymentReversal:
    """Rejette une demande d'annulation (President, motif obligatoire).
    Aucune ecriture financiere : le paiement reste valide."""

    club = reversal.club
    _require_service_club(club)
    _require_roles(
        rejected_by, club, REVERSAL_DECIDERS, "Seul le Président peut rejeter une annulation de paiement."
    )
    cleaned = _require_reason(rejection_reason, "Le motif du rejet est obligatoire.")
    with db_transaction.atomic():
        locked = PaymentReversal.all_objects.select_for_update().get(pk=reversal.pk)
        if locked.status != PaymentReversal.Status.PENDING_APPROVAL:
            raise TreasuryValidationError("Cette annulation a déjà été traitée.")
        before = _reversal_snapshot(locked)
        locked.status = PaymentReversal.Status.REJECTED
        locked.rejected_by = rejected_by
        locked.rejected_at = now or timezone.now()
        locked.rejection_reason = cleaned
        _save(locked)
        log_action(
            actor=rejected_by,
            club=club,
            action_type="treasury.payment_reversal.rejected",
            obj=locked,
            before=before,
            after=_reversal_snapshot(locked),
        )
    return locked


# ---------------------------------------------------------------------------
# Enregistrement d'un paiement (CDC 4.4.3, 4.4.4, 7.2 ; tache 2.4)
# ---------------------------------------------------------------------------
#
# Chemin unique d'un paiement valide saisi par le Tresorier ou l'adjoint :
# `Payment` + `Transaction` scellee dans la chaine du club (numero de recu
# attribue au scellement, sequence continue par club) + repartition 4.4.3
# recalculee + journal. La modale « Enregistrer un paiement » passe par
# :func:`record_payment` (confirmation en modale a chaque validation) ; la
# Caisse Terrain Express par :func:`record_cash_payment` (session de caisse
# ouverte par le Tresorier, 10.2 n° 22). Les deux partagent
# :func:`_create_sealed_payment`.
#
# Decisions provisoires (signalees dans le compte rendu de la tache 2.4) :
# - reference obligatoire pour « mobile money » et « lien de paiement »
#   (fiche d'ecran tresorerie-tableau-de-bord.md §4.1 ; le CDC 4.4.4 ne le
#   precise pas) ;
# - un joueur « Parti » ne peut plus payer ; « En attente » et « Inscrit »
#   le peuvent.

REFERENCE_REQUIRED_METHODS = frozenset({Payment.Method.MOBILE_MONEY, Payment.Method.PAYMENT_LINK})


@dataclass(frozen=True)
class AllocationPreviewLine:
    """Une ligne de l'apercu de repartition (CDC 4.4.3, fiche d'ecran §4.1).

    ``status`` : ``paid`` (periode entierement couverte apres paiement),
    ``partial`` (partiellement couverte) ou ``free`` (type libre, hors
    solde)."""

    period: date
    amount: Decimal
    period_amount: Optional[Decimal]
    covered_after: Optional[Decimal]
    status: str


@dataclass(frozen=True)
class PaymentPreview:
    """Apercu calcule par le serveur avant validation (aucune ecriture)."""

    membership: Membership
    contribution_type: ContributionType
    amount: Decimal
    currency: str
    paid_on: date
    is_free_type: bool
    lines: tuple
    unallocated_amount: Decimal
    current: BalanceSummary
    after: BalanceSummary


class _ProjectedPayment:
    """Paiement projete de l'apercu : porte seulement ce que lit
    :func:`_plan_allocations` (jamais enregistre)."""

    def __init__(self, amount: Decimal, paid_on: date, currency: str):
        self.amount = amount
        self.paid_on = paid_on
        self.currency = currency


class _ProjectedDue:
    """Montant du projete (apercu d'un import, CDC 4.4.8) : porte seulement
    ce que lit :func:`_plan_allocations` (jamais enregistre)."""

    def __init__(self, period: date, amount: Decimal):
        self.period = period
        self.amount = amount


def _validate_attachment(attachment) -> None:
    """Controle la piece jointe avant toute ecriture (taille, type reel, CDC 6.7)."""

    if attachment is None:
        return
    try:
        validate_upload_size(attachment)
        validate_image_or_pdf(attachment)
    except DjangoValidationError as exc:
        raise TreasuryValidationError(" ".join(exc.messages)) from None


def _validate_payment_input(
    *, membership: Membership, contribution_type: Optional[ContributionType], amount: Any, paid_on: date, now: datetime
) -> tuple[Decimal, ClubSettings]:
    """Controles metier communs a l'apercu et aux enregistrements (avant toute ecriture)."""

    club = membership.club
    current_status = Membership.all_objects.filter(pk=membership.pk).values_list("status", flat=True).first()
    if current_status is None or current_status == Membership.Status.DEPARTED:
        raise TreasuryValidationError("Ce joueur a quitté le club : aucun paiement ne peut être enregistré.")
    if contribution_type is None:
        raise TreasuryValidationError("Choisissez le type de cotisation.")
    if contribution_type.club_id != club.pk:
        raise TreasuryValidationError("Le type de cotisation choisi n'appartient pas à ce club.")
    if contribution_type.status != ContributionType.Status.ACTIVE:
        raise TreasuryValidationError("Ce type de cotisation est archivé.")
    money = to_money(amount)
    if money <= 0:
        raise InvalidAmountError("Saisissez un montant supérieur à 0.")
    if not isinstance(paid_on, date) or isinstance(paid_on, datetime):
        raise TreasuryValidationError("La date du paiement est invalide.")
    club_settings = _club_settings(club)
    if paid_on > _club_today(club_settings, now):
        raise TreasuryValidationError("La date ne peut pas être dans le futur.")
    return money, club_settings


def _build_preview(
    *, membership: Membership, ctype: ContributionType, money: Decimal, paid_on: date, currency: str
) -> PaymentPreview:
    club = membership.club
    existing = _validated_payments_for(club=club, membership=membership, ctype=ctype)
    projected = _ProjectedPayment(money, paid_on, currency)
    # Meme ordre que la projection enregistree (``paid_on`` puis sequence) :
    # le paiement projete aura la derniere sequence de sa date.
    position = sum(1 for payment in existing if payment.paid_on <= paid_on)
    ordered = existing[:position] + [projected] + existing[position:]
    lines, capacities = _plan_allocations(club=club, membership=membership, ctype=ctype, payments=ordered)

    is_free = ctype.nature == ContributionType.Nature.FREE
    covered: dict[date, Decimal] = {}
    for _, period, allocated in lines:
        covered[period] = covered.get(period, Decimal("0.00")) + allocated
    preview_lines = []
    for payment, period, allocated in lines:
        if payment is not projected:
            continue
        if is_free:
            preview_lines.append(AllocationPreviewLine(period, allocated, None, None, "free"))
            continue
        expected = capacities.get(period)
        status = "paid" if expected is not None and covered[period] >= expected else "partial"
        preview_lines.append(AllocationPreviewLine(period, allocated, expected, covered[period], status))
    allocated_total = sum((line.amount for line in preview_lines), Decimal("0.00"))

    current = get_balance_summary(membership)
    # Le paiement compte dans le solde des sa validation (valeur <= aujourd'hui) ;
    # un type libre n'entre jamais dans le solde (CDC 4.4.2).
    after_balance = current.balance if is_free else current.balance + money
    return PaymentPreview(
        membership=membership,
        contribution_type=ctype,
        amount=money,
        currency=currency,
        paid_on=paid_on,
        is_free_type=is_free,
        lines=tuple(preview_lines),
        unallocated_amount=money - allocated_total,
        current=current,
        after=_summary_from_balance(after_balance, currency),
    )


def preview_payment_allocation(
    *,
    membership: Membership,
    contribution_type: ContributionType,
    amount: Any,
    paid_on: date,
    requested_by,
    now: Optional[datetime] = None,
) -> PaymentPreview:
    """Apercu de la repartition 4.4.3 et du nouveau solde, **sans aucune
    ecriture** (modale « Enregistrer un paiement », CDC 4.4.3 : « La modale
    d'enregistrement affiche cette repartition avant validation »).
    Tresorier ou adjoint du club du joueur."""

    now = now or timezone.now()
    club = membership.club
    _require_service_club(club)
    _require_roles(
        requested_by,
        club,
        PAYMENT_RECORDERS,
        "Seuls le Trésorier et le Trésorier adjoint peuvent enregistrer un paiement.",
    )
    money, club_settings = _validate_payment_input(
        membership=membership, contribution_type=contribution_type, amount=amount, paid_on=paid_on, now=now
    )
    return _build_preview(
        membership=membership, ctype=contribution_type, money=money, paid_on=paid_on, currency=club_settings.currency
    )


def _create_sealed_payment(
    *,
    club,
    membership: Membership,
    ctype: ContributionType,
    money: Decimal,
    currency: str,
    method: str,
    reference: str,
    paid_on: date,
    source: str,
    actor,
    now: datetime,
    attachment=None,
    cash_session: Optional[CashSession] = None,
    client_uuid=None,
    client_recorded_at: Optional[datetime] = None,
    import_batch=None,
    recompute: bool = True,
) -> Payment:
    """Cree le paiement valide, le scelle dans la chaine (numero de recu),
    recalcule la repartition et journalise. A appeler dans ``atomic()``,
    apres tous les controles.

    ``recompute=False`` : l'appelant recalcule lui-meme la repartition une
    seule fois apres plusieurs paiements du meme couple (joueur, type) --
    import historique (CDC 4.4.8) ; le resultat est identique, le moteur
    4.4.3 repartissant toujours l'ensemble des paiements valides."""

    payment = Payment(
        club=club,
        membership=membership,
        contribution_type=ctype,
        amount=money,
        currency=currency,
        method=method,
        reference=reference,
        paid_on=paid_on,
        source=source,
        submitted_by=actor,
        submitted_at=now,
        validated_by=actor,
        validated_at=now,
        cash_session=cash_session,
        client_uuid=client_uuid,
        client_recorded_at=client_recorded_at,
        import_batch=import_batch,
    )
    if attachment is not None:
        rename_upload_to_real_type(attachment)
        payment.attachment = attachment
    _save(payment)
    txn = Transaction(
        club=club,
        kind=Transaction.Kind.PAYMENT,
        payment=payment,
        membership=membership,
        contribution_type=ctype,
        amount=money,
        currency=currency,
        value_date=paid_on,
        provider=Transaction.Provider.MANUAL,
        external_ref=None,
        status=Transaction.Status.SUCCEEDED,
        status_changed_at=now,
        created_at=now,
    )
    _seal(txn, Transaction.Status.SUCCEEDED, now)
    log_action(
        actor=actor,
        club=club,
        action_type="treasury.payment.validated",
        obj=payment,
        before=None,
        after=_payment_snapshot(payment, txn),
    )
    _ensure_fee_due_for_payment(membership=membership, ctype=ctype, actor=actor, now=now)
    if recompute:
        _recompute_allocations(membership=membership, ctype=ctype, actor=actor, now=now)
    return payment


# ---------------------------------------------------------------------------
# Idempotence de la saisie en ligne (correctif securite M4, audit du
# 12/10/2026). Le PIN etant supprime (CLAUDE.md regle 7), un renvoi reseau ou
# un double POST de la modale de confirmation ne doit jamais creer deux
# paiements valides scelles (ni deux recus, ni deux entrees de journal, ni
# deux notifications). L'interface envoie un ``client_uuid`` FACULTATIF,
# genere a l'ouverture de la modale. Meme colonne et meme contrainte unique
# (club, client_uuid) que la Caisse Terrain Express : les NULL y sont
# distincts sur tous les moteurs (SQLite, MySQL/MariaDB, PostgreSQL), donc
# « sans client_uuid » = comportement inchange.
# ---------------------------------------------------------------------------


def _existing_client_uuid_payment(club, parsed_uuid: uuid.UUID) -> Optional[Payment]:
    return Payment.all_objects.filter(club=club, client_uuid=parsed_uuid).first()


def _replayed_entry_payment(
    existing: Payment,
    *,
    membership: Membership,
    contribution_type: Optional[ContributionType],
    amount: Any,
    method: str,
    reference: str,
    paid_on: date,
    actor,
) -> Payment:
    """Rejeu d'une saisie en ligne : renvoie ``existing`` (marque
    ``idempotent_replay``) s'il s'agit bien de la meme saisie, sinon
    :class:`ClientUuidConflictError`. Aucune ecriture.

    ``contribution_type=None`` : frais d'adhesion (type « adhesion » du club,
    quel qu'il soit)."""

    if contribution_type is None:
        same_type = existing.contribution_type.is_membership_fee
    else:
        same_type = existing.contribution_type_id == contribution_type.pk
    same = (
        existing.source == Payment.Source.TREASURER_ENTRY
        and existing.membership_id == membership.pk
        and same_type
        and existing.amount == to_money(amount)
        and existing.method == method
        and existing.reference == (reference or "").strip()
        and existing.paid_on == paid_on
        and existing.validated_by_id == getattr(actor, "pk", None)
    )
    if not same:
        raise ClientUuidConflictError(
            "Cet identifiant de saisie a déjà été utilisé pour un autre paiement : "
            "il n'a pas été enregistré une seconde fois."
        )
    existing.idempotent_replay = True
    return existing


def _create_idempotent(*, club, parsed_uuid: Optional[uuid.UUID], create, replay) -> Payment:
    """Execute ``create()`` dans ``atomic()`` ; en cas de course sur le meme
    ``client_uuid`` (contrainte unique), la premiere saisie recue fait foi et
    la seconde renvoie le meme paiement via ``replay(existing)``."""

    try:
        with db_transaction.atomic():
            payment = create()
    except (IntegrityError, TreasuryValidationError):
        if parsed_uuid is None:
            raise
        existing = _existing_client_uuid_payment(club, parsed_uuid)
        if existing is None:
            raise
        return replay(existing)
    payment.idempotent_replay = False
    return payment


@_retry_idempotent_when_locked
def record_payment(
    *,
    membership: Membership,
    contribution_type: ContributionType,
    amount: Any,
    method: str,
    paid_on: date,
    recorded_by,
    reference: str = "",
    attachment=None,
    client_uuid=None,
    now: Optional[datetime] = None,
) -> Payment:
    """Enregistre et valide un paiement (modale « Enregistrer un paiement »,
    CDC 4.4.4 ; Tresorier ou adjoint ; confirmation dans l'interface, CDC 7.2).

    Controles de role, de donnees, de piece jointe et de gel ;
    puis, atomiquement : `Payment` (source ``treasurer_entry``),
    `Transaction` scellee (``manual``, ``succeeded``, numero de recu
    sequentiel par club), repartition 4.4.3, journal. Rien n'est ecrit si
    une exception est levee.

    ``client_uuid`` (facultatif, correctif M4) : cle d'idempotence unique par
    club, generee par l'interface a l'ouverture de la modale. Un rejeu de la
    meme saisie renvoie le paiement existant, sans aucune ecriture (ni
    transaction, ni recu, ni journal, ni notification) ; le paiement renvoye
    porte ``idempotent_replay = True`` (``False`` pour une creation). Une
    cle deja utilisee pour une autre saisie leve
    :class:`ClientUuidConflictError`. Sans ``client_uuid`` : comportement
    inchange.

    Exceptions : :class:`TreasuryPermissionError`,
    :class:`TreasuryValidationError` (dont :class:`InvalidAmountError` et
    :class:`ClientUuidConflictError`), :class:`LedgerFrozenError`,
    :class:`LedgerKeyError`.
    """

    now = now or timezone.now()
    club = membership.club
    _require_service_club(club)
    _require_roles(
        recorded_by,
        club,
        PAYMENT_RECORDERS,
        "Seuls le Trésorier et le Trésorier adjoint peuvent enregistrer un paiement.",
    )
    parsed_uuid = None if client_uuid is None else _parse_client_uuid(client_uuid)

    def replay(existing: Payment) -> Payment:
        return _replayed_entry_payment(
            existing,
            membership=membership,
            contribution_type=contribution_type,
            amount=amount,
            method=method,
            reference=reference,
            paid_on=paid_on,
            actor=recorded_by,
        )

    if parsed_uuid is not None:
        existing = _existing_client_uuid_payment(club, parsed_uuid)
        if existing is not None:
            return replay(existing)

    money, club_settings = _validate_payment_input(
        membership=membership, contribution_type=contribution_type, amount=amount, paid_on=paid_on, now=now
    )
    if method not in TREASURER_ENTRY_METHODS:
        raise TreasuryValidationError("Mode de paiement invalide : espèces, mobile money ou lien de paiement.")
    cleaned_reference = (reference or "").strip()
    if len(cleaned_reference) > 120:
        raise TreasuryValidationError("La référence ne doit pas dépasser 120 caractères.")
    if method in REFERENCE_REQUIRED_METHODS and not cleaned_reference:
        raise TreasuryValidationError("Indiquez la référence de la transaction.")
    _validate_attachment(attachment)
    _precheck_ledger_writable(club)

    return _create_idempotent(
        club=club,
        parsed_uuid=parsed_uuid,
        replay=replay,
        create=lambda: _create_sealed_payment(
            club=club,
            membership=membership,
            ctype=contribution_type,
            money=money,
            currency=club_settings.currency,
            method=method,
            reference=cleaned_reference,
            paid_on=paid_on,
            source=Payment.Source.TREASURER_ENTRY,
            actor=recorded_by,
            now=now,
            attachment=attachment,
            client_uuid=parsed_uuid,
        ),
    )


# ---------------------------------------------------------------------------
# Caisse Terrain Express (CDC 4.4.5, 6.6, 7.2 ; 10.2 n° 22 ; schema §5.4)
# ---------------------------------------------------------------------------
#
# - Session ouverte EN LIGNE par le Tresorier ou l'adjoint (confirmation en
#   modale cote interface, plus de PIN) ; l'appareil ne recoit que
#   l'identifiant public de la session et son heure d'expiration (minuit,
#   fuseau du club).
# - Reouverture (choix le plus simple, documente) : tant qu'une session
#   valide existe pour ce tresorier dans ce club, « ouvrir » renvoie cette session au lieu d'en creer une seconde ; apres
#   expiration ou fermeture, une nouvelle session est creee. Au plus une
#   session valide par (club, auteur).
# - Encaissement : valide si la session du meme club, ouverte
#   par l'auteur, couvrait l'HEURE DE SAISIE declaree par l'appareil
#   (``client_recorded_at``), bornee : pas dans le futur (tolerance
#   d'horloge ci-dessous), pas avant l'ouverture, strictement avant minuit
#   (et avant la fermeture). La synchronisation peut arriver apres minuit.
# - Idempotence : ``client_uuid`` unique par club ; une synchronisation
#   rejouee renvoie le paiement deja cree, jamais un second.
#
# Points NON tranches (compte rendu de la tache 2.4) : duree de
# conservation de l'horodatage client, delai maximal de synchronisation
# apres minuit (Q22 a), horloge fausse de l'appareil (tolerance ci-dessous
# provisoire), sort d'une session quand son auteur perd le role (Q22 c :
# ici l'encaissement exige le role au moment de la reception), plafond
# d'un encaissement en caisse (aucun), cloture manuelle (heure serveur de
# reception).

CASH_CLOCK_TOLERANCE = timedelta(minutes=2)  # provisoire : horloge d'appareil en avance
CASH_SEARCH_LIMIT = 20
CASH_SEARCH_MAX_QUERY_LENGTH = 60
CASH_SEARCH_STATUSES = (Membership.Status.ACTIVE, Membership.Status.PENDING)


class CashSessionNotFoundError(TreasuryError):
    """Session inexistante, d'un autre club ou d'un autre utilisateur (404)."""


class CashSessionNotValidError(TreasuryValidationError):
    """La session ne couvre pas l'instant considere (expiree, fermee,
    heure de saisie hors fenetre)."""


class ClientUuidConflictError(TreasuryValidationError):
    """Cle de synchronisation deja utilisee pour un autre encaissement."""


def _club_tz(club_settings: ClubSettings) -> ZoneInfo:
    try:
        return ZoneInfo(club_settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise TreasuryValidationError("Le fuseau horaire du club est invalide.") from None


def cash_session_expiry(club_settings: ClubSettings, opened_at: datetime) -> datetime:
    """Minuit (00:00) suivant le jour d'ouverture, dans le fuseau du club,
    renvoye en UTC (schema §5.4). Ex. : ouverture dimanche 08:30 a Kinshasa
    -> lundi 00:00 heure de Kinshasa = dimanche 23:00 UTC."""

    tz = _club_tz(club_settings)
    local_day = opened_at.astimezone(tz).date()
    midnight = datetime.combine(local_day + timedelta(days=1), dt_time.min, tzinfo=tz)
    return midnight.astimezone(dt_timezone.utc)


def cash_session_state(session: CashSession, now: Optional[datetime] = None) -> str:
    """Etat calcule a la volee (``open``, ``closed``, ``expired``), jamais
    lu dans ``status`` seul (schema §5.4)."""

    now = now or timezone.now()
    if session.closed_at is not None:
        return CashSession.Status.CLOSED
    if now >= session.expires_at:
        return CashSession.Status.EXPIRED
    return CashSession.Status.OPEN


def _cash_session_snapshot(session: CashSession) -> dict[str, Any]:
    return {
        "cash_session_id": str(session.public_id),
        "opened_by_membership_id": session.opened_by_id,
        "opened_at": session.opened_at,
        "expires_at": session.expires_at,
        "closed_at": session.closed_at,
        "status": session.status,
    }


def _valid_cash_session_for(*, club, user, now: datetime) -> Optional[CashSession]:
    return (
        CashSession.all_objects.filter(
            club=club,
            opened_by__user=user,
            opened_at__lte=now,
            expires_at__gt=now,
            closed_at__isnull=True,
        )
        .order_by("-opened_at", "-pk")
        .first()
    )


def get_current_cash_session(*, club, user, now: Optional[datetime] = None) -> Optional[CashSession]:
    """Session de caisse valide de ``user`` dans ``club`` a l'instant
    ``now``, ou ``None``. Rattachee a l'utilisateur, jamais a un appareil."""

    _require_service_club(club)
    return _valid_cash_session_for(club=club, user=user, now=now or timezone.now())


def open_cash_session(*, club, user, now: Optional[datetime] = None) -> tuple[CashSession, bool]:
    """Ouvre une session de caisse (CDC 4.4.5 ; 10.2 n° 22, modifié le
    11/10/2026 : plus de PIN, ouverture confirmée dans l'interface).

    Tresorier ou adjoint uniquement (matrice 2.4, CDC 4.4.5 : le President
    n'ouvre pas de session). Role, parametres du club et gel verifies.
    Renvoie ``(session, created)`` : ``created`` faux si une session valide
    existait deja (elle est renvoyee telle quelle). Journalise l'ouverture
    avec l'identifiant de session."""

    now = now or timezone.now()
    _require_service_club(club)
    _require_roles(
        user,
        club,
        PAYMENT_RECORDERS,
        "Seuls le Trésorier et le Trésorier adjoint peuvent ouvrir une session de caisse.",
    )
    membership = Membership.all_objects.filter(club=club, user=user, status=Membership.Status.ACTIVE).first()
    if membership is None:  # pragma: no cover - garanti par le controle de role
        raise TreasuryPermissionError("Aucune adhésion active dans ce club.")
    club_settings = _club_settings(club)
    expires_at = cash_session_expiry(club_settings, now)
    _precheck_ledger_writable(club)

    with db_transaction.atomic():
        # Serialise les ouvertures d'un meme tresorier (sans effet sous SQLite,
        # voir _lock_chain_state) : au plus une session valide par auteur.
        Membership.all_objects.select_for_update().filter(pk=membership.pk).first()
        existing = _valid_cash_session_for(club=club, user=user, now=now)
        if existing is not None:
            return existing, False
        session = CashSession(
            club=club,
            opened_by=membership,
            opened_at=now,
            expires_at=expires_at,
            status=CashSession.Status.OPEN,
        )
        _save(session)
        log_action(
            actor=user,
            club=club,
            action_type="treasury.cash_session.opened",
            obj=session,
            before=None,
            after=_cash_session_snapshot(session),
        )
    return session, True


def _owned_cash_session(*, club, user, public_id) -> CashSession:
    try:
        parsed = public_id if isinstance(public_id, uuid.UUID) else uuid.UUID(str(public_id))
    except (TypeError, ValueError, AttributeError):
        raise CashSessionNotFoundError("Cette session de caisse n'existe pas.") from None
    session = (
        CashSession.all_objects.filter(club=club, public_id=parsed, opened_by__user=user)
        .select_related("opened_by")
        .first()
    )
    if session is None:
        raise CashSessionNotFoundError("Cette session de caisse n'existe pas.")
    return session


def _require_session_valid_now(session: CashSession, now: datetime) -> None:
    state = cash_session_state(session, now)
    if state == CashSession.Status.EXPIRED:
        raise CashSessionNotValidError(
            "Session de caisse expirée à minuit. Ouvrez une nouvelle session pour continuer."
        )
    if state == CashSession.Status.CLOSED:
        raise CashSessionNotValidError("Session de caisse fermée. Ouvrez une nouvelle session pour continuer.")


def get_owned_cash_session(*, club, user, public_id) -> CashSession:
    """Session ``public_id`` de ``user`` dans ``club`` (quel que soit son
    etat), sinon :class:`CashSessionNotFoundError`."""

    _require_service_club(club)
    return _owned_cash_session(club=club, user=user, public_id=public_id)


def close_cash_session(*, club, user, public_id, now: Optional[datetime] = None) -> CashSession:
    """Fermeture manuelle par son auteur (fiche d'ecran §4.2). Idempotente :
    une session deja fermee ou expiree est renvoyee sans changement (une
    fermeture saisie hors connexion peut arriver apres minuit). Une session
    fermee n'est jamais rouverte. Heure de fermeture = heure serveur de
    reception (point ouvert)."""

    now = now or timezone.now()
    _require_service_club(club)
    with db_transaction.atomic():
        session = _owned_cash_session(club=club, user=user, public_id=public_id)
        session = CashSession.all_objects.select_for_update().get(pk=session.pk)
        if cash_session_state(session, now) != CashSession.Status.OPEN or now < session.opened_at:
            return session
        before = _cash_session_snapshot(session)
        session.closed_at = now
        session.status = CashSession.Status.CLOSED
        _save(session)
        log_action(
            actor=user,
            club=club,
            action_type="treasury.cash_session.closed",
            obj=session,
            before=before,
            after=_cash_session_snapshot(session),
        )
    return session


def cash_session_totals(session: CashSession) -> tuple[int, Decimal]:
    """Nombre et total des encaissements de la session (bandeau de session)."""

    row = Payment.all_objects.filter(club_id=session.club_id, cash_session=session).aggregate(
        count=Count("pk"), total=Sum("amount")
    )
    return row["count"] or 0, (row["total"] or Decimal("0.00")).quantize(MONEY_QUANTUM)


def get_default_contribution_type_ids(club, membership_ids: Iterable[int], at_date: date) -> dict[int, Optional[int]]:
    """Type par defaut de la Caisse Terrain Express : « la mensuelle du
    joueur » (CDC 4.4.5), en deux requetes quel que soit le nombre de
    joueurs.

    Regle : type obligatoire mensuel actif ; d'abord celui auquel le joueur
    est **rattache** a cette date (types « liste » ou « rattaches », CDC
    4.4.1 : « les mensuelles se rattachent joueur par joueur ») ; a defaut
    le type mensuel « Tous ». Si plusieurs types sont candidats au meme
    niveau, aucun defaut n'est invente (``None`` : l'interface demande le
    type)."""

    ids = list(membership_ids)
    if not ids:
        return {}
    period = _period_start(at_date)
    types = list(
        ContributionType.all_objects.filter(
            club=club,
            nature=ContributionType.Nature.MANDATORY,
            periodicity=ContributionType.Periodicity.MONTHLY,
            status=ContributionType.Status.ACTIVE,
        )
        .order_by("pk")
        .values_list("pk", "scope")
    )
    for_all = [pk for pk, scope in types if scope == ContributionType.Scope.ALL]
    individual = [pk for pk, scope in types if scope != ContributionType.Scope.ALL]
    assigned: dict[int, set[int]] = {}
    if individual:
        rows = (
            ContributionAssignment.all_objects.filter(
                club=club, membership_id__in=ids, contribution_type_id__in=individual, starts_on__lte=period
            )
            .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=period))
            .values_list("membership_id", "contribution_type_id")
        )
        for membership_id, type_id in rows:
            assigned.setdefault(membership_id, set()).add(type_id)
    result: dict[int, Optional[int]] = {}
    for membership_id in ids:
        own = assigned.get(membership_id, set())
        if len(own) == 1:
            result[membership_id] = next(iter(own))
        elif not own and len(for_all) == 1:
            result[membership_id] = for_all[0]
        else:
            result[membership_id] = None
    return result


def get_default_contribution_type(membership: Membership, at_date: Optional[date] = None) -> Optional[ContributionType]:
    """Mensuelle par defaut d'un joueur (voir :func:`get_default_contribution_type_ids`)."""

    club = membership.club
    at_date = _balance_date(club, at_date)
    type_id = get_default_contribution_type_ids(club, [membership.pk], at_date).get(membership.pk)
    if type_id is None:
        return None
    return ContributionType.all_objects.get(pk=type_id, club=club)


@dataclass(frozen=True)
class CashPlayerResult:
    """Joueur propose par la recherche de la caisse (champs utiles seulement)."""

    membership: Membership
    summary: BalanceSummary
    default_contribution_type_id: Optional[int]


def search_cash_session_players(
    *, club, user, public_id, query: str, now: Optional[datetime] = None, limit: int = CASH_SEARCH_LIMIT
) -> list[CashPlayerResult]:
    """Recherche d'un joueur par nom ou numero (CDC 4.4.5), avec solde et
    statut **calcules a la lecture** (jamais mis en cache : un joueur
    regularise par un encaissement apparait « En ordre » des la requete
    suivante). Reservee au Tresorier ou a l'adjoint dont la session est
    valide. Nombre de requetes SQL constant (aucun N+1), au plus
    ``limit`` (20) resultats. Joueurs « Inscrit » et « En attente » ; les
    joueurs partis sont exclus."""

    now = now or timezone.now()
    _require_service_club(club)
    _require_roles(
        user,
        club,
        PAYMENT_RECORDERS,
        "Seuls le Trésorier et le Trésorier adjoint peuvent utiliser la Caisse Terrain Express.",
    )
    session = _owned_cash_session(club=club, user=user, public_id=public_id)
    _require_session_valid_now(session, now)
    cleaned = " ".join((query or "").split())
    if not cleaned:
        raise TreasuryValidationError("Saisissez un nom ou un numéro de maillot.")
    if len(cleaned) > CASH_SEARCH_MAX_QUERY_LENGTH:
        raise TreasuryValidationError("Recherche trop longue.")
    limit = max(1, min(int(limit), CASH_SEARCH_LIMIT))

    name_filter = Q()
    for term in cleaned.split(" "):
        name_filter &= Q(user__first_name__icontains=term) | Q(user__last_name__icontains=term)
    condition = name_filter
    if cleaned.isdigit():
        condition = condition | Q(jersey_number=int(cleaned))
    memberships = list(
        Membership.all_objects.filter(club=club, status__in=CASH_SEARCH_STATUSES)
        .filter(condition)
        .select_related("user")
        .order_by("user__last_name", "user__first_name", "pk")[:limit]
    )
    if not memberships:
        return []
    club_settings = _club_settings(club)
    today = _club_today(club_settings, now)
    ids = [membership.pk for membership in memberships]
    paid, owed = _balance_aggregates(club=club, at_date=today, membership_ids=ids)
    defaults = get_default_contribution_type_ids(club, ids, today)
    results = []
    for membership in memberships:
        balance = (paid.get(membership.pk) or Decimal("0.00")) - (owed.get(membership.pk) or Decimal("0.00"))
        results.append(
            CashPlayerResult(
                membership=membership,
                summary=_summary_from_balance(balance, club_settings.currency),
                default_contribution_type_id=defaults.get(membership.pk),
            )
        )
    return results


def _parse_client_uuid(value) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise TreasuryValidationError("Identifiant d'encaissement invalide.") from None


def _check_recorded_at(session: CashSession, recorded_at, now: datetime) -> datetime:
    """Regle de validite d'un encaissement de caisse (10.2 n° 22 ; schema
    §5.4), evaluee sur l'HEURE DE SAISIE declaree par l'appareil."""

    if not isinstance(recorded_at, datetime) or recorded_at.tzinfo is None:
        raise TreasuryValidationError("L'heure de saisie de l'encaissement est invalide.")
    if recorded_at > now + CASH_CLOCK_TOLERANCE:
        raise CashSessionNotValidError("L'heure de saisie de l'encaissement ne peut pas être dans le futur.")
    if recorded_at < session.opened_at:
        raise CashSessionNotValidError(
            "L'heure de saisie précède l'ouverture de la session de caisse : encaissement refusé."
        )
    if recorded_at >= session.expires_at:
        raise CashSessionNotValidError(
            "Encaissement saisi après minuit, heure d'expiration de la session de caisse : il est refusé. "
            "Ouvrez une nouvelle session de caisse."
        )
    if session.closed_at is not None and recorded_at >= session.closed_at:
        raise CashSessionNotValidError(
            "Encaissement saisi après la fermeture de la session de caisse : il est refusé."
        )
    return recorded_at


def _replayed_cash_payment(existing: Payment, *, session: CashSession, membership: Membership, amount: Any) -> Payment:
    same = (
        existing.cash_session_id == session.pk
        and existing.membership_id == membership.pk
        and existing.amount == to_money(amount)
    )
    if not same:
        raise ClientUuidConflictError(
            "Cet identifiant d'encaissement a déjà été utilisé pour un autre encaissement : "
            "il n'a pas été enregistré une seconde fois."
        )
    return existing


def preview_cash_payment(
    *,
    club,
    user,
    public_id,
    membership: Membership,
    amount: Any,
    contribution_type: Optional[ContributionType] = None,
    now: Optional[datetime] = None,
) -> PaymentPreview:
    """Apercu (repartition, nouveau solde et statut) d'un encaissement de
    caisse a la date du jour du club, sans aucune ecriture. Type par defaut :
    la mensuelle du joueur."""

    now = now or timezone.now()
    _require_service_club(club)
    _require_roles(
        user,
        club,
        PAYMENT_RECORDERS,
        "Seuls le Trésorier et le Trésorier adjoint peuvent utiliser la Caisse Terrain Express.",
    )
    session = _owned_cash_session(club=club, user=user, public_id=public_id)
    _require_session_valid_now(session, now)
    if membership.club_id != club.pk:
        raise TreasuryValidationError("Ce joueur n'appartient pas à ce club.")
    today = _club_today(_club_settings(club), now)
    ctype = contribution_type or get_default_contribution_type(membership, at_date=today)
    money, club_settings = _validate_payment_input(
        membership=membership, contribution_type=ctype, amount=amount, paid_on=today, now=now
    )
    return _build_preview(membership=membership, ctype=ctype, money=money, paid_on=today, currency=club_settings.currency)


@_retry_idempotent_when_locked
def record_cash_payment(
    *,
    club,
    user,
    public_id,
    membership: Membership,
    amount: Any,
    client_uuid,
    client_recorded_at: datetime,
    contribution_type: Optional[ContributionType] = None,
    now: Optional[datetime] = None,
) -> tuple[Payment, bool]:
    """Encaissement en especes de la Caisse Terrain Express (CDC 4.4.5 ;
    10.2 n° 22), en ligne ou synchronise apres une saisie hors connexion.

    L'attestation est la session de caisse, ouverte par le Tresorier.
    Refuse si la session n'appartient pas a ``user`` dans
    ``club`` (:class:`CashSessionNotFoundError`, 404) ou si l'heure de
    saisie ``client_recorded_at`` sort de sa fenetre de validite
    (:class:`CashSessionNotValidError`) -- la synchronisation, elle, peut
    arriver apres minuit.

    Idempotent : ``client_uuid`` (UUID genere par l'appareil) est unique par
    club ; une synchronisation rejouee renvoie le paiement existant
    (``created`` faux) ; une cle reutilisee pour un autre encaissement leve
    :class:`ClientUuidConflictError`.

    Meme chemin chaine que :func:`record_payment` : `Payment` (source
    ``field_cash``, mode especes, ``cash_session``), `Transaction` scellee,
    numero de recu, repartition 4.4.3, journal portant l'identifiant de la
    session. Date de valeur = jour de la saisie dans le fuseau du club.
    Type par defaut : la mensuelle du joueur."""

    now = now or timezone.now()
    _require_service_club(club)
    _require_roles(
        user,
        club,
        PAYMENT_RECORDERS,
        "Seuls le Trésorier et le Trésorier adjoint peuvent encaisser en caisse.",
    )
    session = _owned_cash_session(club=club, user=user, public_id=public_id)
    if membership.club_id != club.pk:
        raise TreasuryValidationError("Ce joueur n'appartient pas à ce club.")
    parsed_uuid = _parse_client_uuid(client_uuid)
    existing = Payment.all_objects.filter(club=club, client_uuid=parsed_uuid).first()
    if existing is not None:
        return _replayed_cash_payment(existing, session=session, membership=membership, amount=amount), False

    recorded_at = _check_recorded_at(session, client_recorded_at, now)
    club_settings = _club_settings(club)
    paid_on = _club_today(club_settings, recorded_at)
    ctype = contribution_type or get_default_contribution_type(membership, at_date=paid_on)
    if ctype is None:
        raise TreasuryValidationError(
            "Aucune cotisation mensuelle par défaut pour ce joueur : choisissez le type de cotisation."
        )
    money, club_settings = _validate_payment_input(
        membership=membership, contribution_type=ctype, amount=amount, paid_on=paid_on, now=now
    )
    _precheck_ledger_writable(club)

    try:
        with db_transaction.atomic():
            payment = _create_sealed_payment(
                club=club,
                membership=membership,
                ctype=ctype,
                money=money,
                currency=club_settings.currency,
                method=Payment.Method.CASH,
                reference="",
                paid_on=paid_on,
                source=Payment.Source.FIELD_CASH,
                actor=user,
                now=now,
                cash_session=session,
                client_uuid=parsed_uuid,
                client_recorded_at=recorded_at,
            )
    except (IntegrityError, TreasuryValidationError):
        # Synchronisation concurrente de la meme saisie : la premiere recue
        # fait foi (CDC 6.6), la seconde renvoie le meme paiement.
        existing = Payment.all_objects.filter(club=club, client_uuid=parsed_uuid).first()
        if existing is None:
            raise
        return _replayed_cash_payment(existing, session=session, membership=membership, amount=amount), False
    return payment, True


# ---------------------------------------------------------------------------
# Paiement en ligne, phase 1 : lien externe et « J'ai paye » (CDC 4.6 ;
# schema-treasury.md §5.1 source ``player_declaration`` ; tache 2.5)
# ---------------------------------------------------------------------------
#
# Circuit, sans aucun modele nouveau (la preparation FlexPaie du CDC 4.6
# est deja portee par ``Transaction.provider``/``external_ref``/``status``) :
#
# 1. Le joueur declare POUR LUI-MEME (matrice 2.4, « P ») : `Payment`
#    (mode ``payment_link``, source ``player_declaration``, sans valideur)
#    + `Transaction` NON scellee ``pending``, fournisseur ``link`` -- c'est
#    le statut « A valider ». Comme une depense « En attente » avant sa
#    liberation, elle n'entre dans aucun solde, aucune caisse, aucune
#    repartition et n'a ni sequence ni numero de recu. Le
#    joueur declare, il ne valide rien. Trésorier et adjoint notifies
#    (CDC 4.17).
# 2. Validation par le Tresorier ou l'adjoint, apres confirmation en modale
#    (CLAUDE.md regle n7) : la transaction passe a ``succeeded`` et
#    est scellee (sequence, empreinte, numero de recu), la repartition 4.4.3
#    est recalculee, le joueur est notifie -- « traitee comme un paiement
#    normal » (CDC 4.6). Une erreur ulterieure se corrige par annulation.
# 3. Refus motive par le Tresorier ou l'adjoint (comme les autres
#    refus : depense, annulation, assistance) : la transaction passe a
#    ``failed`` et est scellee -- la declaration reste tracee, inalterable,
#    et le joueur est prevenu avec le motif.
#
# Decisions provisoires (compte rendu de la tache 2.5, a confirmer) :
# - reference obligatoire, capture facultative (fiche comptes-mon-profil.md
#   §4.2 et point ouvert §7) ; motif obligatoire au refus (fiche
#   tresorerie-tableau-de-bord.md §7) ;
# - date de valeur = jour de la declaration dans le fuseau du club (la
#   modale n'a pas de champ date) ;
# - declaration refusee tant que le club n'a pas configure de lien ;
# - types proposes et acceptes : types actifs qui concernent le joueur
#   (« Tous », ou rattachement ouvert a la date du jour) ;
# - une meme reference « lien de paiement » ne peut exister qu'une fois a
#   l'etat « a valider » ou « valide » (non annule) dans le club ;
#   ``external_ref`` n'est renseignee qu'a la validation : la contrainte
#   ``(club, provider, external_ref)`` garantit alors un seul paiement
#   valide par reference fournisseur, sans qu'un refus n'empeche une
#   nouvelle declaration corrigee ;
# - ecritures gelees (CDC 5.3) : declaration, validation et refus refuses.

PAYMENT_STATUS_LABELS = {
    "to_validate": "À valider",
    "validated": "Validé",
    "refused": "Refusé",
    "cancelled": "Annulé",
}

PAYMENT_LINK_MISSING_MESSAGE = (
    "Le club n'a pas encore configuré de lien de paiement. Réglez auprès du trésorier."
)


class PaymentLinkNotConfiguredError(TreasuryValidationError):
    """Aucun lien de paiement dans les parametres du club (CDC 4.6)."""


class DeclarationAlreadyProcessedError(TreasuryValidationError):
    """La declaration « J'ai paye » a deja ete validee ou refusee."""


@dataclass(frozen=True)
class ContributeInfo:
    """Donnees du bouton « Contribuer » et de la modale « J'ai paye »."""

    payment_link_url: str
    currency: str
    contribution_types: tuple
    default_contribution_type_id: Optional[int]


def get_payment_link(club) -> str:
    """Lien de paiement externe du club (``ClubSettings.payment_link_url``,
    CDC 4.6 : jamais ecrit en dur). Chaine vide s'il n'est pas configure."""

    return (_club_settings(club).payment_link_url or "").strip()


def _declarable_types_queryset(membership: Membership, at_date: date):
    club = membership.club
    assigned = ContributionAssignment.all_objects.filter(
        club=club, membership=membership, starts_on__lte=at_date
    ).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=at_date))
    return ContributionType.all_objects.filter(club=club, status=ContributionType.Status.ACTIVE).filter(
        Q(scope=ContributionType.Scope.ALL) | Q(pk__in=assigned.values("contribution_type_id"))
    )


def get_declarable_contribution_types(membership: Membership, at_date: Optional[date] = None) -> list:
    """Types actifs qui concernent le joueur a ``at_date`` : types « Tous »
    et types auxquels il est rattache (CDC 4.4.1 ; fiche comptes-mon-profil
    §4.2 « types actifs du joueur »). Une seule requete."""

    club = membership.club
    _require_service_club(club)
    at_date = _balance_date(club, at_date)
    return list(_declarable_types_queryset(membership, at_date).order_by("name", "pk"))


def get_contribute_info(membership: Membership, at_date: Optional[date] = None) -> ContributeInfo:
    """Bouton « Contribuer » (lien du club, vide si non configure) et
    contenu de la modale « J'ai paye » (types proposes, type par defaut =
    la mensuelle du joueur, devise du club)."""

    club = membership.club
    _require_service_club(club)
    club_settings = _club_settings(club)
    at_date = _balance_date(club, at_date)
    types = get_declarable_contribution_types(membership, at_date)
    default = get_default_contribution_type_ids(club, [membership.pk], at_date).get(membership.pk)
    return ContributeInfo(
        payment_link_url=(club_settings.payment_link_url or "").strip(),
        currency=club_settings.currency,
        contribution_types=tuple(types),
        default_contribution_type_id=default if default in {ctype.pk for ctype in types} else None,
    )


def payment_status_key(payment: Payment) -> str:
    """Statut affiche d'un paiement (cle du design system : ``to_validate``,
    ``validated``, ``refused``, ``cancelled``), deduit de sa transaction et
    de son annulation eventuelle -- jamais stocke (schema §5.1)."""

    # Relations inverses (``select_related("transaction")`` et
    # ``prefetch_related(reversal_prefetch())`` dans les listes : aucune
    # requete supplementaire par ligne).
    try:
        txn = payment.transaction
    except Transaction.DoesNotExist:
        return "to_validate"
    if txn.status == Transaction.Status.SUCCEEDED:
        try:
            reversal = payment.reversal
        except PaymentReversal.DoesNotExist:
            reversal = None
        approved = reversal is not None and reversal.status == PaymentReversal.Status.APPROVED
        return "cancelled" if approved else "validated"
    if txn.status == Transaction.Status.FAILED:
        return "refused"
    return "to_validate"


def _clean_declared_reference(reference) -> str:
    cleaned = reference.strip() if isinstance(reference, str) else ""
    if not cleaned:
        raise TreasuryValidationError("Indiquez la référence reçue lors du paiement.")
    if len(cleaned) > 120:
        raise TreasuryValidationError("La référence ne doit pas dépasser 120 caractères.")
    return cleaned


def _references_in_use(club, reference: str, *, exclude_pk: Optional[int] = None, membership=None):
    """Paiements « lien de paiement » a valider ou valides (non annules) du
    club portant ``reference`` (``membership`` : restreint a ce joueur).
    Comparaison insensible a la casse (``iexact``), identique sous SQLite et
    MySQL/MariaDB pour les references ASCII."""

    queryset = Payment.all_objects.filter(
        club=club,
        method=Payment.Method.PAYMENT_LINK,
        reference__iexact=reference,
        transaction__status__in=[
            Transaction.Status.INITIATED,
            Transaction.Status.PENDING,
            Transaction.Status.SUCCEEDED,
        ],
    ).exclude(reversal__status=PaymentReversal.Status.APPROVED)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    if membership is not None:
        queryset = queryset.filter(membership=membership)
    return queryset


def _require_reference_available(
    club, reference: str, *, exclude_pk: Optional[int] = None, membership=None
) -> None:
    """Refuse une reference « lien de paiement » deja a valider ou validee
    (non annulee) : un meme paiement fournisseur ne compte qu'une fois.

    ``membership`` fourni (declaration par un joueur) : seuls **ses propres**
    paiements sont consultes, pour qu'un joueur ne puisse pas sonder les
    references des autres joueurs via le message d'erreur (audit securite
    A6). Le doublon avec le paiement d'un autre joueur est signale au
    Tresorier (notification) et bloque a la validation, controle complet
    du club (``membership`` omis)."""

    if _references_in_use(club, reference, exclude_pk=exclude_pk, membership=membership).exists():
        raise TreasuryValidationError(
            "Cette référence de transaction a déjà été déclarée ou enregistrée : vérifiez-la auprès du trésorier."
        )


def _require_ledger_not_frozen(club) -> None:
    state = LedgerChainState.all_objects.filter(club=club).first()
    if state is not None and state.is_frozen:
        raise LedgerFrozenError(_frozen_message(state))


def declare_payment(
    *,
    membership: Membership,
    declared_by,
    contribution_type: Optional[ContributionType],
    amount: Any,
    reference: str,
    attachment=None,
    now: Optional[datetime] = None,
) -> Payment:
    """Declaration « J'ai paye » d'un paiement fait par le lien du club
    (CDC 4.6), par le joueur pour lui-meme (ce n'est pas une
    validation). Cree le `Payment` (source ``player_declaration``, mode
    ``payment_link``) et sa `Transaction` **non scellee** ``pending``
    (fournisseur ``link``) : « A valider » chez le Tresorier, sans aucun
    effet sur le solde. Journalise et notifie le Tresorier et l'adjoint.

    Exceptions : :class:`TreasuryPermissionError` (declaration pour un
    autre joueur), :class:`PaymentLinkNotConfiguredError`,
    :class:`TreasuryValidationError` (dont :class:`InvalidAmountError` :
    montant, type, reference, capture, joueur parti),
    :class:`LedgerFrozenError`. Rien n'est ecrit si une exception est levee.
    """

    now = now or timezone.now()
    club = membership.club
    _require_service_club(club)
    if membership.user_id != getattr(declared_by, "pk", None):
        raise TreasuryPermissionError(
            "Un paiement ne peut être déclaré que par le joueur concerné, pour lui-même."
        )
    club_settings = _club_settings(club)
    if not (club_settings.payment_link_url or "").strip():
        raise PaymentLinkNotConfiguredError(PAYMENT_LINK_MISSING_MESSAGE)
    today = _club_today(club_settings, now)
    money, club_settings = _validate_payment_input(
        membership=membership, contribution_type=contribution_type, amount=amount, paid_on=today, now=now
    )
    if not _declarable_types_queryset(membership, today).filter(pk=contribution_type.pk).exists():
        raise TreasuryValidationError(
            "Ce type de cotisation ne vous concerne pas : choisissez l'un de vos types de cotisation."
        )
    cleaned_reference = _clean_declared_reference(reference)
    # Audit securite A6 : controle immediat limite aux paiements du joueur
    # lui-meme ; un doublon chez un autre joueur n'est jamais revele au
    # declarant, il est signale au Tresorier et bloque a la validation.
    _require_reference_available(club, cleaned_reference, membership=membership)
    _validate_attachment(attachment)
    _require_ledger_not_frozen(club)
    duplicated_elsewhere = _references_in_use(club, cleaned_reference).exists()

    from apps.notifications.models import Notification

    with db_transaction.atomic():
        payment = Payment(
            club=club,
            membership=membership,
            contribution_type=contribution_type,
            amount=money,
            currency=club_settings.currency,
            method=Payment.Method.PAYMENT_LINK,
            reference=cleaned_reference,
            paid_on=today,
            source=Payment.Source.PLAYER_DECLARATION,
            submitted_by=declared_by,
            submitted_at=now,
        )
        if attachment is not None:
            rename_upload_to_real_type(attachment)
            payment.attachment = attachment
        _save(payment)
        txn = open_payment_transaction(
            payment=payment, provider=Transaction.Provider.LINK, status=Transaction.Status.PENDING, now=now
        )
        log_action(
            actor=declared_by,
            club=club,
            action_type="treasury.payment.declared",
            obj=payment,
            before=None,
            after=_payment_snapshot(payment, txn),
        )
        _notify_roles(
            club,
            PAYMENT_RECORDERS,
            event_type=Notification.EventType.I_PAID_DECLARED,
            message=(
                f"Déclaration « J'ai payé » de {_membership_name(membership)} à valider : "
                f"{money:.2f} {payment.currency} ({contribution_type.name}), réf. {cleaned_reference}."
                + (
                    " Attention : cette référence figure déjà sur un autre paiement du club, "
                    "vérifiez-la avant toute validation."
                    if duplicated_elsewhere
                    else ""
                )
            ),
            target=payment,
            now=now,
        )
    return payment


def _pending_declaration(payment: Payment) -> tuple[Payment, Transaction]:
    """Relit la declaration dans son club et verifie qu'elle est encore
    « A valider » (transaction ``pending`` non scellee)."""

    stored = (
        Payment.all_objects.select_related("membership__user", "contribution_type")
        .filter(pk=payment.pk, club_id=payment.club_id)
        .first()
    )
    if stored is None or stored.source != Payment.Source.PLAYER_DECLARATION:
        raise TreasuryValidationError("Ce paiement n'est pas une déclaration « J'ai payé ».")
    txn = Transaction.all_objects.filter(club_id=stored.club_id, payment=stored).first()
    if txn is None or txn.is_sealed or txn.status != Transaction.Status.PENDING:
        raise DeclarationAlreadyProcessedError("Cette déclaration a déjà été traitée.")
    return stored, txn


def _lock_pending_declaration(stored: Payment, txn: Transaction) -> tuple[Payment, Transaction]:
    """Verrouille la transaction puis le paiement (dans ``atomic()``) et
    revérifie l'etat : deux decisions concurrentes ne peuvent pas aboutir."""

    locked_txn = Transaction.all_objects.select_for_update().get(pk=txn.pk)
    if locked_txn.is_sealed or locked_txn.status != Transaction.Status.PENDING:
        raise DeclarationAlreadyProcessedError("Cette déclaration a déjà été traitée.")
    locked = Payment.all_objects.select_for_update().select_related("membership__user", "contribution_type").get(
        pk=stored.pk
    )
    return locked, locked_txn


_DECLARATION_PROCESSORS_MESSAGE = (
    "Seuls le Trésorier et le Trésorier adjoint traitent les déclarations « J'ai payé »."
)


def preview_declared_payment(*, payment: Payment, requested_by, now: Optional[datetime] = None) -> PaymentPreview:
    """Apercu de la repartition 4.4.3 et du nouveau solde avant validation
    d'une declaration (fiche tresorerie-tableau-de-bord §4.5), sans ecriture."""

    now = now or timezone.now()
    club = payment.club
    _require_service_club(club)
    _require_roles(requested_by, club, PAYMENT_RECORDERS, _DECLARATION_PROCESSORS_MESSAGE)
    stored, _ = _pending_declaration(payment)
    money, club_settings = _validate_payment_input(
        membership=stored.membership,
        contribution_type=stored.contribution_type,
        amount=stored.amount,
        paid_on=stored.paid_on,
        now=now,
    )
    return _build_preview(
        membership=stored.membership,
        ctype=stored.contribution_type,
        money=money,
        paid_on=stored.paid_on,
        currency=club_settings.currency,
    )


def validate_declared_payment(*, payment: Payment, validated_by, now: Optional[datetime] = None) -> Payment:
    """Valide une declaration « J'ai paye » (Tresorier ou adjoint, CDC 4.6 ;
    confirmation dans l'interface, CDC 7.2). La declaration devient un paiement normal :
    transaction ``succeeded`` scellee (``external_ref`` = reference
    declaree), numero de recu, repartition 4.4.3, journal, notification du
    joueur (CDC 4.17).

    Controles de role, d'etat, de donnees, de reference et de gel. Rien
    n'est ecrit si une exception est levee.
    """

    now = now or timezone.now()
    club = payment.club
    _require_service_club(club)
    _require_roles(validated_by, club, PAYMENT_RECORDERS, _DECLARATION_PROCESSORS_MESSAGE)
    stored, txn = _pending_declaration(payment)
    _money, club_settings = _validate_payment_input(
        membership=stored.membership,
        contribution_type=stored.contribution_type,
        amount=stored.amount,
        paid_on=stored.paid_on,
        now=now,
    )
    if stored.currency != club_settings.currency:
        raise TreasuryValidationError("La devise de la déclaration ne correspond plus à celle du club.")
    _require_reference_available(club, stored.reference, exclude_pk=stored.pk)
    _precheck_ledger_writable(club)

    with db_transaction.atomic():
        locked, locked_txn = _lock_pending_declaration(stored, txn)
        before = _payment_snapshot(locked, locked_txn)
        locked.validated_by = validated_by
        locked.validated_at = now
        _save(locked)
        sealed = advance_transaction(
            transaction_obj=locked_txn,
            status=Transaction.Status.SUCCEEDED,
            external_ref=locked.reference,
            now=now,
            actor=validated_by,
        )
        locked.refresh_from_db()
        log_action(
            actor=validated_by,
            club=club,
            action_type="treasury.payment.validated",
            obj=locked,
            before=before,
            after=_payment_snapshot(locked, sealed),
        )
        # Joueur notifié au scellement (:func:`_notify_payment_validated`),
        # jamais une seconde fois ici.
    payment.refresh_from_db()
    return payment


def reject_declared_payment(*, payment: Payment, rejected_by, reason: str, now: Optional[datetime] = None) -> Payment:
    """Refus motive d'une declaration « J'ai paye » (Tresorier ou adjoint).
    La declaration ne devient pas un paiement : sa transaction passe a
    ``failed`` et est scellee (trace inalterable, CDC 5.3), le paiement
    porte ``rejected_*`` et le joueur est prevenu avec le motif."""

    now = now or timezone.now()
    club = payment.club
    _require_service_club(club)
    _require_roles(rejected_by, club, PAYMENT_RECORDERS, _DECLARATION_PROCESSORS_MESSAGE)
    cleaned = _require_reason(reason if isinstance(reason, str) else "", "Indiquez le motif du refus.")
    stored, txn = _pending_declaration(payment)
    _precheck_ledger_writable(club)

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    with db_transaction.atomic():
        locked, locked_txn = _lock_pending_declaration(stored, txn)
        before = _payment_snapshot(locked, locked_txn)
        locked.rejected_by = rejected_by
        locked.rejected_at = now
        locked.rejection_reason = cleaned
        _save(locked)
        sealed = advance_transaction(
            transaction_obj=locked_txn, status=Transaction.Status.FAILED, now=now, actor=rejected_by
        )
        locked.refresh_from_db()
        log_action(
            actor=rejected_by,
            club=club,
            action_type="treasury.payment.rejected",
            obj=locked,
            before=before,
            after=_payment_snapshot(locked, sealed),
        )
        create_notification(
            recipient=locked.membership.user,
            event_type=Notification.EventType.I_PAID_REJECTED,
            title="Déclaration « J'ai payé » refusée",
            message=(
                f"Votre déclaration de {locked.amount:.2f} {locked.currency} (réf. {locked.reference}) "
                f"a été refusée : {cleaned}"
            ),
            club=club,
            target=locked,
            now=now,
        )
    payment.refresh_from_db()
    return payment


# ---------------------------------------------------------------------------
# Depenses et assistance sociale (tache 2.2 ; CDC 4.5 ; schema-treasury.md §7-8)
# ---------------------------------------------------------------------------
#
# Matrice 2.4 :
# - Categories de depenses : É Pdt, Trés ; L VP, Adj.
# - Saisie d'une depense : É Trés, Adj ; L Pdt, VP.
# - Validation d'une depense : É Pdt, VP ; L Trés, Adj.
# - Demande d'assistance sociale : P (chaque joueur pour lui-meme) ;
#   traitement par le Pdt ou le VP (CDC 4.5.3).
#
# Decisions provisoires (non tranchees par le CDC, a confirmer par le
# client, signalees dans le compte rendu de la tache 2.2) :
# - Q10 : le plafond d'une categorie s'applique par depense et bloque la
#   saisie comme la liberation (lecture la plus restrictive) ;
# - Q11 : le bareme d'assistance est gere par le Pdt et le Trésorier ;
# - Q12 : un paiement valide apres l'evenement compte pour l'eligibilite ;
# - Q13 : l'approbation d'une demande cree une depense « En attente » qui
#   suit ensuite le circuit normal (liberation confirmee en modale) ;
# - fiche d'ecran §9 q.5 : le justificatif est televerse par le Trésorier
#   ou l'adjoint ;
# - Q19 : sans justificatif obligatoire, une depense liberee reste
#   « Liberee » sans delai ni blocage.

TREASURY_READERS = frozenset(
    {
        MembershipRole.Role.PRESIDENT,
        MembershipRole.Role.VICE_PRESIDENT,
        MembershipRole.Role.TREASURER,
        MembershipRole.Role.ASSISTANT_TREASURER,
    }
)
EXPENSE_READERS = TREASURY_READERS
EXPENSE_CATEGORY_MANAGERS = TREASURY_MANAGERS
EXPENSE_RECORDERS = PAYMENT_RECORDERS
EXPENSE_VALIDATORS = frozenset({MembershipRole.Role.PRESIDENT, MembershipRole.Role.VICE_PRESIDENT})
EXPENSE_RECEIPT_UPLOADERS = PAYMENT_RECORDERS
ASSISTANCE_PROCESSORS = EXPENSE_VALIDATORS
ASSISTANCE_SCALE_MANAGERS = TREASURY_MANAGERS

EXPENSE_BLOCKED_MESSAGE = "Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée."


class ExpenseReleaseBlockedError(TreasuryValidationError):
    """Liberation refusee : une depense est « Non justifiee » (CDC 4.5.2)."""


def get_club_today(club) -> date:
    """Date du jour dans le fuseau du club (echeances, delais)."""

    return _club_today(_club_settings(club), timezone.now())


def get_club_currency(club) -> str:
    """Devise du club (``ClubSettings.currency``), jamais ecrite en dur."""

    return _club_settings(club).currency


def _membership_name(membership: Membership) -> str:
    user = membership.user
    return f"{user.first_name} {user.last_name}".strip() or f"Joueur {membership.pk}"


def _role_holder_users(club, roles: Iterable[str]) -> list:
    rows = (
        MembershipRole.all_objects.filter(
            club=club,
            role__in=list(roles),
            revoked_at__isnull=True,
            membership__status=Membership.Status.ACTIVE,
        )
        .select_related("membership__user")
        .order_by("membership_id")
    )
    users, seen = [], set()
    for row in rows:
        user = row.membership.user
        if user.pk not in seen:
            seen.add(user.pk)
            users.append(user)
    return users


def _notify_roles(club, roles: Iterable[str], *, event_type: str, message: str, target, now: datetime) -> None:
    from apps.notifications.services import create_notification

    for user in _role_holder_users(club, roles):
        create_notification(recipient=user, event_type=event_type, message=message, club=club, target=target, now=now)


def _require_date(value, message: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TreasuryValidationError(message)
    return value


# --- Instantanes du journal (identifiants et montants) -------


def _expense_category_snapshot(category: ExpenseCategory) -> dict[str, Any]:
    return {
        "name": category.name,
        "ceiling": _money_str(category.ceiling),
        "receipt_required": category.receipt_required,
        "good_standing_only": category.good_standing_only,
        "status": category.status,
        "archived_at": category.archived_at,
        "archived_by_id": category.archived_by_id,
    }


def _expense_snapshot(expense: Expense, txn: Optional[Transaction] = None) -> dict[str, Any]:
    snapshot = {
        "category_id": expense.category_id,
        "amount": _money_str(expense.amount),
        "currency": expense.currency,
        "beneficiary_name": expense.beneficiary_name,
        "beneficiary_membership_id": expense.beneficiary_membership_id,
        "reason": expense.reason,
        "expense_date": expense.expense_date,
        "status": expense.status,
        "created_by_id": expense.created_by_id,
        "refused_by_id": expense.refused_by_id,
        "refusal_reason": expense.refusal_reason,
        "released_by_id": expense.released_by_id,
        "released_at": expense.released_at,
        "justification_deadline": expense.justification_deadline,
        "justified_by_id": expense.justified_by_id,
        "justified_at": expense.justified_at,
        "unjustified_at": expense.unjustified_at,
        "social_assistance_request_id": expense.social_assistance_request_id,
    }
    snapshot.update(_transaction_snapshot(txn))
    return snapshot


def _expense_attachment_snapshot(attachment: ExpenseAttachment) -> dict[str, Any]:
    return {
        "expense_id": attachment.expense_id,
        "kind": attachment.kind,
        "uploaded_by_id": attachment.uploaded_by_id,
        "uploaded_at": attachment.uploaded_at,
    }


def _scale_snapshot(scale: SocialAssistanceScale) -> dict[str, Any]:
    return {
        "event_type": scale.event_type,
        "amount": _money_str(scale.amount),
        "processing_days": scale.processing_days,
        "expense_category_id": scale.expense_category_id,
        "status": scale.status,
        "archived_at": scale.archived_at,
    }


def _assistance_request_snapshot(request_obj: SocialAssistanceRequest) -> dict[str, Any]:
    # Ni la description ni la piece jointe : donnees personnelles du joueur,
    # inutiles a la tracabilite de l'action (CDC 5.1, 7.5).
    return {
        "membership_id": request_obj.membership_id,
        "event_type": request_obj.event_type,
        "event_date": request_obj.event_date,
        "scale_id": request_obj.scale_id,
        "planned_amount": _money_str(request_obj.planned_amount),
        "currency": request_obj.currency,
        "eligible_at_submission": request_obj.eligible_at_submission,
        "amount_to_regularize": _money_str(request_obj.amount_to_regularize),
        "status": request_obj.status,
        "decided_by_id": request_obj.decided_by_id,
        "decided_at": request_obj.decided_at,
        "rejection_reason": request_obj.rejection_reason,
    }


# --- Categories de depenses (CDC 4.5.1) ------------------------------------


def _clean_ceiling(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    money = to_money(value)
    if money <= 0:
        raise InvalidAmountError("Le plafond doit être strictement positif.")
    return money


def create_expense_category(
    *,
    club,
    created_by,
    name: str,
    ceiling: Any = None,
    receipt_required: bool = True,
    good_standing_only: bool = False,
    now: Optional[datetime] = None,
) -> ExpenseCategory:
    """Cree une categorie de depense (President ou Tresorier, CDC 4.5.1)."""

    _require_service_club(club)
    _require_roles(
        created_by,
        club,
        EXPENSE_CATEGORY_MANAGERS,
        "Seuls le Président et le Trésorier peuvent créer une catégorie de dépense.",
    )
    cleaned = _require_reason(name, "Le nom de la catégorie est obligatoire.")
    if len(cleaned) > 120:
        raise TreasuryValidationError("Le nom de la catégorie ne doit pas dépasser 120 caractères.")
    if ExpenseCategory.all_objects.filter(club=club, name=cleaned).exists():
        raise TreasuryValidationError("Une catégorie de dépense porte déjà ce nom dans ce club.")
    category = ExpenseCategory(
        club=club,
        name=cleaned,
        ceiling=_clean_ceiling(ceiling),
        receipt_required=bool(receipt_required),
        good_standing_only=bool(good_standing_only),
        created_at=now or timezone.now(),
        created_by=created_by,
    )
    with db_transaction.atomic():
        _save(category)
        log_action(
            actor=created_by,
            club=club,
            action_type="treasury.expense_category.created",
            obj=category,
            before=None,
            after=_expense_category_snapshot(category),
        )
    return category


def update_expense_category(*, category: ExpenseCategory, updated_by, **changes) -> ExpenseCategory:
    """Modifie une categorie active (President ou Tresorier). Les depenses
    deja saisies gardent leur montant ; une depense liberee est figee."""

    club = category.club
    _require_service_club(club)
    _require_roles(
        updated_by,
        club,
        EXPENSE_CATEGORY_MANAGERS,
        "Seuls le Président et le Trésorier peuvent modifier une catégorie de dépense.",
    )
    allowed = {"name", "ceiling", "receipt_required", "good_standing_only"}
    if set(changes) - allowed:
        raise TreasuryValidationError("Champ de modification inconnu pour cette catégorie.")
    with db_transaction.atomic():
        stored = ExpenseCategory.all_objects.select_for_update().get(pk=category.pk, club=club)
        if stored.status == ExpenseCategory.Status.ARCHIVED:
            raise TreasuryValidationError("Une catégorie archivée ne peut plus être modifiée.")
        before = _expense_category_snapshot(stored)
        if "name" in changes:
            cleaned = _require_reason(changes["name"], "Le nom de la catégorie est obligatoire.")
            if len(cleaned) > 120:
                raise TreasuryValidationError("Le nom de la catégorie ne doit pas dépasser 120 caractères.")
            if ExpenseCategory.all_objects.filter(club=club, name=cleaned).exclude(pk=stored.pk).exists():
                raise TreasuryValidationError("Une catégorie de dépense porte déjà ce nom dans ce club.")
            stored.name = cleaned
        if "ceiling" in changes:
            stored.ceiling = _clean_ceiling(changes["ceiling"])
        if "receipt_required" in changes:
            stored.receipt_required = bool(changes["receipt_required"])
        if "good_standing_only" in changes:
            wanted = bool(changes["good_standing_only"])
            if not wanted and SocialAssistanceScale.all_objects.filter(
                club=club, expense_category=stored, status=SocialAssistanceScale.Status.ACTIVE
            ).exists():
                raise TreasuryValidationError(
                    "Cette catégorie est utilisée par un barème d'assistance sociale : elle doit rester "
                    "« réservée aux membres en ordre »."
                )
            stored.good_standing_only = wanted
        _save(stored)
        log_action(
            actor=updated_by,
            club=club,
            action_type="treasury.expense_category.updated",
            obj=stored,
            before=before,
            after=_expense_category_snapshot(stored),
        )
    category.refresh_from_db()
    return category


def archive_expense_category(
    *, category: ExpenseCategory, archived_by, now: Optional[datetime] = None
) -> ExpenseCategory:
    """Archive une categorie (jamais de suppression). Elle n'est plus
    proposee a la saisie ; les depenses existantes suivent leur circuit."""

    club = category.club
    _require_service_club(club)
    _require_roles(
        archived_by,
        club,
        EXPENSE_CATEGORY_MANAGERS,
        "Seuls le Président et le Trésorier peuvent archiver une catégorie de dépense.",
    )
    with db_transaction.atomic():
        stored = ExpenseCategory.all_objects.select_for_update().get(pk=category.pk, club=club)
        if stored.status == ExpenseCategory.Status.ARCHIVED:
            raise TreasuryValidationError("Cette catégorie est déjà archivée.")
        if SocialAssistanceScale.all_objects.filter(
            club=club, expense_category=stored, status=SocialAssistanceScale.Status.ACTIVE
        ).exists():
            raise TreasuryValidationError(
                "Cette catégorie est utilisée par un barème d'assistance sociale actif : "
                "archivez ou modifiez d'abord ce barème."
            )
        before = _expense_category_snapshot(stored)
        stored.status = ExpenseCategory.Status.ARCHIVED
        stored.archived_at = now or timezone.now()
        stored.archived_by = archived_by
        _save(stored)
        log_action(
            actor=archived_by,
            club=club,
            action_type="treasury.expense_category.archived",
            obj=stored,
            before=before,
            after=_expense_category_snapshot(stored),
        )
    category.refresh_from_db()
    return category


# --- Saisie et circuit d'une depense (CDC 4.5.2) ---------------------------


def _check_ceiling(category: ExpenseCategory, amount: Decimal, currency: str) -> None:
    if category.ceiling is not None and amount > category.ceiling:
        raise TreasuryValidationError(
            f"Le montant dépasse le plafond de la catégorie « {category.name} » "
            f"({category.ceiling:.2f} {currency})."
        )


def _require_beneficiary_in_good_standing(membership: Optional[Membership], category: ExpenseCategory) -> None:
    if membership is None:
        raise TreasuryValidationError(
            f"La catégorie « {category.name} » est réservée aux membres en ordre : "
            "choisissez le joueur bénéficiaire."
        )
    in_order, amount_due, _reason = is_in_good_standing(membership)
    if not in_order:
        currency = get_club_currency(membership.club)
        raise TreasuryValidationError(
            f"La catégorie « {category.name} » est réservée aux membres en ordre : "
            f"{_membership_name(membership)} est en dette ({amount_due:.2f} {currency} à régulariser)."
        )


def _create_expense_unchecked(
    *,
    club,
    created_by,
    category: ExpenseCategory,
    amount: Decimal,
    beneficiary_name: str,
    beneficiary_membership: Optional[Membership],
    reason: str,
    expense_date: date,
    currency: str,
    attachment=None,
    social_assistance_request: Optional[SocialAssistanceRequest] = None,
    now: datetime,
) -> Expense:
    """Ecrit la depense « En attente » (a appeler dans ``atomic()``, controles faits)."""

    expense = Expense(
        club=club,
        category=category,
        amount=amount,
        currency=currency,
        beneficiary_name=beneficiary_name,
        beneficiary_membership=beneficiary_membership,
        reason=reason,
        expense_date=expense_date,
        status=Expense.Status.PENDING,
        created_by=created_by,
        created_at=now,
        social_assistance_request=social_assistance_request,
    )
    _save(expense)
    log_action(
        actor=created_by,
        club=club,
        action_type="treasury.expense.created",
        obj=expense,
        before=None,
        after=_expense_snapshot(expense),
    )
    if attachment is not None:
        _add_expense_attachment(
            expense=expense, file=attachment, kind=ExpenseAttachment.Kind.SUPPORTING, uploaded_by=created_by, now=now
        )
    from apps.notifications.models import Notification

    _notify_roles(
        club,
        EXPENSE_VALIDATORS,
        event_type=Notification.EventType.EXPENSE_SUBMITTED,
        message=(
            f"Dépense à examiner : {expense.amount:.2f} {currency} — {category.name} "
            f"({expense.beneficiary_name})."
        ),
        target=expense,
        now=now,
    )
    return expense


def _add_expense_attachment(*, expense: Expense, file, kind: str, uploaded_by, now: datetime) -> ExpenseAttachment:
    rename_upload_to_real_type(file)
    attachment = ExpenseAttachment(
        club=expense.club, expense=expense, file=file, kind=kind, uploaded_by=uploaded_by, uploaded_at=now
    )
    _save(attachment)
    log_action(
        actor=uploaded_by,
        club=expense.club,
        action_type="treasury.expense_attachment.created",
        obj=attachment,
        before=None,
        after=_expense_attachment_snapshot(attachment),
    )
    return attachment


def create_expense(
    *,
    club,
    created_by,
    category: ExpenseCategory,
    amount: Any,
    beneficiary_name: str = "",
    reason: str,
    expense_date: date,
    beneficiary_membership: Optional[Membership] = None,
    attachment=None,
    now: Optional[datetime] = None,
) -> Expense:
    """Saisie d'une depense « En attente » par le Tresorier ou l'adjoint
    (CDC 4.5.2). Justificatif facultatif a la saisie. Notifie le President
    et le Vice-president (CDC 4.17). Aucune ecriture financiere : la
    transaction chainee n'est creee qu'a la liberation."""

    _require_service_club(club)
    _require_roles(
        created_by,
        club,
        EXPENSE_RECORDERS,
        "Seuls le Trésorier et le Trésorier adjoint peuvent saisir une dépense.",
    )
    if category.club_id != club.pk:
        raise TreasuryValidationError("La catégorie choisie n'appartient pas à ce club.")
    if category.status != ExpenseCategory.Status.ACTIVE:
        raise TreasuryValidationError("Cette catégorie est archivée : choisissez une catégorie active.")
    money = to_money(amount)
    if money <= 0:
        raise InvalidAmountError("Saisissez un montant supérieur à 0.")
    currency = get_club_currency(club)
    _check_ceiling(category, money, currency)
    cleaned_reason = _require_reason(reason, "Le motif de la dépense est obligatoire.")
    expense_date = _require_date(expense_date, "La date de la dépense est invalide.")
    now = now or timezone.now()
    # Correctif D-A6 : comme pour un paiement, jamais de date future (fuseau du club).
    if expense_date > _club_today(_club_settings(club), now):
        raise TreasuryValidationError("La date de la dépense ne peut pas être dans le futur.")
    if beneficiary_membership is not None and beneficiary_membership.club_id != club.pk:
        raise TreasuryValidationError("Le joueur bénéficiaire n'appartient pas à ce club.")
    name = (beneficiary_name or "").strip()
    if not name and beneficiary_membership is not None:
        name = _membership_name(beneficiary_membership)
    if not name:
        raise TreasuryValidationError("Le bénéficiaire de la dépense est obligatoire.")
    if len(name) > 160:
        raise TreasuryValidationError("Le nom du bénéficiaire ne doit pas dépasser 160 caractères.")
    if category.good_standing_only:
        _require_beneficiary_in_good_standing(beneficiary_membership, category)

    with db_transaction.atomic():
        return _create_expense_unchecked(
            club=club,
            created_by=created_by,
            category=category,
            amount=money,
            beneficiary_name=name,
            beneficiary_membership=beneficiary_membership,
            reason=cleaned_reason,
            expense_date=expense_date,
            currency=currency,
            attachment=attachment,
            now=now,
        )


def refuse_expense(*, expense: Expense, refused_by, reason: str, now: Optional[datetime] = None) -> Expense:
    """Refus motive d'une depense en attente (President ou VP).
    Etat final : la depense n'est jamais supprimee."""

    club = expense.club
    _require_service_club(club)
    _require_roles(
        refused_by,
        club,
        EXPENSE_VALIDATORS,
        "Seuls le Président et le Vice-président peuvent refuser une dépense.",
    )
    cleaned = _require_reason(reason, "Indiquez le motif du refus.")
    with db_transaction.atomic():
        stored = Expense.all_objects.select_for_update().get(pk=expense.pk, club=club)
        if stored.status != Expense.Status.PENDING:
            raise TreasuryValidationError("Cette dépense n'est plus en attente : elle ne peut pas être refusée.")
        before = _expense_snapshot(stored)
        stored.status = Expense.Status.REFUSED
        stored.refused_by = refused_by
        stored.refused_at = now or timezone.now()
        stored.refusal_reason = cleaned
        _save(stored)
        log_action(
            actor=refused_by,
            club=club,
            action_type="treasury.expense.refused",
            obj=stored,
            before=before,
            after=_expense_snapshot(stored),
        )
    return stored


class ExpenseReleaseCheck(NamedTuple):
    """Resultat de :func:`can_release_expense` : booleen + raison lisible."""

    allowed: bool
    reason: str
    blocking_expense_ids: tuple = ()


def _blocking_expenses(club, today: date):
    # Evalue a la volee (invariant I8) : une depense liberee dont le delai
    # est depasse bloque meme si la tache quotidienne n'est pas encore passee.
    return Expense.all_objects.filter(club=club).filter(
        Q(status=Expense.Status.UNJUSTIFIED)
        | Q(status=Expense.Status.RELEASED, justification_deadline__isnull=False, justification_deadline__lt=today)
    )


def can_release_expense(club, *, today: Optional[date] = None) -> ExpenseReleaseCheck:
    """Blocage automatique (CDC 4.5.2) : aucune nouvelle liberation tant
    qu'une depense est « Non justifiee » (ou liberee avec un delai de
    justification depasse). Service expose aux autres modules."""

    _require_service_club(club)
    today = today or get_club_today(club)
    ids = tuple(_blocking_expenses(club, today).order_by("pk").values_list("pk", flat=True))
    if ids:
        return ExpenseReleaseCheck(False, EXPENSE_BLOCKED_MESSAGE, ids)
    return ExpenseReleaseCheck(True, "Aucune dépense non justifiée : la libération est possible.", ())


def is_expense_overdue(expense: Expense, today: date) -> bool:
    """Vrai si le delai de justification d'une depense liberee est depasse."""

    return (
        expense.status in (Expense.Status.RELEASED, Expense.Status.UNJUSTIFIED)
        and expense.justification_deadline is not None
        and expense.justification_deadline < today
    )


def _check_releasable(expense: Expense, today: date) -> None:
    """Controles metier communs a la liberation normale et par derogation."""

    if expense.status != Expense.Status.PENDING:
        raise TreasuryValidationError("Cette dépense n'est plus en attente : elle ne peut pas être libérée.")
    currency = get_club_currency(expense.club)
    if expense.currency != currency:
        raise TreasuryValidationError("La devise de la dépense ne correspond plus à celle du club.")
    category = expense.category
    _check_ceiling(category, expense.amount, currency)
    request_obj = expense.social_assistance_request
    if request_obj is not None:
        # 10.2 n° 37 : un joueur toujours en dette ne peut pas etre libere,
        # meme par derogation.
        eligibility = get_social_assistance_eligibility(
            request_obj.membership, request_obj.event_date, at_date=today
        )
        if not eligibility.can_be_approved:
            raise TreasuryValidationError(
                f"Assistance sociale non libérable : {eligibility.reason}"
            )
    elif category.good_standing_only:
        _require_beneficiary_in_good_standing(expense.beneficiary_membership, category)


def _release_locked(
    *, expense: Expense, released_by, now: datetime, derogation_reason: Optional[str] = None
) -> Expense:
    """Libere et scelle la depense (a appeler dans ``atomic()``, droits deja
    verifie). Le verrou de la tete de chaine serialise les liberations du
    club : le blocage est reevalue sous ce verrou."""

    club = expense.club
    _lock_chain_state(club)
    stored = (
        Expense.all_objects.select_for_update()
        .select_related("category", "beneficiary_membership", "social_assistance_request")
        .get(pk=expense.pk, club=club)
    )
    today = _club_today(_club_settings(club), now)
    _check_releasable(stored, today)
    blocking_ids = tuple(
        _blocking_expenses(club, today).exclude(pk=stored.pk).order_by("pk").values_list("pk", flat=True)
    )
    if derogation_reason is None and blocking_ids:
        raise ExpenseReleaseBlockedError(
            f"{EXPENSE_BLOCKED_MESSAGE} Seul le Président peut libérer par dérogation, avec un motif."
        )
    if derogation_reason is not None and not blocking_ids:
        raise TreasuryValidationError(
            "Aucune dépense non justifiée ne bloque la libération : libérez cette dépense sans dérogation."
        )

    before = _expense_snapshot(stored)
    club_settings = _club_settings(club)
    stored.status = Expense.Status.RELEASED
    stored.released_by = released_by
    stored.released_at = now
    stored.justification_deadline = (
        today + timedelta(days=club_settings.expense_justification_days) if stored.category.receipt_required else None
    )
    _save(stored)
    txn = Transaction(
        club=club,
        kind=Transaction.Kind.EXPENSE_RELEASE,
        expense=stored,
        membership=stored.beneficiary_membership,
        contribution_type=None,
        amount=-stored.amount,
        currency=stored.currency,
        value_date=today,
        provider=Transaction.Provider.MANUAL,
        external_ref=None,
        status=Transaction.Status.SUCCEEDED,
        status_changed_at=now,
        created_at=now,
    )
    _seal(txn, Transaction.Status.SUCCEEDED, now)

    if derogation_reason is not None:
        derogation = ExpenseDerogation(
            club=club, expense=stored, reason=derogation_reason, granted_by=released_by, granted_at=now
        )
        _save(derogation)
        derogation.blocking_expenses.set(blocking_ids)
        log_action(
            actor=released_by,
            club=club,
            action_type="treasury.expense.derogation_granted",
            obj=derogation,
            before=None,
            after={
                "expense_id": stored.pk,
                "reason": derogation_reason,
                "granted_by_id": released_by.pk,
                "granted_at": now,
                "blocking_expense_ids": list(blocking_ids),
            },
        )
    log_action(
        actor=released_by,
        club=club,
        action_type="treasury.expense.released",
        obj=stored,
        before=before,
        after=_expense_snapshot(stored, txn),
    )
    return stored


def _load_expense(expense: Expense) -> Expense:
    return (
        Expense.all_objects.select_related("category", "beneficiary_membership", "social_assistance_request")
        .get(pk=expense.pk, club_id=expense.club_id)
    )


def release_expense(*, expense: Expense, released_by, now: Optional[datetime] = None) -> Expense:
    """Validation et liberation d'une depense par le President ou le VP,
    apres confirmation dans l'interface (CDC 4.5.2, 7.2). Cree une transaction chainee negative.

    Refusee (:class:`ExpenseReleaseBlockedError`) tant qu'une depense est
    « Non justifiee » ; refusee si la categorie est reservee aux membres en
    ordre et que le beneficiaire est en dette (assistance sociale : 10.2
    n° 37). Controles de role et d'etat avant toute ecriture."""

    club = expense.club
    _require_service_club(club)
    _require_roles(
        released_by,
        club,
        EXPENSE_VALIDATORS,
        "Seuls le Président et le Vice-président peuvent libérer une dépense.",
    )
    now = now or timezone.now()
    stored = _load_expense(expense)
    today = _club_today(_club_settings(club), now)
    _check_releasable(stored, today)
    check = can_release_expense(club, today=today)
    if not check.allowed:
        raise ExpenseReleaseBlockedError(
            f"{check.reason} Seul le Président peut libérer par dérogation, avec un motif."
        )
    _precheck_ledger_writable(club)

    with db_transaction.atomic():
        released = _release_locked(expense=stored, released_by=released_by, now=now)
    expense.refresh_from_db()
    return released


def release_expense_with_derogation(
    *, expense: Expense, president, reason: str, now: Optional[datetime] = None
) -> Expense:
    """Dérogation (CDC 4.5.2) : le President seul libere une depense malgre
    le blocage, avec un motif obligatoire et apres confirmation dans l'interface. Journalisee (``ExpenseDerogation``
    + entree ``treasury.expense.derogation_granted``) pour etre signalee a la
    prochaine AG. Ne contourne jamais l'eligibilite d'un beneficiaire
    (10.2 n° 37)."""

    club = expense.club
    _require_service_club(club)
    _require_roles(
        president, club, PRESIDENT_ONLY, "Seul le Président peut libérer une dépense par dérogation."
    )
    cleaned = _require_reason(reason, "Le motif de la dérogation est obligatoire.")
    now = now or timezone.now()
    stored = _load_expense(expense)
    today = _club_today(_club_settings(club), now)
    _check_releasable(stored, today)
    if can_release_expense(club, today=today).allowed:
        raise TreasuryValidationError(
            "Aucune dépense non justifiée ne bloque la libération : libérez cette dépense sans dérogation."
        )
    _precheck_ledger_writable(club)

    with db_transaction.atomic():
        released = _release_locked(expense=stored, released_by=president, now=now, derogation_reason=cleaned)
    expense.refresh_from_db()
    return released


def justify_expense(*, expense: Expense, uploaded_by, file, now: Optional[datetime] = None) -> Expense:
    """Televersement du justificatif (photo ou PDF) : Liberee -> Justifiee
    ou Non justifiee -> Justifiee (CDC 4.5.2). Leve le blocage des que plus
    aucune depense n'est non justifiee."""

    club = expense.club
    _require_service_club(club)
    _require_roles(
        uploaded_by,
        club,
        EXPENSE_RECEIPT_UPLOADERS,
        "Seuls le Trésorier et le Trésorier adjoint peuvent téléverser le justificatif d'une dépense.",
    )
    if not file:
        raise TreasuryValidationError("Le justificatif (photo ou PDF) est obligatoire.")
    now = now or timezone.now()
    with db_transaction.atomic():
        stored = Expense.all_objects.select_for_update().get(pk=expense.pk, club=club)
        if stored.status not in (Expense.Status.RELEASED, Expense.Status.UNJUSTIFIED):
            raise TreasuryValidationError(
                "Seule une dépense libérée ou non justifiée peut recevoir son justificatif."
            )
        before = _expense_snapshot(stored)
        _add_expense_attachment(
            expense=stored, file=file, kind=ExpenseAttachment.Kind.RECEIPT, uploaded_by=uploaded_by, now=now
        )
        stored.status = Expense.Status.JUSTIFIED
        stored.justified_by = uploaded_by
        stored.justified_at = now
        _save(stored)
        log_action(
            actor=uploaded_by,
            club=club,
            action_type="treasury.expense.justified",
            obj=stored,
            before=before,
            after=_expense_snapshot(stored),
        )
    expense.refresh_from_db()
    return stored


def mark_overdue_expenses_unjustified(club, *, now: Optional[datetime] = None, actor=None) -> list[Expense]:
    """Passe « Non justifiee » les depenses liberees dont le delai est
    depasse, et alerte le Tresorier, l'adjoint et le President (CDC 4.5.2,
    4.17). Idempotente. Appelee chaque jour par la commande cron
    ``mark_unjustified_expenses`` (via :func:`run_unjustified_expenses`).

    ``actor`` : utilisateur a inscrire au journal. Une tache cron n'a pas
    d'acteur reel ; le journal exige un acteur (CDC 5.1) : sans ``actor``,
    la transition reste tracee par ``Expense.unjustified_at`` et la
    notification, sans entree de journal (meme choix que
    ``apps.licences.services.process_licence_expirations``, point ouvert).
    Le blocage, lui, ne depend pas de cette fonction (:func:`can_release_expense`).
    """

    from apps.notifications.models import Notification

    _require_service_club(club)
    now = now or timezone.now()
    today = _club_today(_club_settings(club), now)
    changed = []
    with db_transaction.atomic():
        overdue = list(
            Expense.all_objects.select_for_update()
            .filter(
                club=club,
                status=Expense.Status.RELEASED,
                justification_deadline__isnull=False,
                justification_deadline__lt=today,
            )
            .select_related("category")
            .order_by("pk")
        )
        for expense in overdue:
            before = _expense_snapshot(expense)
            expense.status = Expense.Status.UNJUSTIFIED
            expense.unjustified_at = now
            _save(expense)
            if actor is not None:
                log_action(
                    actor=actor,
                    club=club,
                    action_type="treasury.expense.unjustified",
                    obj=expense,
                    before=before,
                    after=_expense_snapshot(expense),
                )
            _notify_roles(
                club,
                {
                    MembershipRole.Role.TREASURER,
                    MembershipRole.Role.ASSISTANT_TREASURER,
                    MembershipRole.Role.PRESIDENT,
                },
                event_type=Notification.EventType.EXPENSE_BLOCKING,
                message=(
                    f"Dépense non justifiée ({expense.amount:.2f} {expense.currency} — "
                    f"{expense.category.name}) : délai dépassé le {expense.justification_deadline:%d/%m/%Y}. "
                    "Aucune nouvelle dépense ne peut être libérée."
                ),
                target=expense,
                now=now,
            )
            changed.append(expense)
    return changed


def get_available_cash(club) -> Decimal:
    """Caisse disponible = encaissements - depenses liberees (CDC 4.4.6).

    Calculee, jamais stockee : une seule agregation SQL sur les
    transactions scellees reussies du club (paiements > 0, annulations et
    liberations de depenses < 0), tous types de cotisation confondus."""

    _require_service_club(club)
    total = Transaction.all_objects.filter(
        club=club, status=Transaction.Status.SUCCEEDED, sealed_at__isnull=False
    ).aggregate(total=Sum("amount"))["total"]
    return (total or Decimal("0.00")).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


# --- Indicateurs du tableau de bord (CDC 4.4.6) ----------------------------
#
# Formules (provisoires pour le taux de recouvrement, point ouvert connu) :
# - encaisse du mois = somme des transactions scellees reussies de type
#   « paiement » et « annulation de paiement » dont la date de valeur tombe
#   dans le mois, tous types de cotisation (obligatoires et libres), hors
#   depenses. Une annulation approuvee porte la date de valeur du paiement
#   d'origine : un paiement annule ne compte donc plus dans son mois ;
# - taux de recouvrement = montants dus echus du mois couverts / montants
#   dus echus du mois (types obligatoires). « Echus » = meme regle que le
#   solde (:func:`_matured_mandatory_dues`, tolerance du club comprise) a la
#   date du jour du club ; « couvert » = repartition 4.4.3 enregistree
#   (``PaymentAllocation``) sur le meme (joueur, type, mois), plafonnee au
#   montant du. ``None`` si aucun montant du du mois n'est encore echu ;
# - total des dettes = somme des soldes negatifs (valeur absolue) des
#   adhesions non parties (Inscrit, En attente), a la date du jour ;
# - caisse disponible = :func:`get_available_cash`, tel quel.

DASHBOARD_READERS = TREASURY_READERS
# Joueurs « Inscrit » uniquement : un joueur « En attente » n'est jamais « En
# dette » (CDC 4.1, 4.3 ; decision du client du 17/11/2026 -- ses frais
# d'adhesion dus restent visibles dans sa situation, pas dans les dettes).
DASHBOARD_DEBT_STATUSES = (Membership.Status.ACTIVE,)


@dataclass(frozen=True)
class TreasuryDashboardSummary:
    period: date
    currency: str
    collected: Decimal
    matured_due_total: Decimal
    matured_due_covered: Decimal
    collection_rate: Optional[Decimal]
    total_debts: Decimal
    members_in_debt: int
    available_cash: Decimal


def _quantize(value) -> Decimal:
    return Decimal(value or 0).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _collected_transactions(club, start: date, end: date):
    """Encaissements nets (CDC 4.4.6) dont la date de valeur tombe dans
    ``[start, end[`` : paiements et annulations de paiement scelles reussis,
    tous types de cotisation. **Seule definition** de « l'encaisse »,
    partagee par le tableau de bord Tresorerie et celui du bureau
    (``apps.treasury.dashboard``)."""

    return Transaction.all_objects.filter(
        club=club,
        kind__in=(Transaction.Kind.PAYMENT, Transaction.Kind.PAYMENT_REVERSAL),
        status=Transaction.Status.SUCCEEDED,
        sealed_at__isnull=False,
        value_date__gte=start,
        value_date__lt=end,
    )


def _matured_dues_coverage(club, start: date, end: date, today: date):
    """Montants dus **echus** a ``today`` (meme regle que le solde) des mois
    ``[start, end[``, annotes ``capped`` = part couverte par la repartition
    4.4.3 enregistree, plafonnee au montant du. **Seule definition** du
    taux de recouvrement (tableau de bord Tresorerie et tableau de bord du
    bureau) : ``Sum("capped") / Sum("amount")``."""

    return _annotate_due_coverage(club, _matured_mandatory_dues(club, today).filter(period__gte=start, period__lt=end))


def _annotate_due_coverage(club, dues_qs):
    """Annote chaque montant du de ``covered`` (allocations 4.4.3
    enregistrees sur le meme joueur, type et mois) et ``capped`` (couverture
    plafonnee au montant du). Une sous-requete correlee : aucune boucle."""

    from django.db.models import DecimalField, OuterRef, Subquery, Value
    from django.db.models.functions import Coalesce, Least

    money = DecimalField(max_digits=12, decimal_places=2)
    covered_subquery = (
        PaymentAllocation.all_objects.filter(
            club=club,
            membership_id=OuterRef("membership_id"),
            contribution_type_id=OuterRef("contribution_type_id"),
            period=OuterRef("period"),
        )
        .values("membership_id")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    return (
        dues_qs
        .annotate(covered=Coalesce(Subquery(covered_subquery, output_field=money), Value(Decimal("0.00")), output_field=money))
        .annotate(capped=Least("covered", "amount", output_field=money))
    )


def _collection_rate(due_total: Decimal, covered_total: Decimal) -> Optional[Decimal]:
    """Taux de recouvrement en pourcentage (2 decimales), ``None`` sans du echu."""

    if due_total > 0:
        return (covered_total * 100 / due_total).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return None


def get_treasury_dashboard_summary(club, *, period: Optional[date] = None) -> TreasuryDashboardSummary:
    """Indicateurs du tableau de bord Tresorerie (CDC 4.4.6), tous calcules
    par agregations SQL, jamais stockes. ``period`` : n'importe quel jour du
    mois voulu (defaut : mois en cours, fuseau du club). Le total des
    dettes et la caisse disponible sont toujours ceux du jour."""

    _require_service_club(club)
    club_settings = _club_settings(club)
    today = _club_today(club_settings, timezone.now())
    start = _period_start(period or today)
    end = _next_period(start)

    collected = _collected_transactions(club, start, end).aggregate(total=Sum("amount"))["total"]
    rate_totals = _matured_dues_coverage(club, start, end, today).aggregate(due=Sum("amount"), covered=Sum("capped"))
    due_total = _quantize(rate_totals["due"])
    covered_total = _quantize(rate_totals["covered"])
    rate = _collection_rate(due_total, covered_total)

    paid, owed = _balance_aggregates(club=club, at_date=today)
    debts = Decimal("0.00")
    in_debt = 0
    member_ids = Membership.all_objects.filter(club=club, status__in=DASHBOARD_DEBT_STATUSES).values_list(
        "pk", flat=True
    )
    for membership_id in member_ids:
        balance = (paid.get(membership_id) or Decimal("0.00")) - (owed.get(membership_id) or Decimal("0.00"))
        if balance < 0:
            debts -= balance
            in_debt += 1

    return TreasuryDashboardSummary(
        period=start,
        currency=club_settings.currency,
        collected=_quantize(collected),
        matured_due_total=due_total,
        matured_due_covered=covered_total,
        collection_rate=rate,
        total_debts=_quantize(debts),
        members_in_debt=in_debt,
        available_cash=get_available_cash(club),
    )


# --- Assistance sociale (CDC 4.5.3) ----------------------------------------


def create_social_assistance_scale(
    *,
    club,
    created_by,
    event_type: str,
    amount: Any,
    processing_days: int,
    expense_category: ExpenseCategory,
    now: Optional[datetime] = None,
) -> SocialAssistanceScale:
    """Cree le bareme d'un evenement (Q11 provisoire : Pdt ou Tresorier).
    Aucun montant par defaut : le club le fixe lui-meme."""

    _require_service_club(club)
    _require_roles(
        created_by,
        club,
        ASSISTANCE_SCALE_MANAGERS,
        "Seuls le Président et le Trésorier peuvent définir le barème d'assistance sociale.",
    )
    if event_type not in SocialAssistanceEvent.values:
        raise TreasuryValidationError("Événement inconnu : naissance, mariage ou décès.")
    money = to_money(amount)
    if money <= 0:
        raise InvalidAmountError("Le montant du barème doit être strictement positif.")
    days = _clean_processing_days(processing_days)
    _check_scale_category(club, expense_category)
    scale = SocialAssistanceScale(
        club=club,
        event_type=event_type,
        amount=money,
        processing_days=days,
        expense_category=expense_category,
        created_at=now or timezone.now(),
        created_by=created_by,
    )
    with db_transaction.atomic():
        _save(scale)
        log_action(
            actor=created_by,
            club=club,
            action_type="treasury.social_assistance_scale.created",
            obj=scale,
            before=None,
            after=_scale_snapshot(scale),
        )
    return scale


def _clean_processing_days(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > 365:
        raise TreasuryValidationError("Le délai de traitement doit être un nombre de jours entre 1 et 365.")
    return value


def _check_scale_category(club, category: ExpenseCategory) -> None:
    if category.club_id != club.pk:
        raise TreasuryValidationError("La catégorie choisie n'appartient pas à ce club.")
    if category.status != ExpenseCategory.Status.ACTIVE:
        raise TreasuryValidationError("La catégorie choisie est archivée.")
    if not category.good_standing_only:
        raise TreasuryValidationError(
            "La catégorie d'un barème d'assistance sociale doit être « réservée aux membres en ordre »."
        )


def update_social_assistance_scale(*, scale: SocialAssistanceScale, updated_by, **changes) -> SocialAssistanceScale:
    """Modifie un bareme actif. Les demandes deja envoyees gardent le
    montant et le delai figes a leur envoi."""

    club = scale.club
    _require_service_club(club)
    _require_roles(
        updated_by,
        club,
        ASSISTANCE_SCALE_MANAGERS,
        "Seuls le Président et le Trésorier peuvent modifier le barème d'assistance sociale.",
    )
    if set(changes) - {"amount", "processing_days", "expense_category"}:
        raise TreasuryValidationError("Champ de modification inconnu pour ce barème.")
    with db_transaction.atomic():
        stored = SocialAssistanceScale.all_objects.select_for_update().get(pk=scale.pk, club=club)
        if stored.status == SocialAssistanceScale.Status.ARCHIVED:
            raise TreasuryValidationError("Un barème archivé ne peut plus être modifié.")
        before = _scale_snapshot(stored)
        if "amount" in changes:
            money = to_money(changes["amount"])
            if money <= 0:
                raise InvalidAmountError("Le montant du barème doit être strictement positif.")
            stored.amount = money
        if "processing_days" in changes:
            stored.processing_days = _clean_processing_days(changes["processing_days"])
        if "expense_category" in changes:
            _check_scale_category(club, changes["expense_category"])
            stored.expense_category = changes["expense_category"]
        _save(stored)
        log_action(
            actor=updated_by,
            club=club,
            action_type="treasury.social_assistance_scale.updated",
            obj=stored,
            before=before,
            after=_scale_snapshot(stored),
        )
    scale.refresh_from_db()
    return scale


def archive_social_assistance_scale(
    *, scale: SocialAssistanceScale, archived_by, now: Optional[datetime] = None
) -> SocialAssistanceScale:
    """Archive un bareme : plus aucune demande ne peut etre envoyee pour cet
    evenement tant qu'un nouveau bareme n'est pas defini."""

    club = scale.club
    _require_service_club(club)
    _require_roles(
        archived_by,
        club,
        ASSISTANCE_SCALE_MANAGERS,
        "Seuls le Président et le Trésorier peuvent archiver le barème d'assistance sociale.",
    )
    with db_transaction.atomic():
        stored = SocialAssistanceScale.all_objects.select_for_update().get(pk=scale.pk, club=club)
        if stored.status == SocialAssistanceScale.Status.ARCHIVED:
            raise TreasuryValidationError("Ce barème est déjà archivé.")
        before = _scale_snapshot(stored)
        stored.status = SocialAssistanceScale.Status.ARCHIVED
        stored.archived_at = now or timezone.now()
        stored.archived_by = archived_by
        _save(stored)
        log_action(
            actor=archived_by,
            club=club,
            action_type="treasury.social_assistance_scale.archived",
            obj=stored,
            before=before,
            after=_scale_snapshot(stored),
        )
    scale.refresh_from_db()
    return scale


class SocialAssistanceEligibility(NamedTuple):
    """Eligibilite a l'assistance sociale (CDC 4.5.3 ; 10.2 n° 33 et 37).

    - ``was_in_good_standing_at_event`` / ``amount_due_at_event`` : situation
      stricte a la date de l'evenement (paiements valides jusqu'a cette date) ;
    - ``eligible`` : en ordre a la date de l'evenement, un paiement valide
      depuis comptant comme regularisation (Q12, provisoire) ;
    - ``amount_to_regularize`` : montant a regler aujourd'hui pour que la
      demande puisse etre approuvee puis liberee ;
    - ``can_be_approved`` : aucune dette a la date de l'evenement ni
      aujourd'hui (10.2 n° 37 : jamais d'approbation d'un joueur toujours
      en dette).
    """

    eligible: bool
    was_in_good_standing_at_event: bool
    amount_due_at_event: Decimal
    amount_to_regularize: Decimal
    can_be_approved: bool
    currency: str
    reason: str


def _paid_total(club, membership_id: int, at_date: date) -> Decimal:
    total = (
        _validated_mandatory_transactions(club, at_date)
        .filter(membership_id=membership_id)
        .aggregate(total=Sum("amount"))["total"]
    )
    return total or Decimal("0.00")


def _owed_total(club, membership_id: int, at_date: date) -> Decimal:
    total = (
        _matured_mandatory_dues(club, at_date)
        .filter(membership_id=membership_id)
        .aggregate(total=Sum("amount"))["total"]
    )
    return total or Decimal("0.00")


def get_social_assistance_eligibility(
    membership: Membership, event_date: date, at_date: Optional[date] = None
) -> SocialAssistanceEligibility:
    """Calcule l'eligibilite (agregations SQL, rien n'est stocke)."""

    club = membership.club
    _require_service_club(club)
    event_date = _require_date(event_date, "La date de l'événement est invalide.")
    at_date = _balance_date(club, at_date)
    currency = get_club_currency(club)

    at_event = get_balance_summary(membership, at_date=event_date)
    paid_now = _paid_total(club, membership.pk, at_date)
    event_gap = max(_owed_total(club, membership.pk, event_date) - paid_now, Decimal("0.00"))
    current_due = max(_owed_total(club, membership.pk, at_date) - paid_now, Decimal("0.00"))
    amount_to_regularize = max(event_gap, current_due).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    eligible = event_gap <= 0
    can_be_approved = amount_to_regularize == 0

    if can_be_approved:
        reason = "Le joueur est en ordre : la demande est éligible."
    elif eligible:
        reason = (
            "Le joueur était en ordre à la date de l'événement mais est toujours en dette aujourd'hui : "
            f"{amount_to_regularize:.2f} {currency} à régulariser avant toute approbation."
        )
    else:
        reason = (
            "Le joueur n'était pas en ordre à la date de l'événement : "
            f"{amount_to_regularize:.2f} {currency} à régulariser pour devenir éligible."
        )
    return SocialAssistanceEligibility(
        eligible=eligible,
        was_in_good_standing_at_event=at_event.is_in_good_standing,
        amount_due_at_event=at_event.amount_due,
        amount_to_regularize=amount_to_regularize,
        can_be_approved=can_be_approved,
        currency=currency,
        reason=reason,
    )


class SocialAssistancePreview(NamedTuple):
    """Ce que la modale affiche avant l'envoi (CDC 4.5.3)."""

    scale: Optional[SocialAssistanceScale]
    eligibility: SocialAssistanceEligibility


def _active_scale(club, event_type: str) -> Optional[SocialAssistanceScale]:
    return (
        SocialAssistanceScale.all_objects.filter(
            club=club, event_type=event_type, status=SocialAssistanceScale.Status.ACTIVE
        )
        .select_related("expense_category")
        .first()
    )


def _check_event(club, event_type: str, event_date: date) -> date:
    if event_type not in SocialAssistanceEvent.values:
        raise TreasuryValidationError("Événement inconnu : naissance, mariage ou décès.")
    event_date = _require_date(event_date, "La date de l'événement est invalide.")
    if event_date > get_club_today(club):
        raise TreasuryValidationError("La date de l'événement ne peut pas être dans le futur.")
    return event_date


def get_social_assistance_preview(
    *, membership: Membership, event_type: str, event_date: date
) -> SocialAssistancePreview:
    """Eligibilite, montant du bareme et delai de traitement, avant l'envoi."""

    club = membership.club
    _require_service_club(club)
    event_date = _check_event(club, event_type, event_date)
    return SocialAssistancePreview(
        scale=_active_scale(club, event_type),
        eligibility=get_social_assistance_eligibility(membership, event_date),
    )


def submit_social_assistance_request(
    *,
    membership: Membership,
    submitted_by,
    event_type: str,
    event_date: date,
    description: str,
    attachment,
    now: Optional[datetime] = None,
) -> SocialAssistanceRequest:
    """Demande d'assistance sociale d'un joueur pour lui-meme (CDC 4.5.3 ;
    matrice 2.4 « P »). Envoyable meme si le joueur n'est pas eligible
    (10.2 n° 33) : l'eligibilite et le montant a regulariser sont figes a
    titre informatif. Notifie le President et le Vice-president (CDC 4.17)."""

    club = membership.club
    _require_service_club(club)
    if membership.user_id != getattr(submitted_by, "pk", None):
        raise TreasuryPermissionError(
            "Une demande d'assistance sociale ne peut être envoyée que par le joueur concerné."
        )
    current_status = Membership.all_objects.filter(pk=membership.pk).values_list("status", flat=True).first()
    if current_status != Membership.Status.ACTIVE:
        raise TreasuryValidationError("Seul un joueur inscrit au club peut demander une assistance sociale.")
    event_date = _check_event(club, event_type, event_date)
    cleaned = _require_reason(description, "La description est obligatoire.")
    if not attachment:
        raise TreasuryValidationError("La pièce justificative est obligatoire.")
    scale = _active_scale(club, event_type)
    if scale is None:
        raise TreasuryValidationError(
            "Le club n'a pas encore défini de barème pour cet événement : la demande ne peut pas être "
            "envoyée. Contactez le Président ou le Trésorier."
        )
    eligibility = get_social_assistance_eligibility(membership, event_date)
    now = now or timezone.now()
    rename_upload_to_real_type(attachment)
    request_obj = SocialAssistanceRequest(
        club=club,
        membership=membership,
        event_type=event_type,
        event_date=event_date,
        description=cleaned,
        attachment=attachment,
        scale=scale,
        planned_amount=scale.amount,
        currency=eligibility.currency,
        processing_days=scale.processing_days,
        eligible_at_submission=eligibility.eligible,
        amount_to_regularize=eligibility.amount_to_regularize,
        status=SocialAssistanceRequest.Status.SUBMITTED,
        submitted_at=now,
        submitted_by=submitted_by,
    )
    from apps.notifications.models import Notification

    with db_transaction.atomic():
        _save(request_obj)
        log_action(
            actor=submitted_by,
            club=club,
            action_type="treasury.social_assistance.submitted",
            obj=request_obj,
            before=None,
            after=_assistance_request_snapshot(request_obj),
        )
        _notify_roles(
            club,
            ASSISTANCE_PROCESSORS,
            event_type=Notification.EventType.SOCIAL_ASSISTANCE_REQUEST,
            message=(
                f"Demande d'assistance sociale de {_membership_name(membership)} "
                f"({request_obj.get_event_type_display().lower()} du {event_date:%d/%m/%Y})."
            ),
            target=request_obj,
            now=now,
        )
    return request_obj


def approve_social_assistance_request(
    *, request_obj: SocialAssistanceRequest, approved_by, now: Optional[datetime] = None
) -> Expense:
    """Approbation par le President ou le VP (CDC 4.5.3) : la demande devient
    une depense « En attente » de la categorie du bareme, au montant fige a
    l'envoi, qui suit ensuite le circuit 4.5.2 (liberation confirmee en modale ; Q13).

    Refusee si le joueur est toujours en dette (10.2 n° 37), y compris a la
    date de l'evenement non regularisee."""

    club = request_obj.club
    _require_service_club(club)
    _require_roles(
        approved_by,
        club,
        ASSISTANCE_PROCESSORS,
        "Seuls le Président et le Vice-président peuvent approuver une demande d'assistance sociale.",
    )
    stored = SocialAssistanceRequest.all_objects.select_related("scale__expense_category", "membership__user").get(
        pk=request_obj.pk, club=club
    )
    if stored.status != SocialAssistanceRequest.Status.SUBMITTED:
        raise TreasuryValidationError("Cette demande a déjà été traitée.")
    category = stored.scale.expense_category
    if category.status != ExpenseCategory.Status.ACTIVE:
        raise TreasuryValidationError(
            "La catégorie de dépense du barème est archivée : mettez à jour le barème avant d'approuver."
        )
    if not category.good_standing_only:
        raise TreasuryValidationError(
            "La catégorie du barème doit être « réservée aux membres en ordre »."
        )
    currency = get_club_currency(club)
    if stored.currency != currency:
        raise TreasuryValidationError("La devise de la demande ne correspond plus à celle du club.")
    _check_ceiling(category, stored.planned_amount, currency)
    now = now or timezone.now()
    today = _club_today(_club_settings(club), now)
    eligibility = get_social_assistance_eligibility(stored.membership, stored.event_date, at_date=today)
    if not eligibility.can_be_approved:
        raise TreasuryValidationError(f"Demande non approuvable : {eligibility.reason}")

    with db_transaction.atomic():
        locked = SocialAssistanceRequest.all_objects.select_for_update().get(pk=stored.pk)
        if locked.status != SocialAssistanceRequest.Status.SUBMITTED:
            raise TreasuryValidationError("Cette demande a déjà été traitée.")
        before = _assistance_request_snapshot(locked)
        locked.status = SocialAssistanceRequest.Status.APPROVED
        locked.decided_by = approved_by
        locked.decided_at = now
        _save(locked)
        log_action(
            actor=approved_by,
            club=club,
            action_type="treasury.social_assistance.approved",
            obj=locked,
            before=before,
            after=_assistance_request_snapshot(locked),
        )
        expense = _create_expense_unchecked(
            club=club,
            created_by=approved_by,
            category=category,
            amount=stored.planned_amount,
            beneficiary_name=_membership_name(stored.membership),
            beneficiary_membership=stored.membership,
            reason=(
                f"Assistance sociale — {stored.get_event_type_display().lower()} "
                f"du {stored.event_date:%d/%m/%Y}."
            ),
            expense_date=today,
            currency=currency,
            social_assistance_request=locked,
            now=now,
        )
    request_obj.refresh_from_db()
    return expense


def reject_social_assistance_request(
    *, request_obj: SocialAssistanceRequest, rejected_by, reason: str, now: Optional[datetime] = None
) -> SocialAssistanceRequest:
    """Refus motive d'une demande (President ou VP). Aucune ecriture financiere."""

    club = request_obj.club
    _require_service_club(club)
    _require_roles(
        rejected_by,
        club,
        ASSISTANCE_PROCESSORS,
        "Seuls le Président et le Vice-président peuvent refuser une demande d'assistance sociale.",
    )
    cleaned = _require_reason(reason, "Indiquez le motif du refus.")
    with db_transaction.atomic():
        locked = SocialAssistanceRequest.all_objects.select_for_update().get(pk=request_obj.pk, club=club)
        if locked.status != SocialAssistanceRequest.Status.SUBMITTED:
            raise TreasuryValidationError("Cette demande a déjà été traitée.")
        before = _assistance_request_snapshot(locked)
        locked.status = SocialAssistanceRequest.Status.REJECTED
        locked.decided_by = rejected_by
        locked.decided_at = now or timezone.now()
        locked.rejection_reason = cleaned
        _save(locked)
        log_action(
            actor=rejected_by,
            club=club,
            action_type="treasury.social_assistance.rejected",
            obj=locked,
            before=before,
            after=_assistance_request_snapshot(locked),
        )
    request_obj.refresh_from_db()
    return locked


# --- Capacites de l'utilisateur, calculees cote serveur ----------------------


def get_treasury_capabilities(user, club) -> dict[str, bool]:
    """Capacites tresorerie de ``user`` dans ``club``, deduites de ses roles
    actifs (matrice 2.4, cumul de roles). Remplace toute copie de la matrice
    cote interface."""

    roles = get_active_roles(user, club=club)
    is_member = Membership.all_objects.filter(
        club=club, user_id=getattr(user, "pk", None), status=Membership.Status.ACTIVE
    ).exists()
    return {
        "can_read": bool(roles & TREASURY_READERS),
        "can_write": bool(roles & TREASURY_MANAGERS),
        "can_record_payments": bool(roles & PAYMENT_RECORDERS),
        "can_read_expenses": bool(roles & EXPENSE_READERS),
        "can_manage_expense_categories": bool(roles & EXPENSE_CATEGORY_MANAGERS),
        "can_submit_expenses": bool(roles & EXPENSE_RECORDERS),
        "can_validate_expenses": bool(roles & EXPENSE_VALIDATORS),
        "can_derogate": bool(roles & PRESIDENT_ONLY),
        "can_upload_expense_receipts": bool(roles & EXPENSE_RECEIPT_UPLOADERS),
        "can_manage_assistance_scales": bool(roles & ASSISTANCE_SCALE_MANAGERS),
        "can_process_assistance_requests": bool(roles & ASSISTANCE_PROCESSORS),
        "can_request_assistance": is_member,
        # Valider / refuser une annulation de paiement (CDC 4.4.4) : memes
        # roles que :func:`approve_payment_reversal` et
        # :func:`reject_payment_reversal` (President seul).
        "can_decide_payment_reversal": bool(roles & REVERSAL_DECIDERS),
    }


# ---------------------------------------------------------------------------
# Traitements periodiques (cron, tache 2.3 ; CDC 4.4.2, 4.5.2, 5.3, 6.5)
# ---------------------------------------------------------------------------
#
# Appeles club par club par les commandes de gestion
# ``generate_monthly_dues``, ``verify_ledger_chain`` et
# ``mark_unjustified_expenses`` (hebergement cPanel : pas de processus
# permanent, tout traitement periodique est une commande cron).
#
# Aucune de ces taches n'a d'acteur reel : aucune entree `AuditLog` n'est
# ecrite (le journal exige un acteur reel, CDC 5.1), meme convention que
# ``apps.licences.services.process_licence_expirations`` -- point ouvert.
# Les donnees creees restent tracees par leurs propres horodatages
# (``Due.created_at``/``source``, ``LedgerChainState.frozen_at``/
# ``frozen_reason``, ``Expense.unjustified_at``).
#
# ``dry_run`` : tout le traitement est execute puis annule
# (``set_rollback``) -- le rapport est exactement celui d'une vraie
# execution, sans aucune ecriture (ni notification) conservee.
#
# Il n'existe volontairement **aucune** tache « passage en dette » : la
# dette est calculee a la lecture (:func:`_matured_mandatory_dues`).


@dataclass(frozen=True)
class MonthlyDuesRun:
    """Rapport de :func:`run_monthly_dues` pour un club."""

    period: Optional[date]
    created_count: int = 0
    # Montants dus de mois d'arrivee crees (proposition par defaut 10.2
    # n° 5, non tranchee : mois entier du), inclus dans ``created_count``.
    arrival_count: int = 0
    skipped_reason: str = ""

    @property
    def skipped(self) -> bool:
        return bool(self.skipped_reason)


def get_club_current_period(club, now: Optional[datetime] = None) -> date:
    """Premier jour du mois en cours **dans le fuseau du club**."""

    return _period_start(_club_today(_club_settings(club), now or timezone.now()))


def _dues_generation_blocked_reason(club) -> str:
    """Raison pour laquelle aucun montant du ne doit etre genere (ou "").

    Decision provisoire (la plus protectrice pour les joueurs, a confirmer) :
    on ne cree pas de nouvelle dette dans un club ou les joueurs ne peuvent
    pas payer -- licence suspendue ou resiliee (acces bloque, 10.2 n° 19),
    club en lecture seule (aucune ecriture possible), registre gele (aucun
    paiement ne peut etre scelle, CDC 5.3 « aucun joueur n'est penalise »).
    Le mois peut etre rattrape ensuite (option ``--period``)."""

    from apps.licences.models import Licence

    licence = Licence.objects.filter(club=club).order_by("-created_at").first()
    if licence is not None and licence.status in (Licence.Status.SUSPENDED, Licence.Status.TERMINATED):
        return "licence suspendue ou résiliée : aucun montant dû généré."
    if club.status == club.Status.READ_ONLY:
        return "club en lecture seule : aucun montant dû généré."
    state = LedgerChainState.all_objects.filter(club=club).first()
    if state is not None and state.is_frozen:
        return "écritures financières gelées : aucun montant dû généré tant que le gel n'est pas levé."
    return ""


def run_monthly_dues(
    club, *, period: Optional[date] = None, now: Optional[datetime] = None, dry_run: bool = False
) -> MonthlyDuesRun:
    """Genere les montants dus mensuels d'un club (CDC 4.4.2 : « chaque
    premier du mois, une tache automatique cree le montant du du mois pour
    chaque joueur actif, selon son type mensuel »).

    - ``period`` omis : mois en cours dans le **fuseau du club** (le 1er du
      mois local, meme s'il est encore le mois precedent en UTC). Une
      execution quotidienne (ou horaire) est donc sans risque : la
      generation est idempotente (aucun doublon, contrainte unique).
    - ``period`` fourni : rattrapage d'un mois manque ; un mois futur est
      refuse.
    - Joueurs concernes : ceux retenus par :func:`generate_dues_for_period`
      (adhesion « Inscrit », entree avant la fin du mois, pas sortie avant
      son debut, sans suspension de cotisations, rattachee au type si
      necessaire). Les joueurs « En attente » et partis sont exclus.
    - Joueur dans son **mois d'arrivee** : montant du du mois entier cree
      (proposition par defaut 10.2 n° 5, non tranchee par le client),
      echeance selon :func:`_arrival_due_date` (meme regle que les autres
      mois : le jour d'echeance, ou le meme delai a compter de l'arrivee si
      le joueur arrive apres ce jour ; tolerance du club en plus).
    - Repartition 4.4.3 recalculee pour les joueurs concernes ayant deja
      des paiements (grille jamais perimee).
    - Club bloque (voir :func:`_dues_generation_blocked_reason`) : ignore.

    Aucun joueur n'est bloque par cette generation : un montant du ne
    devient dette qu'apres ``due_date`` + tolerance
    (:func:`_matured_mandatory_dues`).
    """

    _require_service_club(club)
    now = now or timezone.now()
    settings_obj = ClubSettings.objects.filter(club_id=club.id).first()
    if settings_obj is None:
        return MonthlyDuesRun(
            period=period,
            skipped_reason="paramètres du club non configurés (devise, fuseau horaire) : aucun montant dû généré.",
        )
    current = _period_start(_club_today(settings_obj, now))
    target = _period_start(period) if period is not None else current
    if target > current:
        raise TreasuryValidationError(
            f"Impossible de générer les montants dus d'un mois futur ({target:%m/%Y}) : "
            f"le mois en cours du club est {current:%m/%Y}."
        )
    blocked = _dues_generation_blocked_reason(club)
    if blocked:
        return MonthlyDuesRun(period=target, skipped_reason=blocked)
    with db_transaction.atomic():
        created = _generate_dues(club=club, period=target, actor=None, arrival_due_date=None, now=now)
        if dry_run:
            db_transaction.set_rollback(True)
    return MonthlyDuesRun(
        period=target,
        created_count=len(created),
        arrival_count=sum(1 for due in created if due.source == Due.Source.ARRIVAL),
    )


@dataclass(frozen=True)
class LedgerVerificationOutcome:
    """Rapport de :func:`run_ledger_verification` pour un club.

    ``status`` : ``ok`` (chaine saine), ``broken`` (rupture : club gele),
    ``error`` (verification impossible, par exemple cle absente : aucun gel).
    """

    status: str
    result: ChainVerificationResult
    newly_frozen: bool = False
    alerts_sent: int = 0


def _alert_superusers_chain_broken(club, result: ChainVerificationResult, state, now: datetime) -> int:
    """Alerte les Superusers actifs (CDC 5.3 : « une rupture declenche une
    alerte au Superuser » ; 5.5). Aucune donnee personnelle dans le texte."""

    from django.contrib.auth import get_user_model

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    location = (
        f"à la séquence {result.first_broken_sequence}" if result.first_broken_sequence else "dans le registre"
    )
    message = (
        f"Rupture de la chaîne financière du club « {club.name} » détectée {location} : {result.details} "
        "Les écritures financières du club sont gelées jusqu'à analyse. Aucun joueur n'est pénalisé."
    )
    count = 0
    for user in get_user_model().objects.filter(is_superuser=True, is_active=True).order_by("pk"):
        create_notification(
            recipient=user,
            event_type=Notification.EventType.LEDGER_CHAIN_BROKEN,
            message=message,
            club=club,
            target=state,
            now=now,
        )
        count += 1
    return count


def run_ledger_verification(
    club, *, now: Optional[datetime] = None, dry_run: bool = False
) -> LedgerVerificationOutcome:
    """Verification quotidienne de la chaine d'un club (CDC 5.3, 6.5).

    Chaine saine : ne fait rien. Rupture : gel des ecritures du club
    (:func:`freeze_ledger`) et alerte aux Superusers, **une seule fois**
    (un club deja gele n'est ni regele ni realerte). Le gel ne touche
    **que** ``LedgerChainState`` : aucun montant du, paiement, allocation ni
    statut de joueur n'est modifie -- aucun joueur n'est penalise.
    Cle de chainage indisponible : ``error``, sans gel (incident de
    configuration, pas une preuve d'alteration)."""

    _require_service_club(club)
    now = now or timezone.now()
    result = verify_chain(club)
    if result.ok:
        return LedgerVerificationOutcome(status="ok", result=result)
    if result.key_unavailable:
        return LedgerVerificationOutcome(status="error", result=result)
    reason = (
        f"Rupture de chaîne détectée à la séquence {result.first_broken_sequence}"
        if result.first_broken_sequence
        else "Rupture de chaîne détectée"
    )
    with db_transaction.atomic():
        state = _lock_chain_state(club)
        newly_frozen = not state.is_frozen
        alerts = 0
        if newly_frozen:
            state = freeze_ledger(club=club, reason=reason, actor=None, now=now)
            alerts = _alert_superusers_chain_broken(club, result, state, now)
        if dry_run:
            db_transaction.set_rollback(True)
    return LedgerVerificationOutcome(status="broken", result=result, newly_frozen=newly_frozen, alerts_sent=alerts)


def run_unjustified_expenses(club, *, now: Optional[datetime] = None, dry_run: bool = False) -> list[Expense]:
    """Passage quotidien des depenses en « Non justifiee » (CDC 4.5.2) :
    enveloppe de :func:`mark_overdue_expenses_unjustified` (idempotente),
    sans acteur (voir l'en-tete de section). Club sans parametres : aucune
    depense n'a pu y etre saisie, rien a faire."""

    _require_service_club(club)
    if not ClubSettings.objects.filter(club_id=club.id).exists():
        return []
    with db_transaction.atomic():
        changed = mark_overdue_expenses_unjustified(club, now=now, actor=None)
        if dry_run:
            db_transaction.set_rollback(True)
    return changed


# ---------------------------------------------------------------------------
# Dette constatee a l'echeance (CDC 4.17, 4.4.2 ; 10.2 n° 4, n° 108)
# ---------------------------------------------------------------------------
#
# CDC 4.17 : « Dette constatee a l'echeance | Joueur, Tresorier, adjoint |
# In-app ». Le passage en dette reste **calcule** (aucun solde stocke,
# :func:`_matured_mandatory_dues`) ; cette section ne fait que constater,
# une fois, le jour ou une echeance devient dette, et prevenir.
#
# Positions provisoires (le CDC ne precise pas le declencheur exact ; les
# plus prudentes, signalees au compte rendu) :
# - declencheur : montant du d'un type obligatoire dont l'echeance + la
#   tolerance du club est depassee (meme regle que le solde), joueur « En
#   dette » (solde < 0) ET mois non couvert par la repartition 4.4.3 ;
# - une notification par echeance et par destinataire (joueur, Tresorier,
#   adjoint ; un joueur titulaire d'un de ces roles n'en recoit qu'une) ;
# - chaque echeance n'est evaluee qu'une fois (``DebtDueNotice``, unique en
#   base) : jamais deux notifications pour la meme echeance ;
# - fenetre de rattrapage de :data:`DEBT_NOTICE_LOOKBACK_DAYS` jours (cron
#   manque) ; au-dela, une echeance ancienne n'est jamais notifiee apres
#   coup (pas d'avalanche a la mise en service) ;
# - jamais pour un montant du de l'import historique CSV (CDC 4.4.8), ni
#   pour un joueur parti ;
# - club bloque (licence suspendue ou resiliee, lecture seule, registre
#   gele -- 10.2 n° 108 « aucune dette creee tant que les joueurs ne
#   peuvent pas payer ») : rien n'est constate ; les echeances restent
#   evaluables apres deblocage, dans la fenetre de rattrapage.

DEBT_NOTICE_LOOKBACK_DAYS = 7
DEBT_DUE_TITLE = "Dette constatée à l'échéance"
DEBT_NOTICE_MEMBERSHIP_STATUSES = (Membership.Status.ACTIVE, Membership.Status.PENDING)


@dataclass(frozen=True)
class DebtDueRun:
    """Rapport de :func:`run_debt_due_notifications` pour un club."""

    today: Optional[date]
    evaluated_count: int = 0
    notified_count: int = 0
    notifications_sent: int = 0
    skipped_reason: str = ""

    @property
    def skipped(self) -> bool:
        return bool(self.skipped_reason)


def _debt_due_messages(due: Due, amount_due: Decimal, currency: str) -> tuple[str, str]:
    """Textes du joueur et du bureau (montants au format du recu)."""

    month = french_month_label(due.period)
    due_amount = format_receipt_amount(due.amount, currency)
    remaining = format_receipt_amount(amount_due, currency)
    deadline = due.due_date.strftime("%d/%m/%Y")
    type_name = due.contribution_type.name
    player_message = (
        f"Votre cotisation « {type_name} » de {month} ({due_amount}) n'a pas été réglée à l'échéance "
        f"du {deadline}. Montant à régulariser : {remaining}."
    )
    board_message = (
        f"Dette constatée : {_membership_name(due.membership)}, cotisation « {type_name} » de {month} "
        f"({due_amount}) non réglée à l'échéance du {deadline}. Montant à régulariser : {remaining}."
    )
    return player_message, board_message


def run_debt_due_notifications(club, *, now: Optional[datetime] = None, dry_run: bool = False) -> DebtDueRun:
    """Constate les dettes nées a l'echeance et previent le joueur, le
    Tresorier et l'adjoint (CDC 4.17). Appelee par la commande cron
    ``notify_debt_due`` (quotidienne). **Idempotente** : une echeance deja
    traitee (``DebtDueNotice``) n'est jamais retraitee.

    Agregations SQL (solde : :func:`_balance_aggregates` ; repartition :
    une agregation), aucune boucle sur les transactions. Tout est ecrit dans
    une seule transaction : constats, notifications et journal (regle 6,
    acteur « Systeme ») -- si le journal echoue, rien n'est ecrit.
    """

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    _require_service_club(club)
    now = now or timezone.now()
    settings_obj = ClubSettings.objects.filter(club_id=club.id).first()
    if settings_obj is None:
        return DebtDueRun(
            today=None,
            skipped_reason="paramètres du club non configurés (devise, fuseau horaire) : aucune dette constatée.",
        )
    today = _club_today(settings_obj, now)
    blocked = _dues_generation_blocked_reason(club)
    if blocked:
        return DebtDueRun(
            today=today, skipped_reason=blocked.replace("aucun montant dû généré", "aucune dette constatée")
        )

    matured_before = today - timedelta(days=settings_obj.debt_tolerance_days)
    window_start = matured_before - timedelta(days=DEBT_NOTICE_LOOKBACK_DAYS)
    candidates = list(
        Due.all_objects.filter(
            club=club,
            contribution_type__nature=ContributionType.Nature.MANDATORY,
            due_date__lt=matured_before,
            due_date__gte=window_start,
            debt_notice__isnull=True,
            cancellation__isnull=True,
            membership__status__in=DEBT_NOTICE_MEMBERSHIP_STATUSES,
        )
        .exclude(source=Due.Source.IMPORT)
        # Decision du client du 17/11/2026 : les frais d'adhesion d'un joueur
        # « En attente » ne sont jamais une « dette constatee » (CDC 4.3 : il
        # paie d'abord son adhesion et reste « En attente »).
        .exclude(source=Due.Source.MEMBERSHIP_FEE, membership__status=Membership.Status.PENDING)
        .select_related("membership__user", "contribution_type")
        .order_by("due_date", "membership_id", "contribution_type_id", "pk")
    )
    if not candidates:
        return DebtDueRun(today=today)

    membership_ids = {due.membership_id for due in candidates}
    paid, owed = _balance_aggregates(club=club, at_date=today, membership_ids=membership_ids)
    allocated = {
        (row["membership_id"], row["contribution_type_id"], row["period"]): row["total"]
        for row in PaymentAllocation.all_objects.filter(
            club=club,
            membership_id__in=membership_ids,
            period__in={due.period for due in candidates},
        )
        .values("membership_id", "contribution_type_id", "period")
        .annotate(total=Sum("amount"))
    }
    board = _role_holder_users(club, PAYMENT_RECORDERS)
    currency = settings_obj.currency

    notified = sent = 0
    with db_transaction.atomic():
        system_actor = get_system_actor()
        for due in candidates:
            balance = (paid.get(due.membership_id) or _ZERO) - (owed.get(due.membership_id) or _ZERO)
            covered = (allocated.get((due.membership_id, due.contribution_type_id, due.period)) or _ZERO) >= due.amount
            in_debt = balance < 0 and not covered
            amount_due = to_money(-balance) if in_debt else None
            notice = DebtDueNotice(
                club=club,
                due=due,
                outcome=DebtDueNotice.Outcome.NOTIFIED if in_debt else DebtDueNotice.Outcome.NOT_IN_DEBT,
                amount_due=amount_due,
                processed_at=now,
            )
            _save(notice)
            if in_debt:
                player_message, board_message = _debt_due_messages(due, amount_due, currency)
                player_user = due.membership.user
                create_notification(
                    recipient=player_user,
                    event_type=Notification.EventType.DEBT_DUE,
                    title=DEBT_DUE_TITLE,
                    message=player_message,
                    club=club,
                    target=due,
                    now=now,
                )
                sent += 1
                for user in board:
                    if user.pk == player_user.pk:
                        continue  # deja prevenu en tant que joueur
                    create_notification(
                        recipient=user,
                        event_type=Notification.EventType.DEBT_DUE,
                        title=DEBT_DUE_TITLE,
                        message=board_message,
                        club=club,
                        target=due,
                        now=now,
                    )
                    sent += 1
                notified += 1
            log_action(
                actor=system_actor,
                club=club,
                action_type="treasury.debt_due.noticed",
                obj=notice,
                before=None,
                after={
                    "due_id": due.pk,
                    "membership_id": due.membership_id,
                    "contribution_type_id": due.contribution_type_id,
                    "period": due.period.isoformat(),
                    "outcome": notice.outcome,
                    "amount_due": _money_str(amount_due),
                },
            )
        if dry_run:
            db_transaction.set_rollback(True)
    return DebtDueRun(
        today=today, evaluated_count=len(candidates), notified_count=notified, notifications_sent=sent
    )


# ---------------------------------------------------------------------------
# Grille des cotisations (CDC 4.4.7 ; tache 2.6 ; fiche d'ecran
# docs/ecrans/tresorerie-grille-cotisations.md)
# ---------------------------------------------------------------------------
#
# La grille ne stocke rien : chaque cellule est **calculee a la lecture** a
# partir des memes donnees que le solde (montants dus `Due`, echeance +
# tolerance du club, :func:`_matured_mandatory_dues`) et de la projection
# de repartition 4.4.3 (`PaymentAllocation`, recalculee par
# :func:`_recompute_allocations` a chaque paiement ou annulation).
#
# Etats d'une cellule (``GridCell.state``) :
# - ``paid``     : montant affecte >= montant attendu du mois ;
# - ``partial``  : 0 < montant affecte < montant attendu ;
# - ``overdue``  : montant du echu (echeance + tolerance depassees), rien
#                  d'affecte -- **seul etat « rouge »** ;
# - ``upcoming`` : montant du non encore echu, ou mois courant/futur ou le
#                  joueur est concerne, rien d'affecte (« — ») ;
# - ``free``     : type libre, montant verse ce mois (0 = « — ») : une
#                  cotisation libre ne cree jamais de dette (CLAUDE.md
#                  regle n3), jamais d'etat ``overdue`` ;
# - ``not_due``  : rien n'est du ni affecte ce mois (joueur non rattache,
#                  suspendu, pas encore entre, mois passe sans montant du).
#
# ``GridCell.overdue_amount`` : part echue non couverte (montant du echu -
# montant affecte). Somme des cellules d'un type sur toutes les annees =
# part de ce type dans le « montant a regulariser » de
# :func:`get_balance_summary` (repartition 4.4.3 : les montants dus les plus
# anciens sont couverts en premier) -- teste.
#
# Lecture : Pdt, VP, Tres, Adj (matrice 2.4, ligne « Grille des cotisations
# (tous joueurs) » ; le 4.4.7 ne cite pas le VP : point ouvert de la fiche
# d'ecran, defaut applique = la matrice 2.4 fait foi).

GRID_READERS = TREASURY_READERS
# Import historique (CDC 4.4.8) : il enregistre des paiements valides, donc
# ligne « Enregistrement des paiements » de la matrice 2.4, colonne É
# (Tresorier et adjoint). Le 4.4.8 ne nomme aucun role : point ouvert.
CONTRIBUTION_IMPORTERS = PAYMENT_RECORDERS

GRID_STATE_PAID = "paid"
GRID_STATE_PARTIAL = "partial"
GRID_STATE_OVERDUE = "overdue"
GRID_STATE_UPCOMING = "upcoming"
GRID_STATE_FREE = "free"
GRID_STATE_NOT_DUE = "not_due"
GRID_STATE_LABELS = {
    GRID_STATE_PAID: "Payé",
    GRID_STATE_PARTIAL: "Partiel",
    GRID_STATE_OVERDUE: "Impayé échu",
    GRID_STATE_UPCOMING: "À venir",
    GRID_STATE_FREE: "Libre",
    GRID_STATE_NOT_DUE: "Non dû",
}
GRID_ORDERINGS = ("name", "-name", "total", "-total")
GRID_MIN_YEAR = 2000

FRENCH_MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)
FRENCH_MONTHS_SHORT = (
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
)

_GRID_READ_DENIED = "Réservé au Président, au Vice-président, au Trésorier et à son adjoint."
_ZERO = Decimal("0.00")


@dataclass(frozen=True)
class GridCell:
    """Cellule calculee (jamais stockee) : un mois d'un joueur pour un type."""

    period: date
    amount_due: Optional[Decimal]
    allocated: Decimal
    state: str
    overdue_amount: Decimal


@dataclass(frozen=True)
class GridRow:
    membership: Membership
    cells: tuple
    total: Decimal
    overdue_amount: Decimal

    @property
    def has_unpaid(self) -> bool:
        return self.overdue_amount > 0


@dataclass(frozen=True)
class ContributionGrid:
    contribution_type: ContributionType
    year: int
    currency: str
    today: date
    rows: tuple

    @property
    def periods(self) -> list[date]:
        return _year_periods(self.year)


@dataclass(frozen=True)
class GridMonthPayment:
    """Paiement ayant alimente un mois (modale « Detail du mois »)."""

    payment: Payment
    allocated: Decimal
    first_period: date
    last_period: date


@dataclass(frozen=True)
class GridMonthDetail:
    contribution_type: ContributionType
    membership: Membership
    currency: str
    cell: GridCell
    payments: tuple


def french_month_label(period: date, *, short: bool = False) -> str:
    """« mars 2026 » / « mars » (libelle affiche, CLAUDE.md regle n20)."""

    names = FRENCH_MONTHS_SHORT if short else FRENCH_MONTHS
    return f"{names[period.month - 1]} {period.year}"


def _fold(text: str) -> str:
    """Texte replie pour une comparaison insensible a la casse et aux
    accents, **calculee en Python** (identique sous SQLite et MySQL, dont
    les collations different -- CLAUDE.md §9)."""

    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.casefold().split())


def _check_year(year: Any, *, max_year: int) -> int:
    if isinstance(year, bool) or not isinstance(year, int):
        try:
            year = int(str(year).strip())
        except (TypeError, ValueError):
            raise TreasuryValidationError("Année invalide.") from None
    if year < GRID_MIN_YEAR or year > max_year:
        raise TreasuryValidationError(f"Année invalide : choisissez une année entre {GRID_MIN_YEAR} et {max_year}.")
    return year


def year_periods(year: int) -> list[date]:
    """Les douze premiers jours de mois d'une annee (colonnes de la grille)."""

    return [date(year, month, 1) for month in range(1, 13)]


_year_periods = year_periods


def _period_end(period: date) -> date:
    return _next_period(period) - timedelta(days=1)


def _type_rates(ctype: ContributionType) -> list[tuple[date, Decimal]]:
    return list(
        ContributionTypeRate.all_objects.filter(club_id=ctype.club_id, contribution_type_id=ctype.pk)
        .order_by("effective_from")
        .values_list("effective_from", "amount")
    )


def _rate_in(rates: list[tuple[date, Decimal]], period: date, *, extend_backwards: bool = False) -> Optional[Decimal]:
    """Tarif applicable a ``period`` (meme regle que :func:`_rate_for_period`).

    ``extend_backwards`` (import historique uniquement) : pour un mois
    anterieur au premier tarif connu du type (type cree dans Vesta apres les
    mois importes), le premier tarif connu s'applique -- decision
    provisoire, signalee dans l'apercu et le compte rendu."""

    current = None
    for effective_from, amount in rates:
        if effective_from <= period:
            current = amount
        else:
            break
    if current is None and extend_backwards and rates:
        return rates[0][1]
    return current


def _concern_map(*, club, ctype: ContributionType, memberships: list, periods: list[date]) -> set[tuple[int, date]]:
    """Couples (adhesion, mois) ou le joueur est concerne par ``ctype`` :
    meme regle que la capacite du moteur de repartition
    (:func:`_covered_by_assignment` + suspension, :func:`_plan_allocations`),
    calculee en deux requetes quel que soit le nombre de joueurs."""

    if not memberships or not periods:
        return set()
    first, last_end = periods[0], _period_end(periods[-1])
    ids = {membership.pk for membership in memberships}
    suspensions: dict[int, list[tuple[date, Optional[date]]]] = {}
    for membership_id, starts_on, ends_on in (
        ContributionSuspension.all_objects.filter(club=club, starts_on__lte=last_end)
        .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=first))
        .values_list("membership_id", "starts_on", "ends_on")
    ):
        if membership_id in ids:
            suspensions.setdefault(membership_id, []).append((starts_on, ends_on))
    assignments: dict[int, list[tuple[date, Optional[date]]]] = {}
    if ctype.scope != ContributionType.Scope.ALL:
        for membership_id, starts_on, ends_on in (
            ContributionAssignment.all_objects.filter(club=club, contribution_type=ctype, starts_on__lte=periods[-1])
            .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=first))
            .values_list("membership_id", "starts_on", "ends_on")
        ):
            if membership_id in ids:
                assignments.setdefault(membership_id, []).append((starts_on, ends_on))
    concerned: set[tuple[int, date]] = set()
    for membership in memberships:
        for period in periods:
            end = _period_end(period)
            if ctype.scope == ContributionType.Scope.ALL:
                covered = membership.joined_on <= end and (membership.left_on is None or membership.left_on >= period)
            else:
                covered = any(
                    starts_on <= period and (ends_on is None or ends_on >= period)
                    for starts_on, ends_on in assignments.get(membership.pk, ())
                )
            if not covered:
                continue
            suspended = any(
                starts_on <= end and (ends_on is None or ends_on >= period)
                for starts_on, ends_on in suspensions.get(membership.pk, ())
            )
            if not suspended:
                concerned.add((membership.pk, period))
    return concerned


def _grid_cell(
    *, ctype: ContributionType, period: date, dues: list, allocated: Decimal, concerned: bool,
    rate: Optional[Decimal], today: date, tolerance: int,
) -> GridCell:
    """Etat d'une cellule (voir l'en-tete de section). ``dues`` : liste de
    ``(montant, echeance)`` du mois ; regle d'echeance identique a
    :func:`_matured_mandatory_dues` (``echeance < date - tolerance``)."""

    allocated = allocated or _ZERO
    if ctype.nature == ContributionType.Nature.FREE:
        return GridCell(period, None, allocated, GRID_STATE_FREE, _ZERO)
    if dues:
        due_total = sum((amount for amount, _ in dues), _ZERO)
        threshold = today - timedelta(days=tolerance)
        matured = sum((amount for amount, due_date in dues if due_date < threshold), _ZERO)
        if allocated >= due_total:
            state = GRID_STATE_PAID
        elif allocated > 0:
            state = GRID_STATE_PARTIAL
        elif matured > 0:
            state = GRID_STATE_OVERDUE
        else:
            state = GRID_STATE_UPCOMING
        return GridCell(period, due_total, allocated, state, max(matured - allocated, _ZERO))
    expected = rate if concerned else None
    if allocated > 0:
        state = GRID_STATE_PARTIAL if expected is not None and allocated < expected else GRID_STATE_PAID
    elif expected is not None and period >= _period_start(today):
        state = GRID_STATE_UPCOMING
    else:
        state = GRID_STATE_NOT_DUE
    return GridCell(period, expected, allocated, state, _ZERO)


def _compose_grid_row(
    *, ctype: ContributionType, membership: Membership, periods: list[date], dues_by_period: dict,
    allocated_by_period: dict, concerned: set, rates: list, today: date, tolerance: int,
) -> GridRow:
    cells = tuple(
        _grid_cell(
            ctype=ctype,
            period=period,
            dues=dues_by_period.get(period, []),
            allocated=allocated_by_period.get(period, _ZERO),
            concerned=(membership.pk, period) in concerned,
            rate=_rate_in(rates, period),
            today=today,
            tolerance=tolerance,
        )
        for period in periods
    )
    return GridRow(
        membership=membership,
        cells=cells,
        total=sum((cell.allocated for cell in cells), _ZERO),
        overdue_amount=sum((cell.overdue_amount for cell in cells), _ZERO),
    )


def _grid_memberships(*, club, ctype: ContributionType, periods: list[date]) -> list[Membership]:
    """Lignes de la grille : « les joueurs rattaches » (CDC 4.4.7).

    - type « Tous » : joueurs Inscrits ou partis presents au club pendant
      l'annee (les « En attente » n'ont pas de montant du, CDC 4.4.2) ;
    - type « liste » / « rattaches » : rattachement couvrant l'annee ;
    - dans tous les cas, tout joueur ayant un montant du ou un montant
      affecte ce type-la cette annee (aucun argent n'est jamais masque).
    Sous-requetes SQL (aucune liste d'identifiants en parametre)."""

    return list(
        Membership.all_objects.filter(club=club)
        .filter(_grid_membership_condition(club=club, ctype=ctype, periods=periods))
        .select_related("user")
        .order_by("pk")
    )


def _grid_membership_condition(*, club, ctype: ContributionType, periods: list[date]) -> Q:
    """Condition SQL « ce joueur est une ligne de la grille de ``ctype`` »
    (voir :func:`_grid_memberships`) ; partagee avec la ligne personnelle
    du joueur (:func:`build_own_contribution_lines`) pour que les deux
    vues affichent exactement les memes donnees."""

    first, last_end = periods[0], _period_end(periods[-1])
    with_data = Q(
        pk__in=Due.all_objects.filter(
            club=club, contribution_type=ctype, period__gte=first, period__lte=last_end, cancellation__isnull=True
        ).values("membership_id")
    ) | Q(
        pk__in=PaymentAllocation.all_objects.filter(
            club=club, contribution_type=ctype, period__gte=first, period__lte=last_end
        ).values("membership_id")
    )
    if ctype.scope == ContributionType.Scope.ALL:
        concerned = Q(
            status__in=(Membership.Status.ACTIVE, Membership.Status.DEPARTED), joined_on__lte=last_end
        ) & (Q(left_on__isnull=True) | Q(left_on__gte=first))
    else:
        concerned = Q(
            pk__in=ContributionAssignment.all_objects.filter(
                club=club, contribution_type=ctype, starts_on__lte=last_end
            )
            .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=first))
            .values("membership_id")
        )
    return concerned | with_data


def build_contribution_grid(
    *, contribution_type: ContributionType, year: Any, requested_by, today: Optional[date] = None,
    membership: Optional[Membership] = None,
) -> ContributionGrid:
    """Grille d'un type pour une annee (CDC 4.4.7) : une ligne par joueur
    rattache, douze cellules calculees, total annuel.

    Nombre de requetes SQL constant quel que soit le nombre de joueurs
    (agregations ``Sum`` groupees par joueur et par mois ; aucune boucle sur
    les transactions). ``membership`` : une seule ligne (modale « Detail du
    mois »). Pdt, VP, Tres, Adj uniquement (matrice 2.4)."""

    club = contribution_type.club
    _require_service_club(club)
    _require_roles(requested_by, club, GRID_READERS, _GRID_READ_DENIED)
    return _build_grid(contribution_type=contribution_type, year=year, today=today, membership=membership)


def _build_grid(
    *, contribution_type: ContributionType, year: Any, today: Optional[date] = None,
    membership: Optional[Membership] = None, club_settings: Optional[ClubSettings] = None,
) -> ContributionGrid:
    """Calcul de la grille **sans controle d'acces** : n'appeler qu'apres
    avoir verifie le droit de lecture (bureau : :func:`build_contribution_grid` ;
    joueur pour lui-meme : :func:`build_own_contribution_lines`)."""

    ctype = contribution_type
    club = ctype.club
    club_settings = club_settings or _club_settings(club)
    today = today or _club_today(club_settings, timezone.now())
    year = _check_year(year, max_year=today.year + 1)
    periods = _year_periods(year)
    first, last_end = periods[0], _period_end(periods[-1])

    if membership is not None:
        if membership.club_id != club.pk:
            raise TenantMismatchError("Le joueur n'appartient pas au club du type de cotisation.")
        memberships = [membership]
    else:
        memberships = _grid_memberships(club=club, ctype=ctype, periods=periods)

    dues_qs = Due.all_objects.filter(
        club=club, contribution_type=ctype, period__gte=first, period__lte=last_end, cancellation__isnull=True
    )
    alloc_qs = PaymentAllocation.all_objects.filter(
        club=club, contribution_type=ctype, period__gte=first, period__lte=last_end
    )
    if membership is not None:
        dues_qs = dues_qs.filter(membership=membership)
        alloc_qs = alloc_qs.filter(membership=membership)
    dues: dict[int, dict[date, list]] = {}
    for membership_id, period, amount, due_date in dues_qs.values_list("membership_id", "period", "amount", "due_date"):
        dues.setdefault(membership_id, {}).setdefault(_period_start(period), []).append((amount, due_date))
    allocated: dict[int, dict[date, Decimal]] = {}
    for membership_id, period, total in (
        alloc_qs.values("membership_id", "period").annotate(total=Sum("amount")).values_list("membership_id", "period", "total")
    ):
        bucket = allocated.setdefault(membership_id, {})
        key = _period_start(period)
        bucket[key] = bucket.get(key, _ZERO) + total

    concerned = _concern_map(club=club, ctype=ctype, memberships=memberships, periods=periods)
    rates = _type_rates(ctype)
    tolerance = club_settings.debt_tolerance_days
    rows = tuple(
        _compose_grid_row(
            ctype=ctype,
            membership=item,
            periods=periods,
            dues_by_period=dues.get(item.pk, {}),
            allocated_by_period=allocated.get(item.pk, {}),
            concerned=concerned,
            rates=rates,
            today=today,
            tolerance=tolerance,
        )
        for item in memberships
    )
    return ContributionGrid(
        contribution_type=ctype, year=year, currency=club_settings.currency, today=today, rows=rows
    )


def _membership_sort_key(membership: Membership) -> tuple:
    user = membership.user
    return (_fold(user.last_name), _fold(user.first_name), membership.pk)


def filter_grid_rows(
    grid: ContributionGrid, *, query: str = "", unpaid_only: bool = False, ordering: str = "name"
) -> list[GridRow]:
    """Recherche par nom (ou numero de maillot), filtre « Avec impayes » et
    tri (nom par defaut, ou total) -- en Python sur les lignes deja
    calculees, donc identique sous SQLite et MySQL."""

    if ordering not in GRID_ORDERINGS:
        raise TreasuryValidationError("Tri inconnu : nom ou total.")
    cleaned = _fold(query)
    if len(cleaned) > CASH_SEARCH_MAX_QUERY_LENGTH:
        raise TreasuryValidationError("Recherche trop longue.")
    rows = list(grid.rows)
    if cleaned:
        terms = cleaned.split(" ")

        def matches(row: GridRow) -> bool:
            user = row.membership.user
            haystack = _fold(f"{user.first_name} {user.last_name}")
            if cleaned.isdigit() and row.membership.jersey_number == int(cleaned):
                return True
            return all(term in haystack for term in terms)

        rows = [row for row in rows if matches(row)]
    if unpaid_only:
        rows = [row for row in rows if row.has_unpaid]
    rows.sort(key=lambda row: _membership_sort_key(row.membership))
    if ordering == "-name":
        rows.reverse()
    elif ordering in ("total", "-total"):
        rows.sort(key=lambda row: row.total, reverse=ordering == "-total")
    return rows


def get_balance_summaries(club, membership_ids: Iterable[int], at_date: Optional[date] = None) -> dict[int, BalanceSummary]:
    """Situation (solde, statut, raison) de plusieurs joueurs en deux
    agregations SQL -- meme formule que :func:`get_balance_summary`."""

    _require_service_club(club)
    ids = list(membership_ids)
    if not ids:
        return {}
    at_date = _balance_date(club, at_date)
    currency = _club_settings(club).currency
    paid, owed = _balance_aggregates(club=club, at_date=at_date, membership_ids=ids)
    return {
        membership_id: _summary_from_balance(
            (paid.get(membership_id) or _ZERO) - (owed.get(membership_id) or _ZERO), currency
        )
        for membership_id in ids
    }


def get_grid_contribution_types(club) -> tuple[list[ContributionType], list[ContributionType], Optional[int]]:
    """Types actifs, types archives (puces de l'ecran) et type par defaut :
    « le premier type mensuel obligatoire » (fiche d'ecran §3.1), dans
    l'ordre d'affichage (nom)."""

    _require_service_club(club)
    types = list(ContributionType.all_objects.filter(club=club).order_by("name", "pk"))
    active = [ctype for ctype in types if ctype.status == ContributionType.Status.ACTIVE]
    archived = [ctype for ctype in types if ctype.status == ContributionType.Status.ARCHIVED]
    default = next(
        (
            ctype.pk
            for ctype in active
            if ctype.nature == ContributionType.Nature.MANDATORY
            and ctype.periodicity == ContributionType.Periodicity.MONTHLY
        ),
        active[0].pk if active else None,
    )
    return active, archived, default


def get_grid_month_detail(
    *, contribution_type: ContributionType, membership: Membership, year: Any, month: Any, requested_by,
    today: Optional[date] = None,
) -> GridMonthDetail:
    """Modale « Detail du mois » (CDC 4.4.7 : « Clic sur une cellule : detail
    des paiements du mois ») : cellule calculee comme dans la grille et
    paiements ayant alimente ce mois (part affectee, etalement 4.4.3)."""

    month = _check_month(month)
    grid = build_contribution_grid(
        contribution_type=contribution_type, year=year, requested_by=requested_by, today=today, membership=membership
    )
    return _month_detail_from_grid(grid, membership=membership, month=month)


def _check_month(month: Any) -> int:
    try:
        month = int(month)
    except (TypeError, ValueError):
        raise TreasuryValidationError("Mois invalide.") from None
    if month < 1 or month > 12:
        raise TreasuryValidationError("Mois invalide : choisissez un mois entre 1 et 12.")
    return month


def _month_detail_from_grid(grid: ContributionGrid, *, membership: Membership, month: int) -> GridMonthDetail:
    """Detail d'un mois a partir d'une grille d'une seule ligne deja
    calculee (acces deja verifie par l'appelant)."""

    contribution_type = grid.contribution_type
    cell = grid.rows[0].cells[month - 1]
    period = cell.period
    club = contribution_type.club
    allocations = list(
        PaymentAllocation.all_objects.filter(
            club=club,
            membership=membership,
            contribution_type=contribution_type,
            period__gte=period,
            period__lt=_next_period(period),
        )
        .select_related("payment")
        .order_by("payment__paid_on", "payment_id")
    )
    payment_ids = sorted({allocation.payment_id for allocation in allocations})
    spans = {
        row["payment_id"]: (row["first"], row["last"])
        for row in PaymentAllocation.all_objects.filter(club=club, payment_id__in=payment_ids)
        .values("payment_id")
        .annotate(first=Min("period"), last=Max("period"))
    }
    per_payment: dict[int, GridMonthPayment] = {}
    for allocation in allocations:
        existing = per_payment.get(allocation.payment_id)
        first_period, last_period = spans.get(allocation.payment_id, (period, period))
        per_payment[allocation.payment_id] = GridMonthPayment(
            payment=allocation.payment,
            allocated=(existing.allocated if existing else _ZERO) + allocation.amount,
            first_period=first_period,
            last_period=last_period,
        )
    return GridMonthDetail(
        contribution_type=contribution_type,
        membership=membership,
        currency=grid.currency,
        cell=cell,
        payments=tuple(per_payment.values()),
    )


# ---------------------------------------------------------------------------
# Donnees financieres du joueur connecte, pour lui seul (page « Mon profil »,
# fiche docs/ecrans/comptes-mon-profil.md §3.2 ; CDC 4.4.7 « Chaque joueur
# voit sa propre ligne dans son profil » ; matrice 2.4 colonne « P »).
# Lecture seule. Aucune regle nouvelle : memes calculs que la grille du
# bureau (:func:`_build_grid`) et que le solde (:func:`get_balance_summary`).
# ---------------------------------------------------------------------------

_OWN_DATA_DENIED = "Vous ne pouvez consulter que vos propres données financières."
OWN_PAYMENT_STATUS_FILTERS = {
    "validated": ~approved_reversal_exists(),
    "cancelled": approved_reversal_exists(),
}
OWN_PAYMENT_DEFAULT_STATUSES = ("validated",)


class OwnContributionTypeNotFoundError(TreasuryError):
    """Le type demande ne figure pas dans la ligne du joueur pour l'annee."""


@dataclass(frozen=True)
class OwnContributionLine:
    contribution_type: ContributionType
    row: GridRow


@dataclass(frozen=True)
class OwnContributionLines:
    membership: Membership
    year: int
    currency: str
    today: date
    lines: tuple
    summary: BalanceSummary

    @property
    def periods(self) -> list[date]:
        return _year_periods(self.year)


def _require_own_membership(membership: Membership, requested_by) -> None:
    """Seul le titulaire de l'adhesion lit ces donnees (jamais un tiers,
    bureau compris : le bureau passe par la grille et le tableau de bord)."""

    if requested_by is None or membership.user_id != getattr(requested_by, "pk", None):
        raise TreasuryPermissionError(_OWN_DATA_DENIED)


def _own_grid_types(membership: Membership, periods: list[date]) -> list[ContributionType]:
    """Types dont le joueur est une ligne de la grille du bureau pour ces
    mois (meme condition que :func:`_grid_memberships`) : types actifs
    puis archives, par nom. Une requete d'existence par type du club."""

    club = membership.club
    types = list(ContributionType.all_objects.filter(club=club).order_by("name", "pk"))
    own = [
        ctype
        for ctype in types
        if Membership.all_objects.filter(club=club, pk=membership.pk)
        .filter(_grid_membership_condition(club=club, ctype=ctype, periods=periods))
        .exists()
    ]
    own.sort(key=lambda ctype: ctype.status != ContributionType.Status.ACTIVE)
    return own


def build_own_contribution_lines(
    *, membership: Membership, year: Any, requested_by, today: Optional[date] = None
) -> OwnContributionLines:
    """« Mes cotisations {annee} » : la ligne du joueur dans la grille de
    chaque type qui le concerne (cellules identiques a celles de la grille
    du bureau) et sa situation calculee (solde jamais stocke)."""

    club = membership.club
    _require_service_club(club)
    _require_own_membership(membership, requested_by)
    return _contribution_lines(membership=membership, year=year, today=today)


def _contribution_lines(*, membership: Membership, year: Any, today: Optional[date] = None) -> OwnContributionLines:
    """Lignes de grille d'un joueur, **sans controle d'acces** : n'appeler
    qu'apres verification du droit de lecture (joueur pour lui-meme :
    :func:`build_own_contribution_lines` ; bureau :
    :func:`build_member_contribution_lines`)."""

    club = membership.club
    club_settings = _club_settings(club)
    today = today or _club_today(club_settings, timezone.now())
    year = _check_year(year, max_year=today.year + 1)
    lines = tuple(
        OwnContributionLine(
            contribution_type=ctype,
            row=_build_grid(
                contribution_type=ctype, year=year, today=today, membership=membership, club_settings=club_settings
            ).rows[0],
        )
        for ctype in _own_grid_types(membership, _year_periods(year))
    )
    return OwnContributionLines(
        membership=membership,
        year=year,
        currency=club_settings.currency,
        today=today,
        lines=lines,
        summary=get_balance_summary(membership, at_date=today),
    )


def get_own_grid_month_detail(
    *, membership: Membership, contribution_type: ContributionType, year: Any, month: Any, requested_by,
    today: Optional[date] = None,
) -> GridMonthDetail:
    """Modale « Detail du mois » du profil : meme contenu que celle de la
    grille du bureau, pour un type de la ligne du joueur uniquement
    (:class:`OwnContributionTypeNotFoundError` sinon)."""

    club = membership.club
    _require_service_club(club)
    _require_own_membership(membership, requested_by)
    if contribution_type.club_id != club.pk:
        raise OwnContributionTypeNotFoundError("Type de cotisation introuvable dans ce club.")
    month = _check_month(month)
    club_settings = _club_settings(club)
    today = today or _club_today(club_settings, timezone.now())
    year = _check_year(year, max_year=today.year + 1)
    if contribution_type.pk not in {ctype.pk for ctype in _own_grid_types(membership, _year_periods(year))}:
        raise OwnContributionTypeNotFoundError("Ce type de cotisation ne vous concerne pas pour cette année.")
    grid = _build_grid(
        contribution_type=contribution_type, year=year, today=today, membership=membership, club_settings=club_settings
    )
    return _month_detail_from_grid(grid, membership=membership, month=month)


def own_payments_queryset(*, membership: Membership, requested_by, statuses: Iterable[str] = OWN_PAYMENT_DEFAULT_STATUSES):
    """« Mes paiements » : paiements **valides** du joueur (transaction
    ``succeeded``), toutes sources confondues (saisie Tresorier, caisse,
    declaration validee, import, passerelle). ``statuses`` : ``validated``
    (non annules, defaut) et/ou ``cancelled`` (annulation approuvee). Les
    declarations a valider ou refusees restent servies par la liste des
    declarations (``payment-declarations/?mine=1``). Restreint a
    l'adhesion du joueur dans son club (aucune donnee d'un autre joueur ni
    d'un autre club)."""

    club = membership.club
    _require_service_club(club)
    _require_own_membership(membership, requested_by)
    keys = list(statuses) or list(OWN_PAYMENT_DEFAULT_STATUSES)
    if any(key not in OWN_PAYMENT_STATUS_FILTERS for key in keys):
        raise TreasuryValidationError("État de paiement inconnu.")
    condition = Q()
    for index, key in enumerate(keys):
        condition = OWN_PAYMENT_STATUS_FILTERS[key] if index == 0 else condition | OWN_PAYMENT_STATUS_FILTERS[key]
    return (
        Payment.all_objects.filter(club=club, membership=membership, transaction__status=Transaction.Status.SUCCEEDED)
        .filter(condition)
        .select_related("contribution_type", "transaction")
        .prefetch_related("allocations", reversal_prefetch())
        .order_by("-paid_on", "-submitted_at", "-pk")
    )


_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(text: str) -> str:
    """Neutralise une cellule qu'un tableur interpreterait comme une formule
    (injection CSV, CDC 7.6)."""

    text = text or ""
    return "'" + text if text.startswith(_CSV_FORMULA_PREFIXES) else text


def export_contribution_grid_csv(grid: ContributionGrid, rows: Optional[list[GridRow]] = None) -> tuple[str, bytes]:
    """Export CSV de la grille affichee (CDC 4.4.7) : joueurs en lignes,
    mois en colonnes, puis total. Cellule = montant affecte ; « 0.00 » pour
    un impaye echu ; vide sinon (« — » a l'ecran).

    Nom de fichier ``grille-{type}-{annee}.csv`` genere a partir du nom du
    type (fiche d'ecran §4.2) -- jamais de nom de club. Separateur « ; »
    et BOM UTF-8 (ouverture directe dans un tableur configure en
    francais) ; montants a point decimal, 2 decimales."""

    ctype = grid.contribution_type
    rows = list(grid.rows) if rows is None else rows
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        ["Joueur", "N°"]
        + [french_month_label(period, short=True) for period in grid.periods]
        + [f"Total ({grid.currency})"]
    )
    for row in rows:
        user = row.membership.user
        values = []
        for cell in row.cells:
            if cell.allocated > 0:
                values.append(_money_str(cell.allocated))
            elif cell.state == GRID_STATE_OVERDUE:
                values.append("0.00")
            else:
                values.append("")
        writer.writerow(
            [
                _csv_safe(f"{user.last_name} {user.first_name}".strip()),
                row.membership.jersey_number if row.membership.jersey_number is not None else "",
            ]
            + values
            + [_money_str(row.total)]
        )
    slug = slugify(ctype.name) or f"type-{ctype.pk}"
    filename = f"grille-{slug}-{grid.year}.csv"
    return filename, ("﻿" + buffer.getvalue()).encode("utf-8")


# ---------------------------------------------------------------------------
# Import des cotisations historiques CSV (CDC 4.4.8 ; tache 2.6)
# ---------------------------------------------------------------------------
#
# Entree : type de cotisation + annee + fichier CSV (une ligne par joueur,
# une colonne par mois, CDC 4.4.8). Deux temps, comme la modale : un
# APERCU (:func:`preview_contribution_import`, aucune ecriture) puis
# l'IMPORT DEFINITIF (:func:`import_contributions`), qui enregistre des
# paiements valides exactement comme la modale « Enregistrer un paiement »
# (`Payment` + `Transaction` scellee dans la chaine, numero de recu,
# repartition 4.4.3 par le meme moteur, journal), avec la source
# ``csv_import``, le mode « Import historique », la reference
# « Import historique MM/AAAA » et le lot d'import (`ImportBatch`).
#
# Format du fichier
# - Encodage UTF-8 (comme l'import des joueurs), separateur « , » ou « ; ».
# - Ligne d'en-tete cherchee dans les 5 premieres lignes (un titre au-dessus
#   est tolere). Colonnes d'identite : « email » (ou « e-mail »,
#   « courriel ») et/ou « nom » (ou « noms », « joueur »), eventuellement
#   « prenom ». Colonnes de mois : « janv. », « Jan-26 », « aout 2026 »,
#   « 01/2026 », « 2026-01 », « 1 »... Toute autre colonne (« N° »,
#   « Total ») est ignoree et signalee. Un mois d'en-tete portant une autre
#   annee que l'annee choisie bloque le fichier.
# - Cellule : vide, « - » ou « 0 » = rien paye ; « ok » (toute casse) = mois
#   paye au montant plein ; nombre > 0 (« 10 », « 12,50 », « 10 $ ») =
#   paiement de ce montant ; toute autre valeur = ligne en echec
#   (« valeur illisible »).
#
# Recherche du joueur (algorithme documente, aucune devinette)
# 1. Email renseigne et egal (sans tenir compte de la casse) a l'email d'un
#    joueur non parti du club -> ce joueur.
# 2. Sinon, nom renseigne : jetons du nom (casse, accents et ponctuation
#    ignores, ordre libre : « KALALA Patrick » = « Patrick Kalala »)
#    strictement egaux aux jetons « prenom + nom » d'un joueur non parti.
#    Aucune correspondance partielle ou approchee.
# 3. Plusieurs joueurs pour le meme nom -> echec (« ajoutez l'email »).
#    Email et nom designant deux joueurs differents -> echec. Joueur
#    seulement trouve parmi les partis -> echec (« a quitte le club »).
#    Un meme joueur sur deux lignes -> la seconde echoue.
#
# Interpretation d'une ligne (fichiers de suivi du club pilote : un montant
# couvre son mois puis les suivants ; « ok » marque un mois deja couvert)
# - Montant : paiement de ce montant, date de valeur = 1er du mois de la
#   colonne (ou aujourd'hui pour un mois futur), reparti par le moteur 4.4.3.
# - « ok » : le mois doit etre paye au montant plein. Un « report » est tenu
#   de gauche a droite comme dans le fichier : l'argent d'un montant couvre
#   son mois puis les suivants ; un « ok » deja couvert par ce report (ou
#   par un paiement existant hors de cet import) ne cree aucun paiement ;
#   sinon un paiement du montant manquant (le montant plein en general) est
#   cree. Ex. : « 60, ok, ok, ok, ok, ok » sur un type a 10 = un seul
#   paiement de 60 (pas 110).
# - La repartition finale (quel mois est couvert) reste celle du moteur
#   4.4.3 (mois impayes les plus anciens d'abord) : un fichier avec des
#   « trous » peut donc etre affiche decale d'un mois a l'autre, les totaux
#   et le solde restant identiques au fichier.
#
# Montants dus (point ouvert Q17 de schema-treasury.md, proposition
# appliquee a titre provisoire) : l'import cree, pour chaque ligne reussie
# d'un type mensuel obligatoire, les montants dus manquants des mois de
# l'annee importee jusqu'au mois courant, avec les memes regles que la
# generation mensuelle (joueur Inscrit, entre avant la fin du mois,
# rattache, non suspendu ; mois d'arrivee ignore tant que Q4 est ouverte),
# source « import ». Sans eux, une cellule vide ne creerait aucune dette et
# le solde ne correspondrait pas au fichier (9.2 Lot 2).
#
# Re-import : chaque paiement cree porte la reference « Import historique
# MM/AAAA ». Reimporter le meme fichier ne cree aucun doublon (paiement deja
# importe = ignore) ; un montant different pour un mois deja importe fait
# echouer la ligne (correction = annulation, CDC 4.4.4). Les montants dus
# existants ne sont jamais recrees (contrainte d'unicite).

# Limite provisoire : l'import est synchrone (pas de processus permanent
# sur l'hebergement, CDC 6.5) et chaque paiement scelle coute ~0,1 s
# (``TenantModel.save`` -> ``full_clean``) -- point ouvert du compte rendu.
IMPORT_MAX_ROWS = 500
IMPORT_HEADER_SCAN_ROWS = 5
IMPORT_REFERENCE_PREFIX = "Import historique"

_EMAIL_HEADERS = frozenset(
    {"email", "e-mail", "e mail", "mail", "courriel", "adresse email", "adresse e-mail", "adresse mail"}
)
_NAME_HEADERS = frozenset(
    {
        "nom", "noms", "joueur", "joueurs", "nom du joueur", "nom complet", "nom et prenom",
        "nom et prenoms", "noms et prenoms", "nom prenom", "noms prenoms", "name", "player",
    }
)
_FIRST_NAME_HEADERS = frozenset({"prenom", "prenoms", "first name"})
_MONTH_ALIASES = {
    "janvier": 1, "janv": 1, "jan": 1, "january": 1,
    "fevrier": 2, "fevr": 2, "fev": 2, "feb": 2, "february": 2,
    "mars": 3, "mar": 3, "march": 3,
    "avril": 4, "avr": 4, "apr": 4, "april": 4,
    "mai": 5, "may": 5,
    "juin": 6, "jun": 6, "june": 6,
    "juillet": 7, "juil": 7, "jul": 7, "july": 7,
    "aout": 8, "aou": 8, "aug": 8, "august": 8,
    "septembre": 9, "sept": 9, "sep": 9, "september": 9,
    "octobre": 10, "oct": 10, "october": 10,
    "novembre": 11, "nov": 11, "november": 11,
    "decembre": 12, "dec": 12, "december": 12,
}
_EMPTY_CELLS = frozenset({"", "-", "–", "—"})
_AMOUNT_RE = re.compile(r"\d+(?:[.,]\d{1,2})?")


class ContributionImportError(TreasuryValidationError):
    """Fichier d'import inutilisable dans son ensemble (encodage, en-tete,
    annee, taille) : rien n'est importe, aucune ecriture n'est faite."""


@dataclass(frozen=True)
class ImportPaymentLine:
    period: date
    paid_on: date
    amount: Decimal
    origin: str  # "amount" (montant du fichier) ou "ok" (mois « ok » non couvert)
    reference: str


@dataclass(frozen=True)
class ImportDueLine:
    period: date
    amount: Decimal
    due_date: date


@dataclass(frozen=True)
class ImportRowResult:
    line_number: int
    identity: str
    membership: Optional[Membership]
    status: str  # "ok" (apercu), "imported", "failed"
    errors: tuple = ()
    warnings: tuple = ()
    payments: tuple = ()
    already_imported: tuple = ()
    dues: tuple = ()
    grid_row: Optional[GridRow] = None
    balance_before: Optional[Decimal] = None
    balance_after: Optional[Decimal] = None
    summary_after: Optional[BalanceSummary] = None

    @property
    def failed(self) -> bool:
        return self.status == "failed"


@dataclass(frozen=True)
class ContributionImportReport:
    contribution_type: ContributionType
    year: int
    currency: str
    is_preview: bool
    rows: tuple
    ignored_columns: tuple
    ignored_lines: tuple
    import_batch: Optional[ImportBatch] = None

    @property
    def success_count(self) -> int:
        return sum(1 for row in self.rows if not row.failed)

    @property
    def failed_count(self) -> int:
        return sum(1 for row in self.rows if row.failed)

    @property
    def payments_count(self) -> int:
        return sum(len(row.payments) for row in self.rows if not row.failed)

    @property
    def payments_total(self) -> Decimal:
        return sum((line.amount for row in self.rows if not row.failed for line in row.payments), _ZERO)

    @property
    def dues_count(self) -> int:
        return sum(len(row.dues) for row in self.rows if not row.failed)

    @property
    def already_imported_count(self) -> int:
        return sum(len(row.already_imported) for row in self.rows if not row.failed)


@dataclass
class _ParsedRow:
    line_number: int
    email: str
    name: str
    cells: dict  # periode -> texte brut


@dataclass
class _ParsedFile:
    rows: list
    ignored_columns: list
    ignored_lines: list


def _import_reference(period: date) -> str:
    return f"{IMPORT_REFERENCE_PREFIX} {period:%m/%Y}"


def _parse_month_header(text: str) -> Optional[tuple[int, Optional[int]]]:
    """(mois, annee ou None) d'un en-tete de colonne, ou None."""

    folded = _fold(text).replace(".", " ").strip()
    folded = " ".join(folded.split())
    if not folded:
        return None
    match = re.fullmatch(r"(\d{4})\s*[-/]\s*(\d{1,2})", folded)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        return (month, year) if 1 <= month <= 12 else None
    match = re.fullmatch(r"(\d{1,2})\s*[-/]\s*(\d{4})", folded)
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        return (month, year) if 1 <= month <= 12 else None
    match = re.fullmatch(r"(\d{1,2})", folded)
    if match:
        month = int(match.group(1))
        return (month, None) if 1 <= month <= 12 else None
    match = re.fullmatch(r"([a-z]+)(?:\s*[-/' ]\s*(\d{2}|\d{4}))?", folded)
    if match and match.group(1) in _MONTH_ALIASES:
        year_text = match.group(2)
        year = None
        if year_text:
            year = int(year_text) + (2000 if len(year_text) == 2 else 0)
        return _MONTH_ALIASES[match.group(1)], year
    return None


def _identity_kind(text: str) -> Optional[str]:
    folded = _fold(text).replace(".", "").strip()
    if folded in _EMAIL_HEADERS:
        return "email"
    if folded in _NAME_HEADERS:
        return "name"
    if folded in _FIRST_NAME_HEADERS:
        return "first_name"
    return None


def _read_import_file(csv_file) -> bytes:
    try:
        validate_upload_size(csv_file)
        # Structure verifiee par :func:`_parse_contribution_csv` (en-tete
        # reconnu obligatoire), plus stricte que ``csv.Sniffer``.
        validate_csv_file(csv_file, check_structure=False)
    except DjangoValidationError as exc:
        raise ContributionImportError(" ".join(exc.messages)) from None
    csv_file.seek(0)
    return csv_file.read()


def _parse_contribution_csv(raw_bytes: bytes, *, year: int) -> _ParsedFile:
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ContributionImportError(
            "Le fichier n'est pas encodé en UTF-8. Réenregistrez-le en UTF-8 avant de l'importer."
        ) from None
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if text.count(";") > text.count(",") else ","
    all_rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))

    header_index = None
    for index, row in enumerate(all_rows[:IMPORT_HEADER_SCAN_ROWS]):
        kinds = [_identity_kind(cell) for cell in row]
        months = [_parse_month_header(cell) for cell in row]
        if any(kind in ("email", "name") for kind in kinds) and any(months):
            header_index = index
            break
    if header_index is None:
        raise ContributionImportError(
            "En-tête introuvable : le fichier doit contenir une colonne « email » ou « nom » "
            "puis une colonne par mois (par exemple « janv. », « févr. »...)."
        )
    header = all_rows[header_index]
    email_col = name_col = first_name_col = None
    month_cols: dict[int, int] = {}
    ignored_columns = []
    for col, cell in enumerate(header):
        kind = _identity_kind(cell)
        month = _parse_month_header(cell) if kind is None else None
        if kind == "email" and email_col is None:
            email_col = col
        elif kind == "name" and name_col is None:
            name_col = col
        elif kind == "first_name" and first_name_col is None:
            first_name_col = col
        elif month is not None:
            month_number, header_year = month
            if header_year is not None and header_year != year:
                raise ContributionImportError(
                    f"La colonne « {cell.strip()} » concerne l'année {header_year} alors que vous importez "
                    f"l'année {year} : vérifiez l'année choisie ou le fichier."
                )
            if month_number in month_cols.values():
                raise ContributionImportError(
                    f"Le mois de {FRENCH_MONTHS[month_number - 1]} apparaît dans plusieurs colonnes."
                )
            month_cols[col] = month_number
        elif (cell or "").strip():
            ignored_columns.append(cell.strip())

    data_rows = all_rows[header_index + 1:]
    if len(data_rows) > IMPORT_MAX_ROWS:
        raise ContributionImportError(
            f"Fichier trop volumineux : {IMPORT_MAX_ROWS} lignes au plus par import."
        )
    ignored_lines = list(range(1, header_index + 1))
    parsed = []
    for offset, row in enumerate(data_rows):
        line_number = header_index + 2 + offset

        def cell_at(col: Optional[int]) -> str:
            return row[col].strip() if col is not None and col < len(row) else ""

        first_name = cell_at(first_name_col)
        name = " ".join(part for part in (first_name, cell_at(name_col)) if part)
        cells = {date(year, month, 1): cell_at(col) for col, month in month_cols.items()}
        email = cell_at(email_col)
        if not email and not name and not any(value.strip() for value in cells.values()):
            ignored_lines.append(line_number)  # ligne vide
            continue
        parsed.append(_ParsedRow(line_number=line_number, email=email, name=name, cells=cells))
    return _ParsedFile(rows=parsed, ignored_columns=ignored_columns, ignored_lines=ignored_lines)


def _parse_import_cell(raw: str, currency: str) -> tuple[str, Optional[Decimal]]:
    """``("empty"|"ok"|"amount", montant)`` ; ``ValueError`` si illisible."""

    text = (raw or "").strip()
    if text in _EMPTY_CELLS:
        return "empty", None
    folded = text.casefold()
    if folded == "ok":
        return "ok", None
    compact = folded.replace(" ", "").replace(" ", "")
    for token in ("$", currency.casefold()):
        if token and compact.startswith(token):
            compact = compact[len(token):]
        if token and compact.endswith(token):
            compact = compact[: -len(token)]
    if not _AMOUNT_RE.fullmatch(compact):
        raise ValueError(text)
    value = Decimal(compact.replace(",", "."))
    if value == 0:
        return "empty", None
    try:
        return "amount", to_money(value)
    except InvalidAmountError:
        raise ValueError(text) from None


def _name_key(text: str) -> tuple:
    return tuple(sorted(token for token in re.split(r"[^0-9a-z]+", _fold(text)) if token))


class _MemberIndex:
    """Index des joueurs du club pour la recherche par email puis par nom."""

    def __init__(self, club):
        self.by_email: dict[str, list[Membership]] = {}
        self.by_name: dict[tuple, list[Membership]] = {}
        for membership in Membership.all_objects.filter(club=club).select_related("user").order_by("pk"):
            user = membership.user
            if user.email:
                self.by_email.setdefault(user.email.strip().casefold(), []).append(membership)
            key = _name_key(f"{user.first_name} {user.last_name}")
            if key:
                self.by_name.setdefault(key, []).append(membership)

    @staticmethod
    def _split(candidates: list[Membership]) -> tuple[list[Membership], list[Membership]]:
        active = [item for item in candidates if item.status != Membership.Status.DEPARTED]
        departed = [item for item in candidates if item.status == Membership.Status.DEPARTED]
        return active, departed

    def resolve(self, *, email: str, name: str) -> tuple[Optional[Membership], Optional[str], list[str]]:
        """``(adhesion, erreur, avertissements)`` -- voir l'algorithme en
        tete de section."""

        warnings: list[str] = []
        departed_hit = False
        email_match = None
        if email:
            active, departed = self._split(self.by_email.get(email.casefold(), []))
            if active:
                email_match = active[0]
            departed_hit = bool(departed)
        name_match = None
        name_ambiguous = False
        if name:
            key = _name_key(name)
            active, departed = self._split(self.by_name.get(key, []) if key else [])
            if len(active) > 1:
                name_ambiguous = True
            elif active:
                name_match = active[0]
            departed_hit = departed_hit or bool(departed)
        if email_match is not None:
            if name_match is not None and name_match.pk != email_match.pk:
                return None, "L'email et le nom désignent deux joueurs différents du club : ligne ignorée.", warnings
            if name and name_match is None and not name_ambiguous:
                warnings.append("Le nom du fichier ne correspond pas exactement à la fiche : joueur trouvé par son email.")
            return email_match, None, warnings
        if name_ambiguous:
            return None, (
                f"Plusieurs joueurs du club portent le nom « {name} » : ajoutez l'email du joueur pour lever l'ambiguïté."
            ), warnings
        if name_match is not None:
            if email:
                warnings.append("Email inconnu dans ce club : joueur trouvé par son nom.")
            return name_match, None, warnings
        if departed_hit:
            return None, "Ce joueur a quitté le club : aucune cotisation ne peut être importée.", warnings
        label = name or email
        if not label:
            return None, "Joueur non indiqué (colonne email ou nom vide).", warnings
        return None, f"Joueur introuvable dans ce club (« {label} »).", warnings


@dataclass
class _ImportContext:
    club: Any
    ctype: ContributionType
    year: int
    periods: list
    today: date
    currency: str
    tolerance: int
    rates: list
    concerned: set


def _months_label(periods: list[date]) -> str:
    return ", ".join(french_month_label(period, short=True) for period in periods)


def _plan_import_row(ctx: _ImportContext, parsed: _ParsedRow, membership: Membership, warnings: list) -> ImportRowResult:
    """Plan d'une ligne (paiements, montants dus, grille resultante), SANS
    aucune ecriture : partage a l'identique par l'apercu et l'import."""

    club, ctype = ctx.club, ctx.ctype
    is_free = ctype.nature == ContributionType.Nature.FREE
    identity = parsed.name or parsed.email
    errors: list[str] = []
    cells: dict[date, tuple[str, Optional[Decimal]]] = {}
    for period in ctx.periods:
        raw = parsed.cells.get(period, "")
        try:
            cells[period] = _parse_import_cell(raw, ctx.currency)
        except ValueError:
            errors.append(f"Valeur illisible en {french_month_label(period, short=True)} : « {raw.strip()} ».")
    if errors:
        return ImportRowResult(parsed.line_number, identity, membership, "failed", tuple(errors), tuple(warnings))

    current_period = _period_start(ctx.today)
    first, last_end = ctx.periods[0], _period_end(ctx.periods[-1])
    keys = {_import_reference(period): period for period in ctx.periods}

    existing_dues: dict[date, list] = {}
    for period, amount, due_date in Due.all_objects.filter(
        club=club, membership=membership, contribution_type=ctype, period__gte=first, period__lte=last_end
    ).values_list("period", "amount", "due_date"):
        existing_dues.setdefault(_period_start(period), []).append((amount, due_date))

    validated = (
        Payment.all_objects.filter(
            club=club,
            membership=membership,
            contribution_type=ctype,
            transaction__kind=Transaction.Kind.PAYMENT,
            transaction__status=Transaction.Status.SUCCEEDED,
            transaction__sealed_at__isnull=False,
        )
        .exclude(reversal__status=PaymentReversal.Status.APPROVED)
    )
    family: dict[date, Decimal] = {}
    family_ids = []
    for payment_id, reference, amount in validated.filter(
        source=Payment.Source.CSV_IMPORT, reference__in=list(keys)
    ).values_list("pk", "reference", "amount"):
        family_ids.append(payment_id)
        family[keys[reference]] = family.get(keys[reference], _ZERO) + amount
    others = validated.filter(paid_on__gte=first, paid_on__lte=last_end).exclude(pk__in=family_ids).count()
    if others:
        warnings.append(
            f"Ce joueur a déjà {others} paiement(s) enregistré(s) hors import sur ce type en {ctx.year} : "
            "vérifiez qu'ils ne figurent pas aussi dans le fichier (ils seraient comptés deux fois)."
        )
    outside_coverage: dict[date, Decimal] = {
        _period_start(period): total
        for period, total in PaymentAllocation.all_objects.filter(
            club=club, membership=membership, contribution_type=ctype, period__gte=first, period__lte=last_end
        )
        .exclude(payment_id__in=family_ids)
        .values("period")
        .annotate(total=Sum("amount"))
        .values_list("period", "total")
    }

    # Montants dus manquants (Q17, provisoire) : memes regles que la
    # generation mensuelle (:func:`_generate_dues`).
    new_dues: list[ImportDueLine] = []
    not_concerned: list[date] = []
    backdated_rate: list[date] = []
    if not is_free and ctype.periodicity == ContributionType.Periodicity.MONTHLY:
        for period in ctx.periods:
            if period > current_period or period in existing_dues:
                continue
            eligible = (
                membership.status == Membership.Status.ACTIVE
                and membership.joined_on <= _period_end(period)
                and (membership.left_on is None or membership.left_on >= period)
                and (membership.pk, period) in ctx.concerned
            )
            if not eligible:
                not_concerned.append(period)
                continue
            rate = _rate_in(ctx.rates, period, extend_backwards=True)
            if rate is None or rate <= 0:
                not_concerned.append(period)
                continue
            if _rate_in(ctx.rates, period) is None:
                backdated_rate.append(period)
            # Mois d'arrivee : meme regle que la generation mensuelle
            # (proposition par defaut 10.2 n° 5, non tranchee).
            is_arrival = membership.joined_on.year == period.year and membership.joined_on.month == period.month
            due_date = (
                _arrival_due_date(ctype, period, membership.joined_on)
                if is_arrival
                else _due_date_for_month(ctype, period)
            )
            new_dues.append(ImportDueLine(period, rate, due_date))
    if not_concerned:
        warnings.append(
            f"Aucun montant dû créé pour {_months_label(not_concerned)} : joueur non inscrit, pas encore entré "
            f"au club (entrée le {membership.joined_on:%d/%m/%Y}), non rattaché à ce type ou suspendu."
        )
    if backdated_rate:
        warnings.append(
            f"Mois antérieurs au premier tarif du type ({_months_label(backdated_rate)}) : le premier tarif connu "
            f"({_money_str(ctx.rates[0][1])} {ctx.currency}) est appliqué."
        )
    new_due_amounts = {line.period: line.amount for line in new_dues}

    # Paiements a creer (voir « Interpretation d'une ligne » en tete de section).
    planned: list[ImportPaymentLine] = []
    already: list[ImportPaymentLine] = []
    carry = _ZERO

    def add_payment(period: date, amount: Decimal, origin: str) -> None:
        line = ImportPaymentLine(period, min(period, ctx.today), amount, origin, _import_reference(period))
        imported = family.get(period)
        if imported is None:
            planned.append(line)
        elif imported == amount:
            already.append(line)
        else:
            errors.append(
                f"{french_month_label(period).capitalize()} a déjà été importé pour ce joueur avec un montant de "
                f"{_money_str(imported)} {ctx.currency} (fichier : {_money_str(amount)}) : corrigez d'abord par "
                "une annulation."
            )

    for period in ctx.periods:
        kind, amount = cells[period]
        if is_free:
            if kind == "amount":
                add_payment(period, amount, "amount")
            elif kind == "ok":
                suggested = ctype.amount
                if suggested is None or suggested <= 0:
                    errors.append(
                        f"« ok » en {french_month_label(period, short=True)} : ce type libre n'a pas de montant "
                        "suggéré, indiquez le montant versé."
                    )
                else:
                    add_payment(period, to_money(suggested), "ok")
            continue
        dues_here = existing_dues.get(period)
        if dues_here:
            expected = sum((value for value, _ in dues_here), _ZERO)
        elif period in new_due_amounts:
            expected = new_due_amounts[period]
        elif (membership.pk, period) in ctx.concerned:
            expected = _rate_in(ctx.rates, period, extend_backwards=True) or _ZERO
        else:
            expected = _ZERO
        need = max(expected - outside_coverage.get(period, _ZERO), _ZERO)
        if kind == "amount":
            add_payment(period, amount, "amount")
            carry += amount
        consumed = min(carry, need)
        carry -= consumed
        if kind == "ok":
            if expected <= 0:
                errors.append(
                    f"« ok » en {french_month_label(period, short=True)} : aucun montant n'est dû ce mois-là "
                    "(joueur non rattaché à ce type, suspendu ou pas encore entré au club)."
                )
                continue
            missing = need - consumed
            if missing > 0:
                add_payment(period, missing, "ok")
    for period, imported in family.items():
        if not any(line.period == period for line in planned + already):
            warnings.append(
                f"{french_month_label(period).capitalize()} avait déjà été importé ({_money_str(imported)} "
                f"{ctx.currency}) mais le fichier n'y génère plus de paiement : rien n'est supprimé "
                "(annulation manuelle si nécessaire)."
            )
    if errors:
        return ImportRowResult(parsed.line_number, identity, membership, "failed", tuple(errors), tuple(warnings))

    # Grille resultante : meme moteur de repartition que l'enregistrement.
    existing_payments = _validated_payments_for(club=club, membership=membership, ctype=ctype)
    projected = [_ProjectedPayment(line.amount, line.paid_on, ctx.currency) for line in planned]
    ordered = sorted(existing_payments + projected, key=lambda item: item.paid_on)  # tri stable
    allocated: dict[date, Decimal] = {}
    if ordered:
        lines, _ = _plan_allocations(
            club=club, membership=membership, ctype=ctype, payments=ordered, extra_dues=new_due_amounts
        )
        for _, period, value in lines:
            if first <= period <= last_end:
                key = _period_start(period)
                allocated[key] = allocated.get(key, _ZERO) + value
    dues_by_period = {period: list(values) for period, values in existing_dues.items()}
    for line in new_dues:
        dues_by_period.setdefault(line.period, []).append((line.amount, line.due_date))
    grid_row = _compose_grid_row(
        ctype=ctype,
        membership=membership,
        periods=ctx.periods,
        dues_by_period=dues_by_period,
        allocated_by_period=allocated,
        concerned=ctx.concerned,
        rates=ctx.rates,
        today=ctx.today,
        tolerance=ctx.tolerance,
    )
    return ImportRowResult(
        line_number=parsed.line_number,
        identity=identity,
        membership=membership,
        status="ok",
        errors=(),
        warnings=tuple(warnings),
        payments=tuple(planned),
        already_imported=tuple(already),
        dues=tuple(new_dues),
        grid_row=grid_row,
    )


def _with_balances(ctx: _ImportContext, rows: list[ImportRowResult]) -> list[ImportRowResult]:
    """Ajoute le solde avant/apres (formule du solde, CDC 4.4.2) : paiements
    des types obligatoires (valeur <= aujourd'hui) moins montants dus echus."""

    ids = [row.membership.pk for row in rows if not row.failed and row.membership is not None]
    paid, owed = _balance_aggregates(club=ctx.club, at_date=ctx.today, membership_ids=ids) if ids else ({}, {})
    threshold = ctx.today - timedelta(days=ctx.tolerance)
    is_free = ctx.ctype.nature == ContributionType.Nature.FREE
    result = []
    for row in rows:
        if row.failed or row.membership is None:
            result.append(row)
            continue
        before = (paid.get(row.membership.pk) or _ZERO) - (owed.get(row.membership.pk) or _ZERO)
        after = before
        if not is_free:
            after += sum((line.amount for line in row.payments), _ZERO)
            after -= sum((line.amount for line in row.dues if line.due_date < threshold), _ZERO)
        result.append(
            ImportRowResult(
                **{
                    **row.__dict__,
                    "balance_before": before,
                    "balance_after": after,
                    "summary_after": _summary_from_balance(after, ctx.currency),
                }
            )
        )
    return result


def _prepare_import(
    *, contribution_type: ContributionType, year: Any, csv_file, requested_by, now: datetime
) -> tuple[_ImportContext, _ParsedFile, bytes]:
    """Controles communs (avant toute ecriture) et lecture du fichier."""

    ctype = contribution_type
    club = ctype.club
    _require_service_club(club)
    _require_roles(
        requested_by,
        club,
        CONTRIBUTION_IMPORTERS,
        "Seuls le Trésorier et le Trésorier adjoint peuvent importer des cotisations.",
    )
    club_settings = _club_settings(club)
    today = _club_today(club_settings, now)
    year = _check_year(year, max_year=today.year)
    if ctype.status != ContributionType.Status.ACTIVE:
        raise TreasuryValidationError("Ce type de cotisation est archivé : l'import n'est pas possible.")
    if ctype.nature == ContributionType.Nature.MANDATORY and ctype.periodicity != ContributionType.Periodicity.MONTHLY:
        raise TreasuryValidationError(
            "L'import historique (une colonne par mois) ne concerne que les types mensuels ou libres."
        )
    if csv_file is None:
        raise ContributionImportError("Choisissez le fichier CSV à importer.")
    raw_bytes = _read_import_file(csv_file)
    parsed = _parse_contribution_csv(raw_bytes, year=year)
    periods = _year_periods(year)
    ctx = _ImportContext(
        club=club,
        ctype=ctype,
        year=year,
        periods=periods,
        today=today,
        currency=club_settings.currency,
        tolerance=club_settings.debt_tolerance_days,
        rates=_type_rates(ctype),
        concerned=set(),
    )
    return ctx, parsed, raw_bytes


def _plan_import(ctx: _ImportContext, parsed: _ParsedFile) -> list[ImportRowResult]:
    index = _MemberIndex(ctx.club)
    resolved: list[tuple[_ParsedRow, Optional[Membership], Optional[str], list[str]]] = []
    seen: dict[int, int] = {}
    for row in parsed.rows:
        membership, error, warnings = index.resolve(email=row.email, name=row.name)
        if membership is not None and membership.pk in seen:
            error = f"Joueur déjà présent à la ligne {seen[membership.pk]} : ligne ignorée."
            membership = None
        elif membership is not None:
            seen[membership.pk] = row.line_number
        resolved.append((row, membership, error, warnings))
    ctx.concerned = _concern_map(
        club=ctx.club,
        ctype=ctx.ctype,
        memberships=[membership for _, membership, _, _ in resolved if membership is not None],
        periods=ctx.periods,
    )
    results = []
    for row, membership, error, warnings in resolved:
        identity = row.name or row.email
        if error is not None:
            results.append(ImportRowResult(row.line_number, identity, None, "failed", (error,), tuple(warnings)))
            continue
        results.append(_plan_import_row(ctx, row, membership, warnings))
    return _with_balances(ctx, results)


def preview_contribution_import(
    *, contribution_type: ContributionType, year: Any, csv_file, requested_by, now: Optional[datetime] = None
) -> ContributionImportReport:
    """Apercu de l'import (CDC 4.4.8 : « Un apercu de la grille resultante
    est montre avant l'import definitif ») : **aucune ecriture** (ni
    paiement, ni montant du, ni lot, ni journal). Meme plan, ligne par
    ligne, que :func:`import_contributions`."""

    now = now or timezone.now()
    ctx, parsed, _ = _prepare_import(
        contribution_type=contribution_type, year=year, csv_file=csv_file, requested_by=requested_by, now=now
    )
    rows = _plan_import(ctx, parsed)
    return ContributionImportReport(
        contribution_type=ctx.ctype,
        year=ctx.year,
        currency=ctx.currency,
        is_preview=True,
        rows=tuple(rows),
        ignored_columns=tuple(parsed.ignored_columns),
        ignored_lines=tuple(parsed.ignored_lines),
    )


def _import_report_file(rows: list[ImportRowResult]) -> ContentFile:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(["ligne", "joueur", "resultat", "paiements", "montant", "montants_dus", "message"])
    for row in rows:
        writer.writerow(
            [
                row.line_number,
                _csv_safe(row.identity),
                "echec" if row.failed else "importe",
                len(row.payments),
                _money_str(sum((line.amount for line in row.payments), _ZERO)),
                len(row.dues),
                _csv_safe(" ".join(row.errors or row.warnings)),
            ]
        )
    return ContentFile(("﻿" + buffer.getvalue()).encode("utf-8"), name="rapport-import-cotisations.csv")


def _execute_import_row(
    ctx: _ImportContext, row: ImportRowResult, *, batch: ImportBatch, actor, now: datetime
) -> None:
    """Ecrit une ligne planifiee (a appeler dans un point de sauvegarde)."""

    membership, ctype, club = row.membership, ctx.ctype, ctx.club
    for line in row.dues:
        if Due.all_objects.filter(
            club=club, membership=membership, contribution_type=ctype, period=line.period
        ).exists():
            continue
        due = Due(
            club=club,
            membership=membership,
            contribution_type=ctype,
            period=line.period,
            amount=line.amount,
            due_date=line.due_date,
            source=Due.Source.IMPORT,
            import_batch=batch,
            created_at=now,
        )
        _save(due)
        log_action(
            actor=actor,
            club=club,
            action_type="treasury.due.imported",
            obj=due,
            before=None,
            after={**_due_snapshot(due), "import_batch_id": batch.pk},
        )
    for line in row.payments:
        money, _ = _validate_payment_input(
            membership=membership, contribution_type=ctype, amount=line.amount, paid_on=line.paid_on, now=now
        )
        _create_sealed_payment(
            club=club,
            membership=membership,
            ctype=ctype,
            money=money,
            currency=ctx.currency,
            method=Payment.Method.HISTORICAL_IMPORT,
            reference=line.reference,
            paid_on=line.paid_on,
            source=Payment.Source.CSV_IMPORT,
            actor=actor,
            now=now,
            import_batch=batch,
            recompute=False,
        )
    if row.payments or row.dues:
        _recompute_allocations(membership=membership, ctype=ctype, actor=actor, now=now)


def import_contributions(
    *, contribution_type: ContributionType, year: Any, csv_file, imported_by,
    now: Optional[datetime] = None,
) -> ContributionImportReport:
    """Import definitif (CDC 4.4.8) : enregistre les paiements valides de
    chaque ligne reussie comme un enregistrement normal (chaine, recu,
    repartition 4.4.3, journal) et les montants dus manquants (Q17), puis
    produit le rapport (lignes reussies, lignes en echec avec le detail).

    Import confirme dans l'interface (CDC 7.2, decision du 11/10/2026 :
    plus de PIN ; schema-treasury §5.1 : ``csv_import`` = transaction creee
    ``succeeded`` a la validation), apres tous les controles du fichier. Chaque ligne est
    ecrite dans son propre point de sauvegarde : une ligne en echec
    n'annule jamais les autres ; un gel du registre ou une cle absente
    annule tout l'import."""

    now = now or timezone.now()
    ctx, parsed, raw_bytes = _prepare_import(
        contribution_type=contribution_type, year=year, csv_file=csv_file, requested_by=imported_by, now=now
    )
    _precheck_ledger_writable(ctx.club)

    with db_transaction.atomic():
        # Verrou du type de cotisation avant la planification : deux imports
        # concurrents des memes lignes sont serialises, le second voit les
        # montants deja importes et les ignore (sans effet sous SQLite).
        ContributionType.all_objects.select_for_update().get(pk=ctx.ctype.pk, club=ctx.club)
        rows = _plan_import(ctx, parsed)
        batch = ImportBatch(
            club=ctx.club,
            import_type=ImportBatch.ImportType.HISTORICAL_CONTRIBUTIONS,
            source_file=ContentFile(raw_bytes, name="cotisations-historiques.csv"),
            imported_by=imported_by,
            imported_at=now,
        )
        try:
            batch.save()  # full_clean() + journal (signal apps.clubs)
        except DjangoValidationError as exc:
            raise ContributionImportError(" ".join(exc.messages)) from None
        final_rows = []
        for row in rows:
            if row.failed:
                final_rows.append(row)
                continue
            try:
                with db_transaction.atomic():
                    _execute_import_row(ctx, row, batch=batch, actor=imported_by, now=now)
            except (LedgerFrozenError, LedgerKeyError):
                raise
            except TreasuryError as exc:
                final_rows.append(
                    ImportRowResult(
                        **{**row.__dict__, "status": "failed", "errors": (str(exc),), "grid_row": None}
                    )
                )
                continue
            final_rows.append(ImportRowResult(**{**row.__dict__, "status": "imported"}))
        before = {"row_count_success": 0, "row_count_failed": 0}
        batch.row_count_success = sum(1 for row in final_rows if not row.failed)
        batch.row_count_failed = sum(1 for row in final_rows if row.failed)
        batch.report_file = _import_report_file(final_rows)
        batch.save()
        report = ContributionImportReport(
            contribution_type=ctx.ctype,
            year=ctx.year,
            currency=ctx.currency,
            is_preview=False,
            rows=tuple(final_rows),
            ignored_columns=tuple(parsed.ignored_columns),
            ignored_lines=tuple(parsed.ignored_lines),
            import_batch=batch,
        )
        log_action(
            actor=imported_by,
            club=ctx.club,
            action_type="treasury.contribution_import.completed",
            obj=batch,
            before=before,
            after={
                "import_batch_id": batch.pk,
                "contribution_type_id": ctx.ctype.pk,
                "year": ctx.year,
                "row_count_success": batch.row_count_success,
                "row_count_failed": batch.row_count_failed,
                "payments_count": report.payments_count,
                "payments_total": _money_str(report.payments_total),
                "dues_count": report.dues_count,
                "already_imported_count": report.already_imported_count,
            },
        )
    return report


# ---------------------------------------------------------------------------
# Recu de paiement (CDC 4.4.4, 4.6, 6.1, 6.7 ; annexe D §1)
# ---------------------------------------------------------------------------
#
# Declencheur : la validation du paiement (CDC 4.4.4 « Chaque paiement
# valide genere un recu numerote »). Le numero est attribue au scellement
# (:func:`_seal`) ; le PDF est produit **apres** la validation reelle en
# base (``on_commit``) : aucun recu pour une validation annulee par un
# rollback, et un incident de generation (disque, logo...) ne fait jamais
# echouer la validation d'un paiement -- il est trace dans les logs serveur
# et rattrape par la commande cron ``issue_missing_payment_receipts``.
#
# Exception : les paiements de l'import historique CSV (CDC 4.4.8) ne sont
# pas generes pendant la requete d'import (des milliers de PDF possibles en
# une fois sur un hebergement mutualise) ; la commande de rattrapage les
# emet (position provisoire, signalee au compte rendu).
#
# Contenu : la section 4 de l'annexe D (gabarit du recu) n'est pas redigee.
# Position la plus prudente appliquee, signalee au compte rendu : cadre
# commun §1 (en-tete, couleurs, pied de page) et strict objet du document
# -- joueur concerne, type, montant dans la devise du paiement, mode,
# reference, dates. Ni solde, ni statut « En ordre », ni repartition par
# mois (projection recalculable, alors que le recu est fige), ni nom du
# valideur, ni contact, ni mention de l'Editeur ou de « Vesta ».

_receipt_logger = logging.getLogger("apps.treasury.receipts")

RECEIPT_DOC_TYPE_LABEL = "Reçu de paiement"
# Symboles d'affichage par code ISO (annexe D §1.7 : « 1 250 $ »,
# « 25 000 FC ») ; un code inconnu s'affiche tel quel.
_RECEIPT_CURRENCY_SYMBOLS = {"USD": "$", "CDF": "FC"}


def format_receipt_amount(amount: Decimal, currency: str) -> str:
    """« 1 250 $ », « 10,50 $ », « 25 000 FC » (annexe D §1.7) : espace des
    milliers, virgule decimale, decimales masquees si nulles."""

    value = to_money(amount)
    integer_part, _, cents = f"{abs(value):.2f}".partition(".")
    grouped = f"{int(integer_part):,}".replace(",", " ")
    text = grouped if cents == "00" else f"{grouped},{cents}"
    sign = "-" if value < 0 else ""
    return f"{sign}{text} {_RECEIPT_CURRENCY_SYMBOLS.get(currency, currency)}"


def _receipt_reference(payment: Payment) -> str:
    return f"R-{payment.receipt_number}"


def _receipt_filename(payment: Payment) -> str:
    # Aucune donnee personnelle dans le nom stocke ; club + numero suffisent
    # a l'unicite (le numero est unique par club).
    return f"recu-c{payment.club_id}-{payment.receipt_number:06d}.pdf"


def _validated_succeeded_transaction(payment: Payment) -> Optional[Transaction]:
    return Transaction.all_objects.filter(
        club_id=payment.club_id,
        payment_id=payment.pk,
        status=Transaction.Status.SUCCEEDED,
        sealed_at__isnull=False,
    ).first()


def _build_payment_receipt_pdf(payment: Payment, *, issued_at: datetime, validated_at: datetime) -> bytes:
    """PDF d'une page, cadre commun de l'annexe D §1 (identite du club lue
    au moment de la generation, puis figee)."""

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    from apps.core.pdf import (
        DARK_TEXT_RGB,
        MARGIN,
        MUTED_TEXT_RGB,
        NumberedDocumentCanvas,
        club_stripe_colors,
        draw_header,
        format_date_longue,
        make_footer_drawer,
        wrap_text,
    )

    club = payment.club
    club_settings = _club_settings(club)
    try:
        tz = ZoneInfo(club_settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise TreasuryValidationError("Le fuseau horaire du club est invalide.") from None
    issued_local = issued_at.astimezone(tz)
    validated_local = validated_at.astimezone(tz)
    player = payment.membership.user

    doc_type_label = RECEIPT_DOC_TYPE_LABEL
    reference = _receipt_reference(payment)
    title = f"{doc_type_label} n° {payment.receipt_number}"
    width, height = A4
    content_width = width - 2 * MARGIN

    buffer = io.BytesIO()
    footer_fn = make_footer_drawer(
        club_name=club.name,
        doc_type_label=doc_type_label,
        reference=reference,
        generated_at_text=f"{issued_local.strftime('%d/%m/%Y')} à {issued_local.strftime('%H:%M')}",
        width=width,
    )
    pdf = NumberedDocumentCanvas(buffer, pagesize=A4, pageCompression=0, footer_fn=footer_fn)
    pdf.setTitle(title)
    pdf.setAuthor(club.name)
    pdf.setCreator(club.name)
    pdf.setSubject(doc_type_label)

    y = draw_header(
        pdf, club=club, doc_type_label=doc_type_label, reference=f"Réf. {reference}", width=width, height=height
    )

    def write_lines(text: str, *, font: str = "Helvetica", size: float = 10, color=DARK_TEXT_RGB) -> None:
        nonlocal y
        pdf.setFillColorRGB(*color)
        for line in wrap_text(text, font=font, size=size, max_width=content_width):
            pdf.setFont(font, size)
            pdf.drawString(MARGIN, y, line)
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

    def field_row(label: str, value: str, *, bold: bool = False) -> None:
        nonlocal y
        pdf.setFillColorRGB(*MUTED_TEXT_RGB)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(MARGIN, y, label)
        font = "Helvetica-Bold" if bold else "Helvetica"
        pdf.setFillColorRGB(*DARK_TEXT_RGB)
        for line in wrap_text(value, font=font, size=10, max_width=content_width - label_col):
            pdf.setFont(font, 10)
            pdf.drawString(MARGIN + label_col, y, line)
            y -= 10 * 1.35

    pdf.setFillColorRGB(*DARK_TEXT_RGB)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(MARGIN, y, title)
    y -= 16 * 1.2
    write_lines(
        f"Émis le {format_date_longue(issued_local.date())} à {issued_local.strftime('%H:%M')}",
        color=MUTED_TEXT_RGB,
    )
    y -= 6 * mm

    section_title("Joueur")
    field_row("Nom", f"{player.first_name} {player.last_name}")
    y -= 3 * mm

    section_title("Paiement")
    field_row("Cotisation", payment.contribution_type.name)
    field_row("Montant", format_receipt_amount(payment.amount, payment.currency), bold=True)
    field_row("Mode", payment.get_method_display())
    if payment.reference:
        field_row("Référence", payment.reference)
    field_row("Date du paiement", payment.paid_on.strftime("%d/%m/%Y"))
    field_row("Validé le", f"{validated_local.strftime('%d/%m/%Y')} à {validated_local.strftime('%H:%M')}")
    y -= 6 * mm

    write_lines(
        f"Ce reçu est émis automatiquement par {club.name} à la validation du paiement. "
        "Il ne comporte pas de signature manuscrite.",
        font="Helvetica-Oblique",
        size=9,
        color=MUTED_TEXT_RGB,
    )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


from apps.core.reserved_accounts import SYSTEM_ACTOR_DISPLAY_NAME, SYSTEM_ACTOR_EMAIL  # noqa: E402


class SystemActorCompromisedError(TreasuryError):
    """Le compte « Système » a été détourné (actif, mot de passe utilisable,
    Superuser ou adhésion) : aucune écriture automatique ne doit lui être
    attribuée (audit de sécurité MA1)."""


def get_system_actor():
    """Acteur « Système » explicite des traitements automatiques (cron) qui
    n'ont ni auteur ni valideur (audit de sécurité, m9). Compte technique
    distinct de tout humain : inactif, sans mot de passe utilisable, jamais
    Superuser, sans adhésion. Créé à la première utilisation (aucune donnée
    de démonstration dans les migrations). Si le compte trouvé ne respecte
    pas ces garanties, lève :class:`SystemActorCompromisedError`. Libellé du
    journal « Système » (distinct de « Système Vesta », Ghost Mode, CDC 5.4)."""

    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        email=SYSTEM_ACTOR_EMAIL,
        defaults={
            "first_name": SYSTEM_ACTOR_DISPLAY_NAME,
            "last_name": "",
            "is_active": False,
            "is_superuser": False,
            "must_change_password": False,
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
        return user

    from apps.clubs.models import Membership

    if (
        user.is_active
        or user.is_superuser
        or user.has_usable_password()
        or Membership.all_objects.filter(user=user).exists()
    ):
        raise SystemActorCompromisedError(
            "Le compte technique « Système » est altéré (actif, mot de passe, droits ou adhésion). "
            "Traitement automatique interrompu : contactez l'administrateur de la plateforme."
        )
    if user.first_name != SYSTEM_ACTOR_DISPLAY_NAME or user.last_name:
        user.first_name = SYSTEM_ACTOR_DISPLAY_NAME
        user.last_name = ""
        user.save(update_fields=["first_name", "last_name"])
    return user


class ReceiptJournalError(TreasuryError):
    """Le journal d'activité de l'émission d'un reçu n'a pas pu être écrit :
    le reçu n'est pas émis (CLAUDE.md règle 6) ; la commande
    ``issue_missing_payment_receipts`` réessaiera."""


def _log_receipt_issued(payment: Payment, *, club, actor, issued_at) -> None:
    """Journalise l'émission du reçu -- **obligatoire** (CLAUDE.md règle 6).
    Acteur : celui fourni, sinon le valideur, sinon l'auteur, sinon l'acteur
    « Système » (cron). Si l'écriture échoue, lève
    :class:`ReceiptJournalError` : l'appelant (:func:`issue_payment_receipt`)
    annule alors toute l'émission (base restaurée, fichier supprimé) ; aucun
    reçu à moitié émis, la commande de rattrapage réessaiera."""

    try:
        resolved_actor = (
            actor
            or getattr(payment, "validated_by", None)
            or getattr(payment, "submitted_by", None)
            or get_system_actor()
        )
        log_action(
            actor=resolved_actor,
            club=club,
            action_type="treasury.payment.receipt_issued",
            obj=payment,
            before={"receipt_available": False},
            after={
                "receipt_number": payment.receipt_number,
                "receipt_available": True,
                "receipt_issued_at": issued_at,
            },
        )
    except Exception as exc:
        _receipt_logger.exception(
            "Journal du reçu du paiement %s non écrit : reçu non émis, nouvel essai par "
            "la commande issue_missing_payment_receipts.",
            payment.pk,
        )
        raise ReceiptJournalError(
            "Le journal d'activité n'a pas pu être écrit : le reçu n'est pas émis, il le sera au prochain essai."
        ) from exc


def issue_payment_receipt(*, payment: Payment, actor=None, now: Optional[datetime] = None) -> Payment:
    """Emet le recu PDF d'un paiement valide, dans le stockage prive
    (CDC 4.4.4, 6.7). **Idempotent** : un paiement qui a deja son recu le
    garde tel quel (jamais deux recus, jamais regenere -- annexe D §1.9) ;
    un paiement annule conserve son recu d'origine.

    Refuse pour un paiement non valide, et pour un paiement annule qui n'a
    jamais eu de recu (position prudente : pas de recu emis apres coup pour
    une ecriture deja corrigee). Journalise (CLAUDE.md regle 6) sans copier
    le contenu du document. ``actor`` : par defaut le valideur du paiement
    (ou son auteur pour un paiement confirme par la passerelle).
    """

    club = payment.club
    _require_service_club(club)
    txn = _validated_succeeded_transaction(payment)
    if payment.receipt_number is None or txn is None:
        raise TreasuryValidationError("Seul un paiement validé donne lieu à un reçu.")

    with db_transaction.atomic():
        locked = (
            Payment.all_objects.select_for_update()
            .select_related("club", "membership__user", "contribution_type")
            .get(pk=payment.pk, club_id=club.pk)
        )
        if locked.receipt_file:
            return locked
        if PaymentReversal.all_objects.filter(
            club_id=club.pk, payment_id=locked.pk, status=PaymentReversal.Status.APPROVED
        ).exists():
            raise TreasuryValidationError(
                "Ce paiement a été annulé avant l'émission de son reçu : aucun reçu n'est émis après coup."
            )

        issued_at = (now or timezone.now()).replace(microsecond=0)
        validated_at = locked.validated_at or txn.sealed_at
        content = _build_payment_receipt_pdf(locked, issued_at=issued_at, validated_at=validated_at)

        locked.receipt_issued_at = issued_at
        locked.receipt_file.save(_receipt_filename(locked), ContentFile(content), save=False)
        try:
            _save(locked)
            _log_receipt_issued(locked, club=club, actor=actor, issued_at=issued_at)
        except Exception:
            # Jamais de fichier orphelin si l'ecriture en base ou au journal
            # echoue (regle 6) : la base est restauree par le rollback, le
            # fichier supprime ici ; le recu sera emis au prochain essai.
            locked.receipt_file.storage.delete(locked.receipt_file.name)
            raise
    return locked


def _issue_payment_receipt_after_commit(payment_pk: int) -> None:
    """Rappel ``on_commit`` : un echec ne remonte jamais vers la validation
    (deja enregistree) ; il est trace pour la commande de rattrapage."""

    try:
        payment = Payment.all_objects.select_related("club").get(pk=payment_pk)
        with _active_club_context(payment.club):
            issue_payment_receipt(payment=payment)
    except Exception:
        _receipt_logger.exception(
            "Reçu du paiement %s non généré : il sera émis par la commande issue_missing_payment_receipts.",
            payment_pk,
        )


def _schedule_payment_receipt(payment_pk: int) -> None:
    payment_source = Payment.all_objects.filter(pk=payment_pk).values_list("source", flat=True).first()
    if payment_source == Payment.Source.CSV_IMPORT:
        return  # emis par la commande de rattrapage (voir en-tete de section)
    db_transaction.on_commit(partial(_issue_payment_receipt_after_commit, payment_pk), robust=True)


def payments_missing_receipt(club):
    """Paiements valides du club sans recu, hors paiements annules (commande
    de rattrapage). Une seule requete, sans boucle Python."""

    return (
        Payment.all_objects.filter(
            club=club,
            receipt_number__isnull=False,
            transaction__status=Transaction.Status.SUCCEEDED,
            transaction__sealed_at__isnull=False,
        )
        .filter(Q(receipt_file__isnull=True) | Q(receipt_file=""))
        .exclude(reversal__status=PaymentReversal.Status.APPROVED)
        .order_by("receipt_number")
    )


# ---------------------------------------------------------------------------
# Tableau « Membres du club » et modale « Situation financiere » du bureau
# (CDC 4.4.2, 4.4.6 ; fiche tresorerie-tableau-de-bord §3 point 3, §4.3 ;
# matrice 2.4 : Pdt, VP, Tres, Adj -- memes roles que le tableau de bord).
#
# Aucune regle nouvelle : le solde vient de :func:`_balance_aggregates`
# (deux agregations SQL pour tout le club, formule unique du 4.4.2), le
# statut de :func:`_summary_from_balance`, la « mensuelle du joueur » de
# :func:`get_default_contribution_type_ids`, le rattachement a un type de
# :func:`_grid_membership_condition`, la ligne de grille de
# :func:`_contribution_lines`.
#
# Filtres, recherche et tris sont appliques **en Python** sur les lignes
# deja calculees (au plus quelques centaines d'adhesions, aucune boucle sur
# les transactions) : resultat identique sous SQLite et MySQL (comparaison
# exacte de ``Decimal``, repli des accents et de la casse independant des
# collations -- CLAUDE.md §9). Nombre de requetes SQL constant quel que
# soit le nombre de joueurs.
#
# « Suspendu » (discipline) est lu dans ``apps.sport`` (suspension non
# levee et non purgee, meme definition que ``Suspension.is_active``) :
# aucune donnee medicale n'est jamais lue ici (CLAUDE.md regle n° 11).
# ---------------------------------------------------------------------------

MEMBER_STATUS_IN_GOOD_STANDING = "in_good_standing"
MEMBER_STATUS_IN_DEBT = "in_debt"
MEMBER_STATUS_PENDING = "pending"
MEMBER_STATUS_SUSPENDED = "suspended"
MEMBER_STATUS_LEFT = "left"
MEMBER_STATUS_LABELS = {
    MEMBER_STATUS_IN_GOOD_STANDING: "En ordre",
    MEMBER_STATUS_IN_DEBT: "En dette",
    MEMBER_STATUS_PENDING: "En attente",
    MEMBER_STATUS_SUSPENDED: "Suspendu",
    MEMBER_STATUS_LEFT: "Parti",
}
MEMBER_LIST_ORDERINGS = ("balance", "-balance", "name", "-name", "last_payment", "-last_payment")
MEMBER_LIST_DEFAULT_ORDERING = "balance"
_MEMBER_READ_DENIED = "Réservé au Président, au Vice-président, au Trésorier et à son adjoint."


@dataclass(frozen=True)
class MemberFinancialRow:
    """Ligne du tableau « Membres du club » : situation calculee a la lecture."""

    membership: Membership
    summary: BalanceSummary
    is_suspended: bool
    suspension_matches_remaining: Optional[int]
    last_payment_on: Optional[date]
    monthly_type: Optional[ContributionType] = None

    @property
    def financial_status(self) -> str:
        """« En attente » pour une adhesion non encore validee (decision du
        client du 17/11/2026) : ses frais d'adhesion dus ne la font jamais
        presenter « En dette » (CDC 4.1 : En dette / En ordre ne concernent
        qu'un joueur Inscrit ; meme classement exclusif que le tableau de
        bord du bureau)."""

        if self.membership.status == Membership.Status.PENDING:
            return MEMBER_STATUS_PENDING
        return MEMBER_STATUS_IN_GOOD_STANDING if self.summary.is_in_good_standing else MEMBER_STATUS_IN_DEBT

    @property
    def statuses(self) -> list[str]:
        """Badges dans l'ordre d'affichage (design-system §2.5) : financier
        (« En attente » pour une adhesion en attente), puis depart, puis
        discipline."""

        keys = [self.financial_status]
        if self.membership.status == Membership.Status.DEPARTED:
            keys.append(MEMBER_STATUS_LEFT)
        if self.is_suspended:
            keys.append(MEMBER_STATUS_SUSPENDED)
        return keys


@dataclass(frozen=True)
class MemberFinancialPage:
    rows: list
    count: int
    currency: str
    today: date


@dataclass(frozen=True)
class UnpaidMonth:
    contribution_type: ContributionType
    period: date
    due_date: date
    amount_due: Decimal
    allocated: Decimal

    @property
    def remaining(self) -> Decimal:
        return max(self.amount_due - self.allocated, _ZERO)


@dataclass(frozen=True)
class NextDue:
    contribution_type: ContributionType
    period: date
    due_date: date
    amount: Decimal


@dataclass(frozen=True)
class FreeContributionTotal:
    contribution_type: ContributionType
    total: Decimal
    payments_count: int
    last_paid_on: Optional[date]


@dataclass(frozen=True)
class MemberFinancialDetail:
    row: MemberFinancialRow
    today: date
    unpaid_months: list
    next_due: Optional[NextDue]
    free_contributions: list


def _active_suspensions(club, membership_ids: Optional[Iterable[int]] = None) -> dict[int, int]:
    """Matchs de suspension restant a purger par adhesion (suspensions non
    levees et non purgees, ``Suspension.is_active``), en une requete."""

    from django.db.models import F

    from apps.sport.models import Suspension

    queryset = Suspension.all_objects.filter(
        club=club, lifted_at__isnull=True, matches_served__lt=F("matches_total")
    )
    if membership_ids is not None:
        queryset = queryset.filter(membership_id__in=list(membership_ids))
    remaining: dict[int, int] = {}
    for membership_id, total, served in queryset.values_list("membership_id", "matches_total", "matches_served"):
        remaining[membership_id] = max(remaining.get(membership_id, 0), total - served)
    return remaining


def _validated_payments(club):
    """Paiements valides et non annules du club (« Valide » de la liste des
    paiements), tous types de cotisation."""

    return Payment.all_objects.filter(
        club=club, transaction__status=Transaction.Status.SUCCEEDED, transaction__sealed_at__isnull=False
    ).exclude(reversal__status=PaymentReversal.Status.APPROVED)


def _last_payment_dates(club, membership_ids: Optional[Iterable[int]] = None) -> dict[int, date]:
    queryset = _validated_payments(club)
    if membership_ids is not None:
        queryset = queryset.filter(membership_id__in=list(membership_ids))
    return dict(
        queryset.values("membership_id").annotate(last=Max("paid_on")).values_list("membership_id", "last")
    )


def _parse_member_statuses(statuses: Iterable[str]) -> set[str]:
    keys = {key for key in statuses if key}
    if keys - set(MEMBER_STATUS_LABELS):
        raise TreasuryValidationError(
            "Statut inconnu : choisissez parmi En ordre, En dette, En attente, Suspendu, Parti."
        )
    return keys


def _member_matches_statuses(row: MemberFinancialRow, keys: set[str]) -> bool:
    """Union des statuts choisis (filtre a choix multiple). Sans filtre :
    les joueurs partis sont exclus ; « Parti » les fait apparaitre. « En
    ordre », « En dette », « En attente » et « Suspendu » ne portent que sur
    les joueurs non partis (meme perimetre que le total des dettes du
    tableau de bord)."""

    departed = row.membership.status == Membership.Status.DEPARTED
    if not keys:
        return not departed
    if departed:
        return MEMBER_STATUS_LEFT in keys
    if MEMBER_STATUS_PENDING in keys and row.membership.status == Membership.Status.PENDING:
        return True
    if MEMBER_STATUS_SUSPENDED in keys and row.is_suspended:
        return True
    return row.financial_status in keys


def _member_matches_query(membership: Membership, cleaned: str) -> bool:
    """Meme recherche que la grille (:func:`filter_grid_rows`) : numero de
    maillot exact, ou tous les termes dans « prenom nom » (sans casse ni
    accents)."""

    if cleaned.isdigit() and membership.jersey_number == int(cleaned):
        return True
    user = membership.user
    haystack = _fold(f"{user.first_name} {user.last_name}")
    return all(term in haystack for term in cleaned.split(" "))


def _payment_date_key(row: MemberFinancialRow) -> tuple:
    return (row.last_payment_on is not None, row.last_payment_on or date.min)


def _sort_member_rows(rows: list, ordering: str) -> list:
    """Tri stable : nom d'abord (departage), puis la cle demandee. « Jamais
    paye » est traite comme le plus ancien dernier paiement."""

    rows.sort(key=lambda row: _membership_sort_key(row.membership))
    if ordering == "-name":
        rows.reverse()
    elif ordering in ("balance", "-balance"):
        rows.sort(key=lambda row: row.summary.balance, reverse=ordering == "-balance")
    elif ordering in ("last_payment", "-last_payment"):
        rows.sort(key=_payment_date_key, reverse=ordering == "-last_payment")
    return rows


def _club_contribution_types(club, type_ids: Iterable[int]) -> list[ContributionType]:
    ids = set(type_ids)
    types = list(ContributionType.all_objects.filter(club=club, pk__in=ids))
    if len(types) != len(ids):
        raise TreasuryValidationError("Type de cotisation inconnu dans ce club.")
    return types


def _with_monthly_types(club, rows: list, today: date) -> list:
    """Complete les lignes affichees avec la « mensuelle du joueur » (colonne
    « Type mensuel », meme regle que la Caisse Terrain Express), en deux
    requetes."""

    if not rows:
        return rows
    defaults = get_default_contribution_type_ids(club, [row.membership.pk for row in rows], today)
    type_ids = {type_id for type_id in defaults.values() if type_id is not None}
    types = {ctype.pk: ctype for ctype in ContributionType.all_objects.filter(club=club, pk__in=type_ids)}
    return [
        MemberFinancialRow(
            membership=row.membership,
            summary=row.summary,
            is_suspended=row.is_suspended,
            suspension_matches_remaining=row.suspension_matches_remaining,
            last_payment_on=row.last_payment_on,
            monthly_type=types.get(defaults.get(row.membership.pk)),
        )
        for row in rows
    ]


def list_member_finances(
    *,
    club,
    requested_by,
    query: str = "",
    statuses: Iterable[str] = (),
    contribution_type_ids: Iterable[int] = (),
    ordering: str = MEMBER_LIST_DEFAULT_ORDERING,
    offset: int = 0,
    limit: int = 20,
    today: Optional[date] = None,
) -> MemberFinancialPage:
    """Tableau « Membres du club » (CDC 4.4.6) : situation de chaque joueur
    du club (solde calcule, jamais stocke), filtres par statut (choix
    multiple, voir :func:`_member_matches_statuses`), par type de cotisation
    (joueurs rattaches au type ce mois-ci, regle de la grille 4.4.7 ; choix
    multiple = union) et par nom ou numero ; tri (defaut : solde croissant,
    les dettes en premier) ; pagination ``offset``/``limit``.

    Requetes SQL en nombre constant : adhesions, deux agregations du solde,
    dernier paiement, suspensions, puis mensuelle des seules lignes de la
    page."""

    _require_service_club(club)
    _require_roles(requested_by, club, DASHBOARD_READERS, _MEMBER_READ_DENIED)
    if ordering not in MEMBER_LIST_ORDERINGS:
        raise TreasuryValidationError("Tri inconnu : solde, nom ou dernier paiement.")
    keys = _parse_member_statuses(statuses)
    cleaned = _fold(query)
    if len(cleaned) > CASH_SEARCH_MAX_QUERY_LENGTH:
        raise TreasuryValidationError("Recherche trop longue.")
    club_settings = _club_settings(club)
    today = today or _club_today(club_settings, timezone.now())

    memberships = Membership.all_objects.filter(club=club).select_related("user")
    type_ids = list(contribution_type_ids)
    if type_ids:
        periods = [_period_start(today)]
        condition = Q(pk__in=[])
        for ctype in _club_contribution_types(club, type_ids):
            condition |= _grid_membership_condition(club=club, ctype=ctype, periods=periods)
        memberships = memberships.filter(condition)
    memberships = [item for item in memberships if not cleaned or _member_matches_query(item, cleaned)]

    paid, owed = _balance_aggregates(club=club, at_date=today)
    suspensions = _active_suspensions(club)
    last_payments = _last_payment_dates(club)
    rows = []
    for membership in memberships:
        balance = (paid.get(membership.pk) or _ZERO) - (owed.get(membership.pk) or _ZERO)
        row = MemberFinancialRow(
            membership=membership,
            summary=_membership_summary(membership, balance, club_settings.currency),
            is_suspended=membership.pk in suspensions,
            suspension_matches_remaining=suspensions.get(membership.pk),
            last_payment_on=last_payments.get(membership.pk),
        )
        if _member_matches_statuses(row, keys):
            rows.append(row)
    rows = _sort_member_rows(rows, ordering)
    offset = max(0, int(offset))
    limit = max(1, int(limit))
    page = _with_monthly_types(club, rows[offset:offset + limit], today)
    return MemberFinancialPage(rows=page, count=len(rows), currency=club_settings.currency, today=today)


def _require_member_reader(membership: Membership, requested_by) -> None:
    club = membership.club
    _require_service_club(club)
    _require_roles(requested_by, club, DASHBOARD_READERS, _MEMBER_READ_DENIED)


def _member_row(membership: Membership, today: date, currency: str) -> MemberFinancialRow:
    club = membership.club
    paid, owed = _balance_aggregates(club=club, at_date=today, membership_ids=[membership.pk])
    balance = (paid.get(membership.pk) or _ZERO) - (owed.get(membership.pk) or _ZERO)
    suspensions = _active_suspensions(club, [membership.pk])
    row = MemberFinancialRow(
        membership=membership,
        summary=_membership_summary(membership, balance, currency),
        is_suspended=membership.pk in suspensions,
        suspension_matches_remaining=suspensions.get(membership.pk),
        last_payment_on=_last_payment_dates(club, [membership.pk]).get(membership.pk),
    )
    return _with_monthly_types(club, [row], today)[0]


def _allocated_by_type_period(club, membership: Membership) -> dict[tuple[int, date], Decimal]:
    allocated: dict[tuple[int, date], Decimal] = {}
    for type_id, period, total in (
        PaymentAllocation.all_objects.filter(club=club, membership=membership)
        .values("contribution_type_id", "period")
        .annotate(total=Sum("amount"))
        .values_list("contribution_type_id", "period", "total")
    ):
        key = (type_id, _period_start(period))
        allocated[key] = allocated.get(key, _ZERO) + total
    return allocated


def _grouped_dues(rows) -> dict[tuple[int, date], tuple[Decimal, date]]:
    """Montants dus groupes par (type, mois) : somme et premiere echeance."""

    grouped: dict[tuple[int, date], tuple[Decimal, date]] = {}
    for type_id, period, amount, due_date in rows:
        key = (type_id, _period_start(period))
        previous_amount, previous_date = grouped.get(key, (_ZERO, due_date))
        grouped[key] = (previous_amount + amount, min(previous_date, due_date))
    return grouped


def get_member_financial_detail(
    *, membership: Membership, requested_by, today: Optional[date] = None
) -> MemberFinancialDetail:
    """Modale « Situation financiere » (fiche §4.3) : situation calculee,
    mois echus non couverts (« Impayes »), prochaine echeance non encore
    echue et non couverte, totaux des cotisations libres (suivies, hors
    solde). Les onglets « Paiements » et « Grille » reutilisent la liste
    des paiements (filtre ``membership_id``) et
    :func:`build_member_contribution_lines`.

    « Impayes » et « prochaine echeance » s'appuient sur les montants dus
    generes (``Due``) et la repartition enregistree (``PaymentAllocation``),
    comme la grille 4.4.7 : un mois est impaye si son montant du depasse le
    montant qui lui est affecte. Regle d'echeance unique :
    :func:`_matured_mandatory_dues` (tolerance du club comprise)."""

    _require_member_reader(membership, requested_by)
    club = membership.club
    club_settings = _club_settings(club)
    today = today or _club_today(club_settings, timezone.now())
    row = _member_row(membership, today, club_settings.currency)

    allocated = _allocated_by_type_period(club, membership)
    fields = ("pk", "contribution_type_id", "period", "amount", "due_date")
    all_dues = list(
        Due.all_objects.filter(
            club=club,
            membership=membership,
            contribution_type__nature=ContributionType.Nature.MANDATORY,
            cancellation__isnull=True,
        ).values_list(*fields)
    )
    matured_pks = set(
        _matured_mandatory_dues(club, today).filter(membership=membership).values_list("pk", flat=True)
    )
    matured = _grouped_dues(item[1:] for item in all_dues if item[0] in matured_pks)
    upcoming = _grouped_dues(item[1:] for item in all_dues if item[0] not in matured_pks)
    type_ids = {type_id for type_id, _ in list(matured) + list(upcoming)}
    types = {ctype.pk: ctype for ctype in ContributionType.all_objects.filter(club=club, pk__in=type_ids)}

    unpaid = []
    for (type_id, period), (amount, due_date) in matured.items():
        item = UnpaidMonth(
            contribution_type=types[type_id],
            period=period,
            due_date=due_date,
            amount_due=amount,
            allocated=min(allocated.get((type_id, period), _ZERO), amount),
        )
        if item.remaining > 0:
            unpaid.append(item)
    unpaid.sort(key=lambda item: (item.period, item.due_date, _fold(item.contribution_type.name), item.contribution_type.pk))

    next_due = None
    for (type_id, period), (amount, due_date) in sorted(
        upcoming.items(), key=lambda entry: (entry[1][1], entry[0][1], entry[0][0])
    ):
        remaining = amount - min(allocated.get((type_id, period), _ZERO), amount)
        if remaining > 0:
            next_due = NextDue(contribution_type=types[type_id], period=period, due_date=due_date, amount=remaining)
            break

    free_rows = list(
        _validated_payments(club)
        .filter(membership=membership, contribution_type__nature=ContributionType.Nature.FREE)
        .values("contribution_type_id")
        .annotate(total=Sum("amount"), count=Count("pk"), last=Max("paid_on"))
        .values_list("contribution_type_id", "total", "count", "last")
    )
    free_types = {
        ctype.pk: ctype
        for ctype in ContributionType.all_objects.filter(club=club, pk__in=[item[0] for item in free_rows])
    }
    free = sorted(
        (
            FreeContributionTotal(
                contribution_type=free_types[type_id],
                total=_quantize(total),
                payments_count=count,
                last_paid_on=last,
            )
            for type_id, total, count, last in free_rows
        ),
        key=lambda item: (_fold(item.contribution_type.name), item.contribution_type.pk),
    )
    return MemberFinancialDetail(row=row, today=today, unpaid_months=unpaid, next_due=next_due, free_contributions=free)


def build_member_contribution_lines(
    *, membership: Membership, year: Any, requested_by, today: Optional[date] = None
) -> OwnContributionLines:
    """Onglet « Grille {annee} » de la modale « Situation financiere » : la
    ligne du joueur dans la grille de chaque type qui le concerne, cellules
    identiques a la grille du bureau (CDC 4.4.7). Pdt, VP, Tres, Adj."""

    _require_member_reader(membership, requested_by)
    return _contribution_lines(membership=membership, year=year, today=today)
