"""Signaux de l'app clubs : detectent les evenements a journaliser.

CLAUDE.md section 5 : la regle metier (quoi journaliser, avec quel
contenu avant/apres) vit dans ``apps.clubs.services``, jamais ici. Ces
recepteurs se contentent de detecter l'evenement (creation, transition
d'etat) et de leur deleguer l'ecriture reelle.

Branche par ``apps.clubs.apps.ClubsConfig.ready()``.
"""

from __future__ import annotations

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.clubs import services
from apps.clubs.models import ImportBatch, Membership, MembershipRole, PresidencyTransfer


@receiver(pre_save, sender=MembershipRole)
def _stash_membership_role_before(sender, instance, **kwargs):
    """Capture l'etat avant modification (necessaire pour before/after)."""

    if instance.pk is None:
        instance._audit_before = None
        return
    # `all_objects` : usage plateforme legitime (le contexte "club actif"
    # n'existe pas forcement au moment ou un signal se declenche -- ex.
    # commande cron, factory de test hors requete HTTP).
    previous = MembershipRole.all_objects.filter(pk=instance.pk).first()
    instance._audit_before = services.role_snapshot(previous) if previous else None


@receiver(post_save, sender=MembershipRole)
def _log_membership_role(sender, instance, created, **kwargs):
    if created:
        services.log_membership_role_appointed(instance)
        return

    before = getattr(instance, "_audit_before", None)
    if before is not None and before.get("revoked_at") is None and instance.revoked_at is not None:
        services.log_membership_role_revoked(instance, before)


@receiver(pre_save, sender=Membership)
def _stash_membership_before(sender, instance, **kwargs):
    if instance.pk is None:
        instance._audit_before = None
        return
    previous = Membership.all_objects.filter(pk=instance.pk).first()
    instance._audit_before = services.membership_snapshot(previous) if previous else None


@receiver(post_save, sender=Membership)
def _log_membership(sender, instance, created, **kwargs):
    if created:
        services.log_membership_created(instance)
        return

    before = getattr(instance, "_audit_before", None)
    if (
        before is not None
        and before.get("status") != Membership.Status.DEPARTED
        and instance.status == Membership.Status.DEPARTED
    ):
        services.log_membership_departed(instance, before, actor=instance.left_by)


@receiver(post_save, sender=ImportBatch)
def _log_import_batch(sender, instance, created, **kwargs):
    if created:
        services.log_import_batch_created(instance)


@receiver(post_save, sender=PresidencyTransfer)
def _log_presidency_transfer(sender, instance, created, **kwargs):
    if created:
        services.log_presidency_transfer_created(instance)
