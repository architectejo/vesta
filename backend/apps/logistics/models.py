"""Modeles de l'app logistics (CDC 4.13 ; tache 4.3).

Sources : docs/lot0/schema-donnees.md §7 (`Article`, `StockMovement`,
`Inventory`, `InventoryLine`) et §17 (`inventory_open_alert`) ;
docs/ecrans/logistique.md ; CLAUDE.md section 5 (regles metier dans
``services.py``, jamais ici).

Deux entites append-only (``StockMovement``, defense en profondeur du
point ouvert n° 5 de la fiche d'ecran : « aucune modification ni
suppression dans l'interface, puisque le registre sert de base au stock
et a l'inventaire ») ; ``Article``/``Inventory``/``InventoryLine`` restent
des ``TenantModel`` classiques, modifiables via des transitions
controlees par ``apps.logistics.services``.

Le stock theorique n'est **jamais stocke** (invariant J1, schema §15) :
``apps.logistics.services.theoretical_quantity`` le recalcule a partir de
``StockMovement``. Seule exception assumee par le schema :
``InventoryLine.theoretical_quantity``, instantane historique fige au
moment du comptage.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import TenantManager, TenantModel, TenantQuerySet


class LogisticsImmutableError(Exception):
    """Tentative de modifier ou supprimer un mouvement de stock enregistre.

    Fiche d'ecran logistique.md §4.3, §12 point ouvert n° 5 (position
    provisoire, la plus prudente) : « aucune modification ni suppression
    dans l'interface, puisque le registre sert de base au stock et a
    l'inventaire ». Meme principe que ``treasury.LedgerImmutableError``.
    """


class AppendOnlyQuerySet(TenantQuerySet):
    immutable_message = "Mouvement de stock protégé : modification ou suppression en masse interdite (logistique.md §4.3)."

    def update(self, **kwargs):
        raise LogisticsImmutableError(self.immutable_message)

    def delete(self):
        raise LogisticsImmutableError(self.immutable_message)


class AppendOnlyTenantManager(TenantManager.from_queryset(AppendOnlyQuerySet)):
    pass


def _club_fk(related_name: str):
    return models.ForeignKey(
        "clubs.Club",
        on_delete=models.PROTECT,
        db_index=True,
        related_name=related_name,
        help_text="Isolation multi-tenant (CLAUDE.md regle n8).",
    )


class Article(TenantModel):
    """Article du catalogue de materiel (CDC 4.13 ; schema §7.1)."""

    class Category(models.TextChoices):
        JERSEY = "jersey", "Maillots"
        SOCKS = "socks", "Bas"
        CLEATS = "cleats", "Bottines"
        BALLS = "balls", "Ballons"
        MISC = "misc", "Matériel divers"
        SHORTS = "shorts", "Culottes"
        BIBS = "bibs", "Chasubles"
        REFEREE = "referee", "Arbitrage"
        ACCESSORIES = "accessories", "Accessoires"
        FURNITURE = "furniture", "Mobilier"

    # Ordre d'affichage du registre de l'intendance (spec §8).
    REGISTER_ORDER = (
        "jersey", "shorts", "socks", "cleats", "balls", "bibs", "referee", "accessories", "furniture", "misc",
    )

    class Condition(models.TextChoices):
        NEW = "new", "Neuf"
        GOOD = "good", "Bon état"
        WORN = "worn", "Usé"
        DAMAGED = "damaged", "Abîmé"
        UNKNOWN = "unknown", "Non renseigné"

    class Status(models.TextChoices):
        ACTIVE = "active", "Actif"
        ARCHIVED = "archived", "Archivé"

    club = _club_fk("articles")
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=Category.choices)
    unit = models.CharField(max_length=20, default="pièce")
    reference_condition = models.CharField(max_length=10, choices=Condition.choices, default=Condition.NEW)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta(TenantModel.Meta):
        verbose_name = "Article"
        verbose_name_plural = "Articles"
        constraints = [
            models.UniqueConstraint(fields=["club", "name"], name="article_unique_name_per_club"),
            models.CheckConstraint(
                condition=Q(status="active") | Q(archived_at__isnull=False),
                name="article_archived_at_required",
            ),
        ]
        indexes = [models.Index(fields=["club", "category", "status"], name="article_club_category_idx")]

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    def clean(self):
        if not (self.name or "").strip():
            raise ValidationError("Le nom de l'article est obligatoire.")
        if not (self.unit or "").strip():
            raise ValidationError("L'unité est obligatoire.")


class Holder(TenantModel):
    """Détenteur de matériel : un joueur du club ou un lieu (registre de
    l'intendance §3). Le stock d'un détenteur est CALCULÉ à partir des
    mouvements, jamais stocké."""

    class Kind(models.TextChoices):
        MEMBER = "member", "Joueur du club"
        PLACE = "place", "Lieu"

    class Status(models.TextChoices):
        ACTIVE = "active", "Actif"
        ARCHIVED = "archived", "Archivé"

    club = _club_fk("holders")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    membership = models.ForeignKey(
        "clubs.Membership", null=True, blank=True, on_delete=models.PROTECT, related_name="material_holders"
    )
    label = models.CharField(max_length=60, blank=True, default="")
    holder_key = models.CharField(
        max_length=100,
        help_text="« m<id adhésion> » ou « p:<nom normalisé> » : unicité par club sans contrainte conditionnelle.",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta(TenantModel.Meta):
        verbose_name = "Détenteur"
        verbose_name_plural = "Détenteurs"
        constraints = [
            models.UniqueConstraint(fields=["club", "holder_key"], name="holder_unique_key_per_club"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.display_name

    @property
    def display_name(self) -> str:
        if self.kind == self.Kind.MEMBER and self.membership_id:
            user = self.membership.user
            return f"{user.first_name} {user.last_name}".strip()
        return self.label

    @property
    def has_left_club(self) -> bool:
        return (
            self.kind == self.Kind.MEMBER
            and self.membership_id is not None
            and self.membership.status == "departed"
        )

    def clean(self):
        if self.kind == self.Kind.MEMBER:
            if not self.membership_id:
                raise ValidationError("Un détenteur joueur doit porter une adhésion.")
            if self.club_id and self.membership.club_id != self.club_id:
                raise ValidationError("Le détenteur doit porter le même club que le joueur.")
        else:
            if not (self.label or "").strip():
                raise ValidationError("Le nom du lieu est obligatoire.")
            if self.membership_id:
                raise ValidationError("Un lieu ne porte pas d'adhésion.")


class StockMovement(TenantModel):
    """Mouvement de stock (CDC 4.13 ; schema §7.2). Jamais modifié ni supprimé."""

    class MovementType(models.TextChoices):
        IN_PURCHASE = "in_purchase", "Achat"
        IN_DONATION = "in_donation", "Dotation"
        IN_RETURN = "in_return", "Retour"
        OUT_DISTRIBUTION = "out_distribution", "Distribution"
        OUT_LOAN = "out_loan", "Prêt pour un match"
        OUT_WEAR = "out_wear", "Usure"
        OUT_LOSS = "out_loss", "Perte"
        IN_OPENING = "in_opening", "Reprise du registre"
        IN_TRANSFER = "in_transfer", "Transfert reçu"
        OUT_TRANSFER = "out_transfer", "Transfert"
        OUT_DECOMMISSION = "out_decommission", "Déclassement"

    IN_TYPES = (
        MovementType.IN_PURCHASE,
        MovementType.IN_DONATION,
        MovementType.IN_RETURN,
        MovementType.IN_OPENING,
        MovementType.IN_TRANSFER,
    )
    OUT_TYPES = (
        MovementType.OUT_DISTRIBUTION,
        MovementType.OUT_LOAN,
        MovementType.OUT_WEAR,
        MovementType.OUT_LOSS,
        MovementType.OUT_TRANSFER,
        MovementType.OUT_DECOMMISSION,
    )
    TRANSFER_TYPES = (MovementType.IN_TRANSFER, MovementType.OUT_TRANSFER)
    # Types saisissables par POST movements/ (les autres passent par
    # transfers/ et decommissions/).
    MANUAL_TYPES = (
        MovementType.IN_PURCHASE,
        MovementType.IN_DONATION,
        MovementType.IN_RETURN,
        MovementType.IN_OPENING,
        MovementType.OUT_DISTRIBUTION,
        MovementType.OUT_LOAN,
        MovementType.OUT_WEAR,
        MovementType.OUT_LOSS,
    )
    # Entrées qui portent une provenance (registre de l'intendance §5).
    PROVENANCE_TYPES = (MovementType.IN_PURCHASE, MovementType.IN_DONATION, MovementType.IN_OPENING)

    class OriginKind(models.TextChoices):
        DONATION = "donation", "Don"
        CLUB_FUNDS = "club_funds", "Frais de l'équipe"
        UNKNOWN = "unknown", "Inconnue"
    # Joueur concerné affiché seulement pour ces types (fiche §4.4).
    MEMBERSHIP_ALLOWED_TYPES = (
        MovementType.OUT_DISTRIBUTION,
        MovementType.OUT_LOAN,
        MovementType.IN_RETURN,
        MovementType.OUT_LOSS,
    )

    club = _club_fk("stock_movements")
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.PositiveIntegerField()
    movement_date = models.DateField()
    reason = models.TextField(blank=True, default="")
    membership = models.ForeignKey(
        "clubs.Membership", null=True, blank=True, on_delete=models.PROTECT, related_name="stock_movements"
    )
    expense = models.ForeignKey(
        "treasury.Expense",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stock_movements",
        help_text="Achat rattaché à la dépense correspondante (CDC 4.13). Uniquement pour un « Achat ».",
    )
    match = models.ForeignKey(
        "sport.Match",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stock_movements",
        help_text="Sortie/retour d'équipements liés à un match (CDC 4.8, 4.13).",
    )
    holder = models.ForeignKey(
        Holder,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="movements",
        help_text="Entrée : qui reçoit ; sortie : chez qui le matériel sort. Vide = « Non localisé ».",
    )
    origin_kind = models.CharField(max_length=12, choices=OriginKind.choices, blank=True, default="")
    donor_membership = models.ForeignKey(
        "clubs.Membership", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    donor_name = models.CharField(max_length=120, blank=True, default="")
    acquisition_date = models.DateField(null=True, blank=True)
    acquisition_date_unknown = models.BooleanField(default=False)
    acquisition_date_note = models.CharField(max_length=60, blank=True, default="")
    condition_at_entry = models.CharField(max_length=10, choices=Article.Condition.choices, blank=True, default="")
    transfer_group = models.UUIDField(null=True, blank=True, db_index=True)
    decommission = models.ForeignKey(
        "logistics.Decommission", null=True, blank=True, on_delete=models.PROTECT, related_name="movements"
    )
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField()

    objects = AppendOnlyTenantManager()
    all_objects = models.Manager.from_queryset(AppendOnlyQuerySet)()

    class Meta(TenantModel.Meta):
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="stockmovement_quantity_gt_0"),
            models.CheckConstraint(
                condition=~Q(expense__isnull=False) | Q(movement_type="in_purchase"),
                name="stockmovement_expense_only_purchase",
            ),
            models.CheckConstraint(
                condition=Q(transfer_group__isnull=False, movement_type__in=["in_transfer", "out_transfer"])
                | (Q(transfer_group__isnull=True) & ~Q(movement_type__in=["in_transfer", "out_transfer"])),
                name="stockmovement_transfer_group_iff_transfer",
            ),
            models.CheckConstraint(
                condition=Q(decommission__isnull=False, movement_type="out_decommission")
                | (Q(decommission__isnull=True) & ~Q(movement_type="out_decommission")),
                name="stockmovement_decommission_iff_out_decommission",
            ),
        ]
        indexes = [
            models.Index(fields=["club", "article", "movement_date"], name="stockmovement_article_date_idx"),
            models.Index(fields=["club", "match"], name="stockmovement_match_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.movement_type} {self.quantity} / article {self.article_id}"

    @property
    def signed_quantity(self) -> int:
        return self.quantity if self.movement_type in self.IN_TYPES else -self.quantity

    def clean(self):
        if self.club_id and self.article_id and self.article.club_id != self.club_id:
            raise ValidationError("Le mouvement doit porter le même club que l'article.")
        if self.club_id and self.membership_id and self.membership.club_id != self.club_id:
            raise ValidationError("Le mouvement doit porter le même club que le joueur concerné.")
        if self.club_id and self.expense_id and self.expense.club_id != self.club_id:
            raise ValidationError("Le mouvement doit porter le même club que la dépense rattachée.")
        if self.club_id and self.match_id and self.match.club_id != self.club_id:
            raise ValidationError("Le mouvement doit porter le même club que le match rattaché.")
        if self.expense_id and self.movement_type != self.MovementType.IN_PURCHASE:
            raise ValidationError("Seul un mouvement « Achat » peut être rattaché à une dépense.")
        if self.match_id and self.movement_type not in (self.MovementType.OUT_LOAN, self.MovementType.IN_RETURN):
            raise ValidationError("Seuls un « Prêt pour un match » ou un « Retour » peuvent être rattachés à un match.")
        if self.membership_id and self.movement_type not in self.MEMBERSHIP_ALLOWED_TYPES:
            raise ValidationError("Ce type de mouvement n'accepte pas de joueur concerné.")
        if self.club_id and self.holder_id and self.holder.club_id != self.club_id:
            raise ValidationError("Le mouvement doit porter le même club que le détenteur.")
        if self.club_id and self.donor_membership_id and self.donor_membership.club_id != self.club_id:
            raise ValidationError("Le mouvement doit porter le même club que le donateur.")
        if self.club_id and self.decommission_id and self.decommission.club_id != self.club_id:
            raise ValidationError("Le mouvement doit porter le même club que le déclassement.")
        if (self.movement_type in self.TRANSFER_TYPES) != (self.transfer_group is not None):
            raise ValidationError("Un groupe de transfert est requis pour un transfert, et uniquement pour lui.")
        if (self.movement_type == self.MovementType.OUT_DECOMMISSION) != (self.decommission_id is not None):
            raise ValidationError("Un déclassement est requis pour une sortie « Déclassement », et uniquement pour elle.")
        has_provenance = bool(
            self.origin_kind
            or self.donor_membership_id
            or self.donor_name
            or self.acquisition_date
            or self.acquisition_date_unknown
            or self.acquisition_date_note
            or self.condition_at_entry
        )
        if has_provenance and self.movement_type not in self.PROVENANCE_TYPES:
            raise ValidationError(
                "La provenance ne s'applique qu'aux entrées de stock (achat, dotation, reprise du registre)."
            )
        if self.acquisition_date and self.movement_date and self.acquisition_date > self.movement_date:
            raise ValidationError("La date d'acquisition ne peut pas être postérieure à la date d'enregistrement.")

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise LogisticsImmutableError(
                "Un mouvement de stock est immuable après sa création (logistique.md §4.3, §12 point n° 5)."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LogisticsImmutableError(
            "Un mouvement de stock n'est jamais supprimé (logistique.md §4.3, §12 point n° 5)."
        )


class Decommission(TenantModel):
    """Signalement de déclassement, en deux temps (registre de l'intendance §7).

    Le signalement ne change pas le stock ; la sortie physique crée un
    mouvement ``out_decommission``. Jamais supprimé."""

    class Reason(models.TextChoices):
        WORN = "worn", "Usé"
        DAMAGED = "damaged", "Abîmé"
        UNUSABLE = "unusable", "Hors d'usage"
        OTHER = "other", "Autre"

    class Status(models.TextChoices):
        PENDING = "pending", "À déclasser"
        DONE = "done", "Déclassé"
        CANCELLED = "cancelled", "Annulé"

    club = _club_fk("decommissions")
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name="decommissions")
    holder = models.ForeignKey(Holder, null=True, blank=True, on_delete=models.PROTECT, related_name="decommissions")
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=10, choices=Reason.choices)
    reason_note = models.CharField(max_length=500, blank=True, default="")
    noted_on = models.DateField()
    noted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    exit_date = models.DateField(null=True, blank=True)
    exit_destination = models.CharField(max_length=120, blank=True, default="")
    exit_movement = models.OneToOneField(
        StockMovement, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    cancel_reason = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField()

    class Meta(TenantModel.Meta):
        verbose_name = "Déclassement"
        verbose_name_plural = "Déclassements"
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="decommission_quantity_gt_0"),
        ]
        indexes = [models.Index(fields=["club", "article", "status"], name="decomm_article_status_idx")]

    def __str__(self) -> str:  # pragma: no cover
        return f"Déclassement {self.quantity} / article {self.article_id}"

    def clean(self):
        if self.club_id and self.article_id and self.article.club_id != self.club_id:
            raise ValidationError("Le déclassement doit porter le même club que l'article.")
        if self.club_id and self.holder_id and self.holder.club_id != self.club_id:
            raise ValidationError("Le déclassement doit porter le même club que le détenteur.")

    def delete(self, *args, **kwargs):
        raise LogisticsImmutableError("Un déclassement n'est jamais supprimé : il peut seulement être annulé.")


class Inventory(TenantModel):
    """Inventaire trimestriel (CDC 4.13 ; schema §7.3)."""

    class Status(models.TextChoices):
        OPEN = "open", "En cours"
        CLOSED = "closed", "Clôturé"

    club = _club_fk("inventories")
    quarter_label = models.CharField(max_length=10, help_text="Ex. « 2026-Q3 ».")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    opened_at = models.DateTimeField()
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta(TenantModel.Meta):
        verbose_name = "Inventaire"
        verbose_name_plural = "Inventaires"
        constraints = [
            models.UniqueConstraint(fields=["club", "quarter_label"], name="inventory_unique_quarter_per_club"),
            models.CheckConstraint(
                condition=Q(status="open") | Q(closed_at__isnull=False, closed_by__isnull=False),
                name="inventory_closed_fields_required",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Inventaire {self.quarter_label} / club {self.club_id}"


class InventoryLine(TenantModel):
    """Ligne de comptage d'un inventaire (schema §7.3).

    Créée seulement au moment du comptage (un article non compté n'a pas
    de ligne, fiche d'écran §4.10 : « un champ laissé vide = article non
    compté »).
    """

    class DiscrepancyReason(models.TextChoices):
        THEFT = "theft", "Vol"
        WEAR = "wear", "Usure"
        OVERSIGHT = "oversight", "Oubli"
        LOSS = "loss", "Perte"

    club = _club_fk("inventory_lines")
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name="lines")
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name="inventory_lines")
    theoretical_quantity = models.IntegerField(help_text="Instantané figé au moment du comptage.")
    physical_quantity = models.IntegerField()
    discrepancy = models.IntegerField(help_text="physical_quantity - theoretical_quantity, figé.")
    discrepancy_reason = models.CharField(max_length=10, choices=DiscrepancyReason.choices, blank=True, default="")
    justified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    justified_at = models.DateTimeField(null=True, blank=True)
    counted_at = models.DateTimeField()
    counted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta(TenantModel.Meta):
        verbose_name = "Ligne d'inventaire"
        verbose_name_plural = "Lignes d'inventaire"
        constraints = [
            models.UniqueConstraint(fields=["inventory", "article"], name="inventoryline_unique_inventory_article"),
            models.CheckConstraint(condition=Q(physical_quantity__gte=0), name="inventoryline_physical_gte_0"),
            models.CheckConstraint(condition=Q(theoretical_quantity__gte=0), name="inventoryline_theoretical_gte_0"),
            # Pas de contrainte DB « écart -> cause obligatoire » : c'est une
            # règle de *workflow* (contrôlée par
            # ``apps.logistics.services.can_close_inventory``, avant la
            # clôture), pas un invariant de données -- une ligne comptée
            # mais pas encore justifiée est un état normal et temporaire
            # tant que l'inventaire reste ouvert.
            models.CheckConstraint(
                condition=~Q(discrepancy_reason="")
                | Q(justified_by__isnull=True, justified_at__isnull=True),
                name="inventoryline_justified_requires_reason",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Ligne {self.article_id} / inventaire {self.inventory_id}"

    @property
    def is_justified(self) -> bool:
        return self.discrepancy == 0 or self.justified_at is not None

    def clean(self):
        if self.club_id and self.inventory_id and self.inventory.club_id != self.club_id:
            raise ValidationError("La ligne doit porter le même club que l'inventaire.")
        if self.club_id and self.article_id and self.article.club_id != self.club_id:
            raise ValidationError("La ligne doit porter le même club que l'article.")
        if self.theoretical_quantity is not None and self.physical_quantity is not None:
            expected = self.physical_quantity - self.theoretical_quantity
            if self.discrepancy != expected:
                raise ValidationError("L'écart doit être égal au stock compté moins le stock théorique.")
