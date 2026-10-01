import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { listAnnouncements, type Announcement } from "../../api/social";
import { Avatar, Button, EmptyState, Skeleton } from "../../design-system";
import { AnnouncementDetailModal } from "../club/communiques/AnnouncementDetailModal";
import { PublishAnnouncementModal } from "../club/communiques/PublishAnnouncementModal";

function formatDateShort(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}

function AnnouncementRow({ announcement, onOpen }: { announcement: Announcement; onOpen: () => void }) {
  const fullName = `${announcement.published_by.first_name} ${announcement.published_by.last_name}`;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex min-h-14 w-full items-start justify-between gap-2 border-b border-border px-1 py-2 text-left last:border-b-0 hover:bg-surface-muted"
    >
      <div className="min-w-0 flex-1">
        <p className="text-base font-semibold text-text" style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
          {announcement.title}
        </p>
        <div className="mt-1 flex items-center gap-1.5">
          <Avatar name={fullName} photoUrl={announcement.published_by.avatar_url} size={24} />
          <span className="text-[13px] text-text-muted">
            {fullName} · {formatDateShort(announcement.published_at)}
          </span>
        </div>
      </div>
      {!announcement.is_read_by_me ? (
        <span className="flex shrink-0 items-center gap-1 text-[13px] text-primary-text">
          <span aria-hidden="true" className="h-2 w-2 rounded-full bg-primary" />
          Non lu
        </span>
      ) : null}
    </button>
  );
}

/** Carte « Communiqués » (club-accueil.md §4 point 1, §5.1-§5.2). */
export function CommuniquesCard({ canPublish }: { canPublish: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [openId, setOpenId] = useState<number | null>(null);
  const [publishOpen, setPublishOpen] = useState(false);

  const query = useQuery({
    queryKey: ["accueil", "announcements", "pinned"],
    queryFn: () => listAnnouncements({ pinned: true, limit: 3 }),
  });

  function invalidate(): void {
    void queryClient.invalidateQueries({ queryKey: ["accueil", "announcements"] });
    void queryClient.invalidateQueries({ queryKey: ["social", "announcements"] });
  }

  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-base font-semibold text-text">Communiqués</h2>
        {canPublish ? (
          <Button size="sm" variant="secondary" onClick={() => setPublishOpen(true)}>
            Publier un communiqué
          </Button>
        ) : null}
      </div>

      <div className="mt-2">
        {query.isLoading ? (
          <div className="space-y-2">
            <Skeleton variant="row" />
            <Skeleton variant="row" />
          </div>
        ) : query.isError ? (
          <EmptyState
            variant="error"
            message="Impossible de charger les communiqués."
            actionLabel="Réessayer"
            onAction={() => void query.refetch()}
          />
        ) : query.data && query.data.results.length > 0 ? (
          query.data.results.map((a) => (
            <AnnouncementRow key={a.id} announcement={a} onOpen={() => setOpenId(a.id)} />
          ))
        ) : (
          <EmptyState
            message="Aucun communiqué pour l'instant."
            actionLabel={canPublish ? "Publier un communiqué" : undefined}
            onAction={canPublish ? () => setPublishOpen(true) : undefined}
          />
        )}
      </div>

      <Button variant="ghost" size="sm" className="mt-2" onClick={() => navigate("/club/communiques")}>
        Voir tous les communiqués
      </Button>

      {openId !== null ? (
        <AnnouncementDetailModal announcementId={openId} onClose={() => setOpenId(null)} onChanged={invalidate} />
      ) : null}
      {publishOpen ? (
        <PublishAnnouncementModal
          onClose={() => setPublishOpen(false)}
          onPublished={() => {
            setPublishOpen(false);
            invalidate();
          }}
        />
      ) : null}
    </section>
  );
}
