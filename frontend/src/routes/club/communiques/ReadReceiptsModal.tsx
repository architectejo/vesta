import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getAnnouncementReadReceipts } from "../../../api/social";
import { Avatar, EmptyState, Modal, Skeleton } from "../../../design-system";

/** Modale « Accusés de lecture » (B4.1, Président et Vice-président). */
export function ReadReceiptsModal({
  announcementId,
  title,
  onClose,
}: {
  announcementId: number;
  title: string;
  onClose: () => void;
}) {
  const [filter, setFilter] = useState<"unread" | "read">("unread");
  const query = useQuery({
    queryKey: ["social", "announcements", announcementId, "read-receipts", filter],
    queryFn: () => getAnnouncementReadReceipts(announcementId, filter),
  });

  return (
    <Modal open onClose={onClose} title="Accusés de lecture" subtitle={title} size="md" level={2} loading={query.isLoading} cancelLabel="Fermer">
      {query.data ? (
        <div className="space-y-3">
          <p className="text-sm text-text-muted">
            Lu par {query.data.read_count} joueurs sur {query.data.total} (
            {query.data.total > 0 ? Math.round((query.data.read_count / query.data.total) * 100) : 0} %)
          </p>
          <div role="group" aria-label="Filtre des accusés de lecture" className="flex gap-1">
            {(["unread", "read"] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={filter === value}
                onClick={() => setFilter(value)}
                className={[
                  "h-control-sm rounded-sm border px-3 text-sm font-medium",
                  filter === value ? "border-primary bg-primary text-on-primary" : "border-border-strong bg-surface text-text",
                ].join(" ")}
              >
                {value === "unread" ? `Non lus (${query.data.total - query.data.read_count})` : `Lus (${query.data.read_count})`}
              </button>
            ))}
          </div>
          {query.data.results.length > 0 ? (
            <ul className="space-y-2">
              {query.data.results.map((row) => (
                <li key={row.membership_id} className="flex items-center gap-2">
                  <Avatar name={`${row.first_name} ${row.last_name}`} size={32} />
                  <span className="text-sm text-text">{row.first_name} {row.last_name}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              message={
                query.data.total > 0 && query.data.read_count === query.data.total
                  ? "Tous les joueurs ont lu ce communiqué."
                  : query.data.read_count === 0
                    ? "Personne n'a encore lu ce communiqué."
                    : undefined
              }
            />
          )}
        </div>
      ) : query.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} variant="row" />
          ))}
        </div>
      ) : (
        <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void query.refetch()} />
      )}
    </Modal>
  );
}
