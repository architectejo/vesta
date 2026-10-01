"""Modeles de base de l'app core : socle multi-tenant (CLAUDE.md regle n8).

Toute table privee de club doit heriter de :class:`TenantModel` (classe
abstraite) : elle ajoute automatiquement le champ ``club`` obligatoire et
deux managers/gestionnaires de requetes :

- ``objects`` (par defaut) : **tenant-aware**, filtre automatiquement sur
  le club actif du contexte courant (voir ``apps.core.tenant``). Leve
  :class:`~apps.core.tenant.NoActiveClubError` si aucun club actif n'est
  present -- « une requete sans club actif est refusee » (regle n8).
- ``all_objects`` : **non filtre**, reserve aux usages explicitement
  multi-clubs cote plateforme (commandes cron, imports, espace
  Superuser). Ne jamais l'utiliser depuis une vue cote club : c'est
  precisement pour que ce genre d'acces reste visible et exceptionnel a
  la revue de code que ce manager porte un nom distinct de ``objects``
  (regle n8 : « jamais de ``Model.objects.all()`` sur une table privee
  dans une vue »).

Exemple d'utilisation par une autre app (voir ``apps.clubs.models`` pour
un exemple reel) ::

    from apps.core.models import TenantModel

    class Membership(TenantModel):
        user = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
        ...

``Membership.objects.all()`` est alors automatiquement filtre sur le
club actif du contexte courant.

Exceptions documentees a l'usage de ``TenantModel`` (portee plateforme,
pas de filtrage par club) : ``User``, ``Club`` et ``Licence`` eux-memes,
``TermsVersion``/``TermsAcceptance``, ``AuditLog`` (club facultatif),
``Notification`` (club facultatif) -- voir docs/lot0/schema-donnees.md
§1.2.
"""

from __future__ import annotations

from django.db import models

from apps.core.tenant import NoActiveClubError, TenantMismatchError, get_active_club

__all__ = [
    "NoActiveClubError",
    "TenantMismatchError",
    "TenantQuerySet",
    "TenantManager",
    "TenantModel",
]


class TenantQuerySet(models.QuerySet):
    """QuerySet tenant-aware, avec un point d'echappement explicite.

    :meth:`for_club` sert aux usages legitimement multi-clubs (une
    commande cron qui parcourt tous les clubs l'un apres l'autre, par
    exemple) : il filtre explicitement sur un club donne, sans dependre
    du club actif du contexte courant. Il n'est disponible que via
    ``TenantModel.all_objects`` (non filtre par defaut) -- jamais via
    ``objects``, qui reste tenant-aware par defaut.
    """

    def for_club(self, club) -> "TenantQuerySet":
        return self.filter(club=club)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Manager par defaut de :class:`TenantModel` : filtre sur le club actif.

    Leve :class:`NoActiveClubError` si aucun club actif n'est present
    dans le contexte courant au moment de l'evaluation de la requete
    (CLAUDE.md regle n8). Le club actif est fourni par
    ``apps.core.tenant`` : un contexte independant de la requete HTTP
    pour cette tache 1.2, branche sur la requete HTTP reelle par la
    tache 1.3 (authentification JWT).
    """

    def get_queryset(self) -> TenantQuerySet:
        club = get_active_club()
        if club is None:
            raise NoActiveClubError(
                "Aucun club actif dans le contexte de la requete : acces "
                "refuse (CLAUDE.md regle n8 ; voir apps.core.tenant "
                "et apps.core.services.resolve_active_membership)."
            )
        return super().get_queryset().filter(club=club)


class TenantModel(models.Model):
    """Classe abstraite pour toute table privee de club (isolation multi-tenant).

    Ajoute le champ ``club`` obligatoire, indexe, avec suppression en
    cascade quand le club est supprime (un club n'est jamais supprime en
    fonctionnement normal ; cette operation reste reservee au Superuser
    -- voir 2.5 -- et n'a pas de sens sans supprimer aussi ses donnees
    privees).

    Audit de securite du Lot 1 (ecart bloquant B4) : ``TenantManager``
    (ci-dessus) ne protege que les **lectures**. :meth:`save` complete
    cette protection cote **ecriture** :

    - si un club actif existe dans le contexte courant et que ``club``
      differe de ce club actif, l'ecriture est refusee
      (:class:`~apps.core.tenant.TenantMismatchError`) -- sans club actif
      (import, commande de gestion, contexte Superuser), aucune
      restriction n'est appliquee (comportement deja voulu par
      ``TenantManager`` cote lecture) ;
    - dans tous les cas, ``full_clean()`` est appele avant l'ecriture
      reelle : les methodes ``clean()`` de cohorence inter-cles deja
      ecrites par chaque sous-classe (ex. ``MembershipRole``,
      ``Membership``, ``MembershipApplication``, ``PresidencyTransfer``)
      s'appliquent ainsi a **tout** ``create()``/``save()`` direct, pas
      seulement quand un formulaire appelle ``full_clean()``
      explicitement.
    """

    club = models.ForeignKey(
        "clubs.Club",
        on_delete=models.CASCADE,
        db_index=True,
        help_text="Isolation multi-tenant (CLAUDE.md regle n8).",
    )

    objects = TenantManager()
    all_objects = models.Manager.from_queryset(TenantQuerySet)()

    class Meta:
        abstract = True
        # `base_manager_name`/`default_manager_name` = `all_objects`, pas
        # `objects` (audit de securite du Lot 1, ecart bloquant B4) :
        # certaines operations internes de Django (validation d'un champ
        # unique/`OneToOneField` via `full_clean()`, existence d'une
        # cible de `ForeignKey`...) interrogent `Model._default_manager`/
        # `Model._base_manager`, jamais directement l'attribut `objects`.
        # Sans ce reglage, ces operations passeraient par le manager
        # tenant-aware et leveraient `NoActiveClubError` hors de tout
        # contexte "club actif" (import, commande de gestion, factory de
        # test sans `active_club(...)`) -- y compris pour un simple
        # controle d'unicite qui n'a lui-meme aucune raison d'etre limite
        # au club actif (l'unicite se verifie sur toute la table).
        # `Model.objects` reste, lui, l'attribut explicitement tenant-aware
        # utilise par le code applicatif (vues, services) -- ce reglage
        # ne change que la resolution **interne** de Django.
        #
        # Chaque sous-classe concrete doit reprendre ce reglage
        # explicitement (``class Meta(TenantModel.Meta): ...``) : Django
        # ne propage pas automatiquement les options d'un ``Meta``
        # abstrait a un enfant qui declare son propre ``Meta`` sans en
        # heriter (voir ``apps.clubs.models``, seul module a ce jour a
        # definir des sous-classes concretes de ``TenantModel``).
        base_manager_name = "all_objects"
        default_manager_name = "all_objects"

    def save(self, *args, **kwargs):
        active_club = get_active_club()
        if (
            active_club is not None
            and self.club_id is not None
            and self.club_id != active_club.id
        ):
            raise TenantMismatchError(
                "Ecriture refusee : le club renseigne sur cet enregistrement "
                f"({self.club_id!r}) ne correspond pas au club actif du "
                f"contexte courant ({active_club.id!r}) -- CLAUDE.md regle n8."
            )

        self.full_clean()
        super().save(*args, **kwargs)
