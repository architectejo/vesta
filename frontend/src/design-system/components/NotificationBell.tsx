import { IconNotifications } from "../icons";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import { IconButton } from "./IconButton";
import { Modal } from "./Modal";
import { Skeleton } from "./Skeleton";

export interface NotificationBellNotification {
  id: number;
  title: string;
  body: string;
  isRead: boolean;
  createdAt: string;
  /** Type de l'objet cible fourni par l'API (vide : la notification ne mène nulle part). */
  linkObjectType: string;
  linkObjectId: number | null;
}

export interface NotificationBellProps {
  /** `sidebar` : posée sur le fond de la barre latérale (barre mobile). */
  variant?: "ghost" | "sidebar";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  unreadCount: number;
  notifications: NotificationBellNotification[];
  isLoading: boolean;
  isLoadingMore?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  hasMore: boolean;
  onLoadMore: () => void;
  onMarkAllRead: () => void;
  isMarkingAllRead?: boolean;
  onSelect: (notification: NotificationBellNotification) => void;
  className?: string;
}

function formatNotificationDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function NotificationRow({
  notification,
  onSelect,
}: {
  notification: NotificationBellNotification;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className="flex min-h-14 w-full flex-col gap-1 border-b border-border px-1 py-2 text-left last:border-b-0 hover:bg-surface-muted"
    >
      <span className="flex items-start justify-between gap-2">
        <span className={["text-sm text-text", notification.isRead ? "font-normal" : "font-semibold"].join(" ")}>
          {notification.title}
        </span>
        {!notification.isRead ? (
          <span className="flex shrink-0 items-center gap-1 text-[13px] text-primary-text">
            <span aria-hidden="true" className="h-2 w-2 rounded-full bg-primary" />
            Non lu
          </span>
        ) : null}
      </span>
      <span className="text-[13px] text-text-muted">{notification.body}</span>
      <span className="text-[13px] text-text-muted">{formatNotificationDate(notification.createdAt)}</span>
    </button>
  );
}

/**
 * Icône cloche et modale « Notifications » (design-system.md §3.1 ; CDC 3.4,
 * 4.17). Présentationnel : données, compteur et navigation viennent de
 * l'appelant (`layouts/NotificationBellWidget.tsx`), comme `PlayerSearch`.
 */
export function NotificationBell({
  variant = "ghost",
  open,
  onOpenChange,
  unreadCount,
  notifications,
  isLoading,
  isLoadingMore = false,
  isError = false,
  onRetry,
  hasMore,
  onLoadMore,
  onMarkAllRead,
  isMarkingAllRead = false,
  onSelect,
  className = "",
}: NotificationBellProps) {
  return (
    <>
      <IconButton
        aria-label="Notifications"
        variant={variant}
        className={className}
        onClick={() => onOpenChange(true)}
        icon={
          <>
            <IconNotifications aria-hidden="true" className="h-5 w-5" />
            {unreadCount > 0 ? (
              <>
                <span
                  data-testid="notification-badge"
                  aria-hidden="true"
                  className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-status-danger-dot px-1 text-[11px] font-semibold leading-none text-white"
                >
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
                <span className="sr-only">{unreadCount} non lue(s)</span>
              </>
            ) : null}
          </>
        }
      />

      <Modal open={open} onClose={() => onOpenChange(false)} title="Notifications" size="sm" hideFooter>
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-[13px] text-text-muted">
            {unreadCount > 0 ? `${unreadCount} non lue${unreadCount > 1 ? "s" : ""}` : "Tout est lu"}
          </p>
          <Button
            variant="ghost"
            size="sm"
            onClick={onMarkAllRead}
            loading={isMarkingAllRead}
            loadingLabel="Marquage…"
            disabled={unreadCount === 0}
          >
            Tout marquer comme lu
          </Button>
        </div>

        {isLoading ? (
          <div className="space-y-2">
            <Skeleton variant="row" />
            <Skeleton variant="row" />
            <Skeleton variant="row" />
          </div>
        ) : isError ? (
          <EmptyState
            variant="error"
            message="Impossible de charger les notifications."
            actionLabel={onRetry ? "Réessayer" : undefined}
            onAction={onRetry}
          />
        ) : notifications.length === 0 ? (
          <EmptyState message="Aucune notification." />
        ) : (
          <>
            <div>
              {notifications.map((notification) => (
                <NotificationRow
                  key={notification.id}
                  notification={notification}
                  onSelect={() => onSelect(notification)}
                />
              ))}
            </div>
            {hasMore ? (
              <div className="mt-2 text-center">
                <Button
                  variant="secondary"
                  size="sm"
                  loading={isLoadingMore}
                  loadingLabel="Chargement…"
                  onClick={onLoadMore}
                >
                  Voir plus
                </Button>
              </div>
            ) : null}
          </>
        )}
      </Modal>
    </>
  );
}
