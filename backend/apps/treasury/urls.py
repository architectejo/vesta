"""Routes de l'API des types de cotisation."""

from django.urls import path

from apps.treasury import views

app_name = "treasury"

urlpatterns = [
    path("my-balance/", views.MyBalanceView.as_view(), name="my-balance"),
    # Donnees du joueur connecte, pour lui seul (« Mon profil » ; CDC 4.4.7)
    path("my-payments/", views.MyPaymentListView.as_view(), name="my-payments"),
    path("my-payments/<int:pk>/", views.MyPaymentDetailView.as_view(), name="my-payment-detail"),
    path("my-grid/<int:year>/", views.MyContributionGridView.as_view(), name="my-grid"),
    path(
        "my-grid/<int:type_id>/<int:year>/months/<int:month>/",
        views.MyContributionGridMonthView.as_view(),
        name="my-grid-month",
    ),
    path("contribution-types/", views.ContributionTypeListView.as_view(), name="contribution-type-list"),
    path(
        "contribution-types/<int:pk>/",
        views.ContributionTypeDetailView.as_view(),
        name="contribution-type-detail",
    ),
    # Enregistrement des paiements (CDC 4.4.3, 4.4.4 ; tache 2.4)
    path("payments/", views.PaymentCreateView.as_view(), name="payment-create"),
    path("payments/preview/", views.PaymentPreviewView.as_view(), name="payment-preview"),
    # Tableau de bord Tresorerie (CDC 4.4.6) : indicateurs, detail d'un
    # paiement et circuit d'annulation (CDC 4.4.4). La liste des derniers
    # paiements est le GET de ``payments/``.
    path("dashboard/summary/", views.TreasuryDashboardSummaryView.as_view(), name="dashboard-summary"),
    # Tableau « Membres du club » et modale « Situation financière » (CDC 4.4.6)
    path("members/", views.MemberListView.as_view(), name="member-list"),
    path("members/<int:membership_id>/", views.MemberDetailView.as_view(), name="member-detail"),
    path("members/<int:membership_id>/grid/<int:year>/", views.MemberGridView.as_view(), name="member-grid"),
    path("payments/<int:pk>/", views.PaymentDetailView.as_view(), name="payment-detail"),
    path(
        "payments/<int:pk>/reversal/",
        views.PaymentReversalRequestView.as_view(),
        name="payment-reversal-request",
    ),
    path(
        "payments/<int:pk>/reversal/approve/",
        views.PaymentReversalApproveView.as_view(),
        name="payment-reversal-approve",
    ),
    path(
        "payments/<int:pk>/reversal/reject/",
        views.PaymentReversalRejectView.as_view(),
        name="payment-reversal-reject",
    ),
    # Caisse Terrain Express (CDC 4.4.5, 6.6 ; 10.2 n° 22 ; tache 2.4)
    path("cash-sessions/", views.CashSessionOpenView.as_view(), name="cash-session-open"),
    path("cash-sessions/current/", views.CashSessionCurrentView.as_view(), name="cash-session-current"),
    path(
        "cash-sessions/<uuid:public_id>/close/",
        views.CashSessionCloseView.as_view(),
        name="cash-session-close",
    ),
    path(
        "cash-sessions/<uuid:public_id>/players/",
        views.CashSessionPlayerSearchView.as_view(),
        name="cash-session-players",
    ),
    path(
        "cash-sessions/<uuid:public_id>/payments/",
        views.CashSessionPaymentView.as_view(),
        name="cash-session-payments",
    ),
    path(
        "cash-sessions/<uuid:public_id>/payments/preview/",
        views.CashSessionPaymentPreviewView.as_view(),
        name="cash-session-payment-preview",
    ),
    path(
        "payments/<int:pk>/attachment/",
        views.PaymentAttachmentDownloadView.as_view(),
        name="payment-attachment-download",
    ),
    path(
        "payments/<int:pk>/receipt/",
        views.PaymentReceiptDownloadView.as_view(),
        name="payment-receipt-download",
    ),
    # Paiement en ligne, phase 1 : « Contribuer » et « J'ai payé » (CDC 4.6 ; tache 2.5)
    path("contribute/", views.ContributeView.as_view(), name="contribute"),
    path(
        "payment-declarations/",
        views.PaymentDeclarationListView.as_view(),
        name="payment-declaration-list",
    ),
    path(
        "payment-declarations/<int:pk>/",
        views.PaymentDeclarationDetailView.as_view(),
        name="payment-declaration-detail",
    ),
    path(
        "payment-declarations/<int:pk>/preview/",
        views.PaymentDeclarationPreviewView.as_view(),
        name="payment-declaration-preview",
    ),
    path(
        "payment-declarations/<int:pk>/validate/",
        views.PaymentDeclarationValidateView.as_view(),
        name="payment-declaration-validate",
    ),
    path(
        "payment-declarations/<int:pk>/reject/",
        views.PaymentDeclarationRejectView.as_view(),
        name="payment-declaration-reject",
    ),
    # Grille des cotisations (CDC 4.4.7) et import historique (CDC 4.4.8) -- tache 2.6
    path("grid/types/", views.GridContributionTypesView.as_view(), name="grid-types"),
    path("grid/<int:type_id>/<int:year>/", views.ContributionGridView.as_view(), name="grid"),
    path("grid/<int:type_id>/<int:year>/export/", views.ContributionGridExportView.as_view(), name="grid-export"),
    path(
        "grid/<int:type_id>/<int:year>/members/<int:membership_id>/months/<int:month>/",
        views.ContributionGridMonthView.as_view(),
        name="grid-month",
    ),
    path(
        "contribution-imports/preview/",
        views.ContributionImportPreviewView.as_view(),
        name="contribution-import-preview",
    ),
    path("contribution-imports/", views.ContributionImportView.as_view(), name="contribution-import"),
    # Capacites de l'utilisateur et devise du club (tache 2.2)
    path("capabilities/", views.TreasuryCapabilitiesView.as_view(), name="capabilities"),
    # Depenses (CDC 4.5.1, 4.5.2)
    path("expense-categories/", views.ExpenseCategoryListView.as_view(), name="expense-category-list"),
    path(
        "expense-categories/<int:pk>/",
        views.ExpenseCategoryDetailView.as_view(),
        name="expense-category-detail",
    ),
    path("expenses/", views.ExpenseListView.as_view(), name="expense-list"),
    path("expenses/summary/", views.ExpenseSummaryView.as_view(), name="expense-summary"),
    path("expenses/<int:pk>/", views.ExpenseDetailView.as_view(), name="expense-detail"),
    path("expenses/<int:pk>/refuse/", views.ExpenseRefuseView.as_view(), name="expense-refuse"),
    path("expenses/<int:pk>/release/", views.ExpenseReleaseView.as_view(), name="expense-release"),
    path(
        "expenses/<int:pk>/release-with-derogation/",
        views.ExpenseDerogationView.as_view(),
        name="expense-derogation",
    ),
    path("expenses/<int:pk>/receipt/", views.ExpenseReceiptUploadView.as_view(), name="expense-receipt"),
    path(
        "expense-attachments/<int:pk>/",
        views.ExpenseAttachmentDownloadView.as_view(),
        name="expense-attachment-download",
    ),
    # Assistance sociale (CDC 4.5.3)
    path(
        "social-assistance/scales/",
        views.SocialAssistanceScaleListView.as_view(),
        name="social-assistance-scale-list",
    ),
    path(
        "social-assistance/scales/<int:pk>/",
        views.SocialAssistanceScaleDetailView.as_view(),
        name="social-assistance-scale-detail",
    ),
    path(
        "social-assistance/preview/",
        views.SocialAssistancePreviewView.as_view(),
        name="social-assistance-preview",
    ),
    path(
        "social-assistance/requests/",
        views.SocialAssistanceRequestListView.as_view(),
        name="social-assistance-request-list",
    ),
    path(
        "social-assistance/requests/<int:pk>/",
        views.SocialAssistanceRequestDetailView.as_view(),
        name="social-assistance-request-detail",
    ),
    path(
        "social-assistance/requests/<int:pk>/approve/",
        views.SocialAssistanceApproveView.as_view(),
        name="social-assistance-approve",
    ),
    path(
        "social-assistance/requests/<int:pk>/reject/",
        views.SocialAssistanceRejectView.as_view(),
        name="social-assistance-reject",
    ),
    path(
        "social-assistance/requests/<int:pk>/attachment/",
        views.SocialAssistanceAttachmentDownloadView.as_view(),
        name="social-assistance-attachment-download",
    ),
]