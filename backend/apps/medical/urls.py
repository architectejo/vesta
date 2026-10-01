"""Routes de l'API medical (Lot 4, tache 4.2)."""

from django.urls import path

from apps.medical import views

app_name = "medical"

urlpatterns = [
    # Fiche de sante (medical.md §4.2, §4.5)
    path(
        "players/<int:membership_id>/health-record/",
        views.HealthRecordDetailView.as_view(),
        name="health-record-detail",
    ),
    path(
        "players/<int:membership_id>/fitness/",
        views.FitnessUpdateView.as_view(),
        name="fitness-update",
    ),
    # Mon profil (medical.md §4.10, §4.11)
    path("me/self-declaration/", views.MySelfDeclarationView.as_view(), name="my-self-declaration"),
    path("me/processing-consent/", views.MyProcessingConsentView.as_view(), name="my-processing-consent"),
    path("me/president-access/", views.MyPresidentAccessView.as_view(), name="my-president-access"),
    # Blessures (medical.md §4.1, §4.3, §4.7-§4.9)
    path("injuries/", views.InjuryListCreateView.as_view(), name="injury-list"),
    path("injuries/<int:pk>/", views.InjuryDetailView.as_view(), name="injury-detail"),
    path("injuries/<int:pk>/complete/", views.InjuryCompleteView.as_view(), name="injury-complete"),
    path("injuries/<int:pk>/followups/", views.InjuryFollowUpListCreateView.as_view(), name="injury-followups"),
    path("injuries/<int:pk>/return/", views.InjuryReturnView.as_view(), name="injury-return"),
    path("injuries/<int:pk>/documents/", views.InjuryDocumentUploadView.as_view(), name="injury-document-upload"),
    # Page « Medical » (medical.md §3)
    path("page/to-complete/", views.InjuriesToCompleteView.as_view(), name="page-to-complete"),
    path("page/recent-injuries/", views.RecentInjuriesView.as_view(), name="page-recent-injuries"),
    path("page/unfit/", views.UnfitAndRestrictedView.as_view(), name="page-unfit"),
    # Documents medicaux (CDC 6.7)
    path("documents/<int:pk>/download/", views.MedicalDocumentDownloadView.as_view(), name="document-download"),
]
