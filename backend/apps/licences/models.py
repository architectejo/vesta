"""Modeles de l'app licences (CDC 1.4, 2.5, 4.18, 5.4 ; 10.2 n19/n20/n26 ;
tache 1.8) : `Licence`, `LicenceEvent` (historique) et `SupportSession`
(sessions de support en Ghost Mode).

Portee plateforme, geree exclusivement par le Superuser : **pas** de
`TenantModel` ici (schema-donnees.md §1.2 le liste explicitement parmi
les exceptions -- « le club ne modifie jamais sa propre licence », donc
aucun gestionnaire tenant-aware cote club n'est necessaire). Meme choix
pour `LicenceEvent`/`SupportSession` : ce sont des entites de l'espace
Superuser, jamais lues/ecrites par un club via son "club actif".

Decision actee du 25/09/2026 (10.2 n20) : aucune formule ni tarif au
MVP. Une licence est definie uniquement par ses dates de debut et de
fin, saisies par le Superuser. **Aucun modele `LicencePlan`** : voir
docs/lot0/schema-donnees.md §4.4 pour la contrainte de migration
additive (jamais destructive) a respecter le jour ou des formules
seront ajoutees.
"""

from __future__ import annotations

import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Licence(models.Model):
    """Licence d'un club : dates de debut/fin uniquement (schema §4.5).

    Cycle de vie : essai -> active -> expiree -> suspendue -> resiliee
    (CDC 1.4). Une licence suspendue bloque l'acces du club (controle
    d'acces applicatif, pas un changement de `Club.status`) ; seule
    l'expiration au-dela de la periode de grace fait passer
    `Club.status = read_only` (10.2 n19). Logique de service (transitions,
    blocage d'acces, verifications automatiques) implementee dans
    `apps.licences.services` et `apps.core.permissions.HasUsableLicence`
    (tache 1.8) -- hors perimetre de la seule tache 1.2 qui a introduit ce
    modele.
    """

    class Status(models.TextChoices):
        TRIAL = "trial", "Essai"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expiree"
        SUSPENDED = "suspended", "Suspendue"
        TERMINATED = "terminated", "Resiliee"

    club = models.ForeignKey(
        "clubs.Club",
        on_delete=models.CASCADE,
        related_name="licences",
        help_text="Portee plateforme : lecture/ecriture reservees au Superuser.",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TRIAL)
    start_date = models.DateField(help_text="Seule borne de debut, saisie par le Superuser (10.2 n20).")
    end_date = models.DateField(help_text="Seule borne de fin, saisie par le Superuser a chaque attribution/prolongation.")
    grace_period_days = models.PositiveIntegerField(default=15)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "Superuser a l'origine de la creation/gestion de cette licence "
            "(CDC 2.5). Vide UNIQUEMENT pour la licence d'essai creee "
            "automatiquement par l'assistant de creation de club en "
            "libre-service (docs/ecrans/clubs-creation.md §5 ; 10.2 n1/n20) : "
            "aucun Superuser n'intervient dans ce parcours -- l'acteur reel "
            "(le fondateur du club) est neanmoins trace dans l'AuditLog par "
            "`apps.clubs.club_creation.create_club_with_founder`, qui ne peut "
            "simplement pas remplir ce champ (reserve au Superuser par "
            "`clean()` ci-dessous). Toute action ULTERIEURE sur cette licence "
            "(activer, prolonger, suspendre...) reste exclusivement l'oeuvre "
            "d'un Superuser, comme avant."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Licence"
        verbose_name_plural = "Licences"
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="licence_end_after_start"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Licence club {self.club_id} ({self.status})"

    def clean(self):
        if self.created_by_id and not getattr(self.created_by, "is_superuser", False):
            raise ValidationError("Une licence est creee/geree uniquement par un Superuser (CDC 2.5).")


class LicenceEvent(models.Model):
    """Historique d'une licence (CDC 2.5 « historique » ; schema §4.6).

    Journal METIER de la licence, distinct de `apps.audit.models.AuditLog`
    (le journal generique de la plateforme) : les deux ont un role
    different (voir docstring de `apps.licences.services`), ce n'est pas
    une duplication au sens CLAUDE.md regle n6.

    ``event_type`` reprend EXACTEMENT l'enumeration du schema (§4.6) :
    aucune valeur "expiree" n'y figure -- l'expiration automatique d'une
    licence (`apps.licences.services.process_licence_expirations`) ne cree
    donc volontairement aucune ligne ici (voir la docstring de cette
    fonction pour la justification complete).
    """

    class EventType(models.TextChoices):
        CREATED = "created", "Creee"
        ACTIVATED = "activated", "Activee"
        EXTENDED = "extended", "Prolongee"
        SUSPENDED = "suspended", "Suspendue"
        RESUMED = "resumed", "Reprise"
        TERMINATED = "terminated", "Resiliee"
        REMINDER_SENT = "reminder_sent", "Relance envoyee"

    licence = models.ForeignKey(Licence, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    event_date = models.DateTimeField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Superuser a l'origine de l'action. Vide pour une relance automatique (schema §4.6).",
    )
    note = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Evenement de licence"
        verbose_name_plural = "Evenements de licence"
        ordering = ["-event_date", "-id"]
        indexes = [models.Index(fields=["licence", "event_date"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.event_type} / licence {self.licence_id}"

    def clean(self):
        if self.actor_id and not getattr(self.actor, "is_superuser", False):
            raise ValidationError(
                "L'acteur d'un evenement de licence est toujours un Superuser (CDC 2.5)."
            )


class SupportSession(models.Model):
    """Session de support en Ghost Mode (CDC 4.18, 5.4 ; schema §13.1 ; tache 1.8).

    Toute action effectuee par ``superuser`` sur des donnees de ``club``
    pendant ``[started_at, expires_at ou ended_at]`` doit ecrire une
    ``AuditLog`` avec ``acted_as_ghost=True``/``support_session_id``
    renseigne -- voir ``apps.core.ghost_context``/
    ``apps.core.authentication.TenantJWTAuthentication`` pour le mecanisme
    qui l'automatise, et ``apps.licences.services`` pour le cycle de vie
    complet (demarrage, fin anticipee, validite).

    ``expires_at`` est **calcule**, jamais saisi ni modifiable de
    l'exterieur (schema §13.1 : « calcule = started_at + 60 min ») :
    recalcule systematiquement dans :meth:`save` a partir de
    ``started_at``, quelle que soit la valeur transmise par l'appelant.
    """

    club = models.ForeignKey(
        "clubs.Club",
        on_delete=models.CASCADE,
        related_name="support_sessions",
        help_text="Club sur lequel porte l'intervention (schema §13.1).",
    )
    superuser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="support_sessions",
        help_text="Toujours `is_superuser=True` (verifie par `clean()` ci-dessous).",
    )
    reason = models.TextField(
        blank=True,
        help_text=(
            "Motif obligatoire (CDC 4.18) -- `blank=True` au niveau du champ "
            "pour laisser `clean()` ci-dessous produire un message francais "
            "unique et explicite, plutot que de dupliquer l'erreur generique "
            "de Django sur un champ vide."
        ),
    )
    started_at = models.DateTimeField()
    expires_at = models.DateTimeField(
        editable=False,
        help_text="Calcule = started_at + 60 minutes (CDC 4.18). Jamais modifiable directement.",
    )
    ended_at = models.DateTimeField(null=True, blank=True, help_text="Fin anticipee (schema §13.1).")

    MAX_DURATION = datetime.timedelta(minutes=60)

    class Meta:
        verbose_name = "Session de support"
        verbose_name_plural = "Sessions de support"
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["club", "started_at"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"Support club {self.club_id} par {self.superuser_id} ({self.started_at})"

    def clean(self):
        if self.superuser_id and not getattr(self.superuser, "is_superuser", False):
            raise ValidationError(
                "Une session de support est toujours ouverte par un Superuser (CDC 2.5, 4.18)."
            )
        if not (self.reason or "").strip():
            raise ValidationError("Le motif de la session de support est obligatoire (CDC 4.18).")
        if self.ended_at is not None and self.started_at is not None and self.ended_at < self.started_at:
            raise ValidationError("La fin anticipee ne peut pas preceder le debut de la session.")

    def save(self, *args, **kwargs):
        if self.started_at is None:
            self.started_at = timezone.now()
        # Toujours recalcule : `expires_at` n'est jamais une valeur de
        # confiance transmise par l'appelant (schema §13.1).
        self.expires_at = self.started_at + self.MAX_DURATION
        self.full_clean()
        super().save(*args, **kwargs)
