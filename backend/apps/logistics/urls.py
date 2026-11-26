"""Routes de l'API logistics (tâche 4.3 ; fiche d'écran logistique.md)."""

from django.urls import path

from apps.logistics import views

app_name = "logistics"

urlpatterns = [
    path("overview/", views.MaterialOverviewView.as_view(), name="overview"),
    # Catalogue
    path("articles/", views.ArticleListCreateView.as_view(), name="article-list"),
    path("articles/<int:pk>/", views.ArticleDetailView.as_view(), name="article-detail"),
    # Detenteurs, deplacements, declassement, registre de l'intendance
    path("holders/", views.HolderListCreateView.as_view(), name="holder-list"),
    path("holders/<int:pk>/", views.HolderDetailView.as_view(), name="holder-detail"),
    path("holders/<int:pk>/archive/", views.HolderArchiveView.as_view(), name="holder-archive"),
    path("transfers/", views.TransferCreateView.as_view(), name="transfer-create"),
    path("decommissions/", views.DecommissionListCreateView.as_view(), name="decommission-list"),
    path("decommissions/<int:pk>/", views.DecommissionDetailView.as_view(), name="decommission-detail"),
    path("decommissions/<int:pk>/execute/", views.DecommissionExecuteView.as_view(), name="decommission-execute"),
    path("decommissions/<int:pk>/cancel/", views.DecommissionCancelView.as_view(), name="decommission-cancel"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("register/pdf/", views.RegisterPdfView.as_view(), name="register-pdf"),
    path("register/csv/", views.RegisterCsvView.as_view(), name="register-csv"),
    # Registre des mouvements
    path("movements/", views.MovementListCreateView.as_view(), name="movement-list"),
    path("movements/<int:pk>/", views.MovementDetailView.as_view(), name="movement-detail"),
    # Dépenses rattachables à un achat (10.2 n° 167)
    path("expenses/linkable/", views.LinkableExpenseSearchView.as_view(), name="linkable-expenses"),
    # Équipements d'un match (câblage attendu par sport-feuille-de-match.md §4.5)
    path("matches/<int:match_id>/equipment/", views.MatchEquipmentView.as_view(), name="match-equipment"),
    path("matches/<int:match_id>/equipment/out/", views.MatchEquipmentOutView.as_view(), name="match-equipment-out"),
    path(
        "matches/<int:match_id>/equipment/return/",
        views.MatchEquipmentReturnView.as_view(),
        name="match-equipment-return",
    ),
    # Inventaire trimestriel
    path("inventories/open/", views.InventoryOpenView.as_view(), name="inventory-open"),
    path("inventories/<int:pk>/", views.InventoryDetailView.as_view(), name="inventory-detail"),
    path("inventories/<int:pk>/counts/", views.InventoryCountView.as_view(), name="inventory-counts"),
    path("inventories/<int:pk>/close/", views.InventoryCloseView.as_view(), name="inventory-close"),
    path(
        "inventory-lines/<int:pk>/justify/",
        views.InventoryLineJustifyView.as_view(),
        name="inventory-line-justify",
    ),
]
