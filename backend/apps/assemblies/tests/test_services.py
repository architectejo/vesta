"""Tests de `apps.assemblies.services` (CDC 4.15 ; tache 4.5)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.assemblies import services
from apps.assemblies.models import Assembly, Minutes
from apps.assemblies.tests.factories import AgendaItemFactory, AssemblyFactory
from apps.audit.models import AuditLog
from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import ClubFactory, ClubSettingsFactory, MembershipFactory, MembershipRoleFactory
from apps.core.tenant import active_club
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

TZ = ZoneInfo("Africa/Kinshasa")


def _club():
    club = ClubSettingsFactory(timezone="Africa/Kinshasa").club
    return club


def _president(club):
    membership = MembershipFactory(club=club)
    MembershipRoleFactory(membership=membership, role=MembershipRole.Role.PRESIDENT)
    return membership


def _vice_president(club):
    membership = MembershipFactory(club=club)
    MembershipRoleFactory(membership=membership, role=MembershipRole.Role.VICE_PRESIDENT)
    return membership


class TestConveneAssembly:
    def test_convene_creates_assembly_and_agenda_items_and_notifies_active_members(self):
        club = _club()
        president = _president(club)
        player = MembershipFactory(club=club)
        future_date = (timezone.now() + timedelta(days=5)).astimezone(TZ).date()

        with active_club(club):
            assembly = services.convene_assembly(
                club=club,
                actor=president.user,
                assembly_type=Assembly.AssemblyType.ORDINARY,
                scheduled_date=future_date,
                scheduled_time=time(18, 0),
                location="Terrain",
                agenda_items=[{"title": "Bilan"}, {"title": "Elections", "description": "Bureau"}],
            )

        assert assembly.agenda_items.count() == 2
        assert list(assembly.agenda_items.order_by("order").values_list("title", flat=True)) == [
            "Bilan",
            "Elections",
        ]
        assert AuditLog.objects.filter(action_type="assemblies.assembly.convened").exists()
        assert Notification.objects.filter(
            recipient=player.user, event_type=Notification.EventType.ASSEMBLY_CONVENED
        ).exists()
        assert Notification.objects.filter(
            recipient=president.user, event_type=Notification.EventType.ASSEMBLY_CONVENED
        ).exists()

    def test_refuses_a_past_or_today_date(self):
        club = _club()
        president = _president(club)
        today = timezone.now().astimezone(TZ).date()

        with active_club(club):
            with pytest.raises(services.AssemblyValidationError, match="futur"):
                services.convene_assembly(
                    club=club,
                    actor=president.user,
                    assembly_type=Assembly.AssemblyType.ORDINARY,
                    scheduled_date=today,
                    scheduled_time=time(18, 0),
                    agenda_items=[{"title": "Bilan"}],
                )

    def test_refuses_without_any_agenda_item(self):
        club = _club()
        president = _president(club)
        future_date = (timezone.now() + timedelta(days=5)).date()

        with active_club(club):
            with pytest.raises(services.AssemblyValidationError, match="Ajoutez au moins un point à l'ordre du jour."):
                services.convene_assembly(
                    club=club,
                    actor=president.user,
                    assembly_type=Assembly.AssemblyType.ORDINARY,
                    scheduled_date=future_date,
                    scheduled_time=time(18, 0),
                    agenda_items=[],
                )


class TestQuorum:
    def test_quorum_is_computed_but_never_blocks(self):
        """4.15 impose le calcul, jamais un blocage (revision 29/09)."""

        club = _club()
        assembly = AssemblyFactory(club=club, scheduled_date=timezone.now().astimezone(TZ).date())
        # 4 joueurs actifs, aucun present : quorum non atteint, mais rien
        # n'empeche la lecture ni la saisie d'un vote (voir TestRecordDecision).
        for _ in range(4):
            MembershipFactory(club=club)

        with active_club(club):
            quorum = services.get_quorum(assembly)

        assert quorum.total == 4
        assert quorum.present == 0
        assert quorum.threshold == Decimal("50.00")
        assert quorum.reached is False

    def test_default_threshold_is_fifty_percent(self):
        """10.2 n° 18 : pre-rempli a 50 % a la creation du club."""

        club = _club()
        assert club.settings.assembly_quorum_percentage == Decimal("50")


class TestAttendance:
    def test_mark_attendance_only_on_the_day_of_the_assembly(self):
        club = _club()
        president = _president(club)
        member = MembershipFactory(club=club)
        assembly = AssemblyFactory(club=club, scheduled_date=(timezone.now() + timedelta(days=2)).date())

        with active_club(club):
            with pytest.raises(services.AssemblyLockedError):
                services.mark_attendance(assembly=assembly, actor=president.user, membership=member)

    def test_mark_and_remove_attendance_on_the_day(self):
        club = _club()
        president = _president(club)
        member = MembershipFactory(club=club)
        today = timezone.now().astimezone(TZ).date()
        assembly = AssemblyFactory(club=club, scheduled_date=today)

        with active_club(club):
            attendance = services.mark_attendance(assembly=assembly, actor=president.user, membership=member)
            assert attendance.present is True
            services.remove_attendance(assembly=assembly, actor=president.user, membership=member)

        assert AuditLog.objects.filter(action_type="assemblies.attendance.marked").exists()
        assert AuditLog.objects.filter(action_type="assemblies.attendance.removed").exists()


class TestRecordDecision:
    def test_records_a_decision_even_if_votes_exceed_present_count(self):
        """Avertissement non bloquant (revision 29/09) : le service accepte
        un total de votes superieur au nombre de presents."""

        club = _club()
        president = _president(club)
        assembly = AssemblyFactory(club=club)
        agenda_item = AgendaItemFactory(assembly=assembly, club=club, order=1)

        with active_club(club):
            decision = services.record_decision(
                assembly=assembly,
                agenda_item=agenda_item,
                actor=president.user,
                votes_for=50,
                votes_against=10,
                votes_abstain=5,
                outcome="Adopte a la majorite",
            )

        assert decision.votes_for == 50

    def test_updates_the_existing_decision_for_the_same_agenda_item(self):
        club = _club()
        president = _president(club)
        assembly = AssemblyFactory(club=club)
        agenda_item = AgendaItemFactory(assembly=assembly, club=club, order=1)

        with active_club(club):
            services.record_decision(
                assembly=assembly,
                agenda_item=agenda_item,
                actor=president.user,
                votes_for=10,
                votes_against=0,
                votes_abstain=0,
                outcome="Premiere saisie",
            )
            decision = services.record_decision(
                assembly=assembly,
                agenda_item=agenda_item,
                actor=president.user,
                votes_for=12,
                votes_against=1,
                votes_abstain=0,
                outcome="Saisie corrigee",
            )

        from apps.assemblies.models import Decision

        assert Decision.all_objects.filter(agenda_item=agenda_item).count() == 1
        assert decision.outcome == "Saisie corrigee"

    def test_requires_an_outcome(self):
        club = _club()
        president = _president(club)
        assembly = AssemblyFactory(club=club)
        agenda_item = AgendaItemFactory(assembly=assembly, club=club, order=1)

        with active_club(club):
            with pytest.raises(services.AssemblyValidationError):
                services.record_decision(
                    assembly=assembly,
                    agenda_item=agenda_item,
                    actor=president.user,
                    votes_for=1,
                    votes_against=0,
                    votes_abstain=0,
                    outcome="   ",
                )


class TestMinutesSignature:
    def test_president_and_vice_president_signatures_complete_the_pv_and_generate_the_pdf(self):
        club = _club()
        president = _president(club)
        vice_president = _vice_president(club)
        assembly = AssemblyFactory(club=club)

        with active_club(club):
            services.draft_minutes(assembly=assembly, actor=president.user, content="Texte du PV.")
            minutes = services.sign_minutes(assembly=assembly, actor=president.user)
            assert minutes.is_complete is False
            assert minutes.generated_at is None

            minutes = services.sign_minutes(assembly=assembly, actor=vice_president.user)

        assert minutes.is_complete is True
        assert minutes.vp_vacant_at_signature is False
        assert minutes.generated_at is not None
        assert minutes.pdf_file

    def test_president_signs_alone_when_vp_is_vacant(self):
        """10.2 n° 28 : le President signe seul, la vacance est actee."""

        club = _club()
        president = _president(club)
        assembly = AssemblyFactory(club=club)

        with active_club(club):
            services.draft_minutes(assembly=assembly, actor=president.user, content="Texte du PV.")
            minutes = services.sign_minutes(assembly=assembly, actor=president.user)

        assert minutes.is_complete is True
        assert minutes.vp_vacant_at_signature is True
        assert minutes.vp_role_held_by_president is False
        assert minutes.generated_at is not None

    def test_president_and_vp_cumulated_signs_only_once_as_president(self):
        club = _club()
        president = _president(club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.VICE_PRESIDENT)
        assembly = AssemblyFactory(club=club)

        with active_club(club):
            services.draft_minutes(assembly=assembly, actor=president.user, content="Texte du PV.")
            minutes = services.sign_minutes(assembly=assembly, actor=president.user)

        # Signe au titre de President -- la signature VP reste vacante
        # (personne d'autre ne porte le role), donc le PV est complet. Le
        # poste n'est toutefois PAS vacant (le President le cumule) :
        # `vp_role_held_by_president` distingue les deux cas pour l'affichage
        # (modeles-documents.md §8 point 5, correction du cas objectivement
        # faux -- le libelle exact reste un point ouvert).
        assert minutes.president_signed_by_id == president.user_id
        assert minutes.vp_vacant_at_signature is True
        assert minutes.vp_role_held_by_president is True
        assert minutes.is_complete is True

    def test_minutes_cannot_be_edited_after_the_first_signature(self):
        club = _club()
        president = _president(club)
        assembly = AssemblyFactory(club=club)

        with active_club(club):
            services.draft_minutes(assembly=assembly, actor=president.user, content="V1")
            services.sign_minutes(assembly=assembly, actor=president.user)
            with pytest.raises(services.AssemblyLockedError):
                services.draft_minutes(assembly=assembly, actor=president.user, content="V2")

    def test_signature_succeeds_without_pin_and_journal_records_the_author(self):
        club = _club()
        president = _president(club)
        assembly = AssemblyFactory(club=club)

        with active_club(club):
            services.draft_minutes(assembly=assembly, actor=president.user, content="Texte")
            services.sign_minutes(assembly=assembly, actor=president.user)
            minutes = Minutes.all_objects.get(assembly=assembly)
        assert minutes.president_signed_by_id == president.user.id
        entry = AuditLog.objects.filter(action_type="assemblies.minutes.signed").latest("id")
        assert entry.actor_id == president.user.id

    def test_same_signatory_twice_gives_a_single_journal_entry(self):
        club = _club()
        president = _president(club)
        vice_president = _vice_president(club)
        assembly = AssemblyFactory(club=club)

        with active_club(club):
            services.draft_minutes(assembly=assembly, actor=president.user, content="Texte")
            services.sign_minutes(assembly=assembly, actor=president.user)
            with pytest.raises(services.AssemblyValidationError):
                services.sign_minutes(assembly=assembly, actor=president.user)
            # La signature du Vice-president n'est pas perdue par la tentative rejetee.
            minutes = services.sign_minutes(assembly=assembly, actor=vice_president.user)

        assert minutes.president_signed_by_id == president.user_id
        assert minutes.vp_signed_by_id == vice_president.user_id
        assert AuditLog.objects.filter(action_type="assemblies.minutes.signed").count() == 2
        assert AuditLog.objects.filter(
            action_type="assemblies.minutes.signed", actor_id=president.user_id
        ).count() == 1

    def test_signing_a_complete_pv_is_refused_and_not_journaled_again(self):
        club = _club()
        president = _president(club)
        assembly = AssemblyFactory(club=club)

        with active_club(club):
            services.draft_minutes(assembly=assembly, actor=president.user, content="Texte")
            services.sign_minutes(assembly=assembly, actor=president.user)
            with pytest.raises(services.AssemblyLockedError):
                services.sign_minutes(assembly=assembly, actor=president.user)

        assert AuditLog.objects.filter(action_type="assemblies.minutes.signed").count() == 1

    def test_a_plain_player_cannot_sign(self):
        club = _club()
        president = _president(club)
        player = MembershipFactory(club=club)
        assembly = AssemblyFactory(club=club)

        with active_club(club):
            services.draft_minutes(assembly=assembly, actor=president.user, content="Texte")
            with pytest.raises(services.AssemblyPermissionError, match="Réservé au Président et au Vice-président."):
                services.sign_minutes(assembly=assembly, actor=player.user)


class TestMinutesPdfContent:
    """Contenu du PDF genere (docs/annexes/modeles-documents.md §3, §6.1) :
    aucune troncature, heures dans le fuseau du club, libelle correct
    quand le President cumule le role de Vice-president."""

    def _pdf_text(self, minutes: Minutes) -> str:
        minutes.pdf_file.open("rb")
        try:
            content = minutes.pdf_file.read()
        finally:
            minutes.pdf_file.close()
        assert content.startswith(b"%PDF")
        # Canevas sans compression (pageCompression=0) pour permettre cette
        # assertion directe sur le flux de contenu -- voir
        # `apps.core.pdf.NumberedDocumentCanvas`.
        return content.decode("latin-1")

    def test_long_decision_text_is_not_truncated(self):
        club = _club()
        president = _president(club)
        vice_president = _vice_president(club)
        assembly = AssemblyFactory(club=club)
        long_decision = (
            "Decision detaillee votee a l'unanimite concernant le renouvellement complet du "
            "materiel sportif du club et la repartition du budget entre les differentes equipes "
            "pour la saison prochaine, incluant fin de phrase distinctive ZZQVERIFICATION."
        )
        assert len(long_decision) > 120

        with active_club(club):
            item = AgendaItemFactory(club=club, assembly=assembly, order=1, title="Materiel")
            services.record_decision(
                assembly=assembly,
                agenda_item=item,
                actor=president.user,
                votes_for=5,
                votes_against=0,
                votes_abstain=0,
                outcome=long_decision,
            )
            services.draft_minutes(assembly=assembly, actor=president.user, content="Texte du PV.")
            services.sign_minutes(assembly=assembly, actor=president.user)
            minutes = services.sign_minutes(assembly=assembly, actor=vice_president.user)

        text = self._pdf_text(minutes)
        # Le marqueur se trouve au-dela du caractere 120 de la phrase :
        # l'ancien code coupait avec `text[:120]` et ne l'aurait jamais
        # ecrit dans le PDF. Il n'est pas cherche comme sous-chaine contigue
        # de toute la phrase : le repli a la ligne (§3.5) insere des sauts
        # entre les operateurs PDF `Tj`, pas de simples espaces.
        assert long_decision.index("ZZQVERIFICATION") > 120
        assert "ZZQVERIFICATION" in text

    def test_vacancy_wording_when_president_holds_the_vp_role(self):
        club = _club()
        president = _president(club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.VICE_PRESIDENT)
        assembly = AssemblyFactory(club=club)

        with active_club(club):
            services.draft_minutes(assembly=assembly, actor=president.user, content="Texte du PV.")
            minutes = services.sign_minutes(assembly=assembly, actor=president.user)

        text = self._pdf_text(minutes)
        # ReportLab echappe les caracteres accentues en octal dans le flux
        # PDF (ex. « é » -> `\351`) : les fragments de comparaison restent
        # volontairement en ASCII pur pour rester lisibles tels quels dans
        # le flux non compresse (pageCompression=0).
        assert "aussi la fonction de Vice" in text
        assert "Fonction exerc" in text
        assert "vacant" not in text.lower()

    def test_genuine_vacancy_wording_when_there_is_no_vp(self):
        club = _club()
        president = _president(club)
        assembly = AssemblyFactory(club=club)

        with active_club(club):
            services.draft_minutes(assembly=assembly, actor=president.user, content="Texte du PV.")
            minutes = services.sign_minutes(assembly=assembly, actor=president.user)

        text = self._pdf_text(minutes)
        assert "vacant" in text.lower()

    def test_signature_timestamps_are_shown_in_the_clubs_timezone(self):
        club = _club()
        president = _president(club)
        assembly = AssemblyFactory(club=club)
        # 23h30 UTC un jour donne = 00h30 le lendemain a Kinshasa (UTC+1,
        # sans heure d'ete) : verifie que le PDF affiche l'heure et la date
        # locales, pas l'UTC (CLAUDE.md §7).
        utc_instant = datetime(2026, 9, 27, 23, 30, tzinfo=ZoneInfo("UTC"))

        with active_club(club):
            services.draft_minutes(assembly=assembly, actor=president.user, content="Texte du PV.")
            minutes = services.sign_minutes(assembly=assembly, actor=president.user, now=utc_instant)

        text = self._pdf_text(minutes)
        assert "28/09/2026" in text
        assert "00:30" in text
        assert "23:30" not in text

    def test_no_cdc_reference_in_generated_pdf(self):
        club = _club()
        president = _president(club)
        assembly = AssemblyFactory(club=club)

        with active_club(club):
            services.draft_minutes(assembly=assembly, actor=president.user, content="Texte du PV.")
            minutes = services.sign_minutes(assembly=assembly, actor=president.user)

        text = self._pdf_text(minutes)
        assert "CDC" not in text


class TestQuorumThreshold:
    def test_updates_within_range(self):
        club = _club()
        president = _president(club)

        with active_club(club):
            club_settings = services.update_quorum_threshold(club=club, actor=president.user, percentage=66)

        assert club_settings.assembly_quorum_percentage == 66
        assert AuditLog.objects.filter(action_type="assemblies.quorum_threshold.updated").exists()

    @pytest.mark.parametrize("value", [0, 101, -5])
    def test_refuses_out_of_range(self, value):
        club = _club()
        president = _president(club)

        with active_club(club):
            with pytest.raises(services.AssemblyValidationError):
                services.update_quorum_threshold(club=club, actor=president.user, percentage=value)


class TestAssemblyReminders:
    def test_sends_a_reminder_the_day_before_and_is_idempotent(self):
        club = _club()
        MembershipFactory(club=club)
        tomorrow = (timezone.now().astimezone(TZ) + timedelta(days=1)).date()
        assembly = AssemblyFactory(club=club, scheduled_date=tomorrow)

        result = services.send_assembly_reminders()
        assert result["reminders_sent"] == 1
        assembly.refresh_from_db()
        assert assembly.reminder_sent_at is not None

        # Idempotence : un second appel n'envoie rien de plus.
        result = services.send_assembly_reminders()
        assert result["reminders_sent"] == 0
