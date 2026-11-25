"""Permissions de l'app audit : le journal n'est visible que par les
Superusers (CDC 2.4, 5, 5.5)."""

from apps.core.permissions import IsSuperuser

__all__ = ["IsSuperuser"]
