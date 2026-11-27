"""Tests de la commande ``seed_simulation`` sur la base de TEST, avec un
club entierement fictif (aucune donnee reelle, aucun fichier de ``data/``).

Defauts couverts (remontes par dev-b, base neuve + club fictif) :
a) le plan tactique ne place que des joueurs eligibles (jamais un joueur
   que les cartons du seed viennent de suspendre) ;
b) aucune seance/match passe n'est laisse deverrouille (CDC 4.7) ;
c) comptes de simulation : ``must_change_password`` leve et derniere
   version des CGU acceptee (journalisee au nom du compte Systeme) ;
   option refusee en bloc sur un club ayant le moindre compte reel
   (audit M1 : ``.invalid`` n'est PAS un domaine de simulation) ;
d) mercato : aucun slug fige, un autre club 100 % simulation est utilise,
   jamais un club reel (audit m2) ;
e) logo facultatif : ``data/logo.jpeg`` absent -> pas d'echec.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import TermsAcceptance, User
from apps.accounts.tests.factories import SuperuserFactory, TermsVersionFactory, UserFactory
from apps.audit.models import AuditLog
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import ClubFactory, ClubSettingsFactory, MembershipFactory, MembershipRoleFactory
from apps.core.management.commands.seed_simulation import is_simulation_email
from apps.core.reserved_accounts import SYSTEM_ACTOR_EMAIL
from apps.mercato.models import TransferOffer
from apps.sport import services as sport_services
from apps.sport.models import Event, Session, TacticalPlan, TacticalPlanPlacement

pytestmark = pytest.mark.django_db


def _fictive_user(email: str, **kwargs) -> User:
    return UserFactory(email=email, must_change_password=True, **kwargs)


@pytest.fixture
def fictive_setup(settings, tmp_path):
    settings.DEBUG = True
    # Logo absent : BASE_DIR pointe vers un dossier sans ``data/logo.jpeg``.
    fake_backend = tmp_path / "backend"
    fake_backend.mkdir()
    settings.BASE_DIR = fake_backend

    # Superuser de plateforme (PAS le compte technique « Systeme », que la
    # commande cree elle-meme via ``get_system_actor``).
    system = SuperuserFactory(email="superadmin@plateforme.test")
    terms = TermsVersionFactory(created_by=system)

    club = ClubFactory(name="Club Fictif", slug="club-fictif")
    ClubSettingsFactory(club=club)

    def _member(email, *roles):
        membership = MembershipFactory(club=club, user=_fictive_user(email), added_by=system)
        for role in roles:
            MembershipRoleFactory(membership=membership, club=club, role=role, appointed_by=system)
        return membership

    _member("fondateur@demo.local", MembershipRole.Role.PRESIDENT)
    _member("tresorier@demo.local", MembershipRole.Role.TREASURER)
    _member("coach@demo.local", MembershipRole.Role.COACH)
    players = [_member(f"joueur{i:02d}@demo.local") for i in range(24)]

    # Second club fictif (slug quelconque, PAS ``club-test-1``) pour le mercato.
    other = ClubFactory(name="Autre Club Fictif", slug="autre-club-fictif")
    ClubSettingsFactory(club=other)
    other_president = MembershipFactory(club=other, user=_fictive_user("president@autre.test"), added_by=system)
    MembershipRoleFactory(membership=other_president, club=other, role=MembershipRole.Role.PRESIDENT, appointed_by=system)
    other_player = MembershipFactory(club=other, user=_fictive_user("cible@autre.test"), added_by=system)

    return dict(club=club, other_club=other, system=system, terms=terms, players=players, other_player=other_player)


def _add_real_member(club, email: str, added_by) -> User:
    """Compte d'apparence reelle (ou a adresse provisoire ``.invalid``)."""

    user = UserFactory(email=email, must_change_password=True)
    MembershipFactory(club=club, user=user, added_by=added_by)
    return user


def _run_seed(slug: str, *extra):
    out, err = StringIO(), StringIO()
    call_command("seed_simulation", "--club", slug, *extra, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_is_simulation_email():
    assert is_simulation_email("a@demo.local")
    assert is_simulation_email("a@club.test")
    assert is_simulation_email("tresorier.adjoint@example.org")
    # ``.invalid`` = adresses provisoires de comptes REELS (audit M1).
    assert not is_simulation_email("a@club.invalid")
    assert not is_simulation_email(SYSTEM_ACTOR_EMAIL)
    assert not is_simulation_email("joueur@gmail.com")
    assert not is_simulation_email("")


def test_seed_simulation_on_fictive_club(fictive_setup):
    club = fictive_setup["club"]
    out, err = _run_seed(club.slug, "--prepare-e2e-accounts")

    # Aucune section ne doit echouer (en particulier Sport, defaut a).
    assert "ECHEC" not in err, err
    assert "seed_simulation terminé." in out

    # (e) logo absent : signale, sans echec.
    assert "Logo absent" in out

    # (a) plan tactique publie, uniquement avec des joueurs eligibles.
    plan = TacticalPlan.all_objects.get(club=club, name="Simulation — plan de démonstration")
    assert plan.is_published
    placements = list(TacticalPlanPlacement.all_objects.filter(club=club, plan=plan).select_related("membership"))
    assert len(placements) == 11
    from apps.sport.models import Suspension

    suspended_ids = set(Suspension.all_objects.filter(club=club).values_list("membership_id", flat=True))
    assert suspended_ids, "le seed doit declencher au moins une suspension"
    assert not suspended_ids & {p.membership_id for p in placements}

    # (b) aucune seance/match passe n'est laisse deverrouille.
    today = sport_services.get_club_today(club)
    past_events = list(Event.all_objects.filter(club=club, event_date__lt=today))
    assert len(past_events) >= 6
    for event in past_events:
        assert event.unlocked_by_id is None
        assert sport_services.is_event_locked(event)
    assert AuditLog.objects.filter(action_type="sport.event_relocked").count() >= 6

    # (c) comptes de simulation prets pour l'e2e (club 100 % simulation).
    terms = fictive_setup["terms"]
    for email in ("fondateur@demo.local", "coach@demo.local", "joueur00@demo.local", "tresorier.adjoint@example.org"):
        user = User.objects.get(email=email)
        assert user.must_change_password is False, email
        assert TermsAcceptance.objects.filter(user=user, terms_version=terms).exists(), email
    assert AuditLog.objects.filter(action_type="accounts.terms.accepted").exists()

    # (m1) auteur au journal = compte « Systeme » (la commande), jamais le joueur.
    waived = AuditLog.objects.filter(action_type="accounts.simulation_password_change_waived")
    assert waived.exists()
    for entry in waived:
        assert entry.actor.email == SYSTEM_ACTOR_EMAIL
        assert entry.after["context"] == "seed_simulation"
    simulated_terms = AuditLog.objects.filter(action_type="accounts.simulation_terms_accepted")
    assert simulated_terms.exists()
    for entry in simulated_terms:
        assert entry.actor.email == SYSTEM_ACTOR_EMAIL
        assert entry.after["simulated"] is True
        assert entry.after["context"] == "seed_simulation"
    fondateur = User.objects.get(email="fondateur@demo.local")
    # Filtrage en Python (pas de lookup JSON : comportement SQLite/MySQL distinct, CLAUDE.md §9).
    assert any(e.after.get("target_user_id") == fondateur.pk for e in simulated_terms)

    # (d) mercato : l'autre club (100 % simulation) est utilise.
    assert TransferOffer.objects.filter(target_club=club, target_membership=fictive_setup["other_player"]).exists()


def test_prepare_e2e_refused_on_mixed_club_without_any_change(fictive_setup):
    """Audit M1 : tout ou rien. Un club ayant ne serait-ce qu'un compte reel
    (ici une adresse provisoire ``.invalid`` et une adresse ordinaire) est
    refuse AVANT toute ecriture : aucun compte modifie, aucune donnee de
    simulation creee."""

    club = fictive_setup["club"]
    provisional = _add_real_member(club, "x@club.invalid", fictive_setup["system"])
    real = _add_real_member(club, "vrai.joueur@gmail.com", fictive_setup["system"])
    audit_count = AuditLog.objects.count()

    with pytest.raises(CommandError, match="--prepare-e2e-accounts refusée"):
        _run_seed(club.slug, "--prepare-e2e-accounts")

    for user in (provisional, real, User.objects.get(email="fondateur@demo.local")):
        user.refresh_from_db()
        assert user.must_change_password is True, user.email
        assert not TermsAcceptance.objects.filter(user=user).exists(), user.email
    assert AuditLog.objects.count() == audit_count
    assert not Session.all_objects.filter(club=club).exists()
    assert not User.objects.filter(email="tresorier.adjoint@example.org").exists()


def test_provisional_invalid_account_never_treated_as_simulation(fictive_setup):
    """Audit M1 : un compte ``x@club.invalid`` (adresse provisoire d'un vrai
    joueur) seul dans un club suffit a refuser l'option, et reste inchange."""

    club = fictive_setup["club"]
    provisional = _add_real_member(club, "x@club.invalid", fictive_setup["system"])
    with pytest.raises(CommandError, match="1 compte"):
        _run_seed(club.slug, "--prepare-e2e-accounts")
    provisional.refresh_from_db()
    assert provisional.must_change_password is True
    assert not TermsAcceptance.objects.filter(user=provisional).exists()
    assert not AuditLog.objects.filter(action_type__startswith="accounts.simulation_").exists()


def test_mercato_never_uses_a_real_club(fictive_setup):
    """Audit m2 : un autre club ayant un compte reel n'est jamais pris comme
    partenaire du mercato (aucun joueur mis sur le marche, aucune offre) ;
    la section est sautee proprement."""

    other = fictive_setup["other_club"]
    _add_real_member(other, "vrai.joueur@gmail.com", fictive_setup["system"])
    out, err = _run_seed(fictive_setup["club"].slug)
    assert "section mercato ignorée (1 club(s) réel(s) écarté(s)" in out
    assert "ECHEC" not in err, err
    assert not TransferOffer.objects.exists()
    target = Membership.all_objects.get(pk=fictive_setup["other_player"].pk)
    assert target.is_on_transfer_market is False


def test_seed_simulation_is_rerunnable_and_keeps_events_locked(fictive_setup):
    club = fictive_setup["club"]
    _run_seed(club.slug)
    out, err = _run_seed(club.slug)
    assert "seed_simulation terminé." in out
    today = sport_services.get_club_today(club)
    assert not Event.all_objects.filter(club=club, event_date__lt=today, unlocked_by__isnull=False).exists()


def test_mercato_skipped_cleanly_without_other_club(settings, fictive_setup):
    from apps.clubs.models import Club

    other = Club.objects.get(slug="autre-club-fictif")
    from apps.clubs.models import Membership

    Membership.all_objects.filter(club=other).update(status=Membership.Status.DEPARTED)
    out, err = _run_seed(fictive_setup["club"].slug)
    assert "section mercato ignorée" in out
    assert "ECHEC" not in err, err


def test_without_option_no_account_is_modified(fictive_setup):
    """Par defaut (sans --prepare-e2e-accounts), aucun mot de passe initial
    n'est leve et aucune CGU n'est acceptee, meme pour les domaines fictifs
    (le club pilote reel a des comptes a adresse provisoire .invalid)."""

    out, err = _run_seed(fictive_setup["club"].slug)
    assert "option --prepare-e2e-accounts non fournie" in out
    for email in ("fondateur@demo.local", "coach@demo.local", "joueur00@demo.local"):
        user = User.objects.get(email=email)
        assert user.must_change_password is True, email
        assert not TermsAcceptance.objects.filter(user=user).exists(), email
    assert not AuditLog.objects.filter(action_type="accounts.simulation_password_change_waived").exists()
