"""Comptes techniques reserves de la plateforme (audit securite MA1, m-B).

Le compte « Systeme » est l'acteur des traitements automatiques (cron). Il
ne doit jamais pouvoir etre revendique par un humain : son adresse, et tout
domaine ``.invalid`` (reserve par la RFC 2606), sont refuses a toute creation
ou tout changement d'email de compte. Module volontairement sans dependance
vers une app metier (evite accounts -> treasury).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError

SYSTEM_ACTOR_EMAIL = "systeme@vesta.invalid"
# Libelle du journal : distinct de « Système Vesta » (Ghost Mode, CDC 5.4).
SYSTEM_ACTOR_DISPLAY_NAME = "Système"

RESERVED_EMAIL_MESSAGE = "Cette adresse email est réservée et ne peut pas être utilisée pour un compte."


def is_reserved_email(email: str) -> bool:
    normalized = (email or "").strip().lower()
    if normalized == SYSTEM_ACTOR_EMAIL:
        return True
    domain = normalized.rpartition("@")[2]
    return domain == "invalid" or domain.endswith(".invalid")


def validate_email_not_reserved(email: str) -> None:
    if is_reserved_email(email):
        raise ValidationError(RESERVED_EMAIL_MESSAGE, code="reserved_email")
