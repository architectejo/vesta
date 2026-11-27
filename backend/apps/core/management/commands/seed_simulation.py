"""Jeu de simulation complet pour la recette et les demonstrations
(CLAUDE.md §8 « data-import » ; cahier des charges 9.3 ; tache 5.1 du
plan des lots, ``docs/lot0/plan-lots.md``).

``python manage.py seed_simulation --club <slug>``

Peuple, pour un club DEJA EXISTANT (bureau, joueurs deja importes), les
donnees operationnelles de chaque module via les VRAIS services metier
(``apps.*.services``) -- jamais d'ecriture directe qui contournerait les
regles metier -- pour que chaque donnee creee soit journalisee normalement
et coherente avec les contraintes reelles (chainage des paiements,
eligibilite de composition/plan, verrouillage a minuit, etc.), exactement
comme le reste de l'application.

Portee volontairement limitee (CLAUDE.md §3 : jamais de simulation en
production, jamais dans les migrations) :

- Refuse de s'executer si ``settings.DEBUG`` est faux ou si la base n'est
  pas SQLite (sauf base de test MySQL jetable autorisee explicitement par
  ``config.settings.test_mysql``, voir ``_guards.py``) : cette commande ne
  doit jamais tourner en production.
- Ne touche jamais un club reel au-dela du club cible : ``--prepare-e2e-
  accounts`` est refusee si le club cible a un seul compte reel, et le
  mercato n'utilise qu'un autre club 100 % simulation.
- Ne cree aucun joueur reel supplementaire au-dela du strict necessaire :
  un seul compte synthetique est cree (voir ci-dessous), explicitement
  nomme comme tel.

Plus de code PIN (decision client du 11/10/2026, CLAUDE.md regle 7) : les
actions sensibles se confirment par une modale cote interface et l'auteur
est ecrit au journal. Pour les actions du Tresorier adjoint (encaissement,
Caisse Terrain Express), un compte de demonstration synthetique dedie est
cree (nom et email explicitement « Demo/Simulation »). La liberation d'une
depense et la signature du PV d'AG sont jouees par le President du club
cible via les services reels (journalises comme toute action).
"""

from __future__ import annotations

import datetime
import os
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from ._guards import refuse_outside_development
from django.utils import timezone

from apps.accounts import services as accounts_services
from apps.assemblies import services as assemblies_services
from apps.clubs import services as clubs_services
from apps.clubs.models import Club, Membership, MembershipRole, Season
from apps.core.services import log_action
from apps.core.tenant import active_club
from apps.logistics import services as logistics_services
from apps.logistics.models import Article
from apps.medical import services as medical_services
from apps.medical.models import HealthRecord
from apps.mercato import services as mercato_services
from apps.social import services as social_services
from apps.social.models import Post
from apps.sport import services as sport_services
from apps.sport.models import Incident, Match, MatchComposition, Session
from apps.treasury import services as treasury_services
from apps.treasury.models import ContributionType, Expense, ExpenseCategory, SocialAssistanceRequest

TZ = datetime.timezone.utc

# Motif ecrit lors du deverrouillage temporaire des evenements historiques
# (sert aussi a retrouver, pour les re-verrouiller, ceux qu'une execution
# precedente de cette commande aurait laisses deverrouilles).
SEED_UNLOCK_REASON_PREFIX = "Peuplement de la démo"

# Domaines reserves/fictifs (RFC 2606, RFC 6761) : seuls les comptes portant
# un de ces domaines sont consideres comme des comptes de simulation (jamais
# les comptes reels du club pilote).
#
# ``.invalid`` est VOLONTAIREMENT exclu (audit de securite M1) : il est
# reserve au compte « Systeme » et aux ADRESSES PROVISOIRES de comptes reels
# (``apps.core.reserved_accounts``) -- un vrai joueur importe sans email
# porte une adresse ``.invalid`` et ne doit jamais etre traite comme un
# compte de simulation.
FICTITIOUS_EMAIL_DOMAINS = frozenset({"example.com", "example.org", "example.net"})
FICTITIOUS_EMAIL_SUFFIXES = (".local", ".test", ".example", ".localhost")


def is_simulation_email(email: str) -> bool:
    """Vrai pour un email de compte de simulation (domaine reserve/fictif)."""

    email = (email or "").strip().lower()
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1]
    return domain in FICTITIOUS_EMAIL_DOMAINS or domain.endswith(FICTITIOUS_EMAIL_SUFFIXES)


def non_simulation_account_emails(club) -> list[str]:
    """Emails des comptes non Superuser rattaches au club (adhesion de tout
    statut) qui ne sont PAS de domaine de simulation. Liste vide = club
    100 % simulation (critere commun a ``--prepare-e2e-accounts`` et au
    choix du club partenaire du mercato, audit de securite M1/m2)."""

    emails = (
        Membership.all_objects.filter(club=club, user__is_superuser=False)
        .values_list("user__email", flat=True)
        .distinct()
    )
    return sorted({e for e in emails if not is_simulation_email(e)})


def _dt(y, m, d, hh=8, mm=0):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=TZ)


class Command(BaseCommand):
    help = (
        "Peuple un club existant avec un jeu de donnees de simulation complet "
        "(seances, matchs, medical, logistique, mercato, AG, fil social) pour "
        "que la demo ne montre jamais un ecran vide (CDC 9.3). Reserve au "
        "developpement (refuse si DEBUG=False)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--club", required=True, help="Slug du club a peupler.")
        parser.add_argument(
            "--superuser-email",
            default=None,
            help=(
                "Email du Superuser qui deverrouille les seances/matchs passes. Defaut : variable "
                "d'environnement VESTA_SIMULATION_SUPERUSER_EMAIL, sinon le premier Superuser de la base."
            ),
        )

        parser.add_argument(
            "--prepare-e2e-accounts",
            action="store_true",
            default=False,
            help=(
                "Desactive par defaut. Tout ou rien : refusee (aucune donnee modifiee) si le club a au "
                "moins un compte non Superuser dont l'email n'est pas de domaine de simulation "
                "(example.com/.org/.net, *.local, *.test, *.example, *.localhost ; jamais *.invalid, "
                "reserve aux adresses provisoires de comptes reels). Sinon : leve l'obligation de changer "
                "le mot de passe initial et accepte la derniere version des CGU (journalise au nom du "
                "compte Systeme), pour les sessions de recette e2e."
            ),
        )

    def handle(self, *args, **options):
        refuse_outside_development("seed_simulation")
        self.prepare_e2e_accounts = bool(options.get("prepare_e2e_accounts"))
        try:
            club = Club.objects.get(slug=options["club"])
        except Club.DoesNotExist:
            raise CommandError(f"Aucun club avec le slug « {options['club']} ».") from None

        if self.prepare_e2e_accounts:
            # Tout ou rien (audit de securite M1), verifie AVANT toute
            # ecriture : un club ayant le moindre compte reel est refuse.
            real_emails = non_simulation_account_emails(club)
            if real_emails:
                raise CommandError(
                    f"Option --prepare-e2e-accounts refusée : le club « {club.slug} » compte "
                    f"{len(real_emails)} compte(s) dont l'adresse email n'est pas d'un domaine de simulation "
                    "(example.com/.org/.net, .local, .test, .example, .localhost). Cette option lèverait "
                    "l'obligation de changer le mot de passe initial et accepterait les CGU au nom de vraies "
                    "personnes : elle est réservée aux clubs entièrement fictifs. Aucune donnée n'a été modifiée."
                )

        self.superuser_email = (
            options.get("superuser_email") or os.environ.get("VESTA_SIMULATION_SUPERUSER_EMAIL") or ""
        ).strip()
        with active_club(club):
            self._run(club)

    def _resolve_superuser(self):
        """Superuser designe (``--superuser-email`` / variable
        d'environnement), sinon le premier Superuser de la base."""

        superusers = accounts_services.User.objects.filter(is_superuser=True)
        if self.superuser_email:
            return superusers.filter(email__iexact=self.superuser_email).first()
        return superusers.order_by("pk").first()

    def _resolve_command_actor(self):
        """Auteur au journal des ecritures faites PAR LA COMMANDE elle-meme
        (et non par un joueur) : le compte technique « Systeme »
        (``treasury_services.get_system_actor``, meme helper que les
        traitements cron), a defaut le Superuser resolu par la commande
        (audit de securite m1)."""

        try:
            return treasury_services.get_system_actor()
        except treasury_services.SystemActorCompromisedError:
            superuser = self._resolve_superuser()
            if superuser is None:
                raise CommandError(
                    "Compte « Système » altéré et aucun Superuser disponible : impossible d'attribuer "
                    "correctement les écritures de la commande au journal."
                ) from None
            return superuser

    # ------------------------------------------------------------------
    def _run(self, club) -> None:
        self.club = club
        self.president_membership = Membership.all_objects.get(club=club, roles__role=MembershipRole.Role.PRESIDENT, roles__revoked_at__isnull=True)
        self.president = self.president_membership.user
        self.treasurer_membership = Membership.all_objects.get(
            club=club, roles__role=MembershipRole.Role.TREASURER, roles__revoked_at__isnull=True
        )
        self.treasurer = self.treasurer_membership.user
        self.coach_membership = Membership.all_objects.get(
            club=club, roles__role=MembershipRole.Role.COACH, roles__revoked_at__isnull=True
        )
        self.coach = self.coach_membership.user

        real_players = list(
            Membership.all_objects.filter(club=club, status=Membership.Status.ACTIVE)
            .exclude(user=self.president)
            .exclude(user__last_name="À définir")
            .exclude(user__email="tresorier.adjoint@example.org")
            .select_related("user")
            .order_by("pk")
        )
        self.players = real_players
        self.stdout.write(f"{len(self.players)} joueurs actifs disponibles (hors Président, hors placeholders).")

        self._section("0. Saison + rôles (Médecin, Capitaine, compte démo Trésorier adjoint)", self._seed_roles_and_season)
        self._section("1. Trésorerie (dus récents, paiements, Caisse Terrain Express, dépenses, assistance sociale)", self._seed_treasury)
        self._section("2. Sport (séances, matchs, cartons/suspension, plans tactiques)", self._seed_sport)
        self._section("3. Médical (blessure suivie, inaptitude, consentements)", self._seed_medical)
        self._section("4. Logistique (catalogue, mouvements, inventaire)", self._seed_logistics)
        self._section("5. Mercato (offre, messagerie inter-clubs)", self._seed_mercato)
        self._section("6. Assemblée générale (quorum, décision, PV en brouillon)", self._seed_assembly)
        self._section("7. Fil social (publications, communiqué, chat)", self._seed_social)
        self._section("8. Démonstration des règles de blocage (dette, suspension, inaptitude)", self._seed_blocking_rules_demo)
        self._section("9. Re-verrouillage des séances/matchs passés (CDC 4.7)", self._relock_seeded_events)
        self._section("10. Comptes de simulation e2e (option --prepare-e2e-accounts)", self._prepare_simulation_accounts)

        self.stdout.write(self.style.SUCCESS("seed_simulation terminé."))

    def _jpeg_file(self, name: str):
        """Fichier image reel (logo du club), pour les validateurs de format
        qui exigent JPEG/PNG/WebP/PDF (apps.core.validators) -- un texte brut
        est refuse la ou l'interface reelle n'accepterait jamais un tel
        fichier non plus."""

        logo_path = Path(settings.BASE_DIR).parent / "data" / "logo.jpeg"
        if not logo_path.is_file():
            if not getattr(self, "_logo_missing_reported", False):
                self.stdout.write(
                    f"  Logo absent ({logo_path}) : les pièces jointes et images de démonstration sont omises."
                )
                self._logo_missing_reported = True
            return None
        with open(logo_path, "rb") as fh:
            return SimpleUploadedFile(name, fh.read(), content_type="image/jpeg")

    def _social_image_file(self, name: str):
        """Image pour un ``models.ImageField`` validé par
        ``apps.core.validators.validate_image_format`` -- qui exige
        l'attribut ``image`` posé par ``forms.ImageField.to_python``
        (Pillow), normalement fourni par le serializer DRF à la frontière
        API. Un appel direct au service (comme ici) doit reproduire ce
        nettoyage lui-même -- même convention que le test helper
        ``apps.social.tests.factories.uploaded_image``."""

        from django import forms

        upload = self._jpeg_file(name)
        if upload is None:
            return None
        return forms.ImageField().clean(upload)

    def _section(self, title, fn):
        self.stdout.write(self.style.MIGRATE_HEADING(title))
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - on veut continuer les autres sections
            self.stderr.write(f"  ECHEC de cette section : {exc!r}")

    # ------------------------------------------------------------------
    def _seed_roles_and_season(self) -> None:
        club = self.club

        self.season, created = Season.all_objects.get_or_create(
            club=club, label="2026",
            defaults=dict(start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 12, 31),
                          is_current=True, created_by=self.president),
        )
        self.stdout.write(f"  Saison 2026 : {'créée' if created else 'déjà présente'} (id={self.season.pk}).")

        # Compte de démonstration synthétique, explicitement nommé comme tel
        # (pas une vraie personne), pour porter le rôle Trésorier adjoint et
        # -- permet de démontrer l'encaissement/la Caisse Terrain Express sans
        # utiliser le compte d'une vraie personne (voir docstring du module).
        demo_email = "tresorier.adjoint@example.org"
        existing_demo = Membership.all_objects.filter(club=club, user__email=demo_email).first()
        if existing_demo is None:
            result = clubs_services.create_or_update_player(
                club=club, email=demo_email, first_name="Compte Démo (Simulation)", last_name="Trésorier adjoint",
                added_by=self.president, status=Membership.Status.ACTIVE, joined_on=datetime.date(2026, 9, 1),
                now=_dt(2026, 9, 1),
            )
            self.demo_assistant_membership = result.membership
            role = clubs_services.appoint_president_nominated_role(
                president_user=self.president, target_membership=self.demo_assistant_membership,
                role=MembershipRole.Role.ASSISTANT_TREASURER, now=_dt(2026, 9, 1),
            )
            self.stdout.write(f"  Compte démo créé : {demo_email}, rôle Trésorier adjoint (role id={role.pk}).")
        else:
            self.demo_assistant_membership = existing_demo
            self.stdout.write("  Compte démo Trésorier adjoint déjà présent.")
        self.demo_assistant = self.demo_assistant_membership.user

        # Médecin / référent santé (10.2 n°17 : rôle tenable par un joueur
        # non qualifié professionnellement) et Capitaine (choisi par le Coach).
        existing_doctor = MembershipRole.all_objects.filter(club=club, role=MembershipRole.Role.DOCTOR, revoked_at__isnull=True).first()
        if existing_doctor is None and len(self.players) >= 1:
            doctor_candidate = self.players[0]
            role = clubs_services.appoint_president_nominated_role(
                president_user=self.president, target_membership=doctor_candidate,
                role=MembershipRole.Role.DOCTOR, is_qualified_professional=False, now=_dt(2026, 9, 1),
            )
            self.doctor_membership = doctor_candidate
            self.stdout.write(f"  Médecin / référent santé nommé : {doctor_candidate.user.email} (role id={role.pk}).")
        else:
            self.doctor_membership = existing_doctor.membership if existing_doctor else self.players[0]
            self.stdout.write("  Rôle Médecin déjà attribué.")

        existing_captain = MembershipRole.all_objects.filter(club=club, role=MembershipRole.Role.CAPTAIN, revoked_at__isnull=True).first()
        if existing_captain is None and len(self.players) >= 2:
            captain_candidate = self.players[1]
            role = clubs_services.appoint_captain(coach_user=self.coach, target_membership=captain_candidate, now=_dt(2026, 9, 1))
            self.captain_membership = captain_candidate
            self.stdout.write(f"  Capitaine choisi par le Coach : {captain_candidate.user.email} (role id={role.pk}).")
        else:
            self.captain_membership = existing_captain.membership if existing_captain else self.players[1]
            self.stdout.write("  Capitaine déjà désigné.")

    # ------------------------------------------------------------------
    def _seed_treasury(self) -> None:
        club = self.club

        # Montants dus récents : la vraie commande cron du Lot 2, pas une
        # logique réinventée ici (CDC 4.4.2, tâche 2.3).
        call_command("generate_monthly_dues", "--club", str(club.pk), "--period", "2026-08", "--period", "2026-09")
        self.stdout.write("  Montants dus d'août et septembre 2026 générés (generate_monthly_dues).")

        types = list(ContributionType.all_objects.filter(club=club, nature=ContributionType.Nature.MANDATORY, status=ContributionType.Status.ACTIVE))
        self.mandatory_type = types[0] if types else None

        # Un seul joueur reste volontairement en dette (démonstration du
        # blocage, CLAUDE.md règle n°5) : tous les autres joueurs rattachés
        # à un type obligatoire sont réglés (août + septembre, en une seule
        # fois, répartition déléguée à allocate_payment comme n'importe quel
        # paiement normal) pour ne pas bloquer à tort les compositions/plans
        # du reste de l'effectif.
        self.debtor_membership = self.players[-1] if self.players else None
        self.assigned_membership_ids: set[int] = set()
        self.paid_membership_ids: set[int] = set()
        demo_cash_session_done = False
        for ctype in types:
            assigned = Membership.all_objects.filter(
                pk__in=treasury_services.ContributionAssignment.all_objects.filter(contribution_type=ctype).values_list("membership_id", flat=True),
                status=Membership.Status.ACTIVE,
            ).select_related("user")
            for membership in assigned:
                self.assigned_membership_ids.add(membership.pk)
                if self.debtor_membership is not None and membership.pk == self.debtor_membership.pk:
                    continue
                if membership.pk in self.paid_membership_ids:
                    continue
                if treasury_services.get_balance(membership, at_date=datetime.date(2026, 9, 30)) >= 0:
                    # Déjà réglé (relance de cette commande après une exécution
                    # partielle précédente) : rien à repayer.
                    self.paid_membership_ids.add(membership.pk)
                    continue
                if not demo_cash_session_done:
                    session, _ = treasury_services.open_cash_session(club=club, user=self.demo_assistant, now=_dt(2026, 9, 14, 15, 0))
                    treasury_services.record_payment(
                        membership=membership, contribution_type=ctype, amount=str(ctype.amount * 2), method="cash",
                        paid_on=datetime.date(2026, 9, 14), recorded_by=self.demo_assistant,
                        reference="", now=_dt(2026, 9, 14, 15, 5),
                    )
                    self.stdout.write(f"  Encaissement via Caisse Terrain Express (session id={session.pk}) pour {membership.user.email}.")
                    demo_cash_session_done = True
                else:
                    treasury_services.record_payment(
                        membership=membership, contribution_type=ctype, amount=str(ctype.amount * 2), method="cash",
                        paid_on=datetime.date(2026, 9, 12), recorded_by=self.demo_assistant,
                        reference="", now=_dt(2026, 9, 12),
                    )
                self.paid_membership_ids.add(membership.pk)
        self.stdout.write(
            f"  {len(self.paid_membership_ids)} joueur(s) réglés (août + septembre, compte démo Trésorier adjoint) ; "
            f"{self.debtor_membership.user.email if self.debtor_membership else 'aucun'} normalement laissé en dette."
        )

        # NOTE : au fil des relances successives de cette commande pendant sa
        # mise au point, TOUS les joueurs rattachés (y compris le débiteur
        # désigné ci-dessus) ont fini par être réglés intégralement -- et un
        # paiement validé n'est jamais supprimé (règle 4) : on ne remet pas
        # en dette par une annulation de paiement. Pour garantir malgré tout un cas de
        # dette réel et visible (et non contourné), un type de cotisation
        # obligatoire SUPPLÉMENTAIRE, jamais payé par personne, est créé et
        # rattaché au seul débiteur désigné -- toujours via les vrais
        # services (create_contribution_type/create_contribution_assignment/
        # generate_monthly_dues), jamais une écriture Due ad hoc.
        if self.debtor_membership is not None:
            debt_type = ContributionType.all_objects.filter(club=club, name="Cotisation exceptionnelle (tournoi régional)").first()
            if debt_type is None:
                # Service réel (pas un ``get_or_create`` direct) : c'est lui
                # qui crée aussi le tarif (``ContributionTypeRate``), sans
                # quoi le type existe mais n'a « aucun tarif défini » pour
                # la période -- bug constaté à la première tentative.
                debt_type = treasury_services.create_contribution_type(
                    club=club, created_by=self.treasurer, name="Cotisation exceptionnelle (tournoi régional)",
                    nature=ContributionType.Nature.MANDATORY, periodicity=ContributionType.Periodicity.MONTHLY,
                    amount="15", scope=ContributionType.Scope.ATTACHED, due_day=10, now=_dt(2026, 8, 1),
                )
            if not treasury_services.ContributionAssignment.all_objects.filter(membership=self.debtor_membership, contribution_type=debt_type).exists():
                treasury_services.create_contribution_assignment(
                    membership=self.debtor_membership, contribution_type=debt_type, starts_on=datetime.date(2026, 8, 1),
                    created_by=self.treasurer, now=_dt(2026, 8, 1),
                )
            call_command("generate_monthly_dues", "--club", str(club.pk), "--period", "2026-08", "--period", "2026-09")
            balance = treasury_services.get_balance(self.debtor_membership, at_date=datetime.date(2026, 9, 30))
            self.stdout.write(
                f"  Dette garantie pour {self.debtor_membership.user.email} via « Cotisation exceptionnelle (tournoi "
                f"régional) », jamais payée (solde total au 30/09/2026 : {balance})."
            )

        # Dépenses : une justifiée dès la saisie, une en attente de justificatif.
        # Les pièces doivent être JPEG/PNG/WebP/PDF (apps.core.validators) --
        # un simple .txt est refusé : on réutilise le logo réel du club.
        category, _ = ExpenseCategory.all_objects.get_or_create(
            club=club, name="Déplacements",
            defaults=dict(receipt_required=True, created_by=self.treasurer, created_at=_dt(2026, 9, 1)),
        )
        if Expense.all_objects.filter(club=club, reason="Transport pour le match du 27/09/2026").exists():
            self.stdout.write("  Dépenses de démonstration déjà présentes : rien à refaire.")
        else:
            treasury_services.create_expense(
                club=club, created_by=self.treasurer, category=category, amount="45", beneficiary_name="Transporteur du club",
                reason="Transport pour le match du 27/09/2026", expense_date=datetime.date(2026, 9, 26), attachment=self._jpeg_file("justificatif_deplacement.jpg"),
                now=_dt(2026, 9, 26),
            )
            treasury_services.create_expense(
                club=club, created_by=self.treasurer, category=category, amount="20", beneficiary_name="Kiosque à eau",
                reason="Eau pour l'entraînement", expense_date=datetime.date(2026, 9, 23), now=_dt(2026, 9, 23),
            )
            self.stdout.write("  2 dépenses créées (une justifiée à la saisie, une en attente de justificatif).")

        # Libération par le Président (plus de PIN : confirmation en modale
        # côté interface, auteur écrit au journal). Idempotent : seule une
        # dépense encore « En attente » est libérée.
        transport = Expense.all_objects.filter(club=club, reason="Transport pour le match du 27/09/2026").first()
        if transport is not None and transport.status == Expense.Status.PENDING:
            try:
                treasury_services.release_expense(expense=transport, released_by=self.president, now=_dt(2026, 9, 27))
                self.stdout.write("  Dépense « Transport pour le match du 27/09/2026 » libérée par le Président.")
            except treasury_services.TreasuryError as exc:
                self.stdout.write(f"  (libération de la dépense non effectuée : {exc})")

        # Assistance sociale.
        assistance_category, _ = ExpenseCategory.all_objects.get_or_create(
            club=club, name="Assistance sociale", defaults=dict(receipt_required=True, good_standing_only=True, created_by=self.president, created_at=_dt(2026, 9, 1)),
        )
        scale, _ = treasury_services.SocialAssistanceScale.all_objects.get_or_create(
            club=club, event_type=treasury_services.SocialAssistanceEvent.BIRTH,
            defaults=dict(amount=Decimal("50"), processing_days=14, expense_category=assistance_category, created_by=self.president, created_at=_dt(2026, 9, 1)),
        )
        if len(self.players) >= 3:
            requester = self.players[2]
            if SocialAssistanceRequest.all_objects.filter(club=club, membership=requester).exists():
                self.stdout.write("  Demande d'assistance sociale déjà présente : rien à refaire.")
            else:
                piece = self._jpeg_file("acte_naissance.jpg")
                if piece is None:
                    self.stdout.write("  Demande d'assistance sociale non créée : pièce justificative indisponible (logo absent).")
                    return
                treasury_services.submit_social_assistance_request(
                    membership=requester, submitted_by=requester.user, event_type=treasury_services.SocialAssistanceEvent.BIRTH,
                    event_date=datetime.date(2026, 9, 10), description="Naissance de mon enfant", attachment=piece, now=_dt(2026, 9, 11),
                )
                self.stdout.write(f"  Demande d'assistance sociale (naissance) envoyée par {requester.user.email}.")

    # ------------------------------------------------------------------
    def _seed_sport(self) -> None:
        club = self.club
        from apps.sport.models import MatchSheet

        existing_sessions = list(Session.all_objects.filter(club=club).select_related("event"))
        existing_matches = list(Match.all_objects.filter(club=club).select_related("event"))
        matches_fully_processed = len(existing_matches) >= 3 and all(
            MatchSheet.all_objects.filter(club=club, match=m).exists() for m in existing_matches
        )
        if len(existing_sessions) >= 3 and matches_fully_processed:
            # Idempotence (CLAUDE.md : une relance de cette commande ne doit
            # pas dupliquer les séances/matchs, ni recomposer un joueur
            # devenu entretemps suspendu/inapte/en dette par une autre
            # section déjà rejouée) : une fois créés, on les réutilise tels
            # quels plutôt que de les recréer.
            self.sessions = existing_sessions
            self.matches = existing_matches
            from apps.sport.models import Suspension
            from django.db.models import F

            active_suspensions = list(Suspension.all_objects.filter(club=club, matches_served__lt=F("matches_total")).select_related("membership__user"))
            yellow_susp = next((s for s in active_suspensions if s.reason == Suspension.Reason.CUMULATIVE_YELLOW), None)
            red_susp = next((s for s in active_suspensions if s.reason == Suspension.Reason.RED_CARD), None)
            self.yellow_suspended_membership = yellow_susp.membership if yellow_susp else None
            self.red_suspended_membership = red_susp.membership if red_susp else None
            self.stdout.write(
                f"  {len(existing_sessions)} séance(s) et {len(existing_matches)} match(s) déjà présents : rien à refaire."
            )
            eligible_players = [p for p in self.players if sport_services.get_playability(p).eligible]
            self._seed_evaluations(eligible_players[:16] if len(eligible_players) >= 16 else eligible_players)
            return
        if existing_sessions or existing_matches:
            # Reprise d'une exécution précédente restée partielle (ex.
            # interrompue par une exception) : nettoyage des restes avant de
            # recréer proprement plutôt que de bâtir sur un état incohérent.
            from apps.sport.models import Attendance, TeamAssignment

            for s in existing_sessions:
                event = s.event
                TeamAssignment.all_objects.filter(club=club, session=s).delete()
                Attendance.all_objects.filter(club=club, event=event).delete()
                s.delete()
                event.delete()
            from apps.sport.models import MatchComposition as MC, MatchGoal, MatchSheet, Suspension

            for m in existing_matches:
                event = m.event
                Suspension.all_objects.filter(club=club, triggering_incident__event=event).delete()
                Incident.all_objects.filter(club=club, event=event).delete()
                MC.all_objects.filter(club=club, match=m).delete()
                for sheet in MatchSheet.all_objects.filter(club=club, match=m):
                    MatchGoal.all_objects.filter(club=club, match_sheet=sheet).delete()
                    sheet.delete()
                Attendance.all_objects.filter(club=club, event=event).delete()
                m.delete()
                event.delete()
            self.stdout.write(f"  Nettoyage de {len(existing_sessions)} séance(s)/{len(existing_matches)} match(s) partiel(s) d'une exécution précédente.")

        superuser = self._resolve_superuser()
        if superuser is None:
            self.stdout.write("  Aucun Superuser trouvé : les séances/matchs passés resteront verrouillés (non peuplés).")
            return

        # Filtre par éligibilité RÉELLE (et non par simple position dans la
        # liste) : une relance de cette commande après une exécution
        # partielle précédente peut avoir déjà rendu certains joueurs
        # inéligibles (dette/suspension/inaptitude) par une autre section
        # déjà rejouée -- ne jamais les composer (CLAUDE.md règle n°5).
        eligible_players = [p for p in self.players if sport_services.get_playability(p).eligible]
        present = eligible_players[:16] if len(eligible_players) >= 16 else eligible_players

        self.sessions = []
        for idx, day in enumerate([9, 16, 23]):
            date_ = datetime.date(2026, 9, day)
            session = sport_services.create_session(
                club=club, season=self.season, event_date=date_, gathering_time=datetime.time(15, 0),
                late_arrival_cutoff=datetime.time(15, 15), created_by=self.coach, location="Terrain principal",
            )
            sport_services.unlock_event(session.event, superuser=superuser, reason=f"{SEED_UNLOCK_REASON_PREFIX} (séance historique).")
            for i, membership in enumerate(present):
                arrived = _dt(2026, 9, day, 15, 5) if i % 5 != 0 else _dt(2026, 9, day, 15, 20)
                sport_services.mark_arrival(session=session, membership=membership, arrived_at=arrived, marked_by=self.coach)
                if i % 5 != 0:
                    sport_services.assign_team(session=session, membership=membership, team=("A" if i % 2 == 0 else "B"), assigned_by=self.coach)
            # Séance passée : re-verrouillée dès le pointage terminé (CDC 4.7,
            # verrouillage à minuit) -- jamais laissée déverrouillée.
            self._relock_event(session.event, actor=superuser)
            self.sessions.append(session)
        self.stdout.write(f"  {len(self.sessions)} séances créées avec pointage et répartition A/B (dont retards).")

        # Matchs, compositions, score, buts, cartons (5e jaune -> suspension).
        self.matches = []
        yellow_target = present[3] if len(present) > 3 else None
        red_target = present[4] if len(present) > 4 else None
        for idx, day in enumerate([13, 20, 27]):
            match = sport_services.create_match(
                club=club, season=self.season, event_date=datetime.date(2026, 9, day), kickoff_time=datetime.time(16, 0),
                match_type=Match.MatchType.FRIENDLY, venue=Match.Venue.HOME, created_by=self.coach,
                opponent_name=f"Adversaire amical {idx + 1}",
            )
            sport_services.unlock_event(match.event, superuser=superuser, reason=f"{SEED_UNLOCK_REASON_PREFIX} (match historique).")
            # Éligibilité réévaluée à CHAQUE match (pas une seule fois avant
            # la boucle) : un joueur suspendu par le carton rouge du match
            # précédent (idx-1) ne doit plus être composé dans celui-ci.
            match_lineup = [p for p in present[:14] if sport_services.get_playability(p).eligible][:14]
            for i, membership in enumerate(match_lineup):
                sport_services.add_to_composition(
                    match=match, membership=membership, role=(MatchComposition.Role.STARTER if i < 11 else MatchComposition.Role.SUBSTITUTE),
                    position="forward", jersey_number=(membership.jersey_number or (i + 1)), added_by=self.coach,
                )
            sport_services.publish_composition(match=match, published_by=self.coach)
            sheet = sport_services.set_match_score(match=match, score_home=2, score_away=1, filled_by=self.coach)
            sport_services.add_goal(match_sheet=sheet, created_by=self.coach, scorer_membership=present[0], minute=23)
            sport_services.add_goal(match_sheet=sheet, created_by=self.coach, scorer_membership=present[1], minute=67)
            if yellow_target is not None and idx < 2:
                # 2 jaunes par match sur les 2 premiers matchs = 4, puis 1 de plus
                # au 3e match = 5e jaune de la saison -> suspension automatique.
                for _ in range(2):
                    sport_services.record_incident(
                        event=match.event, membership=yellow_target, incident_type=Incident.IncidentType.YELLOW_CARD,
                        cause=Incident.Cause.CONTESTATION, recorded_by=self.coach, minute=40,
                    )
            elif yellow_target is not None and idx == 2:
                sport_services.record_incident(
                    event=match.event, membership=yellow_target, incident_type=Incident.IncidentType.YELLOW_CARD,
                    cause=Incident.Cause.BEHAVIOUR, recorded_by=self.coach, minute=55,
                )
            if red_target is not None and idx == 1:
                sport_services.record_incident(
                    event=match.event, membership=red_target, incident_type=Incident.IncidentType.RED_CARD,
                    cause=Incident.Cause.SERIOUS_FOUL, recorded_by=self.coach, minute=70,
                )
            self._relock_event(match.event, actor=superuser)
            self.matches.append(match)
        self.yellow_suspended_membership = yellow_target
        self.red_suspended_membership = red_target
        self.stdout.write(
            f"  {len(self.matches)} matchs créés (compositions publiées, scores, buts). "
            f"5e carton jaune déclenché pour {getattr(yellow_target, 'user', None) and yellow_target.user.email} ; "
            f"carton rouge direct pour {getattr(red_target, 'user', None) and red_target.user.email}."
        )

        # Plan tactique supplémentaire publié. Éligibilité réévaluée APRÈS
        # les matchs (CLAUDE.md règle n° 5) : les joueurs que les cartons
        # ci-dessus viennent de suspendre ne sont jamais placés.
        plan_players = [p for p in present if sport_services.get_playability(p).eligible][:11]
        if len(plan_players) < 11:
            self.stdout.write(f"  Plan tactique non créé : seulement {len(plan_players)} joueur(s) éligible(s) (11 requis).")
        else:
            plan = sport_services.create_tactical_plan(
                club=club, name="Simulation — plan de démonstration", formation="4-3-3", squad_size=11,
                created_by=self.coach, match=self.matches[-1] if self.matches else None,
            )
            for i, membership in enumerate(plan_players):
                sport_services.place_on_plan(plan=plan, membership=membership, x_coord=Decimal("10") + i * 8, y_coord=Decimal("50"), placed_by=self.coach)
            sport_services.publish_tactical_plan(plan=plan, published_by=self.coach)
            self.stdout.write(f"  Plan tactique supplémentaire publié (id={plan.pk}).")

        self._seed_evaluations(present)

    def _seed_evaluations(self, present) -> None:
        """Évaluations (CDC 4.10) : verrouillées 48 h après le DÉBUT RÉEL de
        l'événement (``timezone.now()``, jamais un ``now`` de simulation) --
        impossible à démontrer sur les séances/matchs historiques (bien après
        la fenêtre). Une séance datée d'aujourd'hui est donc créée
        spécifiquement pour ce seul besoin. Appelée depuis les deux chemins
        de ``_seed_sport`` (séances déjà présentes ou nouvellement créées)."""

        club = self.club
        today = timezone.localdate()
        eval_session = Session.all_objects.filter(club=club, event__event_date=today).first()
        if eval_session is None and len(present) >= 3:
            eval_session = sport_services.create_session(
                club=club, season=self.season, event_date=today, gathering_time=datetime.time(15, 0),
                late_arrival_cutoff=datetime.time(15, 15), created_by=self.coach, location="Terrain principal",
            )
        if eval_session is not None and len(present) >= 3:
            now_eval = timezone.now()
            for membership in present[:3]:
                sport_services.mark_arrival(session=eval_session, membership=membership, arrived_at=now_eval, marked_by=self.coach)
                if not sport_services.get_average_evaluation(eval_session.event, membership):
                    sport_services.submit_evaluation(
                        event=eval_session.event, membership=membership, evaluator=self.coach, overall_score=Decimal("7.5"),
                        comment="Bonne séance, continue ainsi.", comment_visible_to_player=True,
                    )
            self.stdout.write(f"  Évaluations soumises pour {min(3, len(present))} joueur(s) (séance du jour, id={eval_session.pk}).")

    def _relock_event(self, event, *, actor) -> bool:
        """Re-verrouille un événement passé que cette commande a dû
        déverrouiller pour le peupler (CDC 4.7). La règle
        ``is_event_locked`` n'est pas modifiée : on efface simplement le
        déverrouillage, et l'opération est journalisée (CLAUDE.md règle 6)."""

        if not event.unlocked_by_id:
            return False
        if event.event_date >= sport_services.get_club_today(event.club):
            return False  # événement du jour ou futur : pas de verrouillage à rétablir
        before = {"unlocked_by": event.unlocked_by_id, "unlock_reason": event.unlock_reason}
        event.unlocked_by = None
        event.unlocked_at = None
        event.unlock_reason = ""
        event.save(update_fields=["unlocked_by", "unlocked_at", "unlock_reason"])
        log_action(
            actor=actor, club=event.club, action_type="sport.event_relocked", obj=event, before=before,
            after={"unlocked_by": None, "unlock_reason": "", "context": "seed_simulation"},
        )
        return True

    # ------------------------------------------------------------------
    def _seed_medical(self) -> None:
        if len(self.players) < 4:
            self.stdout.write("  Pas assez de joueurs pour peupler le module médical.")
            return
        doctor_user = self.doctor_membership.user

        # Indices choisis hors de la plage utilisée par les séances/matchs
        # (present = players[:16]) et hors du joueur suspendu (present[3]/
        # present[4]) et du débiteur (players[-1]), CLAUDE.md règle n°5 : un
        # cas distinct par règle de blocage, pas le même joueur cumulant
        # tout, et jamais un joueur déjà composé ailleurs (sinon une relance
        # de la commande le ferait échouer, déjà devenu inapte/suspendu).
        consenting = self.players[20] if len(self.players) > 20 else self.players[0]
        medical_services.give_processing_consent(membership=consenting, actor=consenting.user, now=_dt(2026, 9, 2))
        medical_services.grant_president_access(membership=consenting, actor=consenting.user, now=_dt(2026, 9, 2, 8, 5))
        self.stdout.write(f"  Consentement au traitement + accès Président accordés par {consenting.user.email}.")

        injured = self.players[21] if len(self.players) > 21 else self.players[3]
        medical_services.give_processing_consent(membership=injured, actor=injured.user, now=_dt(2026, 9, 13))
        matches_list = getattr(self, "matches", None)
        match = matches_list[0] if matches_list else None
        from apps.medical.models import Injury

        existing_injury = Injury.all_objects.filter(club_id=self.club.id, membership=injured, status=Injury.Status.OPEN).first()
        if existing_injury is not None:
            injury = existing_injury
            self.stdout.write(f"  Blessure déjà déclarée pour {injured.user.email} (injury id={injury.pk}) : rien à refaire.")
        else:
            injury = medical_services.report_injury(
                membership=injured, actor=self.coach, circumstances="Entorse à la cheville lors du match du 13/09/2026.",
                event=match.event if match else None, occurred_minute=55, now=_dt(2026, 9, 13, 18, 0),
            )
            medical_services.add_injury_followup(
                injury=injury, actor=doctor_user, entry_date=datetime.date(2026, 9, 20),
                note="Reprise progressive de la course, douleur en nette diminution.", now=_dt(2026, 9, 20, 9, 0),
            )
            self.stdout.write(f"  Blessure déclarée et suivie (en cours) pour {injured.user.email} (injury id={injury.pk}).")

        if len(self.players) > 22:
            unfit = self.players[22]
            medical_services.update_fitness(membership=unfit, actor=doctor_user, status=HealthRecord.FitnessStatus.UNFIT, now=_dt(2026, 9, 25))
            self.unfit_membership = unfit
            self.stdout.write(f"  Joueur rendu inapte (visible) : {unfit.user.email}.")
        else:
            self.unfit_membership = None

    # ------------------------------------------------------------------
    def _seed_logistics(self) -> None:
        club = self.club

        def _article(name, category):
            existing = Article.all_objects.filter(club=club, name=name).first()
            if existing is not None:
                return existing, False
            return logistics_services.create_article(club=club, actor=self.coach, name=name, category=category, unit="pièce"), True

        jerseys, jerseys_new = _article("Maillots équipe A", Article.Category.JERSEY)
        balls, balls_new = _article("Ballons de match", Article.Category.BALLS)
        kit, kit_new = _article("Trousse de premiers secours", Article.Category.MISC)

        if jerseys_new:
            logistics_services.record_movement(club=club, actor=self.coach, movement_type="in_purchase", article=jerseys, quantity=20, movement_date=datetime.date(2026, 9, 1), reason="Achat de début de saison")
        if balls_new:
            logistics_services.record_movement(club=club, actor=self.coach, movement_type="in_purchase", article=balls, quantity=10, movement_date=datetime.date(2026, 9, 1), reason="Achat de début de saison")
            logistics_services.record_movement(club=club, actor=self.coach, movement_type="out_wear", article=balls, quantity=2, movement_date=datetime.date(2026, 9, 20), reason="Ballons usés lors des entraînements")
        if kit_new:
            logistics_services.record_movement(club=club, actor=self.coach, movement_type="in_donation", article=kit, quantity=3, movement_date=datetime.date(2026, 9, 1), reason="Dotation")
        self.stdout.write("  3 articles (créés ou déjà présents), mouvements d'entrée/sortie enregistrés si nouveaux.")

        from apps.logistics.models import Inventory

        quarter_label = logistics_services.get_current_quarter_label(club, now=_dt(2026, 9, 28))
        already_closed = Inventory.all_objects.filter(club=club, quarter_label=quarter_label, status=Inventory.Status.CLOSED).first()
        if already_closed is not None:
            self.stdout.write(f"  Inventaire du trimestre {quarter_label} déjà clôturé (id={already_closed.pk}) : rien à refaire.")
            return
        inventory = logistics_services.get_open_inventory(club) or logistics_services.open_inventory(club=club, actor=self.president, now=_dt(2026, 9, 28))
        theoretical_jerseys = logistics_services.theoretical_quantity(jerseys)
        theoretical_balls = logistics_services.theoretical_quantity(balls)
        theoretical_kit = logistics_services.theoretical_quantity(kit)
        # NOTE (constat d'environnement, pas une règle métier) : la base de
        # dev locale porte encore une ancienne contrainte SQL
        # ``inventoryline_reason_required_if_gap`` que le modèle actuel ne
        # définit plus (``inventoryline_justified_requires_reason``,
        # apps/logistics/models.py) -- elle interdit d'INSÉRER une ligne
        # d'écart avant même sa justification, ce que le workflow réel de
        # ``record_counts``/``justify_discrepancy`` fait pourtant en deux
        # temps. Dérive schéma/DB de dev à signaler à backend-dev/
        # devops-cpanel. Faute de pouvoir la contourner sans risquer la
        # base de dev partagée, cette commande compte sans écart (aucune
        # démonstration d'écart justifié possible tant que la dérive n'est
        # pas corrigée) -- voir compte rendu, point ouvert.
        logistics_services.record_counts(
            inventory=inventory, actor=self.president,
            counts=[
                {"article": jerseys, "physical_quantity": theoretical_jerseys},
                {"article": balls, "physical_quantity": theoretical_balls},
                {"article": kit, "physical_quantity": theoretical_kit},
            ],
            now=_dt(2026, 9, 28, 10, 0),
        )
        logistics_services.close_inventory(inventory=inventory, actor=self.president, now=_dt(2026, 9, 28, 10, 10))
        self.stdout.write(f"  Inventaire trimestriel ouvert, compté (sans écart -- voir note ci-dessus) et clôturé (id={inventory.pk}).")

    # ------------------------------------------------------------------
    def _seed_mercato(self) -> None:
        from apps.clubs.models import Club as ClubModel

        # Second club ENTIÈREMENT DE SIMULATION (tous ses comptes non
        # Superuser à domaine fictif, même critère que
        # --prepare-e2e-accounts, audit de sécurité m2) ayant au moins un
        # joueur actif. Jamais un slug figé, jamais un club réel : un vrai
        # joueur ne doit pas être mis sur le marché ni recevoir d'offre.
        other_club = None
        target_membership = None
        skipped_real_clubs = 0
        for candidate in ClubModel.objects.exclude(pk=self.club.pk).order_by("pk"):
            if non_simulation_account_emails(candidate):
                skipped_real_clubs += 1
                continue
            with active_club(candidate):
                president_ids = MembershipRole.all_objects.filter(
                    club=candidate, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
                ).values_list("membership_id", flat=True)
                target_membership = (
                    Membership.all_objects.filter(club=candidate, status=Membership.Status.ACTIVE)
                    .exclude(pk__in=president_ids)
                    .select_related("user")
                    .order_by("pk")
                    .first()
                )
            if target_membership is not None:
                other_club = candidate
                break
        if other_club is None:
            self.stdout.write(
                "  Aucun autre club de simulation (tous comptes à domaine fictif) avec un joueur actif : "
                f"section mercato ignorée ({skipped_real_clubs} club(s) réel(s) écarté(s), jamais modifié(s))."
            )
            return

        with active_club(other_club):
            mercato_services.set_market_availability(membership=target_membership, actor=target_membership.user, is_on_market=True, now=_dt(2026, 9, 15))

        from apps.mercato.models import TransferOffer

        existing_offer = TransferOffer.objects.filter(target_membership=target_membership, target_club=self.club).first()
        if existing_offer is not None:
            self.stdout.write(f"  Offre de transfert déjà présente (id={existing_offer.pk}) : rien à refaire.")
            return

        offer = mercato_services.create_transfer_offer(
            initiated_by=self.president, target_club=self.club, target_membership=target_membership,
            message=f"Nous aimerions vous accueillir à {self.club.name} pour la saison en cours.", now=_dt(2026, 9, 16),
        )
        thread = mercato_services.get_or_create_thread(club_a=self.club, club_b=other_club, subject="Transfert", transfer_offer=offer, now=_dt(2026, 9, 16))
        mercato_services.send_message(thread=thread, actor=self.president, club=self.club, body="Bonjour, avez-vous des questions sur notre proposition ?", now=_dt(2026, 9, 16, 10, 0))
        try:
            mercato_services.send_message(thread=thread, actor=target_membership.user, club=other_club, body="Bonjour, je vais réfléchir et vous répondre rapidement.", now=_dt(2026, 9, 17, 9, 0))
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(f"  (réponse du joueur non envoyée : {exc})")
        self.stdout.write(f"  Offre de transfert créée (id={offer.pk}) pour {target_membership.user.email} ({other_club.slug}), messagerie inter-clubs amorcée.")

    # ------------------------------------------------------------------
    def _seed_assembly(self) -> None:
        club = self.club
        from apps.assemblies.models import Assembly

        existing_assembly = Assembly.all_objects.filter(club=club, scheduled_date=datetime.date(2026, 9, 20)).first()
        if existing_assembly is not None:
            self.stdout.write(f"  AG déjà présente (id={existing_assembly.pk}) : rien à refaire.")
            return

        assembly = assemblies_services.convene_assembly(
            club=club, actor=self.president, assembly_type=assemblies_services.Assembly.AssemblyType.ORDINARY,
            scheduled_date=datetime.date(2026, 9, 20), scheduled_time=datetime.time(10, 0), location="Terrain principal",
            agenda_items=[{"title": "Bilan de la saison", "description": "Point sur les résultats sportifs et financiers."}],
            now=_dt(2026, 9, 5),
        )
        for membership in self.players[:max(1, int(len(self.players) * 0.6))]:
            assemblies_services.mark_attendance(assembly=assembly, actor=self.president, membership=membership, now=_dt(2026, 9, 20, 10, 5))
        quorum = assemblies_services.get_quorum(assembly)
        agenda_item = assembly.agenda_items.first()
        assemblies_services.record_decision(
            assembly=assembly, agenda_item=agenda_item, actor=self.president, votes_for=len(self.players), votes_against=0,
            votes_abstain=0, outcome="Adopté à l'unanimité : poursuite de la saison selon le plan présenté.", now=_dt(2026, 9, 20, 11, 0),
        )
        assemblies_services.draft_minutes(
            assembly=assembly, actor=self.president,
            content="Assemblée générale ordinaire du 20/09/2026. Bilan présenté et approuvé à l'unanimité.",
            now=_dt(2026, 9, 20, 11, 30),
        )
        # Signature du PV par le Président (plus de PIN : confirmation en modale
        # côté interface, auteur écrit au journal). Idempotent : l'AG n'est
        # traitée qu'à sa création (retour anticipé plus haut si elle existe).
        try:
            assemblies_services.sign_minutes(assembly=assembly, actor=self.president, now=_dt(2026, 9, 20, 12, 0))
            signature_note = "PV signé par le Président."
        except Exception as exc:  # noqa: BLE001 - on veut continuer les autres sections
            signature_note = f"signature du PV non effectuée ({exc})."
        self.stdout.write(
            f"  AG convoquée (id={assembly.pk}), quorum {quorum.present}/{quorum.total} ({quorum.percentage}% >= {quorum.threshold}% : "
            f"{'atteint' if quorum.reached else 'NON atteint'}), décision enregistrée, PV rédigé ; {signature_note}"
        )

    # ------------------------------------------------------------------
    def _seed_social(self) -> None:
        club = self.club
        image_body = "Entraînement réussi ce soir, merci à tous !"
        if Post.all_objects.filter(club=club, body=image_body).exists():
            self.stdout.write("  Publication avec image déjà présente : rien à refaire.")
        else:
            image = self._social_image_file("logo.jpeg")
            social_services.create_post(
                club=club, actor=self.coach, body=image_body,
                visibility=Post.Visibility.CLUB_ONLY, images=[image] if image is not None else [], now=_dt(2026, 9, 23, 20, 0),
            )
            self.stdout.write(
                "  Publication avec image créée (logo.jpeg)." if image is not None else "  Publication créée sans image (logo absent)."
            )

        public_body = "Merci à tous pour votre engagement ce mois-ci."
        if not Post.all_objects.filter(club=club, body=public_body).exists():
            social_services.create_post(club=club, actor=self.president, body=public_body, visibility=Post.Visibility.PUBLIC, now=_dt(2026, 9, 25, 9, 0))

        from apps.social.models import Announcement

        if not Announcement.all_objects.filter(club=club, title="Reprise des cotisations 2026").exists():
            social_services.create_announcement(
                club=club, actor=self.president, title="Reprise des cotisations 2026",
                body="Merci de régulariser vos cotisations auprès du Trésorier ou de la Caisse Terrain Express.",
                now=_dt(2026, 9, 24, 8, 0),
            )
            self.stdout.write("  Communiqué officiel publié.")
        else:
            self.stdout.write("  Communiqué déjà présent : rien à refaire.")

        general, _board = social_services.ensure_channels(club)
        if general.messages.filter(body__startswith="Message de démonstration").exists():
            self.stdout.write("  Messages de chat déjà présents : rien à refaire.")
        else:
            for i, membership in enumerate(self.players[:3]):
                social_services.send_chat_message(channel=general, actor=membership.user, body=f"Message de démonstration {i + 1} dans le canal général.", now=_dt(2026, 9, 26, 18, i))
            self.stdout.write("  Messages de chat envoyés dans le canal général.")

    # ------------------------------------------------------------------
    def _seed_blocking_rules_demo(self) -> None:
        """Ne place jamais reellement un joueur bloque : demontre juste que
        le service refuse, avec la raison, comme l'exige CLAUDE.md regle n5."""

        match = getattr(self, "matches", [None])[-1] if getattr(self, "matches", None) else None
        if match is None:
            self.stdout.write("  Aucun match disponible pour la démonstration.")
            return

        candidates = []
        if getattr(self, "yellow_suspended_membership", None) is not None:
            candidates.append(("suspendu (5e carton jaune)", self.yellow_suspended_membership))
        if getattr(self, "unfit_membership", None) is not None:
            candidates.append(("inapte", self.unfit_membership))
        # Un joueur en dette : rattaché au type mensuel mais sans paiement de
        # septembre (donc dû échu impayé après generate_monthly_dues).
        assigned_ids = getattr(self, "assigned_membership_ids", set())
        paid_ids = getattr(self, "paid_membership_ids", set())
        unpaid_ids = assigned_ids - paid_ids
        debtor = next((p for p in self.players if p.pk in unpaid_ids), None)
        if debtor is not None:
            candidates.append(("en dette (septembre impayé)", debtor))
        for label, membership in candidates:
            try:
                sport_services.add_to_composition(match=match, membership=membership, role=MatchComposition.Role.SUBSTITUTE, position="forward", jersey_number=(membership.jersey_number or 77), added_by=self.coach)
                self.stdout.write(f"  INATTENDU : {label} a été composé sans blocage ({membership.user.email}).")
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(f"  Blocage confirmé pour joueur {label} ({membership.user.email}) : {exc}")

    # ------------------------------------------------------------------
    def _relock_seeded_events(self) -> None:
        """Filet de sécurité (et réparation des bases peuplées par une
        version antérieure de cette commande) : aucun événement passé
        déverrouillé par cette commande ne reste ouvert (CDC 4.7)."""

        from apps.sport.models import Event

        relocked = 0
        candidates = Event.all_objects.filter(
            club=self.club, unlocked_by__isnull=False, unlock_reason__startswith=SEED_UNLOCK_REASON_PREFIX
        ).select_related("club", "unlocked_by")
        for event in candidates:
            if self._relock_event(event, actor=event.unlocked_by):
                relocked += 1
        self.stdout.write(f"  {relocked} événement(s) passé(s) re-verrouillé(s) (aucune séance passée laissée ouverte).")

    # ------------------------------------------------------------------
    def _prepare_simulation_accounts(self) -> None:
        """Club 100 % simulation uniquement (vérifié dans ``handle`` AVANT
        toute écriture : la commande est refusée si le club a le moindre
        compte non Superuser hors domaine de simulation -- jamais ``.invalid``,
        réservé aux adresses provisoires de comptes réels ; voir
        ``is_simulation_email``). Lève l'obligation de changer le mot de
        passe initial et accepte la dernière version des CGU via le service
        existant (``accept_terms``). Auteur au journal : le compte
        « Système » (la commande), jamais le joueur ; l'acceptation des CGU,
        que le signal attribue à l'utilisateur, reçoit en plus une entrée
        explicite « acceptation simulée » au nom du Système."""

        if not getattr(self, "prepare_e2e_accounts", False):
            self.stdout.write(
                "  Section sautée (option --prepare-e2e-accounts non fournie) : aucun mot de passe initial "
                "levé, aucune CGU acceptée."
            )
            return

        from apps.accounts.models import TermsVersion, User

        command_actor = self._resolve_command_actor()
        latest_terms = TermsVersion.objects.order_by("-published_at", "-id").first()
        users = (
            User.objects.filter(memberships__club=self.club, is_superuser=False)
            .distinct()
            .order_by("pk")
        )
        password_waived = terms_accepted = skipped_real = 0
        for user in users:
            if not is_simulation_email(user.email):
                skipped_real += 1
                continue
            if user.must_change_password:
                user.must_change_password = False
                user.save(update_fields=["must_change_password"])
                log_action(
                    actor=command_actor, club=self.club, action_type="accounts.simulation_password_change_waived", obj=user,
                    before={"must_change_password": True},
                    after={"must_change_password": False, "target_user_id": user.pk, "context": "seed_simulation"},
                )
                password_waived += 1
            if latest_terms is not None and accounts_services.get_pending_terms_version(user) is not None:
                acceptance = accounts_services.accept_terms(user=user, terms_version=latest_terms)
                # Le signal ``log_terms_accepted`` attribue l'acceptation à
                # l'utilisateur : entrée explicite au nom du Système pour que
                # le journal montre qu'elle a été SIMULÉE par la commande.
                log_action(
                    actor=command_actor, club=self.club, action_type="accounts.simulation_terms_accepted", obj=acceptance,
                    before=None,
                    after={
                        "target_user_id": user.pk, "terms_version_id": latest_terms.pk, "simulated": True,
                        "context": "seed_simulation",
                    },
                )
                terms_accepted += 1
        if latest_terms is None:
            self.stdout.write("  Aucune version des CGU publiée : acceptation non effectuée.")
        self.stdout.write(
            f"  Comptes de simulation : {password_waived} mot(s) de passe initial(aux) levé(s), "
            f"{terms_accepted} acceptation(s) des CGU ; {skipped_real} compte(s) réel(s) non modifié(s)."
        )
