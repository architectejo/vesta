"""Routes de l'API mercato (tâche 4.4 ; fiche d'écran mercato.md)."""

from django.urls import path

from apps.mercato import views

app_name = "mercato"

urlpatterns = [
    path("availability/", views.AvailabilityView.as_view(), name="availability"),
    path("market/", views.MarketListView.as_view(), name="market-list"),
    path("players/<int:membership_id>/", views.PublicPlayerDetailView.as_view(), name="player-public-detail"),
    path("offers/", views.OfferCreateView.as_view(), name="offer-create"),
    path("offers/mine/", views.MyOffersView.as_view(), name="offer-mine"),
    path("offers/club/", views.ClubOffersView.as_view(), name="offer-club"),
    path("offers/<int:pk>/", views.OfferDetailView.as_view(), name="offer-detail"),
    path("offers/<int:pk>/respond/", views.OfferRespondView.as_view(), name="offer-respond"),
    path("offers/<int:pk>/quitus/", views.OfferQuitusDownloadView.as_view(), name="offer-quitus"),
    path("threads/", views.ThreadListCreateView.as_view(), name="thread-list"),
    path("threads/<int:pk>/messages/", views.ThreadMessagesView.as_view(), name="thread-messages"),
]
