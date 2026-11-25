import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getNotifications,
  getUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
  type AppNotification,
} from "../api/notifications";
import type { MyProfile } from "../api/clubs";
import { NotificationBell, type NotificationBellNotification } from "../design-system";
import { resolveNotificationRoute } from "./notificationLinks";

/** Interrogation toutes les 30 s, suspendue si l'onglet est inactif (CDC 6.5). */
const POLL_INTERVAL_MS = 30_000;

function toBellNotification(n: AppNotification): NotificationBellNotification {
  return {
    id: n.id,
    title: n.title,
    body: n.body,
    isRead: n.is_read,
    createdAt: n.created_at,
    linkObjectType: n.link_object_type,
    linkObjectId: n.link_object_id,
  };
}

function pollInterval(): number | false {
  return document.visibilityState === "hidden" ? false : POLL_INTERVAL_MS;
}

export function NotificationBellWidget({ variant = "ghost" }: { variant?: "ghost" | "sidebar" }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const unreadQuery = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: getUnreadCount,
    refetchInterval: pollInterval,
  });

  const listQuery = useInfiniteQuery({
    queryKey: ["notifications", "list"],
    queryFn: ({ pageParam }) => getNotifications(pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage, allPages) => (lastPage.next ? allPages.length + 1 : undefined),
    enabled: open,
    refetchInterval: pollInterval,
  });
  const allResults = useMemo(
    () => (listQuery.data?.pages ?? []).flatMap((page) => page.results),
    [listQuery.data],
  );

  function invalidate(): void {
    void queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }

  const markRead = useMutation({
    mutationFn: (id: number) => markNotificationRead(id),
    onSuccess: invalidate,
  });
  const markAllRead = useMutation({
    mutationFn: () => markAllNotificationsRead(),
    onSuccess: invalidate,
  });

  function handleOpenChange(next: boolean): void {
    setOpen(next);
    // À la fermeture, la liste repart de la première page à la prochaine ouverture.
    if (!next) queryClient.removeQueries({ queryKey: ["notifications", "list"] });
  }

  function handleSelect(notification: NotificationBellNotification): void {
    if (!notification.isRead) markRead.mutate(notification.id);
    handleOpenChange(false);
    const source = allResults.find((n) => n.id === notification.id);
    // Profil déjà chargé par la mise en page : lecture du cache, aucune requête.
    const profile = queryClient.getQueryData<MyProfile>(["profile", "me"]);
    const isPaymentRecorder =
      profile?.roles.some((r) => r.role === "treasurer" || r.role === "assistant_treasurer") ?? false;
    const isTreasuryViewer =
      profile?.roles.some((r) => ["treasurer", "assistant_treasurer", "president"].includes(r.role)) ?? false;
    const isCoach = profile?.roles.some((r) => r.role === "coach" || r.role === "assistant_coach") ?? false;
    const route = resolveNotificationRoute(
      {
        eventType: source?.event_type ?? "",
        linkObjectType: notification.linkObjectType,
        linkObjectId: notification.linkObjectId,
      },
      { isPaymentRecorder, isCoach, isTreasuryViewer },
    );
    if (route) navigate(route);
  }

  const notifications = useMemo(() => allResults.map(toBellNotification), [allResults]);

  return (
    <NotificationBell
      variant={variant}
      open={open}
      onOpenChange={handleOpenChange}
      unreadCount={unreadQuery.data?.unread_count ?? 0}
      notifications={notifications}
      isLoading={listQuery.isLoading}
      isLoadingMore={listQuery.isFetchingNextPage}
      isError={listQuery.isError}
      onRetry={() => void listQuery.refetch()}
      hasMore={listQuery.hasNextPage}
      onLoadMore={() => void listQuery.fetchNextPage()}
      onMarkAllRead={() => markAllRead.mutate()}
      isMarkingAllRead={markAllRead.isPending}
      onSelect={handleSelect}
    />
  );
}
