"""URLs de l'app notifications (CDC 3.4, 4.17 ; tache 1.7)."""

from __future__ import annotations

from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="list"),
    path("unread-count/", views.NotificationUnreadCountView.as_view(), name="unread-count"),
    path("<int:notification_id>/read/", views.NotificationMarkReadView.as_view(), name="mark-read"),
    path("read-all/", views.NotificationMarkAllReadView.as_view(), name="mark-all-read"),
    path("preference/", views.NotificationPreferenceView.as_view(), name="preference"),
]
