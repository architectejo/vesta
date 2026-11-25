"""Routes de l'API audit (CDC 5.5), lecture seule, Superuser."""

from django.urls import path

from apps.audit import views

app_name = "audit"

urlpatterns = [
    path("logs/", views.AuditLogListView.as_view(), name="log-list"),
    path("logs/export/", views.AuditLogExportView.as_view(), name="log-export"),
    path("logs/<int:pk>/", views.AuditLogDetailView.as_view(), name="log-detail"),
    path("action-types/", views.AuditActionTypeListView.as_view(), name="action-types"),
]
