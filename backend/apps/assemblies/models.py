"""Modeles de l'app assemblies : assemblees generales (CDC 4.15).

Sources : docs/lot0/schema-donnees.md §9 ; docs/ecrans/assemblees-page-ag.md ;
10.2 n 18, 24, 28. Voir CLAUDE.md section 5 : toute table privee porte
``club`` et n'est accedee que via les managers tenant-aware de
``apps.core`` (``TenantModel``).

Ecarts assumes par rapport au schema figé de Lot 0 (additifs, non
destructifs, signales au compte rendu de la tache 4.5) :

- ``Assembly.reminder_sent_at`` : champ technique absent de
  schema-donnees.md §9.1, necessaire pour que la commande de gestion du
  rappel la veille (assemblees-page-ag.md §4.7) reste idempotente -- meme
  principe que ``MembershipApplication.sponsor_reminder_sent_at``
  (apps.clubs.models).
- ``Decision`` porte une contrainte d'unicite ``(agenda_item)`` : le
  schema ne la déclare pas explicitement, mais l'ecran (§4.2 « Decisions »)
  affiche « un bloc par point » -- un seul vote enregistre par point
  d'ordre du jour, modifiable (« Saisir le vote » ouvre la meme modale).
  Decision technique, a confirmer avec le client si un point venait a
  necessiter plusieurs votes successifs.

Point ouvert (assemblees-page-ag.md §7, plusieurs titulaires du poste de
VP, 10.2 n° 24) : ``Minutes`` ne porte qu'UN champ ``vp_signed_by``/
``vp_signed_at`` (schema §9.5, non modifie ici : ce document fait foi pour
la structure de donnees du Lot 0). La position appliquee par
``apps.assemblies.services.sign_minutes`` est donc necessairement « un
seul Vice-president suffit » -- pas « tous les titulaires » -- puisque le
schema ne prevoit qu'un seul emplacement de signature. A confirmer avec le
client ; une extension du schema (table de signatures multiples) serait
necessaire pour appliquer la position la plus restrictive.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TenantModel
from apps.core.storage import private_storage


class Assembly(TenantModel):
    class AssemblyType(models.TextChoices):
        ORDINARY = "ordinary", "Ordinaire"
        EXTRAORDINARY = "extraordinary", "Extraordinaire"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Convoquee"
        HELD = "held", "Tenue"
        CANCELLED = "cancelled", "Annulee"

    assembly_type = models.CharField(max_length=15, choices=AssemblyType.choices)
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField()
    location = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    reminder_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Rappel la veille deja envoye (idempotence de la commande de gestion, champ additif).",
    )

    class Meta(TenantModel.Meta):
        verbose_name = "Assemblee generale"
        verbose_name_plural = "Assemblees generales"
        ordering = ["-scheduled_date", "-scheduled_time"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.assembly_type} {self.scheduled_date} (club {self.club_id})"


class AgendaItem(TenantModel):
    assembly = models.ForeignKey(Assembly, on_delete=models.CASCADE, related_name="agenda_items")
    order = models.PositiveIntegerField()
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Point de l'ordre du jour"
        verbose_name_plural = "Points de l'ordre du jour"
        ordering = ["assembly_id", "order"]
        constraints = [
            models.UniqueConstraint(fields=["assembly", "order"], name="assemblies_agendaitem_unique_order"),
            models.CheckConstraint(condition=Q(order__gt=0), name="assemblies_agendaitem_order_gt_0"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.order}. {self.title}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.assembly_id and self.club_id and self.assembly.club_id != self.club_id:
            raise ValidationError("Le point d'ordre du jour doit porter le meme club que l'assemblee.")


class AssemblyAttendance(TenantModel):
    assembly = models.ForeignKey(Assembly, on_delete=models.CASCADE, related_name="attendances")
    membership = models.ForeignKey("clubs.Membership", on_delete=models.CASCADE, related_name="+")
    checked_in_at = models.DateTimeField(null=True, blank=True)
    present = models.BooleanField(default=False)

    class Meta(TenantModel.Meta):
        verbose_name = "Presence en AG"
        verbose_name_plural = "Presences en AG"
        constraints = [
            models.UniqueConstraint(fields=["assembly", "membership"], name="assemblies_attendance_unique"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"AG {self.assembly_id} / adhesion {self.membership_id}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.assembly_id and self.club_id and self.assembly.club_id != self.club_id:
            raise ValidationError("La presence doit porter le meme club que l'assemblee.")
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("La presence doit porter le meme club que l'adhesion.")


class Decision(TenantModel):
    assembly = models.ForeignKey(Assembly, on_delete=models.CASCADE, related_name="decisions")
    agenda_item = models.ForeignKey(AgendaItem, on_delete=models.CASCADE, related_name="decision")
    votes_for = models.PositiveIntegerField(default=0)
    votes_against = models.PositiveIntegerField(default=0)
    votes_abstain = models.PositiveIntegerField(default=0)
    outcome = models.TextField()
    linked_object_type = models.CharField(max_length=60, blank=True)
    linked_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    recorded_at = models.DateTimeField()

    class Meta(TenantModel.Meta):
        verbose_name = "Decision d'AG"
        verbose_name_plural = "Decisions d'AG"
        constraints = [
            models.UniqueConstraint(fields=["agenda_item"], name="assemblies_decision_one_per_agenda_item"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Decision point {self.agenda_item_id}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.assembly_id and self.club_id and self.assembly.club_id != self.club_id:
            raise ValidationError("La decision doit porter le meme club que l'assemblee.")
        if self.agenda_item_id and self.assembly_id and self.agenda_item.assembly_id != self.assembly_id:
            raise ValidationError("La decision doit porter sur un point de la meme assemblee.")


def _minutes_pdf_upload_to(instance: "Minutes", filename: str) -> str:
    return f"assemblies/minutes/{instance.assembly_id}/{filename}"


class Minutes(TenantModel):
    assembly = models.OneToOneField(Assembly, on_delete=models.CASCADE, primary_key=True, related_name="minutes")
    content = models.TextField(blank=True)
    president_signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    president_signed_at = models.DateTimeField(null=True, blank=True)
    vp_signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    vp_signed_at = models.DateTimeField(null=True, blank=True)
    vp_vacant_at_signature = models.BooleanField(default=False)
    vp_role_held_by_president = models.BooleanField(
        default=False,
        help_text=(
            "Vrai quand vp_vacant_at_signature l'est parce que le seul "
            "titulaire actif du role Vice-president est le President "
            "signataire (cumul de roles) -- distinct d'une vacance reelle "
            "du poste. Sert uniquement a corriger le texte affiche sur le "
            "PV et a l'ecran (docs/annexes/modeles-documents.md §3.4 cas 2, "
            "point ouvert §8 n. 5 : le libelle exact n'est pas tranche par "
            "le client, seul le cas objectivement faux -- 'poste vacant' "
            "affiche alors que le poste est occupe -- est corrige ici)."
        ),
    )
    pdf_file = models.FileField(
        upload_to=_minutes_pdf_upload_to, storage=private_storage, null=True, blank=True
    )
    generated_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Proces-verbal d'AG"
        verbose_name_plural = "Proces-verbaux d'AG"

    def __str__(self) -> str:  # pragma: no cover
        return f"PV AG {self.assembly_id}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.assembly_id and self.club_id and self.assembly.club_id != self.club_id:
            raise ValidationError("Le PV doit porter le meme club que l'assemblee.")

    @property
    def is_complete(self) -> bool:
        if self.president_signed_by_id is None:
            return False
        if self.vp_vacant_at_signature:
            return True
        return self.vp_signed_by_id is not None
