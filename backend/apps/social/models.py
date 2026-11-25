"""Modeles de l'app social : fil d'actualite, communiques, chat (CDC 4.16).

Sources : docs/lot0/schema-donnees.md §10 ; docs/ecrans/fil-public-communication.md ;
10.2 n° 12, 16, 23. Voir CLAUDE.md section 5 : toute table privee porte
``club`` et n'est accedee que via les managers tenant-aware de
``apps.core`` (``TenantModel``).

Point de securite CRITIQUE (fil-public-communication.md, point ouvert
F.13 ; alerte deja remontee au client, position provisoire la plus
prudente appliquee ici -- CLAUDE.md section 1, contradiction schema/besoin
non definitivement tranchee) :

``schema-donnees.md`` §1.1 classe le type ``Image`` comme un **asset
public par conception** (« servi comme un asset public de l'application »)
-- correct pour le logo du club, la photo de profil, et une publication de
visibilite **Publique**. Ce n'est PAS correct pour une image d'une
publication de visibilite **Club** (§10.1 ``PostImage.file``), ni pour une
image du **chat** (§10.3 ``ChatMessage.image``, y compris le canal
General) : ces images ne doivent jamais etre atteignables sans
authentification qui verifie le club (et, pour le canal Bureau, le role),
sous peine de fuite de donnees privees via une URL publique devinable
(CLAUDE.md regle n° 10).

Application concrete ici :

- ``PostImage.file`` utilise un champ ``ImageField`` dont le stockage est
  **calcule dynamiquement a chaque acces** (:class:`PostVisibilityAwareImageField`/
  :class:`PostVisibilityAwareImageFieldFile` ci-dessous), et non fige au
  premier enregistrement : indispensable, car un simple attribut
  d'instance positionne pendant ``save()`` ne survivrait pas a une
  RELECTURE ulterieure de la ligne depuis la base (chaque nouvelle requete
  reconstruit un objet ``FieldFile`` neuf, dont l'attribut ``storage``
  reprendrait alors le stockage par defaut du champ -- premiere version de
  ce correctif, corrigee pendant la tache 4.6 apres qu'un test l'a revele).
  Avec ce champ dedie, ``image.file.storage``/``image.file.url`` refletent
  TOUJOURS l'etat actuel de ``post.visibility`` : publique -> stockage
  public existant (``MEDIA_URL``, conforme au schema) ; Club ->
  ``apps.core.storage.private_storage`` (jamais d'URL publique, `.url`
  leve ``ValueError`` comme toute autre valeur privee du projet).
- ``ChatMessage.image`` est TOUJOURS sur ``private_storage`` (declare
  directement au champ, sans logique conditionnelle) : le chat n'a aucune
  notion de publication « Publique » (§10.3), y compris le canal General
  -- servi uniquement par une vue authentifiee qui verifie le club et,
  pour le canal Bureau, le role (``apps.social.views``).

Ecarts assumes par rapport au schema figé de Lot 0 (additifs, non
destructifs, signales au compte rendu de la tache 4.6) :

- ``ChatChannelRead`` : absente de schema-donnees.md §10.3 (qui indique
  « aucune entite supplementaire n'est necessaire cote donnees », a propos
  de la frequence d'interrogation -- pas du compteur de non-lus). Necessaire
  pour persister « le dernier message vu » par membre et par canal
  (fil-public-communication.md §C3 : compteur de non-lus, §C4 : « l'API
  recoit le dernier identifiant vu »). A faire valider par `backend-dev`/le
  client, comme les autres additifs techniques du projet
  (``Assembly.reminder_sent_at``).
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Q
from django.db.models.fields.files import ImageFieldFile

from apps.core.models import TenantModel
from apps.core.storage import private_storage
from apps.core.validators import validate_image_format, validate_upload_size


class PostVisibilityAwareImageFieldFile(ImageFieldFile):
    """``ImageFieldFile`` dont le stockage depend, a CHAQUE acces, de la
    visibilite du ``Post`` parent (voir docstring du module -- point de
    securite critique). Ne stocke jamais ce choix en base : il est
    recalcule a chaque lecture, donc jamais perime apres une RELECTURE de
    la ligne depuis la base (contrairement a un attribut d'instance
    positionne une seule fois pendant ``save()``)."""

    @property
    def storage(self):
        if self.instance.post.visibility == Post.Visibility.CLUB_ONLY:
            return private_storage
        return default_storage

    @storage.setter
    def storage(self, value):
        # `FieldFile.__init__` fait `self.storage = field.storage` : on
        # ignore cette affectation initiale (la propriete ci-dessus
        # recalcule toujours la bonne valeur), sans lever d'erreur.
        pass


class PostVisibilityAwareImageField(models.ImageField):
    attr_class = PostVisibilityAwareImageFieldFile


class Post(TenantModel):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Publique"
        CLUB_ONLY = "club_only", "Club"

    class PostKind(models.TextChoices):
        MANUAL = "manual", "Manuelle"
        AUTO_RESULT = "auto_result", "Resultat automatique"
        AUTO_TRANSFER = "auto_transfer", "Transfert automatique"
        AUTO_NEW_PLAYER = "auto_new_player", "Nouveau joueur automatique"

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="posts")
    body = models.TextField(blank=True)
    visibility = models.CharField(max_length=10, choices=Visibility.choices)
    post_kind = models.CharField(max_length=20, choices=PostKind.choices, default=PostKind.MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Publication"
        verbose_name_plural = "Publications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["club", "visibility", "created_at"]),
            models.Index(fields=["visibility", "created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Post {self.pk} / club {self.club_id}"

    def clean(self):
        if not self.body and self.pk is None:
            # Controle complet (au moins un texte OU une image) fait en
            # service, apres l'ecriture des images associees -- ici on ne
            # bloque jamais un `Post` sans image au moment de sa propre
            # creation (les `PostImage` sont creees apres, CLAUDE.md
            # section 5 : la regle vit dans `apps.social.services`).
            pass


class PostImage(TenantModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="images")
    file = PostVisibilityAwareImageField(
        upload_to="social/posts/",
        validators=[validate_upload_size, validate_image_format],
        help_text=(
            "Stockage calcule dynamiquement selon la visibilite du post "
            "parent (voir docstring du module, point de securite critique)."
        ),
    )
    order = models.PositiveSmallIntegerField()

    class Meta(TenantModel.Meta):
        verbose_name = "Image de publication"
        verbose_name_plural = "Images de publication"
        ordering = ["post_id", "order"]
        constraints = [
            models.UniqueConstraint(fields=["post", "order"], name="social_postimage_unique_order"),
            models.CheckConstraint(condition=Q(order__gte=1) & Q(order__lte=4), name="social_postimage_order_1_4"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Image {self.order} / post {self.post_id}"

    def clean(self):
        if self.post_id and self.club_id and self.post.club_id != self.club_id:
            raise ValidationError("L'image doit porter le même club que la publication.")

    def save(self, *args, **kwargs):
        # Point de securite critique (voir docstring du module) : une
        # image nouvellement televersee (pas encore stockee) bascule vers
        # le stockage prive des que la publication parente n'est PAS
        # publique -- jamais l'inverse (une image deja stockee ne change
        # pas de stockage a une simple mise a jour de `order`).
        if self.file and not getattr(self.file, "_committed", True):
            if self.post_id and self.post.visibility == Post.Visibility.CLUB_ONLY:
                self.file.storage = private_storage
        super().save(*args, **kwargs)


class Comment(TenantModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Commentaire"
        verbose_name_plural = "Commentaires"
        ordering = ["created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"Commentaire {self.pk} / post {self.post_id}"

    def clean(self):
        if self.post_id and self.club_id and self.post.club_id != self.club_id:
            raise ValidationError("Le commentaire doit porter le même club que la publication.")


class Like(TenantModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        verbose_name = "J'aime"
        verbose_name_plural = "J'aime"
        constraints = [models.UniqueConstraint(fields=["post", "user"], name="social_like_unique_post_user")]

    def __str__(self) -> str:  # pragma: no cover
        return f"Like {self.user_id} / post {self.post_id}"

    def clean(self):
        if self.post_id and self.club_id and self.post.club_id != self.club_id:
            raise ValidationError("Le « J'aime » doit porter le même club que la publication.")


class PostReport(TenantModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reports")
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Signalement de publication"
        verbose_name_plural = "Signalements de publication"
        constraints = [
            # Proposition (fil-public-communication.md, point ouvert F.3) :
            # un joueur ne peut signaler la meme publication qu'une fois.
            models.UniqueConstraint(fields=["post", "reported_by"], name="social_postreport_unique_post_reporter"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Signalement {self.pk} / post {self.post_id}"

    def clean(self):
        if self.post_id and self.club_id and self.post.club_id != self.club_id:
            raise ValidationError("Le signalement doit porter le même club que la publication.")


class Announcement(TenantModel):
    title = models.CharField(max_length=160)
    body = models.TextField()
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    published_at = models.DateTimeField(auto_now_add=True)
    pinned = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Communique"
        verbose_name_plural = "Communiques"
        ordering = ["-published_at"]

    def __str__(self) -> str:  # pragma: no cover
        return self.title


class AnnouncementImage(TenantModel):
    """Image jointe a un communique (club-accueil.md §5.2, 4 au plus).

    Toujours privee : un communique n'est « jamais public » (matrice
    2.4, fil-public-communication.md §B2), donc son image ne peut jamais
    rejoindre le stockage public -- pas de logique conditionnelle ici,
    contrairement a ``PostImage``.
    """

    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="images")
    file = models.ImageField(
        upload_to="social/announcements/",
        storage=private_storage,
        validators=[validate_upload_size, validate_image_format],
    )
    order = models.PositiveSmallIntegerField()

    class Meta(TenantModel.Meta):
        verbose_name = "Image de communique"
        verbose_name_plural = "Images de communique"
        ordering = ["announcement_id", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "order"], name="social_announcementimage_unique_order"
            ),
            models.CheckConstraint(
                condition=Q(order__gte=1) & Q(order__lte=4), name="social_announcementimage_order_1_4"
            ),
        ]

    def clean(self):
        if self.announcement_id and self.club_id and self.announcement.club_id != self.club_id:
            raise ValidationError("L'image doit porter le même club que le communiqué.")


class AnnouncementRead(TenantModel):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="reads")
    membership = models.ForeignKey("clubs.Membership", on_delete=models.CASCADE, related_name="+")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Accuse de lecture"
        verbose_name_plural = "Accuses de lecture"
        constraints = [
            models.UniqueConstraint(fields=["announcement", "membership"], name="social_announcementread_unique")
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Lu par {self.membership_id} / communique {self.announcement_id}"

    def clean(self):
        if self.announcement_id and self.club_id and self.announcement.club_id != self.club_id:
            raise ValidationError("L'accusé de lecture doit porter le même club que le communiqué.")
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("L'accusé de lecture doit porter le même club que l'adhésion.")


class ChatChannel(TenantModel):
    class ChannelType(models.TextChoices):
        GENERAL = "general", "General"
        BOARD = "board", "Bureau"

    channel_type = models.CharField(max_length=10, choices=ChannelType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Canal de discussion"
        verbose_name_plural = "Canaux de discussion"
        constraints = [
            models.UniqueConstraint(fields=["club", "channel_type"], name="social_chatchannel_unique_per_club")
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.channel_type} / club {self.club_id}"


class ChatMessage(TenantModel):
    channel = models.ForeignKey(ChatChannel, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="chat/",
        storage=private_storage,
        null=True,
        blank=True,
        validators=[validate_upload_size, validate_image_format],
        help_text="Toujours prive (point de securite critique, voir docstring du module).",
    )
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Message de chat"
        verbose_name_plural = "Messages de chat"
        ordering = ["sent_at"]
        indexes = [models.Index(fields=["channel", "sent_at"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"Message {self.pk} / canal {self.channel_id}"

    def clean(self):
        if self.channel_id and self.club_id and self.channel.club_id != self.club_id:
            raise ValidationError("Le message doit porter le même club que le canal.")
        if not self.body and not self.image:
            raise ValidationError("Écrivez un message ou ajoutez une image.")


class ChatChannelRead(TenantModel):
    """Dernier message lu par membre et par canal (additif technique,
    voir docstring du module) -- alimente le compteur de non-lus
    (fil-public-communication.md §C3)."""

    channel = models.ForeignKey(ChatChannel, on_delete=models.CASCADE, related_name="reads")
    membership = models.ForeignKey("clubs.Membership", on_delete=models.CASCADE, related_name="+")
    last_read_message = models.ForeignKey(
        ChatMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantModel.Meta):
        verbose_name = "Lecture de canal"
        verbose_name_plural = "Lectures de canal"
        constraints = [
            models.UniqueConstraint(fields=["channel", "membership"], name="social_chatchannelread_unique")
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Lecture {self.membership_id} / canal {self.channel_id}"

    def clean(self):
        if self.channel_id and self.club_id and self.channel.club_id != self.club_id:
            raise ValidationError("La lecture doit porter le même club que le canal.")
        if self.membership_id and self.club_id and self.membership.club_id != self.club_id:
            raise ValidationError("La lecture doit porter le même club que l'adhésion.")
