"""Serializers DRF de l'app accounts.

Tache 1.3 : authentification, mot de passe, CGU (CDC 4.1, 7.1, 7.5).
Les regles metier vivent dans ``apps.accounts.services`` (CLAUDE.md
section 5) : ces serializers ne font que valider la forme des entrees et
mettre en forme les sorties.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import PasswordResetRequest, TermsVersion, User
from apps.core.validators import validate_image_format, validate_upload_size


class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    # `trim_whitespace=False` : un mot de passe peut legitimement
    # commencer/finir par un espace (rare, mais ce n'est pas a l'API de
    # le corriger silencieusement).
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    # CDC 7.3 : slug de l'adresse `/c/<slug>`, transmis par le frontend
    # pour desambiguiser (voir apps.accounts.services.resolve_login_club).
    club_slug = serializers.SlugField(required=False, allow_blank=True)


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "is_superuser",
            "must_change_password",
            "preferred_theme",
        ]


class ForcedPasswordChangeSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class SuperuserPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="Email du compte a reinitialiser.")


class TermsVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TermsVersion
        fields = ["id", "version_number", "published_at", "content"]


class AcceptTermsSerializer(serializers.Serializer):
    terms_version_id = serializers.IntegerField()


# ---------------------------------------------------------------------------
# Comptes -- espace Superuser (CDC 2.5, 4.18 ; tache 1.8)
# ---------------------------------------------------------------------------


class AccountSearchQuerySerializer(serializers.Serializer):
    """Parametres de recherche (CDC 4.18 : « recherche sur tous les
    comptes, identifiant, club, roles »)."""

    query = serializers.CharField(required=False, allow_blank=True, default="")
    club_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    role = serializers.CharField(required=False, allow_blank=True, default="")


class AccountDeactivateInputSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class PersonalInfoUpdateSerializer(serializers.Serializer):
    """Onglet « Informations » de Mon profil (comptes-mon-profil.md §4.1)."""

    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=30, default="")
    birth_date = serializers.DateField(required=False, allow_null=True, default=None)
    weight_kg = serializers.DecimalField(
        max_digits=5, decimal_places=1, required=False, allow_null=True, default=None, min_value=30, max_value=200
    )
    height_cm = serializers.DecimalField(
        max_digits=5, decimal_places=1, required=False, allow_null=True, default=None, min_value=120, max_value=230
    )

    def validate_birth_date(self, value):
        from django.utils import timezone

        if value is not None and value > timezone.now().date():
            raise serializers.ValidationError("La date ne peut pas être dans le futur.")
        return value


class CredentialsUpdateSerializer(serializers.Serializer):
    """Onglet « Identifiant et mot de passe » de Mon profil
    (comptes-mon-profil.md §4.1)."""

    email = serializers.EmailField()
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, required=False, allow_blank=True, default=""
    )
    confirm_new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, required=False, allow_blank=True, default=""
    )


class ProfilePhotoUpdateSerializer(serializers.Serializer):
    """CDC 6.7 : JPEG/PNG/WebP, 10 Mo maximum -- type reel verifie via
    Pillow (deja fait par ``rest_framework.fields.ImageField``, complete
    par ces deux validateurs, voir ``apps.core.validators``)."""

    photo = serializers.ImageField(validators=[validate_upload_size, validate_image_format])


class PendingPasswordResetRequestSerializer(serializers.ModelSerializer):
    """Demande de reinitialisation en attente (CDC 4.18)."""

    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_first_name = serializers.CharField(source="user.first_name", read_only=True)
    user_last_name = serializers.CharField(source="user.last_name", read_only=True)

    class Meta:
        model = PasswordResetRequest
        fields = ["id", "user_id", "user_email", "user_first_name", "user_last_name", "requested_at", "status"]
        read_only_fields = fields
