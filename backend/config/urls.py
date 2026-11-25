"""URLs racine du projet Vesta.

Tache 1.3 : premieres routes API metier (authentification, CDC 4.1, 7.1,
7.5), sous ``api/v1/auth/``.

``/admin/`` (audit de securite du Lot 1, ecart bloquant B2) : n'est
branche **que si ``settings.DEBUG`` est vrai**. ``/admin/login/`` passe
par ``django.contrib.auth.backends.ModelBackend``, pas par
``apps.accounts.services.authenticate_login`` : aucun blocage apres
echecs, aucune limitation de requetes, aucune entree de journal --
c'etait deja, a lui seul, une deuxieme surface de connexion non
protegee par les garde-fous de CDC 7.1/7.6. Pire : ``User`` n'a pas
d'attribut ``is_staff`` (ce modele n'utilise pas
``django.contrib.auth.models.PermissionsMixin``, voir
``apps.accounts.models.User``), donc un mot de passe **correct** y
provoquait une erreur 500 (``AttributeError``) alors qu'un mot de passe
faux y repondait simplement 200 -- un oracle de mot de passe trivial,
sans meme se connecter. ``DEBUG`` est deja force a ``False`` en
production (``config.settings.prod``) : ``/admin/`` n'existe donc
tout simplement plus en production (404, aucune route enregistree),
sans dependre d'une eventuelle future correction de ``User``/de
l'admin. Il reste un outil utile en developpement local (verification
de demarrage, tache 1.0) : toujours branche quand ``DEBUG`` est vrai.
"""

from django.conf import settings
from django.urls import include, path

urlpatterns = [
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/clubs/", include("apps.clubs.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/licences/", include("apps.licences.urls")),
    path("api/v1/treasury/", include("apps.treasury.urls")),
    path("api/v1/sport/", include("apps.sport.urls")),
    path("api/v1/medical/", include("apps.medical.urls")),
    path("api/v1/logistics/", include("apps.logistics.urls")),
    path("api/v1/mercato/", include("apps.mercato.urls")),
    path("api/v1/assemblies/", include("apps.assemblies.urls")),
    path("api/v1/social/", include("apps.social.urls")),
    path("api/v1/audit/", include("apps.audit.urls")),
]

if settings.DEBUG:
    from django.conf.urls.static import static
    from django.contrib import admin

    urlpatterns.append(path("admin/", admin.site.urls))
    # Sert MEDIA_ROOT (photos, logos, images de publication -- fichiers
    # PUBLICS uniquement, cf. apps.core.storage : jamais les fichiers prives)
    # en developpement local. En production, un vrai serveur web (LiteSpeed)
    # sert ces fichiers directement -- Django ne les sert jamais lui-meme.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
