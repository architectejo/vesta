"""Routes de l'API assemblies (CDC 4.15 ; tache 4.5)."""

from django.urls import path

from apps.assemblies import views

app_name = "assemblies"

urlpatterns = [
    path("", views.AssemblyListCreateView.as_view(), name="assembly-list"),
    path("<int:pk>/", views.AssemblyDetailView.as_view(), name="assembly-detail"),
    path("<int:pk>/attendance/", views.AssemblyAttendanceListMarkView.as_view(), name="assembly-attendance"),
    path(
        "<int:pk>/attendance/<int:membership_id>/",
        views.AssemblyAttendanceRemoveView.as_view(),
        name="assembly-attendance-remove",
    ),
    path(
        "<int:pk>/agenda-items/<int:agenda_item_id>/decision/",
        views.AssemblyDecisionView.as_view(),
        name="assembly-decision",
    ),
    path("<int:pk>/minutes/", views.AssemblyMinutesView.as_view(), name="assembly-minutes"),
    path("<int:pk>/minutes/sign/", views.AssemblyMinutesSignView.as_view(), name="assembly-minutes-sign"),
    path("<int:pk>/minutes/pdf/", views.AssemblyMinutesPdfDownloadView.as_view(), name="minutes-pdf-download"),
    path("quorum-threshold/", views.QuorumThresholdView.as_view(), name="quorum-threshold"),
]
