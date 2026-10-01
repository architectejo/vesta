"""Modeles de l'app treasury (tache 1.4b -- forme definitive).

Sources : CDC 4.3, 4.4.1, 4.4.4, 4.6, 5.3, 7.2 ; docs/lot0/schema-treasury.md
§4.1 (`ContributionType`), §5.1 (`Payment`), §5.3 (`PaymentReversal`), §6.1
(`Transaction`), §6.2 (`LedgerChainState`), §6.4 (empreinte), §9 (invariants).

Ces modeles sont des structures de donnees : les regles metier (qui peut
enregistrer, validation PIN, calcul de l'empreinte, scellement, verification
de la chaine, frais d'adhesion payes...) vivent dans
``apps.treasury.services`` (CLAUDE.md section 5). Les modeles portent
seulement les garde-fous d'integrite qui doivent tenir quel que soit le
chemin d'ecriture (defense en profondeur, meme principe que
``apps.audit.models.AuditLog``) :

- coherence de club entre cles etrangeres (CLAUDE.md regle n8) ;
- immuabilite d'une `Transaction` scellee, d'un `Payment` valide (champs
  financiers) et d'une `PaymentReversal` decidee (invariant 5, CDC 5.3) ;
- aucune suppression d'une entite financiere, ni par instance, ni en masse
  (``QuerySet.update()``/``delete()`` bloques).

**Le solde n'est stocke nulle part** (invariant 1, CLAUDE.md regle n2).

Caisse Terrain Express (tache 2.4 ; CDC 4.4.5, 10.2 n° 22 ; schema §5.4) :
`CashSession` et ``Payment.cash_session`` (migration additive 0009).

Elements du schema **volontairement absents** a ce stade (ajoutes par
migrations additives, sans reprise des lignes existantes) :
``LedgerChainState.frozen_by_run``/
``unfrozen_*`` (FK vers `LedgerVerificationRun`, levee du gel -- Q8),
``ExpenseDerogation.reported_assembly`` (l'app ``assemblies`` n'a pas encore
de modele `Assembly`). ``Transaction.expense`` existe depuis la tache 2.2 :
le contenu hache incluait deja la cle ``expense`` (``null``), aucune
empreinte existante ne change.

Depenses et assistance sociale (tache 2.2 ; CDC 4.5 ; schema §7-8) :
`ExpenseCategory`, `Expense`, `ExpenseAttachment`, `ExpenseDerogation`,
`SocialAssistanceScale`, `SocialAssistanceRequest`. Aucune n'est jamais
supprimee ; les champs financiers d'une depense sont figes des sa
liberation.
"""

from __future__ import annotations

import datetime
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import TenantManager, TenantModel, TenantQuerySet
from apps.core.storage import private_storage
from apps.core.validators import validate_image_or_pdf, validate_upload_size

MONEY_MAX_DIGITS = 12
MONEY_DECIMAL_PLACES = 2
HASH_LENGTH = 64


class LedgerImmutableError(Exception):
    """Tentative de modifier ou supprimer une ecriture financiere protegee.

    CDC 4.4.4 : « Un paiement valide n'est jamais supprime. » ; CDC 5.3 :
    transactions chainees ; CLAUDE.md regle n4.
    """


class AppendOnlyQuerySet(TenantQuerySet):
    """Bloque ``update()``/``delete()`` en masse (SQL direct qui contournerait
    ``Model.save()``/``Model.delete()``), comme ``AuditLogQuerySet``."""

    immutable_message = "Écriture financière protégée : modification ou suppression en masse interdite (CDC 5.3)."

    def update(self, **kwargs):
        raise LedgerImmutableError(self.immutable_message)

    def delete(self):
        raise LedgerImmutableError(self.immutable_message)


class AppendOnlyTenantManager(TenantManager.from_queryset(AppendOnlyQuerySet)):
    """Manager tenant-aware (``objects``) base sur :class:`AppendOnlyQuerySet`."""


def _club_fk(related_name: str):
    # Surcharge du champ `club` de `TenantModel` : suppression PROTEGEE
    # (schema-treasury.md §1.3 -- aucune entite financiere n'est supprimee,
    # on ne peut donc pas supprimer un club qui en porte).
    return models.ForeignKey(
        "clubs.Club",
        on_delete=models.PROTECT,
        db_index=True,
        related_name=related_name,
        help_text="Isolation multi-tenant (CLAUDE.md regle n8).",
    )


def _money_field(**kwargs):
    return models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, **kwargs)


# ---------------------------------------------------------------------------
# Cotisations
# ---------------------------------------------------------------------------


class ContributionType(TenantModel):
    """Type de cotisation (CDC 4.4.1 ; schema-treasury.md §4.1)."""

    class Nature(models.TextChoices):
        MANDATORY = "mandatory", "Obligatoire"
        FREE = "free", "Libre"

    class Periodicity(models.TextChoices):
        MONTHLY = "monthly", "Mensuelle"
        ANNUAL = "annual", "Annuelle"
        ONE_OFF = "one_off", "Ponctuelle"

    class Scope(models.TextChoices):
        ALL = "all", "Tous"
        SELECTED = "selected", "Liste de joueurs"
        ATTACHED = "attached", "Joueurs rattachés"

    class Status(models.TextChoices):
        ACTIVE = "active", "Actif"
        ARCHIVED = "archived", "Archivé"

    club = _club_fk("contribution_types")
    name = models.CharField(max_length=120)
    nature = models.CharField(max_length=10, choices=Nature.choices)
    amount = _money_field(
        null=True,
        blank=True,
        help_text="Montant courant : fixe (> 0) si obligatoire, suggéré (>= 0, facultatif) si libre.",
    )
    periodicity = models.CharField(max_length=10, choices=Periodicity.choices)
    due_day = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Jour d'échéance 1-28 (mensuelle/annuelle ; 10 par défaut, 10.2 n° 4)."
    )
    due_month = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Mois d'échéance (annuelle).")
    deadline = models.DateField(null=True, blank=True, help_text="Date limite (ponctuelle).")
    is_membership_fee = models.BooleanField(
        default=False, help_text="Frais d'adhésion (CDC 4.3) ; au plus un type actif par club."
    )
    scope = models.CharField(max_length=10, choices=Scope.choices, default=Scope.ALL)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Type de cotisation"
        verbose_name_plural = "Types de cotisation"
        constraints = [
            models.UniqueConstraint(fields=["club", "name"], name="contributiontype_unique_name_per_club"),
            models.CheckConstraint(
                condition=Q(amount__isnull=True) | Q(amount__gte=0), name="contributiontype_amount_gte_0"
            ),
            models.CheckConstraint(
                condition=~Q(nature="mandatory") | Q(amount__gt=0),
                name="contributiontype_mandatory_amount_gt_0",
            ),
            models.CheckConstraint(
                condition=Q(is_membership_fee=False) | Q(amount__gt=0),
                name="contributiontype_membership_fee_amount_gt_0",
            ),
            models.CheckConstraint(
                condition=Q(due_day__isnull=True) | (Q(due_day__gte=1) & Q(due_day__lte=28)),
                name="contributiontype_due_day_range",
            ),
            models.CheckConstraint(
                condition=Q(due_month__isnull=True) | (Q(due_month__gte=1) & Q(due_month__lte=12)),
                name="contributiontype_due_month_range",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    def clean(self):
        errors = []
        if self.periodicity in (self.Periodicity.MONTHLY, self.Periodicity.ANNUAL) and self.due_day is None:
            errors.append("Le jour d'échéance est obligatoire pour une cotisation mensuelle ou annuelle.")
        if self.periodicity == self.Periodicity.ANNUAL and self.due_month is None:
            errors.append("Le mois d'échéance est obligatoire pour une cotisation annuelle.")
        if self.periodicity != self.Periodicity.ANNUAL and self.due_month is not None:
            errors.append("Le mois d'échéance ne concerne que les cotisations annuelles.")
        if self.periodicity == self.Periodicity.ONE_OFF:
            # Frais d'adhesion : echeance propre a chaque adhesion, pas une
            # date limite commune (point ouvert Q1 de schema-treasury.md).
            if self.deadline is None and not self.is_membership_fee:
                errors.append("La date limite est obligatoire pour une cotisation ponctuelle.")
        elif self.deadline is not None:
            errors.append("La date limite ne concerne que les cotisations ponctuelles.")
        if self.nature == self.Nature.MANDATORY and (self.amount is None or self.amount <= 0):
            errors.append("Une cotisation obligatoire exige un montant fixe strictement positif.")
        if self.is_membership_fee and (self.amount is None or self.amount <= 0):
            errors.append("Les frais d'adhésion exigent un montant fixe strictement positif (CDC 4.3).")
        if self.status == self.Status.ARCHIVED and self.archived_at is None:
            errors.append("Un type archivé doit porter sa date d'archivage.")

        if self.is_membership_fee and self.status == self.Status.ACTIVE and self.club_id:
            duplicate = (
                ContributionType.all_objects.filter(
                    club_id=self.club_id, is_membership_fee=True, status=self.Status.ACTIVE
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if duplicate:
                errors.append(
                    "Ce club a déjà un type de cotisation « adhésion » actif : archivez-le avant d'en créer un autre."
                )
        if errors:
            raise ValidationError(errors)


class ContributionTypeRate(TenantModel):
    """Tarif d'un type de cotisation à partir d'un mois donné (schema §4.2)."""

    club = _club_fk("contribution_type_rates")
    contribution_type = models.ForeignKey(
        ContributionType, on_delete=models.PROTECT, related_name="rates"
    )
    amount = _money_field()
    effective_from = models.DateField()
    created_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta(TenantModel.Meta):
        verbose_name = "Tarif de cotisation"
        verbose_name_plural = "Historique des tarifs de cotisation"
        constraints = [
            models.UniqueConstraint(
                fields=["contribution_type", "effective_from"],
                name="contributiontyperate_unique_type_effective_from",
            ),
            models.CheckConstraint(condition=Q(amount__gte=0), name="contributiontyperate_amount_gte_0"),
        ]

    def clean(self):
        errors = []
        if self.effective_from and self.effective_from.day != 1:
            errors.append("Un tarif de cotisation doit prendre effet le premier jour d'un mois.")
        if self.contribution_type_id and self.club_id:
            contribution_type = ContributionType.all_objects.filter(pk=self.contribution_type_id).only(
                "club_id", "nature"
            ).first()
            if contribution_type and contribution_type.club_id != self.club_id:
                errors.append("Le type de cotisation et son tarif doivent appartenir au même club.")
            if contribution_type and contribution_type.nature == ContributionType.Nature.MANDATORY and self.amount <= 0:
                errors.append("Le tarif d'une cotisation obligatoire doit être strictement positif.")
        if errors:
            raise ValidationError(errors)


class ContributionAssignment(TenantModel):
    """Rattachement d'une adhesion a un type de cotisation (schema §4.3)."""

    club = _club_fk("contribution_assignments")
    contribution_type = models.ForeignKey(
        ContributionType, on_delete=models.PROTECT, related_name="assignments"
    )
    membership = models.ForeignKey(
        "clubs.Membership", on_delete=models.PROTECT, related_name="contribution_assignments"
    )
    starts_on = models.DateField()
    ends_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta(TenantModel.Meta):
        verbose_name = "Rattachement de cotisation"
        verbose_name_plural = "Rattachements de cotisation"
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_on__isnull=True) | Q(ends_on__gte=models.F("starts_on")),
                name="contributionassignment_end_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["club", "contribution_type", "starts_on"], name="contribassign_type_start_idx"),
        ]

    def clean(self):
        errors = []
        if self.club_id and self.membership_id and self.membership.club_id != self.club_id:
            errors.append("Le rattachement et l'adhésion doivent appartenir au même club.")
        if self.club_id and self.contribution_type_id:
            ctype = self.contribution_type
            if ctype.club_id != self.club_id:
                errors.append("Le type de cotisation et le rattachement doivent appartenir au même club.")
            if ctype.scope not in (ContributionType.Scope.SELECTED, ContributionType.Scope.ATTACHED):
                errors.append("Seuls les types à joueurs sélectionnés ou rattachés acceptent un rattachement.")
            if ctype.periodicity == ContributionType.Periodicity.MONTHLY and self.starts_on.day != 1:
                errors.append("Un rattachement mensuel doit commencer le premier jour d'un mois.")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            errors.append("La fin du rattachement ne peut pas précéder son début.")
        if self.club_id and self.membership_id and self.contribution_type_id and self.starts_on:
            overlapping = ContributionAssignment.all_objects.filter(
                club_id=self.club_id,
                membership_id=self.membership_id,
                contribution_type_id=self.contribution_type_id,
                starts_on__lte=self.ends_on or datetime.date.max,
            ).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=self.starts_on))
            if self.pk:
                overlapping = overlapping.exclude(pk=self.pk)
            if overlapping.exists():
                errors.append("Les périodes de rattachement d'un joueur à ce type ne peuvent pas se chevaucher.")
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        if Due.all_objects.filter(membership_id=self.membership_id, contribution_type_id=self.contribution_type_id).exists():
            raise LedgerImmutableError("Un rattachement ayant généré un montant dû ne peut pas être supprimé.")
        return super().delete(*args, **kwargs)


class ContributionSuspension(TenantModel):
    """Suspension tracee des cotisations d'un joueur (schema §4.4)."""

    club = _club_fk("contribution_suspensions")
    membership = models.ForeignKey(
        "clubs.Membership", on_delete=models.PROTECT, related_name="contribution_suspensions"
    )
    starts_on = models.DateField()
    ends_on = models.DateField(null=True, blank=True)
    reason = models.TextField()
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decided_at = models.DateTimeField()
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Suspension de cotisation"
        verbose_name_plural = "Suspensions de cotisation"
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_on__isnull=True) | Q(ends_on__gte=models.F("starts_on")),
                name="contributionsuspension_end_after_start",
            ),
            models.CheckConstraint(
                condition=Q(ended_by__isnull=True, ended_at__isnull=True)
                | Q(ended_by__isnull=False, ended_at__isnull=False),
                name="contributionsuspension_ended_fields_together",
            ),
            models.CheckConstraint(condition=~Q(reason=""), name="contributionsuspension_reason_required"),
        ]
        indexes = [
            models.Index(fields=["club", "membership", "starts_on"], name="contribsusp_member_start_idx"),
        ]

    def clean(self):
        errors = []
        if self.club_id and self.membership_id and self.membership.club_id != self.club_id:
            errors.append("La suspension et l'adhésion doivent appartenir au même club.")
        if self.starts_on and self.starts_on.day != 1:
            errors.append("Une suspension doit commencer le premier jour d'un mois.")
        if self.ends_on:
            next_month = self.ends_on.replace(day=28) + datetime.timedelta(days=4)
            last_day = next_month - datetime.timedelta(days=next_month.day)
            if self.ends_on != last_day:
                errors.append("Une suspension doit se terminer le dernier jour d'un mois.")
        if not (self.reason or "").strip():
            errors.append("Le motif de suspension est obligatoire.")
        if errors:
            raise ValidationError(errors)


class Due(TenantModel):
    """Montant du genere, fige apres sa creation (schema §4.5)."""

    class Source(models.TextChoices):
        SCHEDULER = "scheduler", "Planificateur"
        ARRIVAL = "arrival", "Arrivée"
        ASSIGNMENT = "assignment", "Rattachement"
        IMPORT = "import", "Import"

    club = _club_fk("treasury_dues")
    membership = models.ForeignKey("clubs.Membership", on_delete=models.PROTECT, related_name="treasury_dues")
    contribution_type = models.ForeignKey(ContributionType, on_delete=models.PROTECT, related_name="dues")
    period = models.DateField()
    amount = _money_field()
    due_date = models.DateField()
    source = models.CharField(max_length=12, choices=Source.choices)
    import_batch = models.ForeignKey(
        "clubs.ImportBatch", null=True, blank=True, on_delete=models.PROTECT, related_name="treasury_dues"
    )
    created_at = models.DateTimeField()

    objects = AppendOnlyTenantManager()
    all_objects = models.Manager.from_queryset(AppendOnlyQuerySet)()

    class Meta(TenantModel.Meta):
        verbose_name = "Montant dû"
        verbose_name_plural = "Montants dus"
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "contribution_type", "period"], name="due_unique_member_type_period"
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="due_amount_gt_0"),
            models.CheckConstraint(
                condition=~Q(source="import") | Q(import_batch__isnull=False),
                name="due_import_batch_required",
            ),
        ]
        indexes = [models.Index(fields=["club", "membership", "due_date"], name="due_club_member_date_idx")]

    def clean(self):
        errors = []
        if self.club_id and self.membership_id and self.membership.club_id != self.club_id:
            errors.append("Le montant dû et l'adhésion doivent appartenir au même club.")
        if self.club_id and self.contribution_type_id:
            ctype = self.contribution_type
            if ctype.club_id != self.club_id:
                errors.append("Le type de cotisation et le montant dû doivent appartenir au même club.")
            if ctype.nature != ContributionType.Nature.MANDATORY:
                errors.append("Un type libre ne peut pas générer de montant dû.")
        if self.club_id and self.import_batch_id and self.import_batch.club_id != self.club_id:
            errors.append("Le lot d'import et le montant dû doivent appartenir au même club.")
        if self.source == self.Source.IMPORT and self.import_batch_id is None:
            errors.append("Un montant dû importé doit être rattaché à un lot d'import.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk is not None and Due.all_objects.filter(pk=self.pk).exists():
            raise LedgerImmutableError("Un montant dû est immuable après sa création.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("Un montant dû n'est jamais supprimé (schema-treasury.md §4.5).")


# ---------------------------------------------------------------------------
# Encaissements
# ---------------------------------------------------------------------------


class CashSession(TenantModel):
    """Session de caisse de la Caisse Terrain Express (CDC 4.4.5, 6.6, 7.2 ;
    10.2 n° 22 ; schema-treasury.md §5.4 ; tache 2.4).

    Ouverte **en ligne** par le Tresorier ou l'adjoint apres verification
    **serveur** de son code PIN (``pin_verified_at``) ; couvre ensuite ses
    encaissements en especes, en ligne comme hors connexion, jusqu'a minuit
    dans le fuseau du club (``expires_at``, calcule a la creation et fige).

    - **Aucun PIN** n'est stocke ici ni transmis a l'appareil : l'appareil
      ne garde que ``public_id`` (identifiant non devinable, seul
      identifiant expose par l'API) et ``expires_at``.
    - **Validite evaluee a la volee** (:meth:`is_valid_at`) a partir des
      horodatages ; ``status`` n'est qu'un reflet (fermeture manuelle).
    - Jamais supprimee (trace d'audit des encaissements qu'elle couvre).
    """

    class Status(models.TextChoices):
        OPEN = "open", "Ouverte"
        CLOSED = "closed", "Fermée"
        EXPIRED = "expired", "Expirée"

    # Champs figes des la creation (schema §5.4).
    IMMUTABLE_FIELDS = ("club_id", "public_id", "opened_by_id", "pin_verified_at", "opened_at", "expires_at")

    club = _club_fk("cash_sessions")
    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Identifiant public non devinable, transmis à l'appareil et joint à chaque encaissement.",
    )
    opened_by = models.ForeignKey(
        "clubs.Membership",
        on_delete=models.PROTECT,
        related_name="cash_sessions",
        help_text="Trésorier ou Trésorier adjoint qui a ouvert la session (même club).",
    )
    pin_verified_at = models.DateTimeField(help_text="Vérification serveur du code PIN à l'ouverture.")
    opened_at = models.DateTimeField()
    expires_at = models.DateTimeField(help_text="Minuit suivant le jour d'ouverture, fuseau du club (UTC en base).")
    closed_at = models.DateTimeField(null=True, blank=True, help_text="Fermeture manuelle par son auteur.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    objects = AppendOnlyTenantManager()
    all_objects = models.Manager.from_queryset(AppendOnlyQuerySet)()

    class Meta(TenantModel.Meta):
        verbose_name = "Session de caisse"
        verbose_name_plural = "Sessions de caisse"
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__gt=models.F("opened_at")), name="cashsession_expires_after_opening"
            ),
            models.CheckConstraint(
                condition=Q(pin_verified_at__lte=models.F("opened_at")),
                name="cashsession_pin_verified_before_opening",
            ),
            models.CheckConstraint(
                condition=Q(closed_at__isnull=True)
                | (Q(closed_at__gte=models.F("opened_at")) & Q(closed_at__lt=models.F("expires_at"))),
                name="cashsession_closed_within_validity",
            ),
            models.CheckConstraint(
                condition=(Q(status="closed") & Q(closed_at__isnull=False))
                | (~Q(status="closed") & Q(closed_at__isnull=True)),
                name="cashsession_closed_status_consistency",
            ),
        ]
        indexes = [
            models.Index(fields=["club", "opened_by", "expires_at"], name="cashsession_owner_expiry_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Session de caisse {self.public_id} / club {self.club_id}"

    def is_valid_at(self, moment: datetime.datetime) -> bool:
        """Vrai si la session couvre l'instant ``moment`` (schema §5.4) :
        ``opened_at <= moment < expires_at`` et ``moment < closed_at`` si
        la session a ete fermee."""

        if moment < self.opened_at or moment >= self.expires_at:
            return False
        return self.closed_at is None or moment < self.closed_at

    def clean(self):
        if self.club_id and self.opened_by_id and self.opened_by.club_id != self.club_id:
            raise ValidationError("La session de caisse et son auteur doivent appartenir au même club.")

    def save(self, *args, **kwargs):
        if self.pk is not None:
            original = CashSession.all_objects.filter(pk=self.pk).values(*self.IMMUTABLE_FIELDS).first()
            if original is not None and any(getattr(self, f) != original[f] for f in self.IMMUTABLE_FIELDS):
                raise LedgerImmutableError(
                    "Une session de caisse ne peut pas être modifiée après son ouverture (seule sa fermeture est possible)."
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("Une session de caisse n'est jamais supprimée (trace des encaissements).")


class Payment(TenantModel):
    """Paiement (CDC 4.4.4, 4.4.5, 4.6 ; schema-treasury.md §5.1).

    Le statut (a valider, valide, rejete, en cours chez le fournisseur) est
    celui de la `Transaction` liee (``payment.transaction``), jamais duplique.
    """

    class Method(models.TextChoices):
        CASH = "cash", "Espèces"
        MOBILE_MONEY = "mobile_money", "Mobile money"
        PAYMENT_LINK = "payment_link", "Lien de paiement"
        CARD = "card", "Carte"
        # Import des cotisations historiques (CDC 4.4.8 ; tache 2.6) : le
        # mode reel du versement n'est pas connu du fichier de suivi. Jamais
        # propose dans la modale d'enregistrement (TREASURER_ENTRY_METHODS).
        HISTORICAL_IMPORT = "import", "Import historique"

    class Source(models.TextChoices):
        TREASURER_ENTRY = "treasurer_entry", "Saisie Trésorier"
        FIELD_CASH = "field_cash", "Caisse Terrain Express"
        PLAYER_DECLARATION = "player_declaration", "Déclaration « J'ai payé »"
        CSV_IMPORT = "csv_import", "Import CSV"
        GATEWAY = "gateway", "Passerelle de paiement"

    # Champs figes des que la transaction liee est scellee (schema §5.1).
    # ``attachment`` : la piece jointe justificative est figee elle aussi
    # (audit securite A2) ; seuls les champs du recu restent completables.
    FINANCIAL_FIELDS = (
        "attachment",
        "club_id",
        "membership_id",
        "contribution_type_id",
        "amount",
        "currency",
        "method",
        "reference",
        "paid_on",
        "source",
        "submitted_by_id",
        "submitted_at",
        "validated_by_id",
        "validated_at",
        "rejected_by_id",
        "rejected_at",
        "rejection_reason",
        "receipt_number",
        "client_uuid",
        "client_recorded_at",
        "import_batch_id",
        "cash_session_id",
    )

    club = _club_fk("treasury_payments")
    membership = models.ForeignKey("clubs.Membership", on_delete=models.PROTECT, related_name="payments")
    contribution_type = models.ForeignKey(ContributionType, on_delete=models.PROTECT, related_name="payments")
    amount = _money_field()
    currency = models.CharField(max_length=3)
    method = models.CharField(max_length=15, choices=Method.choices)
    reference = models.CharField(max_length=120, blank=True, default="")
    paid_on = models.DateField()
    source = models.CharField(max_length=20, choices=Source.choices)
    attachment = models.FileField(
        upload_to="treasury/payments/attachments/",
        null=True,
        blank=True,
        storage=private_storage,
        validators=[validate_upload_size, validate_image_or_pdf],
        help_text=(
            "Pièce jointe justificative (CDC 4.4.4, 6.7). Stockage privé, jamais servi "
            "directement : voir apps.treasury.views.PaymentAttachmentDownloadView."
        ),
    )
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    submitted_at = models.DateTimeField()
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    receipt_number = models.PositiveIntegerField(null=True, blank=True)
    receipt_file = models.FileField(
        upload_to="treasury/payments/receipts/",
        null=True,
        blank=True,
        storage=private_storage,
        help_text=(
            "Reçu PDF numéroté (CDC 4.4.4, 6.7). Stockage privé, jamais servi "
            "directement : voir apps.treasury.views.PaymentReceiptDownloadView."
        ),
    )
    receipt_issued_at = models.DateTimeField(null=True, blank=True)
    client_uuid = models.UUIDField(null=True, blank=True)
    client_recorded_at = models.DateTimeField(null=True, blank=True)
    import_batch = models.ForeignKey(
        "clubs.ImportBatch", null=True, blank=True, on_delete=models.PROTECT, related_name="payments"
    )
    cash_session = models.ForeignKey(
        CashSession,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payments",
        help_text="Session de caisse de l'encaissement (requise si et seulement si source = Caisse Terrain Express).",
    )

    objects = AppendOnlyTenantManager()
    all_objects = models.Manager.from_queryset(AppendOnlyQuerySet)()

    class Meta(TenantModel.Meta):
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_gt_0"),
            models.UniqueConstraint(fields=["club", "receipt_number"], name="payment_unique_receipt_per_club"),
            models.UniqueConstraint(fields=["club", "client_uuid"], name="payment_unique_client_uuid_per_club"),
            models.CheckConstraint(
                condition=~Q(source="csv_import") | Q(import_batch__isnull=False),
                name="payment_import_batch_required_for_csv",
            ),
            models.CheckConstraint(
                condition=Q(client_uuid__isnull=True) | Q(client_recorded_at__isnull=False),
                name="payment_client_recorded_at_required_with_uuid",
            ),
            models.CheckConstraint(
                condition=Q(rejected_at__isnull=True) | ~Q(rejection_reason=""),
                name="payment_rejection_reason_required",
            ),
            models.CheckConstraint(
                condition=Q(validated_by__isnull=True, validated_at__isnull=True)
                | Q(validated_by__isnull=False, validated_at__isnull=False),
                name="payment_validated_by_and_at_together",
            ),
            models.CheckConstraint(
                condition=(Q(source="field_cash") & Q(cash_session__isnull=False))
                | (~Q(source="field_cash") & Q(cash_session__isnull=True)),
                name="payment_cash_session_iff_field_cash",
            ),
        ]
        indexes = [
            models.Index(fields=["club", "submitted_at"], name="payment_club_submitted_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Paiement {self.pk} / club {self.club_id}"

    def clean(self):
        if self.club_id and self.membership_id and self.membership.club_id != self.club_id:
            raise ValidationError("Le paiement doit porter le même club que l'adhésion du joueur.")
        if self.club_id and self.cash_session_id and self.cash_session.club_id != self.club_id:
            raise ValidationError("La session de caisse doit appartenir au même club que le paiement.")
        if self.club_id and self.contribution_type_id and self.contribution_type.club_id != self.club_id:
            raise ValidationError("Le type de cotisation doit appartenir au même club que le paiement.")
        if self.club_id and self.import_batch_id and self.import_batch.club_id != self.club_id:
            raise ValidationError("Le lot d'import doit appartenir au même club que le paiement.")

    def _has_sealed_transaction(self) -> bool:
        return Transaction.all_objects.filter(payment_id=self.pk, sealed_at__isnull=False).exists()

    @staticmethod
    def _normalized(field: str, value):
        """Valeur comparable d'un champ financier : pour la piece jointe, son
        nom de fichier (``None`` et ``""`` signifient tous deux « aucune »)."""

        if field == "attachment":
            name = getattr(value, "name", value)
            return name or None
        return value

    def save(self, *args, **kwargs):
        if self.pk is not None and self._has_sealed_transaction():
            original = Payment.all_objects.filter(pk=self.pk).values(*self.FINANCIAL_FIELDS).first()
            if original is not None:
                changed = [
                    f for f in self.FINANCIAL_FIELDS if self._normalized(f, getattr(self, f)) != self._normalized(f, original[f])
                ]
                if changed:
                    raise LedgerImmutableError(
                        "Un paiement validé ne peut pas être modifié : corrigez-le par une "
                        "écriture d'annulation (CDC 4.4.4)."
                    )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError(
            "Un paiement n'est jamais supprimé : corrigez-le par une écriture d'annulation (CDC 4.4.4)."
        )


class PaymentAllocation(TenantModel):
    """Projection recalculable de la repartition mensuelle (schema §5.2)."""

    club = _club_fk("payment_allocations")
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="allocations")
    membership = models.ForeignKey("clubs.Membership", on_delete=models.PROTECT, related_name="payment_allocations")
    contribution_type = models.ForeignKey(
        ContributionType, on_delete=models.PROTECT, related_name="payment_allocations"
    )
    period = models.DateField()
    amount = _money_field()
    computed_at = models.DateTimeField()

    class Meta(TenantModel.Meta):
        verbose_name = "Répartition de paiement"
        verbose_name_plural = "Répartitions de paiement"
        constraints = [
            models.UniqueConstraint(fields=["payment", "period"], name="paymentallocation_unique_payment_period"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="paymentallocation_amount_gt_0"),
        ]
        indexes = [
            models.Index(fields=["club", "contribution_type", "period"], name="payalloc_club_type_period_idx"),
        ]

    def clean(self):
        errors = []
        if self.club_id and self.payment_id:
            payment = self.payment
            if payment.club_id != self.club_id:
                errors.append("La répartition et le paiement doivent appartenir au même club.")
            if self.membership_id and payment.membership_id != self.membership_id:
                errors.append("La répartition doit concerner le joueur du paiement.")
            if self.contribution_type_id and payment.contribution_type_id != self.contribution_type_id:
                errors.append("La répartition doit concerner le type du paiement.")
        if self.club_id and self.membership_id and self.membership.club_id != self.club_id:
            errors.append("La répartition et l'adhésion doivent appartenir au même club.")
        if self.club_id and self.contribution_type_id and self.contribution_type.club_id != self.club_id:
            errors.append("Le type et la répartition doivent appartenir au même club.")
        if errors:
            raise ValidationError(errors)


class PaymentReversal(TenantModel):
    """Ecriture d'annulation d'un paiement valide (CDC 4.4.4, 7.2 ; schema §5.3)."""

    class ReasonKind(models.TextChoices):
        ERROR = "error", "Erreur"
        REFUND = "refund", "Remboursement"

    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "En attente d'approbation"
        APPROVED = "approved", "Approuvée"
        REJECTED = "rejected", "Rejetée"

    club = _club_fk("payment_reversals")
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="reversal")
    reason = models.TextField()
    reason_kind = models.CharField(max_length=10, choices=ReasonKind.choices, default=ReasonKind.ERROR)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_APPROVAL)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    requested_at = models.DateTimeField()
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")

    objects = AppendOnlyTenantManager()
    all_objects = models.Manager.from_queryset(AppendOnlyQuerySet)()

    class Meta(TenantModel.Meta):
        verbose_name = "Annulation de paiement"
        verbose_name_plural = "Annulations de paiement"
        constraints = [
            models.CheckConstraint(condition=~Q(reason=""), name="paymentreversal_reason_required"),
            models.CheckConstraint(
                condition=~Q(status="approved") | Q(approved_by__isnull=False, approved_at__isnull=False),
                name="paymentreversal_approved_fields",
            ),
            models.CheckConstraint(
                condition=~Q(status="rejected")
                | (Q(rejected_by__isnull=False, rejected_at__isnull=False) & ~Q(rejection_reason="")),
                name="paymentreversal_rejected_fields",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Annulation du paiement {self.payment_id}"

    def clean(self):
        if self.club_id and self.payment_id and self.payment.club_id != self.club_id:
            raise ValidationError("L'annulation doit porter le même club que le paiement annulé.")
        if not (self.reason or "").strip():
            raise ValidationError("Le motif de l'annulation est obligatoire.")

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored_status = PaymentReversal.all_objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if stored_status is not None and stored_status != self.Status.PENDING_APPROVAL:
                raise LedgerImmutableError(
                    "Une annulation approuvée ou rejetée ne peut plus être modifiée (CDC 5.3)."
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("Une annulation de paiement n'est jamais supprimée (CDC 5.3).")


# ---------------------------------------------------------------------------
# Grand livre chaine (CDC 4.6, 5.3)
# ---------------------------------------------------------------------------


class Transaction(TenantModel):
    """Ecriture financiere chainee (schema-treasury.md §6.1, §6.4).

    Non scellee tant qu'elle est ``initiated``/``pending`` : seuls ``status``,
    ``status_changed_at`` et ``external_ref`` evoluent. Scellee
    atomiquement en atteignant ``succeeded``/``failed`` (``sequence``,
    ``previous_hash``, ``hash``, ``key_id``, ``sealed_at``) par
    ``apps.treasury.services`` ; elle devient alors entierement immuable.
    Seules les transactions scellees ``succeeded`` comptent.
    """

    class Kind(models.TextChoices):
        PAYMENT = "payment", "Paiement"
        PAYMENT_REVERSAL = "payment_reversal", "Annulation de paiement"
        EXPENSE_RELEASE = "expense_release", "Libération de dépense"

    class Provider(models.TextChoices):
        MANUAL = "manual", "Manuel"
        LINK = "link", "Lien de paiement"
        FLEXPAIE = "flexpaie", "FlexPaie"

    class Status(models.TextChoices):
        INITIATED = "initiated", "Initié"
        PENDING = "pending", "En attente"
        SUCCEEDED = "succeeded", "Réussi"
        FAILED = "failed", "Échoué"

    TERMINAL_STATUSES = (Status.SUCCEEDED, Status.FAILED)

    club = _club_fk("ledger_transactions")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    payment = models.OneToOneField(
        Payment, null=True, blank=True, on_delete=models.PROTECT, related_name="transaction"
    )
    reversal = models.OneToOneField(
        PaymentReversal, null=True, blank=True, on_delete=models.PROTECT, related_name="transaction"
    )
    expense = models.OneToOneField(
        "treasury.Expense",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transaction",
        help_text="Dépense libérée (kind = expense_release), CDC 4.5.2.",
    )
    membership = models.ForeignKey(
        "clubs.Membership", null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_transactions"
    )
    contribution_type = models.ForeignKey(
        ContributionType, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_transactions"
    )
    amount = _money_field(help_text="Signe : paiement > 0, annulation et dépense < 0.")
    currency = models.CharField(max_length=3)
    value_date = models.DateField()
    provider = models.CharField(max_length=10, choices=Provider.choices)
    external_ref = models.CharField(max_length=120, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    status_changed_at = models.DateTimeField()
    sequence = models.PositiveIntegerField(null=True, blank=True)
    previous_hash = models.CharField(max_length=HASH_LENGTH, null=True, blank=True)
    hash = models.CharField(max_length=HASH_LENGTH, null=True, blank=True, unique=True)
    key_id = models.CharField(max_length=16, blank=True, default="")
    sealed_at = models.DateTimeField(null=True, blank=True)
    payload_version = models.PositiveSmallIntegerField(
        default=1,
        help_text=(
            "Version du format canonique haché (1 : format d'origine ; 2 : inclut les champs du "
            "paiement lié). Fixée au scellement, elle-même couverte par l'empreinte."
        ),
    )
    created_at = models.DateTimeField()

    objects = AppendOnlyTenantManager()
    all_objects = models.Manager.from_queryset(AppendOnlyQuerySet)()

    class Meta(TenantModel.Meta):
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        constraints = [
            models.UniqueConstraint(fields=["club", "sequence"], name="transaction_unique_sequence_per_club"),
            models.UniqueConstraint(
                fields=["club", "provider", "external_ref"], name="transaction_unique_external_ref"
            ),
            models.CheckConstraint(condition=~Q(amount=0), name="transaction_amount_not_zero"),
            models.CheckConstraint(
                condition=(
                    Q(kind="payment", payment__isnull=False, reversal__isnull=True, expense__isnull=True, amount__gt=0)
                    | Q(
                        kind="payment_reversal",
                        payment__isnull=True,
                        reversal__isnull=False,
                        expense__isnull=True,
                        amount__lt=0,
                    )
                    | Q(
                        kind="expense_release",
                        payment__isnull=True,
                        reversal__isnull=True,
                        expense__isnull=False,
                        amount__lt=0,
                    )
                ),
                name="transaction_kind_consistency",
            ),
            models.CheckConstraint(
                condition=Q(kind="expense_release")
                | Q(membership__isnull=False, contribution_type__isnull=False),
                name="transaction_membership_type_required",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status__in=["initiated", "pending"],
                        sequence__isnull=True,
                        previous_hash__isnull=True,
                        hash__isnull=True,
                        sealed_at__isnull=True,
                        key_id="",
                    )
                    | (
                        Q(
                            status__in=["succeeded", "failed"],
                            sequence__isnull=False,
                            previous_hash__isnull=False,
                            hash__isnull=False,
                            sealed_at__isnull=False,
                        )
                        & ~Q(key_id="")
                    )
                ),
                name="transaction_sealed_iff_terminal",
            ),
        ]
        indexes = [
            models.Index(
                fields=["club", "membership", "status", "kind", "value_date"], name="transaction_balance_idx"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Transaction {self.sequence or '-'} / club {self.club_id}"

    @property
    def is_sealed(self) -> bool:
        return self.sealed_at is not None

    def clean(self):
        for related in ("membership", "contribution_type", "payment", "reversal", "expense"):
            obj_id = getattr(self, f"{related}_id")
            if self.club_id and obj_id and getattr(self, related).club_id != self.club_id:
                raise ValidationError("Une transaction ne peut référencer que des données de son propre club.")

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored_sealed_at = (
                Transaction.all_objects.filter(pk=self.pk).values_list("sealed_at", flat=True).first()
            )
            if stored_sealed_at is not None:
                raise LedgerImmutableError(
                    "Une transaction scellée est immuable (CDC 5.3) : aucune modification possible."
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("Une transaction financière n'est jamais supprimée (CDC 5.3).")


class LedgerChainState(TenantModel):
    """Tete de chaine et gel des ecritures d'un club (schema-treasury.md §6.2).

    Sert de verrou de serialisation (``select_for_update``) pendant le
    scellement, porte le compteur des numeros de recu et l'etat de gel
    (CDC 5.3 : une rupture gele les ecritures financieres du club).
    """

    club = models.OneToOneField(
        "clubs.Club",
        primary_key=True,
        on_delete=models.PROTECT,
        related_name="ledger_chain_state",
        help_text="Isolation multi-tenant (CLAUDE.md regle n8).",
    )
    last_sequence = models.PositiveIntegerField(default=0)
    last_hash = models.CharField(max_length=HASH_LENGTH)
    last_receipt_number = models.PositiveIntegerField(default=0)
    is_frozen = models.BooleanField(default=False)
    frozen_at = models.DateTimeField(null=True, blank=True)
    frozen_reason = models.TextField(blank=True, default="")

    class Meta(TenantModel.Meta):
        verbose_name = "État de la chaîne financière"
        verbose_name_plural = "États des chaînes financières"
        constraints = [
            models.CheckConstraint(
                condition=Q(is_frozen=False) | (Q(frozen_at__isnull=False) & ~Q(frozen_reason="")),
                name="ledgerchainstate_frozen_fields",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Chaine du club {self.club_id}"

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("L'état de la chaîne financière d'un club n'est jamais supprimé (CDC 5.3).")


# ---------------------------------------------------------------------------
# Depenses (CDC 4.5.1, 4.5.2 ; schema-treasury.md §7)
# ---------------------------------------------------------------------------


EXPENSE_FILE_VALIDATORS = [validate_upload_size, validate_image_or_pdf]


class ExpenseCategory(TenantModel):
    """Categorie de depense (CDC 4.5.1 ; schema §7.1).

    Jamais supprimee : une categorie ne s'archive que (fiche d'ecran
    tresorerie-depenses-assistance.md §3.5 ; decision D6 du schema).
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archivée"

    club = _club_fk("expense_categories")
    name = models.CharField(max_length=120)
    ceiling = _money_field(null=True, blank=True, help_text="Plafond facultatif (> 0), par dépense (Q10, provisoire).")
    receipt_required = models.BooleanField(default=True, help_text="Justificatif obligatoire (oui par défaut).")
    good_standing_only = models.BooleanField(
        default=False, help_text="Réservée aux membres en ordre : le bénéficiaire doit être un joueur en ordre."
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    # Archivage seul : ``delete()``/``update()`` en masse bloques, comme les
    # autres entites financieres (CDC 4.5.1 ; decision D6).
    objects = AppendOnlyTenantManager()
    all_objects = models.Manager.from_queryset(AppendOnlyQuerySet)()

    class Meta(TenantModel.Meta):
        verbose_name = "Catégorie de dépense"
        verbose_name_plural = "Catégories de dépense"
        constraints = [
            models.UniqueConstraint(fields=["club", "name"], name="expensecategory_unique_name_per_club"),
            models.CheckConstraint(
                condition=Q(ceiling__isnull=True) | Q(ceiling__gt=0), name="expensecategory_ceiling_gt_0"
            ),
            models.CheckConstraint(
                condition=Q(status="active") | Q(archived_at__isnull=False),
                name="expensecategory_archived_at_required",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    def clean(self):
        if not (self.name or "").strip():
            raise ValidationError("Le nom de la catégorie est obligatoire.")
        if self.ceiling is not None and self.ceiling <= 0:
            raise ValidationError("Le plafond doit être strictement positif.")

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("Une catégorie de dépense n'est jamais supprimée : archivez-la.")


class SocialAssistanceEvent(models.TextChoices):
    """Evenements ouvrant droit a une assistance sociale (CDC 4.5.3)."""

    BIRTH = "birth", "Naissance"
    MARRIAGE = "marriage", "Mariage"
    DEATH = "death", "Décès"


class SocialAssistanceScale(TenantModel):
    """Bareme d'assistance sociale d'un club, par evenement (schema §8.1).

    Aucun montant ni delai par defaut : le cahier des charges n'en fixe pas
    et le 10.2 ne propose aucune valeur. Au plus un bareme actif par
    evenement et par club (controle dans ``clean``, sans contrainte
    conditionnelle : non supportee par MySQL/MariaDB).
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Actif"
        ARCHIVED = "archived", "Archivé"

    club = _club_fk("social_assistance_scales")
    event_type = models.CharField(max_length=10, choices=SocialAssistanceEvent.choices)
    amount = _money_field(help_text="Montant prévu, en devise du club.")
    processing_days = models.PositiveSmallIntegerField(help_text="Délai de traitement annoncé au joueur (jours).")
    expense_category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="social_assistance_scales"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    # Archivage seul : ``delete()``/``update()`` en masse bloques.
    objects = AppendOnlyTenantManager()
    all_objects = models.Manager.from_queryset(AppendOnlyQuerySet)()

    class Meta(TenantModel.Meta):
        verbose_name = "Barème d'assistance sociale"
        verbose_name_plural = "Barèmes d'assistance sociale"
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="socialassistancescale_amount_gt_0"),
            models.CheckConstraint(
                condition=Q(processing_days__gt=0), name="socialassistancescale_processing_days_gt_0"
            ),
            models.CheckConstraint(
                condition=Q(status="active") | Q(archived_at__isnull=False),
                name="socialassistancescale_archived_at_required",
            ),
        ]

    def clean(self):
        errors = []
        if self.club_id and self.expense_category_id:
            category = self.expense_category
            if category.club_id != self.club_id:
                errors.append("La catégorie de dépense du barème doit appartenir au même club.")
            if not category.good_standing_only:
                errors.append(
                    "La catégorie d'un barème d'assistance sociale doit être « réservée aux membres en ordre »."
                )
        if self.club_id and self.event_type and self.status == self.Status.ACTIVE:
            duplicate = (
                SocialAssistanceScale.all_objects.filter(
                    club_id=self.club_id, event_type=self.event_type, status=self.Status.ACTIVE
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if duplicate:
                errors.append("Un barème actif existe déjà pour cet événement dans ce club.")
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("Un barème d'assistance sociale n'est jamais supprimé : archivez-le.")


class SocialAssistanceRequest(TenantModel):
    """Demande d'assistance sociale d'un joueur (CDC 4.5.3 ; schema §8.2).

    ``eligible_at_submission`` et ``amount_to_regularize`` sont des
    instantanes informatifs : ils n'empechent jamais l'envoi (10.2 n° 33).
    L'eligibilite est recalculee a la decision (10.2 n° 37).
    """

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Envoyée"
        APPROVED = "approved", "Approuvée"
        REJECTED = "rejected", "Refusée"

    club = _club_fk("social_assistance_requests")
    membership = models.ForeignKey(
        "clubs.Membership", on_delete=models.PROTECT, related_name="social_assistance_requests"
    )
    event_type = models.CharField(max_length=10, choices=SocialAssistanceEvent.choices)
    event_date = models.DateField()
    description = models.TextField()
    attachment = models.FileField(
        upload_to="treasury/social_assistance/",
        storage=private_storage,
        validators=EXPENSE_FILE_VALIDATORS,
        help_text=(
            "Pièce justificative (CDC 4.5.3, 6.7). Stockage privé, servi uniquement par "
            "apps.treasury.views.SocialAssistanceAttachmentDownloadView."
        ),
    )
    scale = models.ForeignKey(SocialAssistanceScale, on_delete=models.PROTECT, related_name="requests")
    planned_amount = _money_field(help_text="Montant du barème figé à l'envoi.")
    currency = models.CharField(max_length=3)
    processing_days = models.PositiveSmallIntegerField(help_text="Délai de traitement du barème figé à l'envoi.")
    eligible_at_submission = models.BooleanField()
    amount_to_regularize = _money_field()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED)
    submitted_at = models.DateTimeField()
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")

    objects = AppendOnlyTenantManager()
    all_objects = models.Manager.from_queryset(AppendOnlyQuerySet)()

    class Meta(TenantModel.Meta):
        verbose_name = "Demande d'assistance sociale"
        verbose_name_plural = "Demandes d'assistance sociale"
        constraints = [
            models.CheckConstraint(condition=~Q(description=""), name="socialassistancerequest_description_required"),
            models.CheckConstraint(condition=Q(planned_amount__gt=0), name="socialassistancerequest_amount_gt_0"),
            models.CheckConstraint(
                condition=Q(amount_to_regularize__gte=0), name="socialassistancerequest_regularize_gte_0"
            ),
            models.CheckConstraint(
                condition=Q(status="submitted", decided_by__isnull=True, decided_at__isnull=True)
                | (~Q(status="submitted") & Q(decided_by__isnull=False, decided_at__isnull=False)),
                name="socialassistancerequest_decision_fields",
            ),
            models.CheckConstraint(
                condition=~Q(status="rejected") | ~Q(rejection_reason=""),
                name="socialassistancerequest_rejection_reason_required",
            ),
        ]
        indexes = [models.Index(fields=["club", "status", "submitted_at"], name="socassist_club_status_idx")]

    def clean(self):
        errors = []
        if self.club_id and self.membership_id and self.membership.club_id != self.club_id:
            errors.append("La demande et l'adhésion du joueur doivent appartenir au même club.")
        if self.club_id and self.scale_id and self.scale.club_id != self.club_id:
            errors.append("La demande et le barème doivent appartenir au même club.")
        if self.scale_id and self.event_type and self.scale.event_type != self.event_type:
            errors.append("Le barème appliqué ne correspond pas à l'événement de la demande.")
        if not (self.description or "").strip():
            errors.append("La description est obligatoire.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored_status = (
                SocialAssistanceRequest.all_objects.filter(pk=self.pk).values_list("status", flat=True).first()
            )
            if stored_status is not None and stored_status != self.Status.SUBMITTED:
                raise LedgerImmutableError("Une demande d'assistance déjà traitée ne peut plus être modifiée.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("Une demande d'assistance sociale n'est jamais supprimée.")


class Expense(TenantModel):
    """Depense (CDC 4.5.2 ; schema §7.2).

    Machine a etats : En attente -> Refusee | Liberee ; Liberee ->
    Justifiee | Non justifiee ; Non justifiee -> Justifiee. Les transitions
    sont portees par ``apps.treasury.services`` ; le modele fige les champs
    financiers des la liberation et interdit toute suppression.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        REFUSED = "refused", "Refusée"
        RELEASED = "released", "Libérée"
        JUSTIFIED = "justified", "Justifiée"
        UNJUSTIFIED = "unjustified", "Non justifiée"

    RELEASED_STATUSES = (Status.RELEASED, Status.JUSTIFIED, Status.UNJUSTIFIED)
    FINAL_STATUSES = (Status.REFUSED, Status.JUSTIFIED)

    # Diagramme CDC 4.5.2, verrouille au niveau du modele (defense en
    # profondeur) : aucun retour en arriere, donc aucune double liberation
    # (Liberee -> En attente -> Liberee). Les etats finaux n'y figurent pas :
    # ils sont figes en bloc dans ``save``.
    ALLOWED_STATUS_TRANSITIONS = {
        Status.PENDING: frozenset({Status.PENDING, Status.REFUSED, Status.RELEASED}),
        Status.RELEASED: frozenset({Status.RELEASED, Status.JUSTIFIED, Status.UNJUSTIFIED}),
        Status.UNJUSTIFIED: frozenset({Status.UNJUSTIFIED, Status.JUSTIFIED}),
    }

    # Figes des que la depense quitte l'etat « En attente ».
    FINANCIAL_FIELDS = (
        "club_id",
        "category_id",
        "amount",
        "currency",
        "beneficiary_name",
        "beneficiary_membership_id",
        "reason",
        "expense_date",
        "created_by_id",
        "created_at",
        "social_assistance_request_id",
        "released_by_id",
        "released_at",
        "justification_deadline",
        "refused_by_id",
        "refused_at",
        "refusal_reason",
    )

    club = _club_fk("expenses")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses")
    amount = _money_field()
    currency = models.CharField(max_length=3)
    beneficiary_name = models.CharField(max_length=160)
    beneficiary_membership = models.ForeignKey(
        "clubs.Membership", null=True, blank=True, on_delete=models.PROTECT, related_name="expenses_received"
    )
    reason = models.TextField()
    expense_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField()
    refused_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    refused_at = models.DateTimeField(null=True, blank=True)
    refusal_reason = models.TextField(blank=True, default="")
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    released_at = models.DateTimeField(null=True, blank=True)
    justification_deadline = models.DateField(
        null=True,
        blank=True,
        help_text="Date locale de libération + délai du club, figée à la libération (si justificatif obligatoire).",
    )
    justified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    justified_at = models.DateTimeField(null=True, blank=True)
    unjustified_at = models.DateTimeField(null=True, blank=True)
    social_assistance_request = models.OneToOneField(
        SocialAssistanceRequest, null=True, blank=True, on_delete=models.PROTECT, related_name="expense"
    )
    updated_at = models.DateTimeField(auto_now=True)

    objects = AppendOnlyTenantManager()
    all_objects = models.Manager.from_queryset(AppendOnlyQuerySet)()

    class Meta(TenantModel.Meta):
        verbose_name = "Dépense"
        verbose_name_plural = "Dépenses"
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="expense_amount_gt_0"),
            models.CheckConstraint(condition=~Q(reason=""), name="expense_reason_required"),
            models.CheckConstraint(condition=~Q(beneficiary_name=""), name="expense_beneficiary_required"),
            models.CheckConstraint(
                condition=~Q(status="refused")
                | (Q(refused_by__isnull=False, refused_at__isnull=False) & ~Q(refusal_reason="")),
                name="expense_refused_fields",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["released", "justified", "unjustified"])
                | Q(released_by__isnull=False, released_at__isnull=False),
                name="expense_released_fields",
            ),
            models.CheckConstraint(
                condition=~Q(status="justified") | Q(justified_by__isnull=False, justified_at__isnull=False),
                name="expense_justified_fields",
            ),
            models.CheckConstraint(
                condition=~Q(status="unjustified")
                | Q(unjustified_at__isnull=False, justification_deadline__isnull=False),
                name="expense_unjustified_fields",
            ),
        ]
        indexes = [
            models.Index(fields=["club", "status", "justification_deadline"], name="expense_blocking_idx"),
            models.Index(fields=["club", "created_at"], name="expense_club_created_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Dépense {self.pk} / club {self.club_id}"

    def clean(self):
        errors = []
        if self.club_id and self.category_id and self.category.club_id != self.club_id:
            errors.append("La catégorie doit appartenir au même club que la dépense.")
        if self.club_id and self.beneficiary_membership_id and self.beneficiary_membership.club_id != self.club_id:
            errors.append("Le joueur bénéficiaire doit appartenir au même club que la dépense.")
        if (
            self.club_id
            and self.social_assistance_request_id
            and self.social_assistance_request.club_id != self.club_id
        ):
            errors.append("La demande d'assistance doit appartenir au même club que la dépense.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        original = None
        if self.pk is not None:
            original = Expense.all_objects.filter(pk=self.pk).values("status", *self.FINANCIAL_FIELDS).first()
        if original is None:
            if self.status != self.Status.PENDING:
                raise LedgerImmutableError("Une dépense est toujours créée « En attente » (CDC 4.5.2).")
        else:
            if original["status"] in self.FINAL_STATUSES:
                raise LedgerImmutableError("Une dépense refusée ou justifiée ne peut plus être modifiée.")
            allowed = self.ALLOWED_STATUS_TRANSITIONS.get(original["status"], frozenset())
            if self.status not in allowed:
                raise LedgerImmutableError(
                    "Changement d'état de dépense interdit : une dépense ne revient jamais à un état "
                    "antérieur (CDC 4.5.2)."
                )
            if original["status"] != self.Status.PENDING:
                changed = [f for f in self.FINANCIAL_FIELDS if getattr(self, f) != original[f]]
                if changed:
                    raise LedgerImmutableError("Une dépense libérée ne peut plus être modifiée (CDC 5.3).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("Une dépense n'est jamais supprimée (CDC 4.5.2).")


class ExpenseAttachment(TenantModel):
    """Piece jointe d'une depense (schema §7.3) : piece a la saisie
    (``supporting``) ou justificatif de cloture (``receipt``). Immuable."""

    class Kind(models.TextChoices):
        SUPPORTING = "supporting", "Pièce jointe à la saisie"
        RECEIPT = "receipt", "Justificatif"

    club = _club_fk("expense_attachments")
    expense = models.ForeignKey(Expense, on_delete=models.PROTECT, related_name="attachments")
    file = models.FileField(
        upload_to="treasury/expenses/",
        storage=private_storage,
        validators=EXPENSE_FILE_VALIDATORS,
        help_text=(
            "Photo ou PDF (CDC 4.5.2, 6.7). Stockage privé, servi uniquement par "
            "apps.treasury.views.ExpenseAttachmentDownloadView."
        ),
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField()

    objects = AppendOnlyTenantManager()
    all_objects = models.Manager.from_queryset(AppendOnlyQuerySet)()

    class Meta(TenantModel.Meta):
        verbose_name = "Pièce jointe de dépense"
        verbose_name_plural = "Pièces jointes de dépense"

    def clean(self):
        if self.club_id and self.expense_id and self.expense.club_id != self.club_id:
            raise ValidationError("La pièce jointe doit appartenir au même club que la dépense.")

    def save(self, *args, **kwargs):
        if self.pk is not None and ExpenseAttachment.all_objects.filter(pk=self.pk).exists():
            raise LedgerImmutableError("Une pièce jointe de dépense ne peut plus être modifiée.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("Une pièce jointe de dépense n'est jamais supprimée.")


class ExpenseDerogation(TenantModel):
    """Liberation d'une depense malgre le blocage, par le President (CDC
    4.5.2 ; schema §7.4). Immuable apres creation ; signalee a la prochaine
    AG (le lien vers l'AG viendra avec l'app ``assemblies``)."""

    club = _club_fk("expense_derogations")
    expense = models.OneToOneField(Expense, on_delete=models.PROTECT, related_name="derogation")
    reason = models.TextField()
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    granted_at = models.DateTimeField()
    blocking_expenses = models.ManyToManyField(
        Expense,
        related_name="+",
        help_text="Dépenses non justifiées qui bloquaient au moment de la dérogation (instantané).",
    )

    objects = AppendOnlyTenantManager()
    all_objects = models.Manager.from_queryset(AppendOnlyQuerySet)()

    class Meta(TenantModel.Meta):
        verbose_name = "Dérogation au blocage des dépenses"
        verbose_name_plural = "Dérogations au blocage des dépenses"
        constraints = [
            models.CheckConstraint(condition=~Q(reason=""), name="expensederogation_reason_required"),
        ]

    def clean(self):
        if self.club_id and self.expense_id and self.expense.club_id != self.club_id:
            raise ValidationError("La dérogation doit appartenir au même club que la dépense.")
        if not (self.reason or "").strip():
            raise ValidationError("Le motif de la dérogation est obligatoire.")

    def save(self, *args, **kwargs):
        if self.pk is not None and ExpenseDerogation.all_objects.filter(pk=self.pk).exists():
            raise LedgerImmutableError("Une dérogation ne peut plus être modifiée (CDC 4.5.2).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("Une dérogation n'est jamais supprimée (CDC 4.5.2).")
