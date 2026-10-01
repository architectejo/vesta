"""Stockage prive pour les fichiers sensibles (CDC 6.7, 7.6 ; CLAUDE.md
section 2 regle n10) : justificatifs, fiches d'adhesion, documents
medicaux, fichiers d'import CSV. Jamais servi directement par le serveur
web -- toujours par une vue authentifiee qui revalide le club et le role
avant de streamer le contenu (voir les vues de telechargement de chaque
app, ex. ``apps.clubs.views.MembershipApplicationPdfDownloadView``).

Corrige l'ecart bloquant B10 de la revue de conformite de fin de Lot 1
(tache 1.14, `cdc-reviewer`) : ``MembershipApplication.application_pdf_file``
et ``ImportBatch.source_file``/``report_file`` etaient serves directement
depuis ``MEDIA_ROOT``, sans aucun controle d'acces.

Une instance de stockage DEDIEE (``django.core.files.storage.FileSystemStorage``),
plutot qu'un changement global de ``MEDIA_ROOT`` : les images publiques de
marque blanche (logo du club, photo de profil -- CLAUDE.md section 2
regle n18) restent sur le stockage public habituel ; seuls les champs qui
declarent explicitement ``storage=private_storage`` changent d'emplacement.
"""

from __future__ import annotations

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.functional import cached_property


class PrivateFileStorage(FileSystemStorage):
    """``FileSystemStorage`` pointant vers ``settings.PRIVATE_MEDIA_ROOT``.

    ``base_location`` est surcharge pour lire ``settings.PRIVATE_MEDIA_ROOT``
    au lieu du ``settings.MEDIA_ROOT`` du parent (meme mecanisme que
    ``FileSystemStorage`` -- ``cached_property`` invalidee via le signal
    ``setting_changed``, voir ``_clear_cached_properties`` ci-dessous) :
    reste reactif si ``PRIVATE_MEDIA_ROOT`` change en cours de processus,
    ex. la fixture pytest qui isole chaque test dans un dossier temporaire
    (meme principe que ``MEDIA_ROOT``, voir ``conftest.py``), plutot que
    de figer un chemin absolu a la construction de ``private_storage``
    ci-dessous -- important aussi pour que la migration Django qui
    reference ce stockage (``storage=apps.core.storage.PrivateFileStorage()``,
    generee sans argument) reste portable entre le poste de developpement
    et la production, ou ``PRIVATE_MEDIA_ROOT`` differe.

    ``.url()`` leve TOUJOURS une erreur, quel que soit ``MEDIA_URL`` :
    defense en profondeur si un serializer oubliait de passer par la vue
    de telechargement authentifiee et appelait `.url` par erreur -- sans
    cette surcharge, ``FileSystemStorage.url()`` se replierait
    silencieusement sur ``settings.MEDIA_URL`` (comportement herite du
    parent, PAS ce qui est voulu ici : ce stockage n'a jamais d'URL
    publique, meme par defaut).
    """

    @cached_property
    def base_location(self):
        return self._value_or_setting(self._location, settings.PRIVATE_MEDIA_ROOT)

    def _clear_cached_properties(self, setting, **kwargs):
        if setting == "PRIVATE_MEDIA_ROOT":
            self.__dict__.pop("base_location", None)
            self.__dict__.pop("location", None)
        else:
            super()._clear_cached_properties(setting, **kwargs)

    def url(self, name):
        raise ValueError(
            "Stockage prive (CDC 6.7, 7.6) : aucune URL publique n'est "
            "jamais generee pour ce fichier. Utilisez la vue de "
            "telechargement authentifiee correspondante, jamais `.url`."
        )


# Instance unique, reutilisee par tous les champs prives (``storage=private_storage``).
private_storage = PrivateFileStorage()
