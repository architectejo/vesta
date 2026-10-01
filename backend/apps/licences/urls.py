"""URLs de l'app licences (CDC 2.5, 4.18 ; tache 1.8)."""

from __future__ import annotations

from django.urls import path

from apps.licences import views

app_name = "licences"

urlpatterns = [
    path("", views.LicenceListView.as_view(), name="licence-list"),
    path("<int:licence_id>/", views.LicenceDetailView.as_view(), name="licence-detail"),
    path("<int:licence_id>/events/", views.LicenceEventListView.as_view(), name="licence-events"),
    path("<int:licence_id>/activate/", views.LicenceActivateView.as_view(), name="licence-activate"),
    path("<int:licence_id>/extend/", views.LicenceExtendView.as_view(), name="licence-extend"),
    path("<int:licence_id>/suspend/", views.LicenceSuspendView.as_view(), name="licence-suspend"),
    path("<int:licence_id>/resume/", views.LicenceResumeView.as_view(), name="licence-resume"),
    path("<int:licence_id>/terminate/", views.LicenceTerminateView.as_view(), name="licence-terminate"),
    path("support-sessions/", views.SupportSessionListView.as_view(), name="support-session-list"),
    path(
        "support-sessions/start/", views.SupportSessionStartView.as_view(), name="support-session-start"
    ),
    path(
        "support-sessions/<int:session_id>/end/",
        views.SupportSessionEndView.as_view(),
        name="support-session-end",
    ),
]
