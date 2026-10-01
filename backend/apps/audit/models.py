"""Modele du journal d'activite (CLAUDE.md regle n6 ; CDC chapitre 5).

Sources : docs/cahier-des-charges.md 5.1 (contenu d'une entree), 5.2
(types d'actions), 5.3 (inalterabilite) ; docs/lot0/schema-donnees.md
§1.2 (isolation multi-tenant, exception `AuditLog`), §1.3 (regle du
journal), §12.1 (champs exacts de `AuditLog`).

`AuditLog` est a portee plateforme, **pas** une sous-classe de
`apps.core.models.TenantModel` : contrairement a une table privee de
club classique, son champ `club` est facultatif (vide pour une action
de portee plateforme -- licence, session de support hors club,
parametres globaux -- schema §1.2). Une lecture de ce modele n'est donc
jamais filtree automatiquement par club actif ; l'ecran de consultation
reserve au Superuser (CDC 5.5, hors perimetre de cette tache) filtrera
explicitement par club quand necessaire.

Reference generique a l'objet concerne : `object_type` (nom du modele)
et `object_id` (identifiant, sous forme texte) forment une paire simple,
conformement a schema-donnees.md §12.1 -- delibierement **pas** le
framework `django.contrib.contenttypes` (pas de `GenericForeignKey`) :
la paire texte est suffisante ici, plus simple, et evite une dependance
supplementaire sur une table `ContentType` pour un simple libelle
d'audit qui n'a pas besoin d'etre traverse par l'ORM (on ne "suit"
jamais une `AuditLog` vers l'objet qu'elle decrit par relation Django).

Append-only, reellement applique (CDC 5.3), pas seulement documente :
- :class:`AuditLogQuerySet` bloque `update()` et `delete()` au niveau
  requete (bloque donc aussi bien `AuditLog.objects.filter(...).delete()`
  qu'un `queryset.update(...)`, qui contournent sinon `Model.save()`/
  `Model.delete()`).
- Le modele bloque en plus toute modification d'une instance deja
  enregistree (`save()`) et toute suppression d'instance (`delete()`),
  en defense en profondeur.
- Cette app n'enregistre volontairement **aucun** `admin.py` : `AuditLog`
  n'apparait donc dans aucun ecran de `django.contrib.admin` (aucune
  action d'edition ou de suppression n'est donc accessible par ce biais,
  CDC 5.3).

**Contenu medical jamais copie dans le journal** (CLAUDE.md regle n11 ;
CDC 5.2 "Medical" ; schema-donnees.md §1.3, §12.1) : c'est une regle
metier, elle vit dans le service d'audit
(`apps.audit.services.create_audit_log`), jamais ici -- ce modele reste
volontairement une structure de donnees passive, sans logique metier
(CLAUDE.md section 5). Le modele delegue neanmoins la verification au
service au moment de `full_clean()` (voir `clean()` ci-dessous), pour
qu'aucun appel direct a `AuditLog(...).save()` ne puisse contourner le
garde-fou -- l'appelant normal reste `create_audit_log`, qui applique la
meme regle avant meme de construire l'instance.
"""

from __future__ import annotations

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class AuditLogImmutableError(Exception):
    """Levee sur toute tentative de modifier ou supprimer une `AuditLog`.

    CDC 5.3 : « Le journal fonctionne en ajout seul : aucune interface, y
    compris celle des Superusers, ne permet de modifier ou supprimer une
    entree. »
    """


class AuditLogQuerySet(models.QuerySet):
    """Queryset append-only : `update()`/`delete()` en masse sont bloques.

    Necessaire en plus du blocage au niveau de l'instance
    (`AuditLog.save()`/`delete()`) : `QuerySet.update()` et
    `QuerySet.delete()` operent en SQL direct (`UPDATE`/`DELETE ... WHERE`)
    sans jamais appeler `Model.save()`/`Model.delete()` sur chaque
    instance -- les bloquer uniquement au niveau du modele laisserait donc
    une voie de contournement triviale (`AuditLog.objects.filter(...).update(...)`).
    """

    def update(self, **kwargs):
        raise AuditLogImmutableError(
            "Le journal d'activite est en ajout seul (CDC 5.3) : impossible "
            "de modifier une ou plusieurs entrees existantes, meme via "
            "update()."
        )

    def delete(self):
        raise AuditLogImmutableError(
            "Le journal d'activite est en ajout seul (CDC 5.3) : impossible "
            "de supprimer une ou plusieurs entrees existantes, meme via "
            "delete()."
        )


class AuditLogManager(models.Manager.from_queryset(AuditLogQuerySet)):
    """Manager par defaut de `AuditLog`, base sur le queryset append-only."""


class AuditLog(models.Model):
    """Entree du journal d'activite (schema-donnees.md §12.1, CDC 5.1)."""

    club = models.ForeignKey(
        "clubs.Club",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        db_index=True,
        help_text=(
            "Facultatif : vide pour une action de portee plateforme "
            "(licence, session de support hors club, parametres globaux -- "
            "CDC 5.1, schema §1.2). `SET_NULL` (et non `CASCADE` comme sur "
            "les tables privees de club classiques) : le journal doit "
            "survivre a la suppression eventuelle d'un club, coherent avec "
            "la conservation minimale sans purge du CDC 5.5/§12.2."
        ),
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_logs",
        db_index=True,
        help_text="Identite reelle de l'acteur, y compris en Ghost Mode (CDC 5.4).",
    )
    acted_as_ghost = models.BooleanField(
        default=False,
        help_text=(
            "Vrai si `actor` est un Superuser agissant dans un club : le "
            "club voit alors « Systeme Vesta » (CDC 5.4). Renseigne "
            "automatiquement par `apps.core.services.log_action` a partir "
            "du contexte `apps.core.ghost_context` (arme par "
            "`apps.core.authentication.TenantJWTAuthentication` pour la "
            "duree d'une requete Superuser porteuse d'une session de "
            "support valide, tache 1.8) quand l'appelant ne le fournit pas "
            "explicitement."
        ),
    )
    support_session_id = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text=(
            "Identifiant (texte) de la `apps.licences.models.SupportSession` "
            "en cours, si `acted_as_ghost` est vrai (tache 1.8). Meme "
            "mecanisme de renseignement automatique que `acted_as_ghost` "
            "ci-dessus."
        ),
    )
    action_type = models.CharField(
        max_length=80,
        help_text=(
            "Chaine hierarchique et stable, ex. « auth.login », "
            "« role.appointed », « medical.record.viewed » (CDC 5.2)."
        ),
    )
    object_type = models.CharField(max_length=80, help_text="Nom du modele concerne.")
    object_id = models.CharField(max_length=40, help_text="Identifiant (texte) de l'objet concerne.")
    before = models.JSONField(
        null=True,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="Etat avant l'action. Jamais de contenu medical (CDC 5.2 ; regle appliquee par le service).",
    )
    after = models.JSONField(
        null=True,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="Etat apres l'action. Jamais de contenu medical (CDC 5.2 ; regle appliquee par le service).",
    )
    ip_address = models.CharField(
        max_length=45,
        blank=True,
        default="",
        help_text=(
            "Adresse IP de la requete a l'origine de l'action (CDC 5.1). "
            "Reste vide pour les appels qui n'ont pas encore de contexte "
            "HTTP (signaux sur les modeles de la tache 1.2, commandes de "
            "gestion) : sera systematiquement renseigne des que les vues "
            "API (tache 1.3 et suivantes) appelleront ce service depuis "
            "une requete authentifiee -- point ouvert signale au compte "
            "rendu de cette tache (1.6)."
        ),
    )
    user_agent = models.TextField(blank=True, default="")
    device = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditLogManager()

    class Meta:
        verbose_name = "Entree de journal"
        verbose_name_plural = "Journal d'activite"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["club", "created_at"], name="auditlog_club_created_idx"),
            models.Index(fields=["actor", "created_at"], name="auditlog_actor_created_idx"),
            models.Index(fields=["object_type", "object_id"], name="auditlog_object_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - representation triviale
        return f"{self.action_type} / {self.object_type}#{self.object_id}"

    def clean(self):
        # Delegue au service d'audit : la regle metier (garde-fou anti
        # contenu medical) vit dans apps.audit.services, jamais ici
        # (CLAUDE.md section 5). Import tardif pour eviter tout import
        # circulaire au chargement des apps.
        from apps.audit.services import assert_no_clinical_content

        assert_no_clinical_content(self.action_type, self.before, field_label="before")
        assert_no_clinical_content(self.action_type, self.after, field_label="after")

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise AuditLogImmutableError(
                "Le journal d'activite est en ajout seul (CDC 5.3) : "
                "impossible de modifier une entree existante."
            )
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditLogImmutableError(
            "Le journal d'activite est en ajout seul (CDC 5.3) : impossible "
            "de supprimer une entree existante."
        )
