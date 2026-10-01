"""Signaux de l'app accounts : detectent les evenements a journaliser.

CLAUDE.md section 5 : la regle metier vit dans ``apps.accounts.services``,
jamais ici. Branche par ``apps.accounts.apps.AccountsConfig.ready()``.
"""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts import services
from apps.accounts.models import TermsAcceptance


@receiver(post_save, sender=TermsAcceptance)
def _log_terms_accepted(sender, instance, created, **kwargs):
    if created:
        services.log_terms_accepted(instance)
