"""Routes de l'API social (CDC 4.16 ; tache 4.6)."""

from django.urls import path

from apps.social import views

app_name = "social"

urlpatterns = [
    # Fil d'actualite (PARTIE A)
    path("posts/", views.PostListCreateView.as_view(), name="post-list"),
    path("posts/<int:pk>/", views.PostDetailView.as_view(), name="post-detail"),
    path("posts/<int:pk>/delete/", views.PostDeleteView.as_view(), name="post-delete"),
    path("posts/<int:pk>/like/", views.PostLikeToggleView.as_view(), name="post-like"),
    path("posts/<int:pk>/comments/", views.PostCommentListCreateView.as_view(), name="post-comments"),
    path("posts/<int:pk>/report/", views.PostReportView.as_view(), name="post-report"),
    path("comments/<int:pk>/", views.CommentDeleteView.as_view(), name="comment-delete"),
    path("post-images/<int:pk>/", views.PostImageDownloadView.as_view(), name="post-image-download"),
    # Communiques (PARTIE B)
    path("announcements/", views.AnnouncementListCreateView.as_view(), name="announcement-list"),
    path("announcements/<int:pk>/", views.AnnouncementDetailView.as_view(), name="announcement-detail"),
    path("announcements/<int:pk>/read/", views.AnnouncementReadView.as_view(), name="announcement-read"),
    path("announcements/<int:pk>/pin/", views.AnnouncementPinView.as_view(), name="announcement-pin"),
    path(
        "announcements/<int:pk>/read-receipts/",
        views.AnnouncementReadReceiptsView.as_view(),
        name="announcement-read-receipts",
    ),
    path(
        "announcement-images/<int:pk>/",
        views.AnnouncementImageDownloadView.as_view(),
        name="announcement-image-download",
    ),
    # Chat d'equipe (PARTIE C)
    path("chat/channels/", views.ChatChannelListView.as_view(), name="chat-channel-list"),
    path("chat/channels/<int:pk>/messages/", views.ChatMessageListCreateView.as_view(), name="chat-message-list"),
    path("chat/channels/<int:pk>/read/", views.ChatChannelReadView.as_view(), name="chat-channel-read"),
    path(
        "chat/messages/<int:pk>/image/",
        views.ChatMessageImageDownloadView.as_view(),
        name="chat-message-image-download",
    ),
]
