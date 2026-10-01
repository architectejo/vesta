"""Factories factory_boy de l'app accounts (tache 1.2)."""

from __future__ import annotations

import factory
from django.utils import timezone

from apps.accounts.models import TermsAcceptance, TermsVersion, User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"joueur{n}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    must_change_password = False

    @factory.post_generation
    def password(self, create, extracted, **kwargs):  # noqa: FBT001
        raw_password = extracted or "MotDePasse123"
        self.set_password(raw_password)
        if create:
            self.save()


class SuperuserFactory(UserFactory):
    """Superuser (CLAUDE.md regle n1 : jamais de fiche joueur/Membership)."""

    is_superuser = True
    must_change_password = False


class TermsVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TermsVersion

    published_at = factory.LazyFunction(timezone.now)
    content = "Texte des CGU (donnee de test, jamais commite en production)."
    created_by = factory.SubFactory(SuperuserFactory)


class TermsAcceptanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TermsAcceptance

    user = factory.SubFactory(UserFactory)
    terms_version = factory.SubFactory(TermsVersionFactory)
    accepted_at = factory.LazyFunction(timezone.now)
