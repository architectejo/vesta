"""Modeles de l'app medical (Lot 4, tache 4.2).

Sources : CDC 4.12 (module medical, en entier), 2.4 (matrice, ligne
« Fiches de sante et blessures »), 6.7 (documents medicaux), 7.5
(consentement, journalisation des consultations) ; 10.2 n15, n16, n17 ;
docs/lot0/schema-donnees.md §6 (`HealthRecord`, `Injury`,
`InjuryFollowUp`, regle `can_president_read_full_record`) ;
docs/ecrans/medical.md (contrat de visibilite N0/N1/N2, §2 ; contrat
`get_unfitness_reason`, §2.4).

Toute regle metier (visibilite, journalisation, aptitude, consentement)
vit dans ``apps.medical.services`` -- ce module ne porte que la
structure des donnees et les coherences structurelles (meme club, meme
adhesion...), conformement a CLAUDE.md section 5.

Deux ajouts au-dela du schema documente, justifies ci-dessous :
- ``HealthRecord.self_declaration_updated_at`` : la spec d'ecran (§4.2,
  §4.10) affiche « Mise a jour par le joueur le {date} » a cote de la
  declaration du joueur -- absent du schema §6.1, necessaire pour ce
  texte.
- ``Injury.occurred_time``/``occurred_minute`` : la modale « Declarer une
  blessure » (medical.md §4.1) distingue le moment de la blessure
  (heure pour une seance/hors seance ou match, minute pour un match) de
  ``reported_at`` (l'heure de la DECLARATION) -- absent du schema §6.2,
  qui ne detaille pas separement ce champ. ``Injury`` n'a par ailleurs
  aucun champ ``occurred_at`` documente : ces deux champs le remplacent
  precisement pour ce besoin d'affichage (§4.3 « Survenue : ... »).
- ``MedicalDocument`` : piece jointe medicale (CDC 6.7 : « [...] et
  documents medicaux : stockes hors du dossier public, servis
  uniquement par une vue authentifiee qui verifie le club et le role »).
  Absente de docs/lot0/schema-donnees.md §6 (point ouvert 11 de
  docs/ecrans/medical.md §11 : « Aucun champ ajoute. A decider. ») et de
  la spec d'ecran validee (aucune modale ne l'expose) : ajoutee ici a la
  demande explicite de la tache 4.2, en respectant la meme regle de
  visibilite N2 (Medecin, joueur concerne, President avec consentement
  actif) que le reste du dossier -- voir ``apps.medical.services`` et
  ``apps.medical.views.MedicalDocumentDownloadView``. Aucune modale
  d'interface n'est construite pour cet ajout (hors perimetre back-end
  de cette tache) : signale au compte rendu comme extension non
  couverte par un ecran valide.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.clubs.models import Membership
from apps.core.models import TenantModel
from apps.core.storage import private_storage
from apps.core.validators import validate_image_or_pdf, validate_upload_size


class HealthRecord(TenantModel):
    """Fiche de sante (CDC 4.12 ; schema §6.1). Une par ``Membership``."""

    class BloodGroup(models.TextChoices):
        A_POS = "A+", "A+"
        A_NEG = "A-", "A-"
        B_POS = "B+", "B+"
        B_NEG = "B-", "B-"
        AB_POS = "AB+", "AB+"
        AB_NEG = "AB-", "AB-"
        O_POS = "O+", "O+"
        O_NEG = "O-", "O-"

    class FitnessStatus(models.TextChoices):
        FIT = "fit", "Apte"
        FIT_WITH_RESTRICTION = "fit_with_restriction", "Apte avec restriction"
        UNFIT = "unfit", "Inapte"

    membership = models.OneToOneField(
        Membership, primary_key=True, on_delete=models.PROTECT, related_name="health_record"
    )
    blood_group = models.CharField(max_length=3, choices=BloodGroup.choices, blank=True)
    allergies = models.TextField(blank=True)
    medical_history = models.TextField(blank=True)
    ongoing_treatments = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=160, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    self_declaration = models.TextField(blank=True, help_text="Declaration du joueur sur son etat de sante.")
    self_declaration_updated_at = models.DateTimeField(
        null=True, blank=True, help_text="Ajout au schema : affiche a cote de la declaration (medical.md §4.2)."
    )
    consent_given_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Consentement au traitement des donnees de sante (CDC 4.12, 7.5), obligatoire avant toute ecriture clinique du Medecin.",
    )
    fitness_status = models.CharField(max_length=21, choices=FitnessStatus.choices, default=FitnessStatus.FIT)
    fitness_return_date = models.DateField(null=True, blank=True)
    fitness_set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "Nullable en pratique (deviation documentee du schema §6.1, qui le dit "
            "obligatoire) : une fiche existe des la premiere lecture/ecriture "
            "(creation paresseuse) avant meme qu'un Medecin n'ait fixe l'aptitude -- "
            "l'aptitude par defaut (Apte) n'a alors ete « fixee » par personne."
        ),
    )
    fitness_set_at = models.DateTimeField(null=True, blank=True)
    president_access_granted_at = models.DateTimeField(
        null=True, blank=True, help_text="Consentement du joueur pour un acces complet du President (10.2 n15)."
    )
    president_access_revoked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Fiche de sante"
        verbose_name_plural = "Fiches de sante"

    def __str__(self) -> str:  # pragma: no cover
        return f"Fiche de sante {self.membership_id}"

    def clean(self):
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("La fiche de sante doit porter le meme club que l'adhesion.")
        if self.fitness_status == self.FitnessStatus.UNFIT and self.fitness_return_date is None:
            # Autorise : « Inapte, date de retour non fixee » (medical.md §2.4). Pas d'erreur ici.
            pass
        if self.fitness_status != self.FitnessStatus.UNFIT and self.fitness_return_date is not None:
            # La date de retour n'a de sens que pour un joueur inapte -- coherence
            # structurelle uniquement, aucune regle metier (celle-ci vit dans
            # apps.medical.services.update_fitness).
            pass


class Injury(TenantModel):
    """Blessure (CDC 4.12 ; schema §6.2)."""

    class Severity(models.TextChoices):
        MILD = "mild", "Legere"
        MODERATE = "moderate", "Moderee"
        SEVERE = "severe", "Grave"

    class Referral(models.TextChoices):
        REST = "rest", "Repos"
        CONSULTATION = "consultation", "Consultation"
        HOSPITAL = "hospital", "Hopital"

    class Status(models.TextChoices):
        OPEN = "open", "En cours"
        RESOLVED = "resolved", "Retour declare"

    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="injuries")
    event = models.ForeignKey(
        "sport.Event",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Seance ou match ou la blessure est survenue (vide : hors seance ou match).",
    )
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reported_at = models.DateTimeField()
    occurred_time = models.TimeField(
        null=True, blank=True, help_text="Heure de survenue (seance ou hors seance/match) -- voir docstring du module."
    )
    occurred_minute = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Minute de match (0-130) -- voir docstring du module."
    )
    circumstances = models.TextField(help_text="Medecin + joueur uniquement (N2).")
    location_on_body = models.CharField(max_length=160, blank=True, help_text="Medecin + joueur uniquement (N2).")
    severity = models.CharField(max_length=8, choices=Severity.choices, blank=True)
    on_site_care = models.TextField(blank=True)
    referral = models.CharField(max_length=12, choices=Referral.choices, blank=True)
    estimated_days_out = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    doctor_completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    doctor_completed_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Blessure"
        verbose_name_plural = "Blessures"
        ordering = ["-reported_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(estimated_days_out__isnull=True)
                | (Q(estimated_days_out__gte=0) & Q(estimated_days_out__lte=365)),
                name="injury_estimated_days_out_range",
            ),
            models.CheckConstraint(
                condition=Q(occurred_minute__isnull=True)
                | (Q(occurred_minute__gte=0) & Q(occurred_minute__lte=130)),
                name="injury_occurred_minute_range",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Blessure {self.pk} - {self.membership_id}"

    def clean(self):
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("La blessure doit porter le meme club que l'adhesion.")
        if self.event_id and self.club_id and self.event.club_id != self.club_id:
            raise ValidationError("La blessure doit porter le meme club que l'evenement.")
        if self.status == self.Status.RESOLVED and (self.resolved_by_id is None or self.resolved_at is None):
            raise ValidationError("Une blessure « Retour declare » doit porter un auteur et une date de retour.")
        if (self.doctor_completed_by_id is None) != (self.doctor_completed_at is None):
            raise ValidationError("Le bilan medical doit porter a la fois un auteur et une date, ou aucun des deux.")


class InjuryFollowUp(TenantModel):
    """Entree de suivi d'une blessure (CDC 4.12 etape 4 ; schema §6.3).

    Immuable une fois creee (medical.md §4.8, point ouvert 7, position
    provisoire retenue : « pas de modification ni de suppression, on
    ajoute une nouvelle entree ») : aucune methode de service de
    modification/suppression n'existe dans ``apps.medical.services``.
    """

    injury = models.ForeignKey(Injury, on_delete=models.PROTECT, related_name="followups")
    entry_date = models.DateField()
    note = models.TextField(help_text="Evolution, soins, examens. Medecin + joueur uniquement (N2).")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Entree de suivi"
        verbose_name_plural = "Entrees de suivi"
        ordering = ["-entry_date", "-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"Suivi {self.pk} - blessure {self.injury_id}"

    def clean(self):
        if self.injury_id and self.club_id and self.injury.club_id != self.club_id:
            raise ValidationError("L'entree de suivi doit porter le meme club que la blessure.")


class MedicalDocument(TenantModel):
    """Piece jointe medicale (CDC 6.7 ; ajout hors schema, voir docstring
    du module). Stockage prive exclusivement (``apps.core.storage.private_storage``),
    jamais servie autrement que par une vue authentifiee (CLAUDE.md regle n10)."""

    injury = models.ForeignKey(
        Injury, null=True, blank=True, on_delete=models.PROTECT, related_name="documents"
    )
    health_record = models.ForeignKey(
        HealthRecord, null=True, blank=True, on_delete=models.PROTECT, related_name="documents"
    )
    file = models.FileField(
        upload_to="medical/documents/",
        storage=private_storage,
        validators=[validate_upload_size, validate_image_or_pdf],
    )
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Document medical"
        verbose_name_plural = "Documents medicaux"
        ordering = ["-uploaded_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(injury__isnull=False, health_record__isnull=True)
                    | Q(injury__isnull=True, health_record__isnull=False)
                ),
                name="medical_document_exactly_one_parent",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Document medical {self.pk}"

    def clean(self):
        if bool(self.injury_id) == bool(self.health_record_id):
            raise ValidationError("Un document medical doit etre rattache a une blessure OU a une fiche, jamais les deux ni aucun.")
        if self.injury_id and self.club_id and self.injury.club_id != self.club_id:
            raise ValidationError("Le document doit porter le meme club que la blessure.")
        if self.health_record_id and self.club_id and self.health_record.club_id != self.club_id:
            raise ValidationError("Le document doit porter le meme club que la fiche de sante.")
