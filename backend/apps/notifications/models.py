"""Modeles de l'app notifications (CDC 4.17 ; tache 1.7).

Deux modeles, conformes a docs/lot0/schema-donnees.md §11 :

- :class:`Notification` : une notification adressee a un utilisateur
  precis. **N'herite pas** de :class:`apps.core.models.TenantModel` bien
  qu'elle porte un champ ``club`` : ce champ est explicitement
  **facultatif** (voir docstring de la classe), alors que
  ``TenantModel`` exige un ``club`` obligatoire et filtre les lectures
  sur le "club actif" du contexte de la requete courante -- un mecanisme
  inadapte ici, puisqu'une notification se lit par SON DESTINATAIRE
  (``recipient``), jamais par le club actif de la requete en cours
  (un joueur peut avoir des adhesions dans plusieurs clubs au fil du
  temps ; une commande cron qui traite tous les clubs n'a, elle, aucun
  "club actif"). L'isolation qui compte reellement pour ce modele est
  donc assuree **au niveau des vues/services** (toujours filtrer sur
  ``recipient=request.user``), pas au niveau du manager -- voir
  ``apps.notifications.services``/``apps.notifications.views``.
  Documente comme exception a ``TenantModel`` dans
  ``apps.core.models`` (voir sa docstring) et dans
  docs/lot0/schema-donnees.md §1.2.
- :class:`NotificationPreference` : preference globale d'envoi email par
  utilisateur (CDC 4.17 : « Chaque utilisateur choisit s'il recoit aussi
  les notifications par email » -- un seul bouton global, pas de
  granularite par type d'evenement, voir docs/lot0/schema-donnees.md
  §11.2 et Q1). Decision par defaut appliquee ici (a documenter au
  compte rendu de la tache 1.7) : ce reglage vit dans un modele dedie de
  ``apps.notifications``, pas comme un champ supplementaire sur
  ``apps.accounts.models.User`` -- ce dernier ne porte ainsi aucun champ
  propre a un module fonctionnel qui n'est pas le sien, et le schema deja
  documente (§11.2, ecrit avant cette tache) le prevoyait ainsi.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


def _default_created_at():
    """Callable indirection (plutot que ``default=timezone.now`` directement) :
    resout ``timezone.now`` a CHAQUE appel plutot qu'une seule fois a
    l'import du module, pour rester compatible avec la convention de test
    du projet qui patche ``django.utils.timezone.now`` (ex.
    ``apps.accounts.tests.test_services_auth``,
    ``apps.notifications.tests.test_views``) -- un ``default=timezone.now``
    capturerait la fonction d'origine une fois pour toutes au chargement
    de ce module et ignorerait silencieusement tout monkeypatch pose
    ensuite par un test."""

    return timezone.now()


class Notification(models.Model):
    """Notification adressee a un utilisateur (CDC 4.17 ; schema §11.1).

    ``club`` **facultatif** : obligatoire en pratique pour toute
    notification adressee a un membre de club (les quatre evenements
    cables par cette tache le renseignent toujours), **vide** pour une
    alerte de portee plateforme adressee a un Superuser sans club de
    rattachement (ex. future notification ``post_reported``,
    ``licence_expiring`` au sens plateforme). Ce champ est denormalise
    depuis la cible de la notification au moment de sa creation (voir
    ``apps.notifications.services.create_notification``), jamais deduit
    d'un "club actif" de la requete courante : un Superuser ou une
    commande cron qui traite plusieurs clubs n'ont pas de club actif.
    """

    class EventType(models.TextChoices):
        """Une valeur par ligne du tableau CDC 4.17, completee par les
        echeances/alertes documentees ailleurs dans le cahier des charges
        (voir schema-donnees.md §11.1 pour la correspondance complete).

        Seuls les evenements marques ci-dessous « (cable tache 1.7) »
        sont effectivement emis a ce jour : les autres appartiennent a
        des modules pas encore construits (tresorerie au-dela de
        l'adhesion, sport, medical, mercato, AG, licences...) et ne sont
        que reserves pour eviter une migration de plus quand ces modules
        arriveront -- CDC 4.17, `docs/lot0/schema-donnees.md` §11.1.
        """

        PAYMENT_VALIDATED = "payment_validated", "Paiement validé"
        DEBT_DUE = "debt_due", "Dette constatée à l'échéance"
        I_PAID_DECLARED = "i_paid_declared", "Déclaration « J'ai payé »"
        I_PAID_REJECTED = "i_paid_rejected", "Déclaration « J'ai payé » refusée"
        EXPENSE_SUBMITTED = "expense_submitted", "Dépense saisie"
        EXPENSE_BLOCKING = "expense_blocking", "Dépense non justifiée, blocage"
        SOCIAL_ASSISTANCE_REQUEST = "social_assistance_request", "Demande d'assistance sociale"
        MEMBERSHIP_SIGNATURE_PENDING = (
            "membership_signature_pending",
            "Fiche d'adhésion à signer",
        )  # cable tache 1.7
        SPONSOR_REMINDER = (
            "sponsor_reminder",
            "Rappel au parrain sans réponse",
        )  # cable tache 1.7
        SPONSOR_ALERT_PRESIDENT = (
            "sponsor_alert_president",
            "Parrain sans réponse depuis 7 jours",
        )  # cable tache 1.7
        SPONSOR_REFUSED = "sponsor_refused", "Refus du parrain"  # cable tache 1.7
        EVENT_CREATED = "event_created", "Séance ou match créé"
        COMPOSITION_OR_PLAN_PUBLISHED = "composition_or_plan_published", "Composition ou plan publié"
        CARD_OR_SUSPENSION = "card_or_suspension", "Carton, suspension"
        INJURY_DECLARED = "injury_declared", "Blessure déclarée"
        TRANSFER_OFFER = "transfer_offer", "Offre de transfert"
        ASSEMBLY_CONVENED = "assembly_convened", "Convocation d'AG"
        ASSEMBLY_REMINDER = "assembly_reminder", "Rappel d'assemblée générale"
        ROLE_APPOINTED_OR_REVOKED = "role_appointed_or_revoked", "Nomination ou révocation"  # cable tache 1.7
        LICENCE_EXPIRING = "licence_expiring", "Licence proche de l'expiration"
        INVENTORY_OPEN_ALERT = "inventory_open_alert", "Inventaire non clôturé"
        POST_REPORTED = "post_reported", "Signalement d'une publication"
        # CDC 5.3 / 5.5 : alerte au Superuser en cas de rupture de la
        # chaine financiere d'un club (tache 2.3, commande
        # `verify_ledger_chain`). Hors tableau 4.17 : destinataires =
        # Superusers uniquement.
        LEDGER_CHAIN_BROKEN = "ledger_chain_broken", "Rupture de la chaîne financière"
        # Lot 4, tache 4.5 (assemblees-page-ag.md §4.7, §7) : absente du
        # tableau CDC 4.17, proposition explicitement marquee « a valider »
        # par l'ecran -- cablee ici par defaut (le second signataire attendu
        # est prevenu), point ouvert signale au compte rendu.
        ASSEMBLY_PV_SIGNATURE_PENDING = (
            "assembly_pv_signature_pending",
            "Signature du PV d'AG en attente",
        )
        # Lot 4, tache 4.6 (fil-public-communication.md, point ouvert F.12) :
        # `club-accueil.md` annonce deja « Tous les joueurs ont ete prevenus »
        # a la publication d'un communique, mais cette ligne manque au
        # tableau CDC 4.17 -- cablee ici par defaut, point ouvert signale au
        # compte rendu (a ajouter au 4.17 ou a retirer du message de succes).
        ANNOUNCEMENT_PUBLISHED = "announcement_published", "Communiqué publié"
        # Tests de performance (sport-statistiques-seance.md C7, question C-Q9,
        # position provisoire) : une notification par joueur et par séance,
        # 1 h après la dernière mesure (commande cron).
        PERFORMANCE_RESULTS_AVAILABLE = (
            "performance_results_available",
            "Mesures de performance disponibles",
        )

    class EmailStatus(models.TextChoices):
        NOT_APPLICABLE = "not_applicable", "Sans objet"
        PENDING = "pending", "En attente"
        SENT = "sent", "Envoyé"
        FAILED = "failed", "Échoué"

    club = models.ForeignKey(
        "clubs.Club",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="notifications",
        help_text=(
            "Facultatif : renseigne pour toute notification liee a un club, "
            "vide pour une alerte de portee plateforme (voir docstring du "
            "modele)."
        ),
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="Destinataire unique. La lecture est TOUJOURS filtree sur ce champ, jamais sur `club`.",
    )
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    title = models.CharField(max_length=160, help_text="Titre court, en francais clair (CLAUDE.md regle n20).")
    body = models.TextField(help_text="Message pret a afficher, en francais clair (CLAUDE.md regle n20).")
    link_object_type = models.CharField(
        max_length=60,
        blank=True,
        default="",
        help_text="Type de l'objet cible du clic (« mene a l'element concerne », CDC 4.17).",
    )
    link_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    email_requested = models.BooleanField(
        default=False,
        help_text=(
            "Vrai si cet evenement fait partie des notifications a double "
            "canal (in-app + email, CDC 4.17) ET que le destinataire a "
            "active l'email (NotificationPreference)."
        ),
    )
    email_status = models.CharField(
        max_length=15,
        choices=EmailStatus.choices,
        default=EmailStatus.NOT_APPLICABLE,
        help_text="Traite par une commande cron (CDC 6.5) : jamais dans la requete qui cree la notification.",
    )
    email_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(
        default=_default_created_at,
        help_text=(
            "Date de creation de la notification. Volontairement PAS "
            "`auto_now_add=True` (bug corrige tache 1.7t) : "
            "`apps.notifications.services.create_notification` doit pouvoir "
            "dater explicitement une notification via son parametre `now` "
            "(ex. import, correction retroactive, tests) sans que Django "
            "n'ecrase silencieusement cette valeur a l'insertion. Le defaut "
            "``_default_created_at`` ne s'applique que si le service omet le "
            "champ, ce qui n'arrive jamais en pratique (le service pose "
            "toujours `created_at` explicitement)."
        ),
    )

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["club", "recipient", "is_read", "created_at"]),
            models.Index(fields=["recipient", "is_read", "created_at"]),
            models.Index(fields=["email_status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - representation triviale
        return f"{self.event_type} / recipient {self.recipient_id}"


class NotificationPreference(models.Model):
    """Preference globale d'envoi email par utilisateur (CDC 4.17 ; §11.2).

    Un seul bouton global (pas de granularite par type d'evenement, la
    formulation du CDC 4.17 ne le demande pas -- voir Q1 de
    schema-donnees.md). Relation 1-1, cree a la premiere ecriture utile
    (voir ``apps.notifications.services.get_or_create_preference``) :
    aucune ligne n'existe pour un utilisateur qui n'a jamais touche ce
    reglage, ce qui n'empeche pas de lui appliquer la valeur par defaut
    ``email_enabled=True`` en lecture.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    email_enabled = models.BooleanField(
        default=True,
        help_text="Defaut vrai : un joueur recoit les notifications par email tant qu'il ne l'a pas desactive.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Preference de notification"
        verbose_name_plural = "Preferences de notification"

    def __str__(self) -> str:  # pragma: no cover - representation triviale
        return f"Preference notification / user {self.user_id}"
