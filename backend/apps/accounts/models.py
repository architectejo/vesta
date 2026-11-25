"""Modeles de l'app accounts : compte global (`User`) et CGU versionnees.

Portee plateforme (pas de champ `club`) : un `User` peut appartenir a
plusieurs clubs dans le temps via `Membership` (apps.clubs), CDC 6.3.
Voir docs/lot0/schema-donnees.md §3.1, §3.6.
"""

from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.validators import validate_image_format, validate_upload_size


class UserManager(BaseUserManager):
    """Manager du modele `User` : email comme identifiant, pas de username.

    CDC 4.1 : « Aucun nom d'utilisateur n'est demande : l'email est
    l'identifiant. » Le mot de passe initial (= email) est fixe par
    l'appelant (service d'ajout de joueur / import, tache 1.4), pas ici.
    """

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("L'adresse email est obligatoire.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields["is_superuser"] = True
        # Un Superuser saisit son propre mot de passe des la creation
        # (pas de "premiere connexion" a changer, contrairement a un
        # joueur -- il n'a pas de fiche joueur, CLAUDE.md regle n1).
        extra_fields.setdefault("must_change_password", False)
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser):
    """Compte utilisateur global (CDC 4.1 ; schema-donnees.md §3.1).

    Un Superuser (`is_superuser=True`) n'a jamais de fiche joueur : voir
    la contrainte appliquee dans `apps.clubs.models.Membership.clean()`
    (CLAUDE.md regle n1). Ce modele n'utilise pas
    `django.contrib.auth.models.PermissionsMixin` : Vesta implemente sa
    propre matrice de permissions (CDC 2.4, via `MembershipRole`), pas
    les groupes/permissions natifs de Django.

    Le champ `password` herite de `AbstractBaseUser` porte le hachage du
    mot de passe (`schema-donnees.md` l'appelle `password_hash` ; c'est
    le meme champ, sous le nom conventionnel de Django). De meme,
    `last_login` (herite) correspond au `last_login_at` du schema.
    """

    class Theme(models.TextChoices):
        CLASSIC = "classic", "Classic"
        LIGHT = "light", "Clair"
        DARK = "dark", "Sombre"

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    email = models.EmailField(
        max_length=255,
        unique=True,
        help_text=(
            "Identifiant de connexion, unique sur toute la plateforme "
            "(CDC 4.1). Normalise en minuscules a l'enregistrement : ne "
            "jamais dependre de la casse geree par le moteur de base de "
            "donnees (SQLite en dev vs MySQL/MariaDB en prod comparent "
            "differemment la casse du texte, voir backend/README.md)."
        ),
    )
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)

    must_change_password = models.BooleanField(
        default=True,
        help_text=(
            "Tant que vrai, aucune donnee n'est accessible (CDC 4.1). "
            "Vrai a la creation initiale (mot de passe = email) et apres "
            "toute reinitialisation par le Superuser (10.2 n21)."
        ),
    )
    temp_password_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Echeance de validite (48h) d'un mot de passe temporaire "
            "genere par le Superuser (10.2 n21). Vide en dehors d'une "
            "reinitialisation en cours."
        ),
    )

    phone = models.CharField(max_length=30, blank=True, help_text="Telephone WhatsApp (recus, communiques).")
    birth_date = models.DateField(null=True, blank=True, help_text="L'age est calcule, jamais stocke.")
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    photo = models.ImageField(
        upload_to="users/photos/",
        null=True,
        blank=True,
        validators=[validate_upload_size, validate_image_format],
        help_text=(
            "Avatar ; demande a la premiere connexion (CDC 4.1). Initiales "
            "affichees a defaut. JPEG/PNG/WebP, 10 Mo maximum (CDC 6.7)."
        ),
    )

    is_superuser = models.BooleanField(
        default=False,
        help_text="Compte Editeur ; ne peut avoir aucun Membership (CLAUDE.md regle n1).",
    )
    is_active = models.BooleanField(default=True, help_text="Desactivation par un Superuser (CDC 4.18).")

    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    login_locked_until = models.DateTimeField(null=True, blank=True, help_text="Blocage 15 min apres 5 echecs (CDC 7.1).")

    card_publication_consent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Consentement a la publication de la carte de joueur (CDC "
            "7.5, decision D2 : portee globale). Point ouvert signale "
            "par le schema (Q4) : un joueur actif dans deux clubs "
            "simultanement pourrait vouloir des reglages differents -- "
            "non traite par cette tache."
        ),
    )

    preferred_theme = models.CharField(
        max_length=10,
        choices=Theme.choices,
        default=Theme.CLASSIC,
        help_text="Preference de theme, memorisee par utilisateur, appliquee sur tous les clubs (CDC 3.6).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self) -> str:  # pragma: no cover - representation triviale
        return self.email

    def save(self, *args, **kwargs):
        # Garde-fou independant du manager : quel que soit le chemin de
        # creation/modification (admin, ORM direct, factory de test...),
        # l'email est toujours normalise en minuscules (voir le champ
        # `email` ci-dessus).
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class TermsVersion(models.Model):
    """Version des CGU de Vesta (10.2 n27 ; schema-donnees.md §3.6).

    Portee plateforme : gere uniquement par un Superuser.
    """

    version_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        blank=True,
        help_text="Genere automatiquement (ex. « 2026-1 »), jamais saisi.",
    )
    published_at = models.DateTimeField(help_text="Date d'entree en vigueur de cette version.")
    content = models.TextField(help_text="Texte des CGU, ou reference au document publie.")
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Superuser ayant publie cette version.",
    )

    class Meta:
        verbose_name = "Version des CGU"
        verbose_name_plural = "Versions des CGU"
        ordering = ["-published_at"]

    def __str__(self) -> str:  # pragma: no cover
        return self.version_number

    def clean(self):
        if self.created_by_id and not self.created_by.is_superuser:
            raise ValidationError(
                "Seul un Superuser peut publier une version des CGU (CDC 2.5)."
            )

    def save(self, *args, **kwargs):
        if not self.version_number:
            if self.published_at:
                year = self.published_at.year
            else:
                from django.utils import timezone

                year = timezone.now().year
            # NOTE (portabilite SQLite/MySQL, voir backend/README.md) :
            # ce comptage n'est pas protege par un verrou de ligne
            # (`select_for_update`, no-op silencieux sous SQLite). Deux
            # publications strictement simultanees pourraient calculer
            # le meme numero de version. Sans consequence pratique ici
            # (action rarissime, reservee au Superuser), mais a corriger
            # par un verrou explicite si la cadence de publication des
            # CGU augmente un jour.
            existing_count = TermsVersion.objects.filter(
                version_number__startswith=f"{year}-"
            ).count()
            self.version_number = f"{year}-{existing_count + 1}"
        super().save(*args, **kwargs)


class PasswordResetRequest(models.Model):
    """Demande de reinitialisation de mot de passe (CDC 4.1, 7.1 ; 10.2 n21).

    Portee plateforme (schema-donnees.md §13.2) : le joueur envoie une
    demande depuis la page de connexion (`status=pending`) ; le
    Superuser la traite (`status=done`), ce qui genere le mot de passe
    temporaire (`apps.accounts.services.reset_password_by_superuser`).
    Aucun mot de passe en clair n'est jamais stocke ici ni ailleurs :
    seul `User.password` (hache) porte le mot de passe temporaire, comme
    n'importe quel mot de passe.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        DONE = "done", "Traitee"

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="password_reset_requests"
    )
    requested_at = models.DateTimeField(help_text="Demande depuis la page de connexion (CDC 4.1).")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    handled_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Superuser qui declenche la generation du mot de passe temporaire.",
    )
    handled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Demande de reinitialisation de mot de passe"
        verbose_name_plural = "Demandes de reinitialisation de mot de passe"
        ordering = ["-requested_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"Reinitialisation / user {self.user_id} ({self.status})"

    def clean(self):
        if self.status == self.Status.DONE and not (self.handled_by_id and self.handled_at):
            raise ValidationError(
                "Une demande traitée doit indiquer qui l'a traitée et quand."
            )
        if self.handled_by_id and not getattr(self.handled_by, "is_superuser", False):
            raise ValidationError(
                "Seul un Superuser traite une demande de reinitialisation (CDC 4.1, 4.18)."
            )


class TermsAcceptance(models.Model):
    """Acceptation des CGU par un utilisateur (10.2 n27).

    Unique par (utilisateur, version) : une nouvelle version publiee
    redemande l'acceptation (CDC 7.5).
    """

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="terms_acceptances"
    )
    terms_version = models.ForeignKey(
        TermsVersion, on_delete=models.PROTECT, related_name="acceptances"
    )
    accepted_at = models.DateTimeField()

    class Meta:
        verbose_name = "Acceptation des CGU"
        verbose_name_plural = "Acceptations des CGU"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "terms_version"], name="unique_terms_acceptance_per_user_version"
            )
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user_id} / {self.terms_version_id}"
