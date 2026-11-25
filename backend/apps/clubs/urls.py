"""URLs de l'app clubs (CDC 2.2-2.4 ; tache 1.5)."""

from __future__ import annotations

from django.urls import path

from apps.clubs import views, views_player_cards

app_name = "clubs"

urlpatterns = [
    # Assistant de creation de club (tache 1.9 ; PUBLIC, non authentifie).
    path(
        "public/creation-settings/",
        views.PublicClubCreationSettingsView.as_view(),
        name="public-creation-settings",
    ),
    path("create/", views.ClubCreationView.as_view(), name="create"),
    # Tableau de bord du Président et du Vice-président (lecture seule).
    path("board-dashboard/", views.BoardDashboardView.as_view(), name="board-dashboard"),
    path("board-dashboard/<str:section>/", views.BoardDashboardSectionView.as_view(), name="board-dashboard-section"),
    # Mon profil (tache 1.9, slice Lot 1).
    path("profile/me/", views.MyProfileView.as_view(), name="profile-me"),
    # Identite du club / fiche publique du joueur (tache 1.9).
    path("settings/identity/", views.ClubIdentityView.as_view(), name="identity"),
    path("players/", views.PlayerListView.as_view(), name="players-list"),
    path("players/cards/", views_player_cards.PlayerCardListView.as_view(), name="players-cards"),
    path("players/compare/", views_player_cards.PlayerComparisonView.as_view(), name="players-compare"),
    path("players/<int:membership_id>/stats/", views_player_cards.PlayerStatsView.as_view(), name="player-stats"),
    path("players/<int:membership_id>/card/", views.PlayerCardView.as_view(), name="player-card"),
    path("roles/", views.RoleListView.as_view(), name="role-list"),
    path("roles/appoint/", views.RoleAppointmentView.as_view(), name="role-appoint"),
    path("roles/revoke/", views.RoleRevocationView.as_view(), name="role-revoke"),
    path("roles/captain/appoint/", views.CaptainAppointmentView.as_view(), name="captain-appoint"),
    path("roles/captain/revoke/", views.CaptainRevocationView.as_view(), name="captain-revoke"),
    path("roles/assistant-coach/appoint/", views.AssistantCoachAppointmentView.as_view(), name="assistant-coach-appoint"),
    path("roles/assistant-coach/revoke/", views.AssistantCoachRevocationView.as_view(), name="assistant-coach-revoke"),
    path(
        "presidency-transfer/handover/",
        views.PresidencyHandoverView.as_view(),
        name="presidency-handover",
    ),
    path(
        "presidency-transfer/superuser-override/",
        views.PresidencySuperuserOverrideView.as_view(),
        name="presidency-superuser-override",
    ),
    path("settings/board-seats/", views.BoardSeatsSettingsView.as_view(), name="board-seats"),
    path("players/import/", views.PlayerImportView.as_view(), name="players-import"),
    path(
        "imports/<int:pk>/source/",
        views.ImportBatchSourceDownloadView.as_view(),
        name="import-source-download",
    ),
    path(
        "imports/<int:pk>/report/",
        views.ImportBatchReportDownloadView.as_view(),
        name="import-report-download",
    ),
    path("players/add/", views.AddPlayerWithSponsorView.as_view(), name="players-add"),
    path(
        "applications/<int:pk>/fiche-pdf/",
        views.MembershipApplicationPdfDownloadView.as_view(),
        name="application-pdf-download",
    ),
    path(
        "players/<int:membership_id>/application/",
        views.MembershipApplicationByMembershipView.as_view(),
        name="application-by-membership",
    ),
    path(
        "applications/pending-sponsor-signature/",
        views.PendingSponsorSignaturesView.as_view(),
        name="applications-pending-sponsor-signature",
    ),
    path(
        "applications/pending-president-decision/",
        views.PendingPresidentDecisionsView.as_view(),
        name="applications-pending-president-decision",
    ),
    path(
        "applications/fee-payment/",
        views.MembershipFeePaymentView.as_view(),
        name="application-fee-payment",
    ),
    path(
        "applications/sponsor/sign/",
        views.SponsorSignatureView.as_view(),
        name="application-sponsor-sign",
    ),
    path(
        "applications/sponsor/refuse/",
        views.SponsorRefusalView.as_view(),
        name="application-sponsor-refuse",
    ),
    path(
        "applications/sponsor/reassign/",
        views.SponsorReassignmentView.as_view(),
        name="application-sponsor-reassign",
    ),
    path(
        "applications/cancel/",
        views.MembershipApplicationCancellationView.as_view(),
        name="application-cancel",
    ),
]
