"""URLs de l'app accounts (CDC 4.1, 7.1, 7.5 ; tache 1.3)."""

from __future__ import annotations

from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("logout-all/", views.LogoutAllDevicesView.as_view(), name="logout-all"),
    path("token/refresh/", views.TokenRefreshView.as_view(), name="token-refresh"),
    path("password/change/", views.ForcedPasswordChangeView.as_view(), name="password-change"),
    path(
        "password/reset-request/",
        views.PasswordResetRequestView.as_view(),
        name="password-reset-request",
    ),
    path("password/reset/", views.SuperuserPasswordResetView.as_view(), name="password-reset-superuser"),
    path(
        "superuser/password-resets/pending/",
        views.SuperuserPendingPasswordResetsView.as_view(),
        name="superuser-password-resets-pending",
    ),
    path("superuser/accounts/", views.SuperuserAccountSearchView.as_view(), name="superuser-accounts-search"),
    path(
        "superuser/accounts/deactivate/",
        views.SuperuserAccountDeactivateView.as_view(),
        name="superuser-accounts-deactivate",
    ),
    path("terms/pending/", views.PendingTermsView.as_view(), name="terms-pending"),
    path("terms/accept/", views.AcceptTermsView.as_view(), name="terms-accept"),
    path(
        "profile/personal-info/",
        views.MyPersonalInfoUpdateView.as_view(),
        name="profile-personal-info",
    ),
    path("profile/credentials/", views.MyCredentialsUpdateView.as_view(), name="profile-credentials"),
    path("profile/pin/", views.MyPinUpdateView.as_view(), name="profile-pin"),
    path("profile/photo/", views.MyProfilePhotoView.as_view(), name="profile-photo"),
]
