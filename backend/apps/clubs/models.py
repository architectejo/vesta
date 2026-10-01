"""Modeles de l'app clubs : club, parametres, saisons et adhesions.

Sources : CDC 2.1-2.5, 4.1, 4.3, 6.3-6.4 ; docs/lot0/schema-donnees.md
§3 (comptes et adhesion) et §4 (club/licence/parametres).

`Club` et `ClubSettings` sont a portee plateforme (pas de `TenantModel` :
un club ne se filtre pas "par club actif", il EST le club). Tous les
autres modeles de ce fichier heritent de `apps.core.models.TenantModel`.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import TenantModel
from apps.core.storage import private_storage
from apps.core.validators import validate_image_format, validate_upload_size


class Club(models.Model):
    """Identite et image de marque du club (CDC 3.5, 7.3 ; schema §4.1).

    Ne porte aucun parametre operationnel (voir `ClubSettings`) : lu
    publiquement (page de connexion, marque blanche), doit rester leger.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Actif"
        READ_ONLY = "read_only", "Lecture seule"

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=60, unique=True, help_text="Adresse propre : /c/<slug> (CDC 7.3).")
    logo = models.ImageField(
        upload_to="clubs/logos/",
        null=True,
        blank=True,
        validators=[validate_upload_size, validate_image_format],
        help_text="JPEG/PNG/WebP, 10 Mo maximum (CDC 6.7).",
    )
    primary_color = models.CharField(max_length=7, blank=True, help_text="Couleur hex, theme Classic (CDC 3.6).")
    secondary_color = models.CharField(max_length=7, blank=True)
    city = models.CharField(max_length=80)
    country = models.CharField(max_length=80)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    founder_membership = models.ForeignKey(
        "clubs.Membership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Renseigne apres creation du premier Membership : le createur devient President (CDC 2.3).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Club"
        verbose_name_plural = "Clubs"

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    def clean(self):
        if self.founder_membership_id and self.founder_membership.club_id != self.id:
            raise ValidationError(
                "Le fondateur du club doit etre une adhesion de ce club (CDC 2.3)."
            )

    def save(self, *args, **kwargs):
        # Audit de securite du Lot 1 (ecart bloquant B4) : `Club` n'est pas
        # un `TenantModel` (il EST le club, pas une donnee scopee par
        # club -- voir docstring du module), mais porte tout de meme une
        # methode `clean()` de coherence inter-cles (`founder_membership`)
        # qui n'etait jusqu'ici jamais appelee automatiquement a
        # l'enregistrement. Meme correction que `TenantModel.save()`
        # (`apps.core.models`), sans le controle de club actif (qui n'a
        # pas de sens ici).
        self.full_clean()
        super().save(*args, **kwargs)


class ClubSettings(models.Model):
    """Parametres operationnels du club (1-1 avec `Club`, schema §4.2).

    Regroupe les parametres financiers et non financiers configurables
    par le President, avec un controle d'acces uniforme (lecture membres
    du club, ecriture President). Jamais lu par une API publique.
    """

    class Currency(models.TextChoices):
        USD = "USD", "USD"
        CDF = "CDF", "CDF"

    class ABAssignmentRule(models.TextChoices):
        ALTERNATING = "alternating", "Alternee"

    club = models.OneToOneField(Club, primary_key=True, on_delete=models.CASCADE, related_name="settings")
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    timezone = models.CharField(max_length=60, help_text="Fuseau IANA du club (ex. Africa/Kinshasa).")
    debt_tolerance_days = models.PositiveIntegerField(default=0)
    expense_justification_days = models.PositiveIntegerField(default=7)
    payment_link_url = models.URLField(blank=True, help_text="Jamais en dur dans le code (CDC 4.6).")
    board_seats_per_role = models.PositiveIntegerField(
        default=1, help_text="Titulaires actifs autorises par role du bureau (10.2 n3/n24)."
    )
    default_jersey_color_a = models.CharField(max_length=7, default="#0000FF")
    default_jersey_color_b = models.CharField(max_length=7, default="#FF0000")
    ab_assignment_rule = models.CharField(
        max_length=20, choices=ABAssignmentRule.choices, default=ABAssignmentRule.ALTERNATING
    )
    late_arrival_counts_absent = models.BooleanField(default=True)
    yellow_card_suspension_threshold = models.PositiveIntegerField(default=5)
    yellow_card_suspension_matches = models.PositiveIntegerField(default=1)
    red_card_suspension_matches = models.PositiveIntegerField(default=1)
    evaluation_window_hours = models.PositiveIntegerField(default=48)
    assembly_quorum_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("50"))
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "Parametres du club"
        verbose_name_plural = "Parametres des clubs"
        constraints = [
            models.CheckConstraint(
                condition=Q(board_seats_per_role__gte=1), name="clubsettings_board_seats_gte_1"
            ),
            models.CheckConstraint(
                condition=Q(expense_justification_days__gt=0), name="clubsettings_expense_justif_gt_0"
            ),
            models.CheckConstraint(
                condition=Q(yellow_card_suspension_threshold__gt=0), name="clubsettings_yellow_threshold_gt_0"
            ),
            models.CheckConstraint(
                condition=Q(yellow_card_suspension_matches__gt=0), name="clubsettings_yellow_matches_gt_0"
            ),
            models.CheckConstraint(
                condition=Q(red_card_suspension_matches__gt=0), name="clubsettings_red_matches_gt_0"
            ),
            models.CheckConstraint(
                condition=Q(evaluation_window_hours__gt=0), name="clubsettings_eval_window_gt_0"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Parametres de {self.club_id}"


class Season(TenantModel):
    """Saison sportive (CDC 4.9 ; schema §4.3).

    Le controle "pas de chevauchement" et "une seule saison courante par
    club" est une regle metier de service (hors perimetre de cette
    tache, cf. taches sportives du Lot 3) : non exprimable de facon
    portable en contrainte SQL simple (SQLite et MySQL/MariaDB).
    """

    label = models.CharField(max_length=20, help_text="Ex. « 2026 ».")
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta(TenantModel.Meta):
        verbose_name = "Saison"
        verbose_name_plural = "Saisons"
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="season_end_after_start"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.label


class Membership(TenantModel):
    """Adhesion : lien utilisateur/club, roles, dates, statut (schema §3.2).

    Coeur du multi-tenant (CDC 6.3). Toute donnee "joueur" propre au club
    (poste, numero, parrain...) vit ici, jamais sur `User`.

    Rappel faisant autorite (schema §3.2.1) : `status` ne contient QUE
    les etats du workflow d'adhesion (En attente / Inscrit / Parti).
    « En ordre »/« En dette » (finance-engine), « Suspendu »
    (discipline, `sport.Suspension`) et « Blesse »/aptitude (medical,
    `HealthRecord`) ne sont jamais stockes ici : ils sont calcules et
    composes a la volee par le service qui expose le profil (hors
    perimetre de cette tache).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        ACTIVE = "active", "Inscrit"
        DEPARTED = "departed", "Parti"

    class Position(models.TextChoices):
        GOALKEEPER = "goalkeeper", "Gardien"
        DEFENDER = "defender", "Defenseur"
        MIDFIELDER = "midfielder", "Milieu"
        FORWARD = "forward", "Attaquant"

    class LeftReason(models.TextChoices):
        TRANSFER = "transfer", "Transfert"
        RESIGNATION = "resignation", "Demission"
        CANCELLED = "cancelled", "Adhesion annulee avant inscription"
        OTHER = "other", "Autre"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    sponsor = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sponsored_memberships",
        help_text="Parrain (CDC 4.3), obligatoire a la creation sauf import historique.",
    )
    position = models.CharField(
        max_length=12,
        choices=Position.choices,
        blank=True,
        help_text="Obligatoire a la creation manuelle, facultatif a l'import (CDC 4.1) -- controle de service.",
    )
    position_detail = models.CharField(max_length=60, blank=True)
    jersey_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Unique parmi les adhesions ACTIVES du club (CDC 4.1). Non "
            "exprime en contrainte DB : une contrainte unique partielle "
            "(condition sur `status`) n'est pas portable sur MySQL/MariaDB "
            "(Django leve NotSupportedError a la migration) -- controle "
            "applique en service (taches ulterieures)."
        ),
    )
    requested_contribution_type_label = models.CharField(
        max_length=80,
        blank=True,
        help_text=(
            "Valeur brute de la colonne `type_cotisation` du CSV d'import "
            "(CDC 4.1), conservee telle quelle. Le modele `ContributionType` "
            "(domaine tresorerie) n'existe pas encore a ce jour (finance-engine, "
            "tache 1.4b/Lot 2) : aucune FK n'est creee ici, et cette colonne ne "
            "bloque jamais une ligne d'import, quelle que soit sa valeur (y "
            "compris vide ou invalide) -- tache 1.4, point ouvert. A rattacher "
            "au vrai type de cotisation par une migration additive future de "
            "finance-engine, sans perdre cette information dans l'intervalle."
        ),
    )
    is_on_transfer_market = models.BooleanField(default=False)
    market_status_changed_at = models.DateTimeField(null=True, blank=True)
    joined_on = models.DateField()
    left_on = models.DateField(null=True, blank=True)
    left_reason = models.CharField(max_length=12, choices=LeftReason.choices, blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="President ou joueur designe (CDC 2.4, colonne « D »).",
    )
    left_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "Acteur reel ayant traite le depart, rempli uniquement quand "
            "`status` passe a DEPARTED (correction de bug remontee par "
            "test-engineer, Lot 1 -- schema §3.2). Distinct de `added_by` "
            "(le recruteur d'origine, jamais utilise comme acteur du "
            "depart -- CDC 5.1)."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Adhesion"
        verbose_name_plural = "Adhesions"
        constraints = [
            models.CheckConstraint(
                condition=Q(left_on__isnull=True) | ~Q(left_reason=""),
                name="membership_left_reason_required_if_left_on",
            ),
            models.CheckConstraint(
                condition=Q(jersey_number__isnull=True)
                | (Q(jersey_number__gte=1) & Q(jersey_number__lte=99)),
                name="membership_jersey_number_range",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user_id} @ club {self.club_id}"

    def clean(self):
        if self.user_id and getattr(self.user, "is_superuser", False):
            raise ValidationError(
                "Un Superuser ne peut pas avoir de fiche joueur (CLAUDE.md regle n1)."
            )
        if self.sponsor_id and self.club_id and self.sponsor.club_id != self.club_id:
            raise ValidationError("Le parrain doit appartenir au meme club que le filleul.")
        if self.left_on and not self.left_reason:
            raise ValidationError("Une raison de depart est requise quand une date de depart est renseignee.")


class MembershipRole(TenantModel):
    """Role attribue a une adhesion (CDC 2.2-2.4 ; schema §3.4).

    Cardinalite (tache 1.5, corrigee suite a la revue 1.5t, CDC 2.3,
    10.2 n3/n24) :

    - Le President est toujours exactement un par club (CDC 2.3 :
      « un club a toujours un et un seul President »). C'est un
      invariant de **donnees**, pas seulement une garantie procedurale :
      `clean()` verifie explicitement ci-dessous qu'aucun autre
      `MembershipRole` PRESIDENT actif (non revoque) n'existe deja pour
      ce club, sans exception et sans dependre de
      `board_seats_per_role` (le nombre de President n'est jamais
      configurable, contrairement aux autres roles, CDC 2.3, 10.2 n24).
      Ce controle vient EN PLUS -- pas a la place -- de la garantie deja
      assuree par la conception atomique des services de passation
      (`apps.clubs.services.transfer_presidency_by_handover`/
      `transfer_presidency_by_superuser`, qui revoquent le titulaire
      sortant et sauvegardent cette revocation en base avant de nommer
      l'entrant, dans la meme transaction atomique avec
      `select_for_update`) : defense en profondeur, pour que
      l'invariant tienne meme via un chemin d'ecriture qui contourne
      ces deux services (ex. `MembershipRole.objects.create()` direct,
      un futur correctif Ghost Mode, un script de migration de
      donnees, un bug dans un autre service).
    - Pour tout autre role, sauf `PLAYER_RECRUITER` (jamais plafonne) :
      au plus `ClubSettings.board_seats_per_role` titulaires **actifs**
      (non revoques) par role et par club -- verifie ci-dessous par
      `clean()`, donc applique automatiquement a tout `save()`
      (`TenantModel.save()` appelle `full_clean()`).
    """

    class Role(models.TextChoices):
        PRESIDENT = "president", "Président"
        VICE_PRESIDENT = "vice_president", "Vice-président"
        SPORTS_DIRECTOR = "sports_director", "Directeur sportif"
        TREASURER = "treasurer", "Trésorier"
        ASSISTANT_TREASURER = "assistant_treasurer", "Trésorier adjoint"
        STEWARD = "steward", "Intendant"
        COACH = "coach", "Coach"
        CAPTAIN = "captain", "Capitaine"
        DOCTOR = "doctor", "Médecin"
        PLAYER_RECRUITER = "player_recruiter", "Joueur autorisé à ajouter des joueurs"

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="roles")
    role = models.CharField(max_length=20, choices=Role.choices)
    appointed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    appointed_at = models.DateTimeField()
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.TextField(blank=True)
    is_qualified_professional = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Uniquement pour le role Medecin : precise si le titulaire est "
            "qualifie professionnellement. Choix explicite du President a "
            "la nomination, jamais devine (CDC 10.2 n17) -- determine le "
            "libelle a afficher (« Medecin » si vrai, « Medecin / referent "
            "sante » si faux, voir apps.clubs.services.get_effective_role_label). "
            "Reste a `None` pour tout autre role : sans objet."
        ),
    )

    class Meta(TenantModel.Meta):
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.role} / membership {self.membership_id}"

    def clean(self):
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("Le role doit porter le meme club que l'adhesion concernee.")

        if self.role == self.Role.DOCTOR:
            if self.is_qualified_professional is None:
                raise ValidationError(
                    "La nomination au role Medecin exige un choix explicite du "
                    "President (qualifie ou non professionnellement), pour "
                    "determiner le libelle affiche -- « Medecin » ou "
                    "« Medecin / referent sante » (CDC 10.2 n17)."
                )
        elif self.is_qualified_professional is not None:
            raise ValidationError(
                "Le champ de qualification professionnelle ne s'applique qu'au "
                "role Medecin (CDC 10.2 n17)."
            )

        if self.revoked_at is None and self.club_id and self.role == self.Role.PRESIDENT:
            # Invariant de donnees (CDC 2.3 : « un club a toujours un et un
            # seul President »), en plus de la garantie procedurale des
            # services de passation (voir docstring de cette classe) :
            # jamais configurable, jamais d'exception, contrairement aux
            # autres roles ci-dessous.
            active_other_presidents = (
                MembershipRole.all_objects.filter(
                    club_id=self.club_id, role=self.Role.PRESIDENT, revoked_at__isnull=True
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if active_other_presidents:
                raise ValidationError(
                    "Ce club a deja un President actif (CDC 2.3). Revoquez-le "
                    "d'abord (passation de presidence) avant d'en nommer un "
                    "autre."
                )

        if (
            self.revoked_at is None
            and self.club_id
            and self.role not in (self.Role.PRESIDENT, self.Role.PLAYER_RECRUITER)
        ):
            # Cardinalite configurable par club (CDC 2.3, 10.2 n3/n24) :
            # au plus `board_seats_per_role` titulaires ACTIFS par role.
            # Le President (garanti par ailleurs, voir docstring de
            # cette classe) et le recruteur (jamais plafonne, CDC 2.3)
            # sont exclus de ce controle.
            try:
                max_seats = self.club.settings.board_seats_per_role
            except ClubSettings.DoesNotExist:
                # Club pas encore configure (ClubSettings absent) :
                # repli sur la valeur par defaut du champ, jamais une
                # erreur technique brute pour ce cas limite.
                max_seats = ClubSettings._meta.get_field("board_seats_per_role").default

            active_others = (
                MembershipRole.all_objects.filter(
                    club_id=self.club_id, role=self.role, revoked_at__isnull=True
                )
                .exclude(pk=self.pk)
                .count()
            )
            if active_others >= max_seats:
                raise ValidationError(
                    "Le nombre maximal de titulaires actifs pour ce role est "
                    f"deja atteint dans ce club ({max_seats} titulaire(s) -- "
                    "CDC 10.2 n24). Revoquez un titulaire existant avant d'en "
                    "nommer un nouveau, ou augmentez le nombre de titulaires "
                    "autorises dans les parametres du club."
                )


class MembershipApplication(TenantModel):
    """Dossier d'adhesion et parrainage (CDC 4.3 ; schema §3.3).

    Logique de parrainage (relances, delais 3/7 jours, refus, annulation)
    construite tache 1.4b -- voir ``apps.clubs.services``
    (``add_player_with_sponsor``, ``record_membership_fee_payment_for_application``,
    ``sign_sponsor_application``, ``refuse_sponsor_application``,
    ``reassign_sponsor``, ``cancel_membership_application``,
    ``process_sponsor_reminders_and_alerts``).

    `membership_fee_payment` (FK vers `treasury.Payment`) : ajoute par la
    migration additive de la tache 1.4b (`finance-engine`). Le paiement
    lui-meme est enregistre exclusivement par
    ``apps.treasury.services.record_membership_fee_payment`` ; ce champ ne
    fait que le referencer (le premier paiement lie -- la suffisance du
    montant total se recalcule via
    ``apps.treasury.services.has_paid_membership_fee``, jamais stockee ici).

    Cas limite « annulation de l'adhesion apres refus du parrain »
    (CDC 4.3) : ``Membership.status`` passe a ``DEPARTED`` (raison
    ``LeftReason.CANCELLED``) plutot que d'ajouter un
    4e statut a ``Membership.Status`` -- ce champ ne porte volontairement
    QUE les trois etats du workflow d'adhesion documentes plus haut (« En
    attente / Inscrit / Parti »), decision deja actee lors de la
    conception du modele (voir docstring de ``Membership`` ci-dessus).
    """

    class SponsorDecision(models.TextChoices):
        PENDING = "pending", "En attente"
        SIGNED = "signed", "Signe"
        REFUSED = "refused", "Refuse"

    class FeeDisposition(models.TextChoices):
        """Sort du paiement des frais d'adhesion apres annulation (CDC 4.3 :
        « le sort du paiement -- remboursement ou conservation -- est
        enregistre »). Decision D9 de schema-treasury.md, **a confirmer
        par le client** : aucune des deux options n'est appliquee par
        defaut -- c'est toujours un choix explicite du President au
        moment de l'annulation (voir
        ``apps.clubs.services.cancel_membership_application``)."""

        REFUNDED = "refunded", "Rembourse"
        KEPT = "kept", "Conserve"

    membership = models.OneToOneField(Membership, on_delete=models.CASCADE, related_name="application")
    application_pdf_file = models.FileField(
        upload_to="clubs/applications/",
        null=True,
        blank=True,
        storage=private_storage,
        help_text=(
            "Fiche d'adhesion signee (donnee personnelle -- CDC 6.7). "
            "Stockage prive, jamais servi directement : voir "
            "apps.clubs.views.MembershipApplicationPdfDownloadView "
            "(ecart bloquant B10, revue de conformite fin de Lot 1)."
        ),
    )
    generated_at = models.DateTimeField(null=True, blank=True)
    sponsor_notified_at = models.DateTimeField(null=True, blank=True)
    sponsor_decision = models.CharField(
        max_length=10, choices=SponsorDecision.choices, default=SponsorDecision.PENDING
    )
    sponsor_signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    sponsor_signed_at = models.DateTimeField(null=True, blank=True)
    sponsor_refused_reason = models.TextField(blank=True)
    sponsor_reminder_sent_at = models.DateTimeField(null=True, blank=True, help_text="Rappel apres 3 jours sans reponse.")
    president_alerted_at = models.DateTimeField(null=True, blank=True, help_text="Alerte apres 7 jours sans reponse.")
    resolved_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    cancelled_reason = models.TextField(blank=True)
    membership_fee_payment = models.ForeignKey(
        "treasury.Payment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Paiement des frais d'adhesion (CDC 4.3 etape 2 ; tache 1.4b).",
    )
    membership_fee_disposition = models.CharField(
        max_length=10,
        choices=FeeDisposition.choices,
        blank=True,
        default="",
        help_text=(
            "Sort du paiement apres annulation de l'adhesion (CDC 4.3 ; D9, "
            "a confirmer). Vide tant qu'aucune annulation n'a eu lieu."
        ),
    )

    class Meta(TenantModel.Meta):
        verbose_name = "Dossier d'adhesion"
        verbose_name_plural = "Dossiers d'adhesion"

    def __str__(self) -> str:  # pragma: no cover
        return f"Dossier adhesion / membership {self.membership_id}"

    def clean(self):
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("Le dossier d'adhesion doit porter le meme club que l'adhesion concernee.")
        if self.membership_fee_payment_id and (
            self.membership_fee_payment.club_id != self.club_id
            or self.membership_fee_payment.membership_id != self.membership_id
        ):
            raise ValidationError(
                "Le paiement des frais d'adhesion doit etre celui du joueur concerne, dans le meme club."
            )


class PresidencyTransfer(TenantModel):
    """Passation de presidence (CDC 2.3 ; schema §3.5).

    `assembly` (FK vers `assemblies.Assembly`) est volontairement absent :
    ce modele n'existe pas encore (Lot 4, tache 4.5). A ajouter par une
    migration additive de cette tache future.
    """

    class Method(models.TextChoices):
        HANDOVER = "handover", "Passation directe"
        SUPERUSER_OVERRIDE = "superuser_override", "Intervention Superuser"

    from_membership = models.ForeignKey(
        Membership, on_delete=models.PROTECT, related_name="presidency_transfers_out"
    )
    to_membership = models.ForeignKey(
        Membership, on_delete=models.PROTECT, related_name="presidency_transfers_in"
    )
    method = models.CharField(max_length=20, choices=Method.choices)
    superuser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Requis si method=superuser_override : trace l'identite reelle (Ghost Mode).",
    )
    reason = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Motif ecrit. Facultatif pour une passation directe ; "
            "obligatoire pour une intervention Superuser, meme principe "
            "que toute intervention Ghost Mode (CDC 2.5 : « bouton "
            "Intervenir sur ce club avec un motif obligatoire »)."
        ),
    )
    transferred_at = models.DateTimeField()

    class Meta(TenantModel.Meta):
        verbose_name = "Passation de presidence"
        verbose_name_plural = "Passations de presidence"
        constraints = [
            models.CheckConstraint(
                condition=~Q(from_membership=models.F("to_membership")),
                name="presidency_transfer_distinct_memberships",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.from_membership_id} -> {self.to_membership_id}"

    def clean(self):
        if (
            self.from_membership_id
            and self.to_membership_id
            and self.from_membership.club_id != self.to_membership.club_id
        ):
            raise ValidationError("Les deux adhesions doivent appartenir au meme club.")
        if self.club_id and self.from_membership_id and self.from_membership.club_id != self.club_id:
            raise ValidationError("La passation doit porter le meme club que les adhesions concernees.")
        if self.method == self.Method.SUPERUSER_OVERRIDE and not self.superuser_id:
            raise ValidationError(
                "Une intervention Superuser doit identifier l'identite reelle du Superuser (Ghost Mode)."
            )
        if self.method == self.Method.SUPERUSER_OVERRIDE and not (self.reason or "").strip():
            raise ValidationError(
                "Une intervention Superuser doit porter un motif ecrit, comme "
                "toute intervention Ghost Mode (CDC 2.5)."
            )


class ImportBatch(TenantModel):
    """Lot d'import CSV (CDC 4.1 ; schema §4.7).

    Referencee par `finance-engine` (`Due.import_batch`,
    `Payment.import_batch`, domaine tresorerie).
    """

    class ImportType(models.TextChoices):
        PLAYERS = "players", "Joueurs"
        HISTORICAL_CONTRIBUTIONS = "historical_contributions", "Cotisations historiques"

    import_type = models.CharField(max_length=30, choices=ImportType.choices)
    source_file = models.FileField(
        upload_to="clubs/imports/",
        storage=private_storage,
        validators=[validate_upload_size],
        help_text=(
            "Fichier CSV source, conserve pour audit -- contient des "
            "donnees personnelles de tous les joueurs importes (CDC 6.7). "
            "Stockage prive, jamais servi directement : voir "
            "apps.clubs.views.ImportBatchSourceDownloadView (ecart "
            "bloquant B10, revue de conformite fin de Lot 1)."
        ),
    )
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    imported_at = models.DateTimeField()
    row_count_success = models.PositiveIntegerField(default=0)
    row_count_failed = models.PositiveIntegerField(default=0)
    report_file = models.FileField(
        upload_to="clubs/imports/reports/",
        null=True,
        blank=True,
        storage=private_storage,
        help_text=(
            "Rapport d'import (donnees personnelles). Stockage prive, "
            "jamais servi directement : voir "
            "apps.clubs.views.ImportBatchReportDownloadView (ecart "
            "bloquant B10, revue de conformite fin de Lot 1)."
        ),
    )

    class Meta(TenantModel.Meta):
        verbose_name = "Lot d'import"
        verbose_name_plural = "Lots d'import"

    def __str__(self) -> str:  # pragma: no cover
        return f"Import {self.import_type} / club {self.club_id}"


class ClubCreationRequest(models.Model):
    """Cle d'idempotence de l'assistant de creation de club (tache 1.9 ;
    docs/ecrans/clubs-creation.md §5, §6 : « Aucune donnee n'est envoyee
    a l'API avant "Creer mon club" [...] un double appui ou une nouvelle
    tentative apres une coupure reseau ne cree jamais deux clubs »).

    Portee plateforme, jamais un `TenantModel` : le club n'existe pas
    encore au moment ou la cle est generee cote client (a l'ouverture de
    l'assistant, avant toute authentification). Mecanisme choisi ici,
    volontairement le plus simple : une contrainte d'unicite en base sur
    `idempotency_key` (pas de verrou applicatif ni de cache externe) --
    voir `apps.clubs.club_creation.create_club_with_founder`, qui
    capture l'`IntegrityError` d'une deuxieme insertion concurrente avec
    la meme cle pour renvoyer le club deja cree par la premiere, plutot
    que d'en creer un second.
    """

    idempotency_key = models.CharField(
        max_length=100,
        unique=True,
        help_text="Generee cote client a l'ouverture de l'assistant (UUID recommande).",
    )
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Requete de creation de club (idempotence)"
        verbose_name_plural = "Requetes de creation de club (idempotence)"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.idempotency_key} -> club {self.club_id}"
