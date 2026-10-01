"""Commande de gestion : publication d'une version des CGU (CDC 2.5, 7.5 ;
10.2 n°27).

L'espace Superuser « Paramètres globaux » (CDC 4.18) n'existe pas encore :
cette commande est le moyen de publier la première version des CGU, sans
laquelle aucun club ne peut être créé (assistant « Créer votre club »).

Le texte des CGU est un contenu juridique fourni par le client : la commande
n'embarque et n'invente aucun texte par défaut.

Usage ::

    python manage.py publish_terms_version \\
        --superuser-email admin@exemple.org --content-file cgu.txt
"""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import TermsPublicationError, publish_terms_version


class Command(BaseCommand):
    help = (
        "Publie une nouvelle version des CGU de Vesta. Le texte doit être "
        "fourni par le client (--content-file ou --content)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--superuser-email",
            required=True,
            help="Adresse email du Superuser qui publie cette version.",
        )
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument(
            "--content-file",
            help="Chemin d'un fichier texte UTF-8 contenant le texte des CGU.",
        )
        source.add_argument("--content", help="Texte des CGU, fourni directement.")
        parser.add_argument(
            "--published-at",
            help="Date d'entrée en vigueur (ISO 8601, ex. 2026-10-01 ou "
            "2026-10-01T08:00:00+02:00). Par défaut : maintenant.",
        )

    def handle(self, *args, **options):
        email = (options["superuser_email"] or "").strip().lower()
        user = User.objects.filter(email=email).first()
        if user is None:
            raise CommandError(f"Aucun compte ne correspond à l'adresse « {email} ».")
        if not user.is_superuser:
            raise CommandError(
                f"Le compte « {email} » n'est pas un Superuser : "
                "seul un Superuser peut publier les CGU."
            )

        content = self._read_content(options)
        published_at = self._parse_published_at(options.get("published_at"))

        try:
            version = publish_terms_version(
                published_by=user, content=content, published_at=published_at
            )
        except TermsPublicationError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Version des CGU publiée : {version.version_number}")
        )

    def _read_content(self, options) -> str:
        if options.get("content") is not None:
            content = options["content"]
        else:
            path = Path(options["content_file"])
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise CommandError(
                    f"Le fichier « {path} » n'est pas encodé en UTF-8."
                ) from exc
            except OSError as exc:
                raise CommandError(
                    f"Impossible de lire le fichier « {path} » : {exc.strerror or exc}."
                ) from exc
        if not content.strip():
            raise CommandError("Le texte des CGU est vide.")
        return content

    def _parse_published_at(self, raw):
        if raw is None:
            return timezone.now()
        try:
            value = datetime.fromisoformat(raw.strip())
        except ValueError as exc:
            raise CommandError(
                f"Date invalide « {raw} » : utilisez le format ISO 8601 "
                "(ex. 2026-10-01 ou 2026-10-01T08:00:00+02:00)."
            ) from exc
        if timezone.is_naive(value):
            # Date sans fuseau : interprétée en UTC (dates stockées en UTC).
            value = value.replace(tzinfo=dt_timezone.utc)
        return value
