"""Limitation du nombre de requetes sur les points d'acces publics de
l'assistant de creation de club (CDC 7.6 ; tache 1.9).

Meme principe que ``apps.accounts.throttling`` (points sensibles non
authentifies de la connexion) : reutilise directement
``HardenedIdentThrottle`` (durcissement de ``get_ident`` contre un
``NUM_PROXIES`` mal configure) plutot que de le dupliquer.
"""

from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle

from apps.accounts.throttling import HardenedIdentThrottle


class ClubCreationSettingsRateThrottle(HardenedIdentThrottle, AnonRateThrottle):
    """Lecture des parametres publics de l'assistant (spec §4.3) : peu
    sensible (aucune ecriture, aucun mot de passe verifie), mais reste un
    point d'acces public -- CDC 7.6."""

    scope = "club_creation_settings"


class ClubCreationRateThrottle(HardenedIdentThrottle, AnonRateThrottle):
    """Creation effective d'un club (spec §2 : « le point d'acces de
    creation est public : l'API applique la limitation de requetes du
    7.6 »). Seuil plus strict que la lecture des parametres : chaque
    reussite cree un club, un compte et une licence d'essai."""

    scope = "club_creation"
