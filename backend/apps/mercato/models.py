"""Modeles de l'app mercato (CDC 4.14 ; tâche 4.4).

Sources : docs/ecrans/mercato.md (spec validée, révision Lot 4) ;
docs/lot0/schema-donnees.md §8 ; CLAUDE.md section 5.

``TransferOffer`` et ``MercatoThread``/``MercatoMessage`` sont
l'**exception documentée** à ``apps.core.models.TenantModel`` (schema
§1.2) : ces entités référencent DEUX clubs (origine et destinataire), pas
un seul « club actif ». Elles restent donc des ``models.Model`` classiques
-- l'isolation est assurée par les services/vues (``apps.mercato.services``/
``apps.mercato.permissions``), jamais par un manager tenant-aware qui
n'aurait de toute façon aucun sens ici (CLAUDE.md règle n8, J7).

**Messagerie inter-clubs : contradiction schéma/CDC, tranchée à titre
provisoire (position la plus prudente).** ``docs/lot0/schema-donnees.md``
§8.2 ouvre la lecture d'un ``MercatoThread`` à « tous les membres de
``club_a`` ou ``club_b`` » ; le CDC 4.14 et ``docs/ecrans/mercato.md``
§2.1 point 5 la réservent au Président et au Directeur sportif de chaque
club. Appliqué ici : le contrôle d'accès (``apps.mercato.services``/
``permissions``) restreint la lecture et l'écriture d'un fil au Président
et au DS de ``club_a`` ou ``club_b``, jamais à « tout membre ». Signalé
comme non définitivement tranché par le client (voir compte rendu).
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.storage import private_storage


class TransferOffer(models.Model):
    """Offre de transfert (CDC 4.14 ; règle non négociable n° 5 ; schema §8.1)."""

    class Status(models.TextChoices):
        SENT = "sent", "En attente"
        ACCEPTED_BY_PLAYER = "accepted_by_player", "Acceptée"
        DECLINED_BY_PLAYER = "declined_by_player", "Refusée"
        BLOCKED_DEBT = "blocked_debt", "Bloquée (dette)"
        COMPLETED = "completed", "Transfert effectué"
        CANCELLED = "cancelled", "Annulée"

    origin_club = models.ForeignKey(
        "clubs.Club", on_delete=models.PROTECT, related_name="+", help_text="Club A, club actuel du joueur."
    )
    target_club = models.ForeignKey(
        "clubs.Club", on_delete=models.PROTECT, related_name="+", help_text="Club B, club offreur."
    )
    target_membership = models.ForeignKey(
        "clubs.Membership",
        on_delete=models.PROTECT,
        related_name="transfer_offers",
        help_text="Joueur visé ; membership.club doit être origin_club.",
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Président ou Directeur sportif de target_club.",
    )
    message = models.TextField()
    conditions = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SENT)
    player_decision_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    player_decision_at = models.DateTimeField(null=True, blank=True)
    debt_checked_at = models.DateTimeField(null=True, blank=True)
    debt_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quitus_generated_at = models.DateTimeField(null=True, blank=True)
    quitus_file = models.FileField(
        upload_to="mercato/quitus/",
        null=True,
        blank=True,
        storage=private_storage,
        help_text="Quitus numérique (PDF), jamais servi directement (CDC 6.7).",
    )
    membership_fee_due_at_target = models.BooleanField(default=True)
    new_membership = models.ForeignKey(
        "clubs.Membership",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Adhésion créée au club B à l'issue du transfert (ajout pragmatique, hors schéma d'origine).",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        verbose_name = "Offre de transfert"
        verbose_name_plural = "Offres de transfert"
        constraints = [
            models.CheckConstraint(condition=~Q(origin_club=models.F("target_club")), name="transferoffer_clubs_differ"),
            models.CheckConstraint(condition=~Q(message=""), name="transferoffer_message_required"),
            models.CheckConstraint(
                condition=~Q(status="blocked_debt") | Q(debt_amount__isnull=False),
                name="transferoffer_blocked_requires_amount",
            ),
        ]
        indexes = [
            models.Index(fields=["origin_club", "status"], name="transferoffer_origin_idx"),
            models.Index(fields=["target_club", "status"], name="transferoffer_target_idx"),
            models.Index(fields=["target_membership", "status"], name="transferoffer_member_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Offre {self.pk} : {self.origin_club_id} -> {self.target_club_id}"

    def clean(self):
        if self.target_membership_id and self.origin_club_id and self.target_membership.club_id != self.origin_club_id:
            raise ValidationError("Le joueur visé doit appartenir au club d'origine de l'offre.")
        if self.origin_club_id and self.target_club_id and self.origin_club_id == self.target_club_id:
            raise ValidationError("Le club d'origine et le club destinataire doivent être différents.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MercatoThread(models.Model):
    """Fil de messagerie entre deux clubs.

    Lecture/écriture restreintes au Président et au DS de ``club_a`` ou
    ``club_b`` (voir docstring du module -- position provisoire, la plus
    prudente, appliquée à la contradiction schéma/CDC)."""

    club_a = models.ForeignKey("clubs.Club", on_delete=models.PROTECT, related_name="+")
    club_b = models.ForeignKey("clubs.Club", on_delete=models.PROTECT, related_name="+")
    subject = models.CharField(max_length=160, blank=True, default="")
    transfer_offer = models.ForeignKey(
        TransferOffer, null=True, blank=True, on_delete=models.SET_NULL, related_name="threads"
    )
    created_at = models.DateTimeField()

    class Meta:
        verbose_name = "Fil mercato"
        verbose_name_plural = "Fils mercato"
        constraints = [
            models.CheckConstraint(condition=~Q(club_a=models.F("club_b")), name="mercatothread_clubs_differ"),
            models.UniqueConstraint(fields=["club_a", "club_b"], name="mercatothread_unique_pair"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Fil {self.club_a_id} <-> {self.club_b_id}"

    def clean(self):
        if self.club_a_id and self.club_b_id and self.club_a_id == self.club_b_id:
            raise ValidationError("Les deux clubs d'un fil de messagerie doivent être différents.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def other_club_id(self, club_id: int) -> int:
        return self.club_b_id if club_id == self.club_a_id else self.club_a_id


class MercatoMessage(models.Model):
    """Message d'un fil mercato (schema §8.2).

    ``club`` est dénormalisé depuis le club de l'expéditeur au moment de
    l'envoi (schema §1.2) : filtrage direct, ne détermine jamais seul le
    contrôle d'accès (voir ``apps.mercato.services``)."""

    club = models.ForeignKey("clubs.Club", on_delete=models.PROTECT, related_name="+", db_index=True)
    thread = models.ForeignKey(MercatoThread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    sent_at = models.DateTimeField()
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Message mercato"
        verbose_name_plural = "Messages mercato"
        constraints = [models.CheckConstraint(condition=~Q(body=""), name="mercatomessage_body_required")]
        indexes = [models.Index(fields=["thread", "sent_at"], name="mercatomessage_thread_sent_idx")]

    def __str__(self) -> str:  # pragma: no cover
        return f"Message {self.pk} / fil {self.thread_id}"

    def clean(self):
        if self.thread_id and self.club_id and self.club_id not in (self.thread.club_a_id, self.thread.club_b_id):
            raise ValidationError("Le club de l'expéditeur doit être l'un des deux clubs du fil.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
