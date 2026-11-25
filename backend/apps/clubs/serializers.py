"""Serializers DRF de l'app clubs (CDC 2.2-2.4 ; tache 1.5).

Aucune regle metier ici (CLAUDE.md section 5) : validation de forme
uniquement (types, choix, bornes). Toute regle metier (qui peut nommer
qui, cardinalite, coherence de club) vit dans ``apps.clubs.services`` et
``apps.clubs.models``.
"""

from __future__ import annotations

import re
import zoneinfo

from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from rest_framework import serializers

from apps.accounts.serializers import TermsVersionSerializer
from apps.clubs import services as clubs_services
from apps.clubs.models import (
    Club,
    ClubSettings,
    ImportBatch,
    Membership,
    MembershipApplication,
    MembershipRole,
    PresidencyTransfer,
)
from apps.core.validators import (
    validate_csv_file,
    validate_image_format,
    validate_image_or_pdf,
    validate_upload_size,
)

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _validate_hex_color(value: str) -> str:
    """Format ``#RRGGBB`` (docs/ecrans/clubs-creation.md §4.1,
    club-comite-bureau.md §4.1). Chaine vide toujours acceptee : les deux
    couleurs sont facultatives (voir le point ouvert harmonise, spec
    clubs-creation.md §8)."""

    if value and not _HEX_COLOR_RE.match(value):
        raise serializers.ValidationError("Saisissez une couleur au format #RRGGBB.")
    return value


def _validate_timezone(value: str) -> str:
    if value not in zoneinfo.available_timezones():
        raise serializers.ValidationError("Ce fuseau horaire n'est pas reconnu.")
    return value


class MembershipRoleSerializer(serializers.ModelSerializer):
    """Representation d'un role, avec le libelle effectif (CDC 10.2 n17)."""

    role_label = serializers.CharField(source="get_role_display", read_only=True)
    effective_label = serializers.SerializerMethodField()

    class Meta:
        model = MembershipRole
        fields = [
            "id",
            "membership_id",
            "role",
            "role_label",
            "effective_label",
            "is_qualified_professional",
            "appointed_by_id",
            "appointed_at",
            "revoked_by_id",
            "revoked_at",
            "revoked_reason",
        ]
        read_only_fields = fields

    def get_effective_label(self, obj: MembershipRole) -> str:
        return clubs_services.get_effective_role_label(obj)


class RoleAppointmentInputSerializer(serializers.Serializer):
    """Nomination d'un role du bureau, du Medecin, du Coach ou d'un
    recruteur (President uniquement, CDC 2.3)."""

    membership_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=sorted(clubs_services.PRESIDENT_NOMINATED_ROLES))
    is_qualified_professional = serializers.BooleanField(required=False, allow_null=True, default=None)


class RoleRevocationInputSerializer(serializers.Serializer):
    """Revocation d'un role (President ou Coach selon le role, cf. la vue)."""

    role_id = serializers.IntegerField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class CaptainAppointmentInputSerializer(serializers.Serializer):
    """Choix du Capitaine parmi les joueurs (Coach uniquement, CDC 2.3)."""

    membership_id = serializers.IntegerField()


class AssistantCoachAppointmentInputSerializer(serializers.Serializer):
    """Nomination de l'Assistant du Coach (Coach uniquement, CDC 10.3 n179)."""

    membership_id = serializers.IntegerField()


class PresidencyTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = PresidencyTransfer
        fields = [
            "id",
            "from_membership_id",
            "to_membership_id",
            "method",
            "reason",
            "superuser_id",
            "transferred_at",
        ]
        read_only_fields = fields


class PresidencyHandoverInputSerializer(serializers.Serializer):
    """Passation directe : le President sortant designe son successeur (CDC 2.3)."""

    to_membership_id = serializers.IntegerField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class PresidencySuperuserOverrideInputSerializer(serializers.Serializer):
    """Intervention Superuser (CDC 2.3, 2.5) : motif ecrit obligatoire."""

    club_id = serializers.IntegerField()
    from_membership_id = serializers.IntegerField()
    to_membership_id = serializers.IntegerField()
    reason = serializers.CharField(allow_blank=False)

    def validate_reason(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError(
                "Le motif est obligatoire pour une intervention du Superuser."
            )
        return value


class ClubSettingsBoardSeatsSerializer(serializers.ModelSerializer):
    """Lecture/ecriture du seul parametre de cette tache (10.2 n24)."""

    class Meta:
        model = ClubSettings
        fields = ["board_seats_per_role", "updated_at", "updated_by_id"]
        read_only_fields = ["updated_at", "updated_by_id"]


class BoardSeatsInputSerializer(serializers.Serializer):
    board_seats_per_role = serializers.IntegerField(min_value=1)


class PlayerImportInputSerializer(serializers.Serializer):
    """Import CSV des joueurs (President ou recruteur designe, CDC 4.1).

    CDC 7.6 : « Verification du type reel des fichiers envoyes » -- le
    controle de l'extension ``.csv`` seul ne suffit pas (ecart bloquant
    B10, revue de conformite fin de Lot 1) : ``validate_csv_file``
    (``apps.core.validators``) verifie le contenu reel (pas seulement le
    nom), ``validate_upload_size`` la taille maximale de 10 Mo (CDC 6.7).
    """

    file = serializers.FileField()

    def validate_file(self, value):
        name = getattr(value, "name", "") or ""
        if not name.lower().endswith(".csv"):
            raise serializers.ValidationError("Le fichier doit être au format CSV.")
        try:
            validate_upload_size(value)
            validate_csv_file(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value


class ImportBatchSerializer(serializers.ModelSerializer):
    """Lot d'import, avec le detail des lignes en echec (CDC 4.1 : « Le
    rapport liste les lignes importees et les lignes en echec »).

    ``source_file``/``report_file`` sont sur un stockage prive (ecart
    bloquant B10) : ``source_file_url``/``report_file_url`` exposent
    l'adresse de la vue de telechargement authentifiee
    (``apps.clubs.views.ImportBatchSourceDownloadView``/
    ``ImportBatchReportDownloadView``), jamais l'URL ``MEDIA_URL``
    publique du fichier."""

    failed_rows = serializers.SerializerMethodField()
    source_file_url = serializers.SerializerMethodField()
    report_file_url = serializers.SerializerMethodField()

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "import_type",
            "imported_by_id",
            "imported_at",
            "row_count_success",
            "row_count_failed",
            "source_file_url",
            "report_file_url",
            "failed_rows",
        ]
        read_only_fields = fields

    def get_source_file_url(self, obj: ImportBatch) -> str | None:
        if not obj.source_file:
            return None
        return reverse("clubs:import-source-download", kwargs={"pk": obj.pk})

    def get_report_file_url(self, obj: ImportBatch) -> str | None:
        if not obj.report_file:
            return None
        return reverse("clubs:import-report-download", kwargs={"pk": obj.pk})

    def get_failed_rows(self, obj: ImportBatch) -> list[dict]:
        # Fourni par la vue via le contexte du serializer (le detail ligne
        # par ligne vient de `apps.clubs.services.ImportSummary`, pas d'un
        # champ du modele `ImportBatch`) : evite d'obliger le client a
        # relire `report_file` pour afficher la liste des echecs (4.6 de
        # docs/ecrans/club-comite-bureau.md).
        rows = self.context.get("rows", [])
        return [
            {"line_number": row.line_number, "message": row.message}
            for row in rows
            if row.outcome == "failed"
        ]


# ---------------------------------------------------------------------------
# Adhesion et parrainage (CDC 4.3 ; tache 1.4b)
# ---------------------------------------------------------------------------


class MembershipApplicationSerializer(serializers.ModelSerializer):
    """Representation du dossier d'adhesion (CDC 4.3).

    ``application_pdf_file`` est sur un stockage prive (ecart bloquant
    B10, revue de conformite fin de Lot 1) : ``application_pdf_url``
    expose l'adresse de la vue de telechargement authentifiee
    (``apps.clubs.views.MembershipApplicationPdfDownloadView``, President /
    adherent concerne / parrain -- CDC 6.7, 7.6), jamais l'URL
    ``MEDIA_URL`` publique du fichier."""

    application_pdf_url = serializers.SerializerMethodField()
    # Champs d'affichage en lecture seule (aucune regle metier) : permettent a
    # l'interface de presenter un dossier sans requete supplementaire.
    player = serializers.SerializerMethodField()
    sponsor = serializers.SerializerMethodField()
    membership_status = serializers.SerializerMethodField()
    membership_fee_paid = serializers.SerializerMethodField()
    membership_fee_amount = serializers.SerializerMethodField()
    membership_fee_paid_on = serializers.SerializerMethodField()

    class Meta:
        model = MembershipApplication
        fields = [
            "id",
            "membership_id",
            "player",
            "sponsor",
            "membership_status",
            "membership_fee_paid",
            "membership_fee_amount",
            "membership_fee_paid_on",
            "application_pdf_url",
            "generated_at",
            "sponsor_notified_at",
            "sponsor_decision",
            "sponsor_signed_by_id",
            "sponsor_signed_at",
            "sponsor_refused_reason",
            "sponsor_reminder_sent_at",
            "president_alerted_at",
            "resolved_at",
            "cancelled_by_id",
            "cancelled_reason",
            "membership_fee_payment_id",
            "membership_fee_disposition",
        ]
        read_only_fields = fields

    @staticmethod
    def _identity(membership) -> dict | None:
        if membership is None:
            return None
        user = membership.user
        return {
            "membership_id": membership.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "photo": user.photo.url if user.photo else None,
            "position_label": membership.get_position_display() if membership.position else "",
            "jersey_number": membership.jersey_number,
        }

    def get_player(self, obj: MembershipApplication) -> dict | None:
        return self._identity(obj.membership)

    def get_sponsor(self, obj: MembershipApplication) -> dict | None:
        return self._identity(obj.membership.sponsor)

    def get_membership_status(self, obj: MembershipApplication) -> str:
        return obj.membership.status

    def get_membership_fee_paid(self, obj: MembershipApplication) -> bool:
        from apps.treasury import services as treasury_services

        return bool(treasury_services.has_paid_membership_fee(obj.membership))

    def get_membership_fee_amount(self, obj: MembershipApplication) -> str | None:
        payment = obj.membership_fee_payment
        return str(payment.amount) if payment is not None else None

    def get_membership_fee_paid_on(self, obj: MembershipApplication) -> str | None:
        payment = obj.membership_fee_payment
        return payment.paid_on.isoformat() if payment is not None else None

    def get_application_pdf_url(self, obj: MembershipApplication) -> str | None:
        if not obj.application_pdf_file:
            return None
        return reverse("clubs:application-pdf-download", kwargs={"pk": obj.pk})


class AddPlayerWithSponsorInputSerializer(serializers.Serializer):
    """Ajout manuel d'un nouveau joueur, parrain obligatoire (CDC 4.3
    etape 1 ; 4.1 : poste obligatoire a la creation manuelle)."""

    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    position = serializers.ChoiceField(choices=Membership.Position.choices)
    position_detail = serializers.CharField(required=False, allow_blank=True, default="")
    jersey_number = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=1, max_value=99)
    birth_date = serializers.DateField(required=False, allow_null=True, default=None)
    weight_kg = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True, default=None)
    height_cm = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True, default=None)
    sponsor_membership_id = serializers.IntegerField()
    requested_contribution_type_label = serializers.CharField(required=False, allow_blank=True, default="")


class MembershipFeePaymentInputSerializer(serializers.Serializer):
    """Paiement des frais d'adhesion d'un dossier (CDC 4.3 etape 2 ; 4.4.4).
    Aucune contrainte de choix ici sur ``method`` : la regle metier exacte
    (especes, mobile money ou lien de paiement -- pas de carte au MVP)
    vit dans ``apps.treasury.services.record_membership_fee_payment``
    (CLAUDE.md section 5), jamais dupliquee dans ce serializer."""

    application_id = serializers.IntegerField()
    amount = serializers.CharField()
    method = serializers.CharField()
    paid_on = serializers.DateField()
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    # CDC 6.7, 7.6 : JPEG/PNG/WebP/PDF verifies sur le contenu reel, 10 Mo max.
    attachment = serializers.FileField(
        required=False,
        allow_null=True,
        default=None,
        validators=[validate_upload_size, validate_image_or_pdf],
    )


class SponsorSignInputSerializer(serializers.Serializer):
    """Signature du parrain (CDC 4.3 etape 4). Tout champ supplementaire recu est ignore."""

    application_id = serializers.IntegerField()


class SponsorRefuseInputSerializer(serializers.Serializer):
    """Refus du parrain, motif obligatoire (CDC 4.3, cas limite)."""

    application_id = serializers.IntegerField()
    reason = serializers.CharField()

    def validate_reason(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError(
                "Un motif est obligatoire pour refuser de parrainer un joueur."
            )
        return value


class SponsorReassignInputSerializer(serializers.Serializer):
    """Le President designe un nouveau parrain apres un refus (CDC 4.3)."""

    application_id = serializers.IntegerField()
    new_sponsor_membership_id = serializers.IntegerField()


class MembershipApplicationCancelInputSerializer(serializers.Serializer):
    """Annulation de l'adhesion par le President apres un refus (CDC 4.3).
    ``disposition`` : sort du paiement, D9 -- a confirmer par le client ;
    aucune valeur par defaut n'est proposee, le President choisit
    explicitement a chaque cas (voir
    ``apps.clubs.services.cancel_membership_application``)."""

    application_id = serializers.IntegerField()
    reason = serializers.CharField()
    disposition = serializers.ChoiceField(choices=MembershipApplication.FeeDisposition.choices)

    def validate_reason(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Un motif est obligatoire pour annuler une adhésion.")
        return value


# ---------------------------------------------------------------------------
# Assistant de creation de club (CDC 1.4, 4.1 ; tache 1.9 ; point d'acces
# PUBLIC, non authentifie -- docs/ecrans/clubs-creation.md)
# ---------------------------------------------------------------------------


class PublicClubCreationSettingsSerializer(serializers.Serializer):
    """Parametres publics de l'etape 3 de l'assistant (spec §4.3), avant
    toute authentification."""

    trial_duration_days = serializers.IntegerField()
    grace_period_days = serializers.IntegerField()
    timezones = serializers.ListField(child=serializers.CharField())
    terms_version = TermsVersionSerializer(allow_null=True)


class ClubCreationInputSerializer(serializers.Serializer):
    """Envoi final de l'assistant (spec §5) : une seule requete pour les
    trois etapes, le logo, la version des CGU acceptee et la cle
    d'idempotence generee cote client a l'ouverture de l'assistant."""

    idempotency_key = serializers.CharField(max_length=100, allow_blank=False)

    # Etape 1 -- « Votre club »
    name = serializers.CharField(max_length=120)
    logo = serializers.ImageField(
        required=False,
        allow_null=True,
        default=None,
        validators=[validate_upload_size, validate_image_format],
    )
    primary_color = serializers.CharField(required=False, allow_blank=True, max_length=7, default="")
    secondary_color = serializers.CharField(required=False, allow_blank=True, max_length=7, default="")
    city = serializers.CharField(max_length=80)
    country = serializers.CharField(max_length=80)
    currency = serializers.ChoiceField(choices=ClubSettings.Currency.choices)
    timezone_name = serializers.CharField(max_length=60)

    # Etape 2 -- « Votre fiche joueur » (memes champs que « Ajouter un
    # joueur », sans Parrain ni Type de cotisation mensuelle, spec §4.2)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    position = serializers.ChoiceField(choices=Membership.Position.choices)
    position_detail = serializers.CharField(required=False, allow_blank=True, max_length=60, default="")
    jersey_number = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=1, max_value=99)
    birth_date = serializers.DateField(required=False, allow_null=True, default=None)
    weight_kg = serializers.DecimalField(
        max_digits=5, decimal_places=1, required=False, allow_null=True, default=None, min_value=30, max_value=200
    )
    height_cm = serializers.DecimalField(
        max_digits=5, decimal_places=1, required=False, allow_null=True, default=None, min_value=120, max_value=230
    )

    # Etape 3 -- CGU
    terms_version_id = serializers.IntegerField()
    accept_terms = serializers.BooleanField()

    def validate_primary_color(self, value: str) -> str:
        return _validate_hex_color(value)

    def validate_secondary_color(self, value: str) -> str:
        return _validate_hex_color(value)

    def validate_timezone_name(self, value: str) -> str:
        return _validate_timezone(value)

    def validate_birth_date(self, value):
        from django.utils import timezone as dj_timezone

        if value is not None and value > dj_timezone.now().date():
            raise serializers.ValidationError("La date ne peut pas être dans le futur.")
        return value

    def validate_accept_terms(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError(
                "Vous devez accepter les conditions générales pour créer votre club."
            )
        return value


# ---------------------------------------------------------------------------
# Identite du club (CDC 3.5 ; club-comite-bureau.md §4.1 ; tache 1.9)
# ---------------------------------------------------------------------------


class ClubIdentitySerializer(serializers.Serializer):
    """Lecture de la carte « Identite du club » (club-comite-bureau.md §3).

    ``payment_link_url`` n'est renvoye en clair qu'au President (spec :
    « visible par le President seulement ») -- les autres membres ne
    recoivent que ``payment_link_configured`` (booleen). Le contexte du
    serializer doit fournir ``is_president`` et ``request`` (ce dernier
    pour construire l'URL absolue de ``logo``, bug remarques.md).
    """

    def to_representation(self, club: Club) -> dict:
        club_settings = club.settings
        is_president = bool(self.context.get("is_president", False))
        # Le contexte DOIT fournir `request` (comme `is_president`) : les
        # deux appelants (ClubIdentityView.get/.patch) le passent tous les
        # deux -- voir apps.clubs.views.
        request = self.context["request"]

        payload = {
            "id": club.id,
            "name": club.name,
            "slug": club.slug,
            # URL ABSOLUE (bug remarques.md) : un chemin relatif pointe vers
            # le mauvais serveur des que interface/API sont sur des
            # origines differentes -- voir docstring
            # apps.accounts.views._serialize_club.
            "logo": request.build_absolute_uri(club.logo.url) if club.logo else None,
            "primary_color": club.primary_color,
            "secondary_color": club.secondary_color,
            "city": club.city,
            "country": club.country,
            "currency": club_settings.currency,
            "currency_locked": clubs_services.club_has_payments(club),
            "timezone": club_settings.timezone,
            "debt_tolerance_days": club_settings.debt_tolerance_days,
        }
        if is_president:
            payload["payment_link_url"] = club_settings.payment_link_url
        else:
            payload["payment_link_configured"] = bool(club_settings.payment_link_url)
        return payload


class ClubIdentityInputSerializer(serializers.Serializer):
    """Modale « Identite du club » (club-comite-bureau.md §4.1). Tous les
    champs sont facultatifs (mise a jour partielle, un seul « Enregistrer »
    pour toute la modale) : un champ absent du corps de la requete n'est
    tout simplement pas modifie -- voir
    ``apps.clubs.services.update_club_identity``."""

    name = serializers.CharField(max_length=120, required=False)
    logo = serializers.ImageField(
        required=False, allow_null=True, validators=[validate_upload_size, validate_image_format]
    )
    primary_color = serializers.CharField(required=False, allow_blank=True, max_length=7)
    secondary_color = serializers.CharField(required=False, allow_blank=True, max_length=7)
    city = serializers.CharField(max_length=80, required=False)
    country = serializers.CharField(max_length=80, required=False)
    currency = serializers.ChoiceField(choices=ClubSettings.Currency.choices, required=False)
    timezone = serializers.CharField(max_length=60, required=False)
    payment_link_url = serializers.CharField(required=False, allow_blank=True)
    debt_tolerance_days = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=90,
        error_messages={
            "invalid": "Saisissez un nombre entier de jours.",
            "min_value": "La tolérance de dette doit être comprise entre 0 et 90 jours.",
            "max_value": "La tolérance de dette doit être comprise entre 0 et 90 jours.",
        },
    )

    def validate_primary_color(self, value: str) -> str:
        return _validate_hex_color(value)

    def validate_secondary_color(self, value: str) -> str:
        return _validate_hex_color(value)

    def validate_timezone(self, value: str) -> str:
        return _validate_timezone(value)

    def validate_payment_link_url(self, value: str) -> str:
        if value and not value.startswith("https://"):
            raise serializers.ValidationError("Saisissez une adresse commençant par https://")
        return value


# ---------------------------------------------------------------------------
# Fiche publique du joueur (club-comite-bureau.md §4.7 ; CDC 4.2 ; tache 1.9)
# ---------------------------------------------------------------------------


class PlayerListQuerySerializer(serializers.Serializer):
    """Parametres de la liste/recherche des membres du club actif
    (club-comite-bureau.md §3.6 « Effectif » ; PlayerSearch, CLAUDE.md
    regle n15). Tous facultatifs -- validation de forme uniquement (une
    valeur de filtre invalide est une erreur 400 claire, pas un
    ecrasement silencieux du filtre)."""

    search = serializers.CharField(required=False, allow_blank=True, max_length=120)
    position = serializers.ChoiceField(choices=Membership.Position.choices, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=Membership.Status.choices, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=MembershipRole.Role.choices, required=False, allow_blank=True)


class PlayerPublicCardSerializer(serializers.Serializer):
    """Fiche publique d'un joueur du club : identite, poste/numero, roles,
    statut d'adhesion. Aucune donnee financiere ni medicale (spec
    explicite, club-comite-bureau.md §4.7)."""

    def to_representation(self, membership: Membership) -> dict:
        user = membership.user
        roles = MembershipRole.objects.filter(membership=membership, revoked_at__isnull=True)

        # CDC 10.2 n16 (precise en 4.12) : « En attente » n'est visible que
        # par le President, le VP, le Directeur sportif, le Coach, le
        # Medecin et le joueur concerne -- decision testable, jamais un
        # `if` dans ce serializer (CLAUDE.md section 5).
        request = self.context.get("request")
        viewer_user = getattr(request, "user", None) if request is not None else None
        membership_status = membership.status
        membership_status_label = membership.get_status_display()
        if membership.status == Membership.Status.PENDING and not clubs_services.can_view_pending_membership_status(
            viewer_user=viewer_user, target_membership=membership
        ):
            membership_status = clubs_services.PLAYER_CARD_NEUTRAL_STATUS_CODE
            membership_status_label = clubs_services.PLAYER_CARD_NEUTRAL_STATUS_LABEL

        data = {
            "membership_id": membership.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            # URL ABSOLUE quand `request` est disponible dans le contexte
            # (bug remarques.md : un chemin relatif pointe vers le mauvais
            # serveur des que interface/API sont sur des origines
            # differentes) -- retombe sur l'URL relative si `request` est
            # absent du contexte (meme tolerance que `viewer_user`
            # ci-dessus, ce serializer est parfois instancie hors requete
            # HTTP, ex. generation de rapport).
            "photo": (
                request.build_absolute_uri(user.photo.url)
                if user.photo and request is not None
                else (user.photo.url if user.photo else None)
            ),
            "position": membership.position,
            "position_label": membership.get_position_display() if membership.position else "",
            "position_detail": membership.position_detail,
            "jersey_number": membership.jersey_number,
            "membership_status": membership_status,
            "membership_status_label": membership_status_label,
            "joined_on": membership.joined_on,
            "roles": [
                {
                    "role": role.role,
                    "label": clubs_services.get_effective_role_label(role),
                }
                for role in roles
            ],
        }
        # « Bloqué » pour le pointage groupé : booléen SEUL, sans motif et
        # pour tous les rôles (10.2 n° 16 : les coéquipiers ne voient que
        # « Indisponible »). Fourni par la vue (calcul groupé, jamais une
        # requête par joueur) ; absent si la vue ne l'a pas calculé.
        unavailable_ids = self.context.get("unavailable_ids")
        if unavailable_ids is not None:
            data["is_unavailable"] = membership.id in unavailable_ids
        return data
