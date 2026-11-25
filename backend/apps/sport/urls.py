"""Routes de l'API sport (tâche 3.6, suite des tâches 3.2-3.4)."""

from django.urls import path

from apps.sport import views, views_performance, views_stats

app_name = "sport"

urlpatterns = [
    # Séances et pointage (CDC 4.7)
    path("sessions/", views.SessionListCreateView.as_view(), name="session-list"),
    path("sessions/<int:pk>/", views.SessionDetailView.as_view(), name="session-detail"),
    path("sessions/<int:pk>/unassigned/", views.SessionUnassignedView.as_view(), name="session-unassigned"),
    path("sessions/<int:pk>/attendance/", views.SessionAttendanceMarkView.as_view(), name="session-attendance-mark"),
    path(
        "sessions/<int:pk>/attendance/excuse/",
        views.SessionAttendanceExcuseView.as_view(),
        name="session-attendance-excuse",
    ),
    path(
        "sessions/<int:pk>/attendance/bulk/",
        views.SessionAttendanceBulkView.as_view(),
        name="session-attendance-bulk",
    ),
    path("sessions/<int:pk>/team-assignment/", views.TeamAssignmentView.as_view(), name="team-assignment"),
    path(
        "sessions/<int:pk>/team-formation/",
        views.SessionTeamFormationView.as_view(),
        name="session-team-formation",
    ),
    path(
        "sessions/<int:pk>/team-placement/",
        views.SessionTeamPlayerPlacementView.as_view(),
        name="session-team-placement",
    ),
    path("attendance/<int:pk>/", views.AttendanceCorrectionView.as_view(), name="attendance-correction"),
    # Événements génériques (verrouillage et incidents, communs séance/match)
    path("events/<int:pk>/unlock/", views.EventUnlockView.as_view(), name="event-unlock"),
    path("events/<int:pk>/incidents/", views.EventIncidentListCreateView.as_view(), name="event-incidents"),
    path("events/<int:pk>/evaluations/", views.EventEvaluationListCreateView.as_view(), name="event-evaluations"),
    path("suspensions/", views.SuspensionListView.as_view(), name="suspension-list"),
    # Matchs et composition (CDC 4.8)
    path("matches/", views.MatchListCreateView.as_view(), name="match-list"),
    path("matches/<int:pk>/", views.MatchDetailView.as_view(), name="match-detail"),
    path(
        "matches/<int:pk>/composition/", views.MatchCompositionAddView.as_view(), name="match-composition-add"
    ),
    path(
        "matches/<int:pk>/composition/publish/",
        views.MatchCompositionPublishView.as_view(),
        name="match-composition-publish",
    ),
    path(
        "matches/<int:pk>/composition/<int:membership_id>/",
        views.MatchCompositionRemoveView.as_view(),
        name="match-composition-remove",
    ),
    path("matches/<int:pk>/attendance/", views.MatchAttendanceMarkView.as_view(), name="match-attendance-mark"),
    path(
        "matches/<int:pk>/attendance/bulk/",
        views.MatchAttendanceBulkView.as_view(),
        name="match-attendance-bulk",
    ),
    path("matches/<int:pk>/score/", views.MatchScoreView.as_view(), name="match-score"),
    path("matches/<int:pk>/publish-result/", views.MatchPublishResultView.as_view(), name="match-publish-result"),
    path("matches/<int:pk>/goals/", views.MatchGoalListCreateView.as_view(), name="match-goal-list"),
    path("goals/<int:pk>/", views.MatchGoalDetailView.as_view(), name="goal-detail"),
    # Plan tactique (CDC 4.11)
    path("tactical-plans/", views.TacticalPlanListCreateView.as_view(), name="tactical-plan-list"),
    path("tactical-plans/<int:pk>/", views.TacticalPlanDetailView.as_view(), name="tactical-plan-detail"),
    path(
        "tactical-plans/<int:pk>/duplicate/",
        views.TacticalPlanDuplicateView.as_view(),
        name="tactical-plan-duplicate",
    ),
    path(
        "tactical-plans/<int:pk>/publish/", views.TacticalPlanPublishView.as_view(), name="tactical-plan-publish"
    ),
    path(
        "tactical-plans/<int:pk>/placements/",
        views.TacticalPlanPlacementCreateView.as_view(),
        name="tactical-plan-placement-create",
    ),
    path("placements/<int:pk>/", views.PlacementDetailView.as_view(), name="placement-detail"),
    path(
        "tactical-plans/<int:pk>/annotations/",
        views.TacticalPlanAnnotationCreateView.as_view(),
        name="tactical-plan-annotation-create",
    ),
    path("annotations/<int:pk>/", views.AnnotationDetailView.as_view(), name="annotation-detail"),
    # Statistiques de séance et évolution (sport-statistiques-seance.md, parties A et B)
    path("sessions/stats/history/", views_stats.SessionStatsHistoryView.as_view(), name="session-stats-history"),
    path("sessions/<int:pk>/stats/", views_stats.SessionStatsView.as_view(), name="session-stats"),
    path("attendance/ranking/", views_stats.AttendanceRankingView.as_view(), name="attendance-ranking"),
    path("attendance/me/", views_stats.MyAttendanceView.as_view(), name="attendance-me"),
    # Tests de performance (partie C)
    path(
        "performance-test-templates/",
        views_performance.PerformanceTemplatesView.as_view(),
        name="performance-test-templates",
    ),
    path("performance-tests/", views_performance.PerformanceTestListCreateView.as_view(), name="performance-test-list"),
    path(
        "performance-tests/<int:pk>/",
        views_performance.PerformanceTestDetailView.as_view(),
        name="performance-test-detail",
    ),
    path(
        "performance-tests/<int:pk>/archive/",
        views_performance.PerformanceTestArchiveView.as_view(),
        name="performance-test-archive",
    ),
    path(
        "performance-tests/<int:pk>/leaderboard/",
        views_performance.PerformanceLeaderboardView.as_view(),
        name="performance-test-leaderboard",
    ),
    path(
        "events/<int:pk>/performance-results/",
        views_performance.EventPerformanceResultsView.as_view(),
        name="event-performance-results",
    ),
    path(
        "events/<int:pk>/performance-results/bulk/",
        views_performance.EventPerformanceResultsBulkView.as_view(),
        name="event-performance-results-bulk",
    ),
    path(
        "performance-results/<int:pk>/",
        views_performance.PerformanceResultDetailView.as_view(),
        name="performance-result-detail",
    ),
    path(
        "performance-results/<int:pk>/void/",
        views_performance.PerformanceResultVoidView.as_view(),
        name="performance-result-void",
    ),
    path(
        "players/<int:membership_id>/performance/",
        views_performance.PlayerPerformanceView.as_view(),
        name="player-performance",
    ),
    path("performance/me/", views_performance.MyPerformanceView.as_view(), name="performance-me"),
    # Vestiaire du jour (sport-vestiaire.md) : lecture seule
    path("locker-room/", views.LockerRoomView.as_view(), name="locker-room"),
]
