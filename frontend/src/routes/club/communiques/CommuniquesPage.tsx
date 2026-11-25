import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getMyProfile } from "../../../api/clubs";
import { getAccueilAccess } from "../../accueil/accueilAccess";
import { listAnnouncements, type Announcement } from "../../../api/social";
import { Avatar, Button, EmptyState, IconPin, Skeleton, useClubBranding } from "../../../design-system";
import { useDeepLink } from "../../../hooks/useDeepLink";
import { AnnouncementDetailModal } from "./AnnouncementDetailModal";
import { PublishAnnouncementModal } from "./PublishAnnouncementModal";

const PAGE_SIZE = 10;

function formatDateShort(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}

function PinIcon() {
  return <IconPin aria-hidden="true" className="h-4 w-4" />;
}

function AnnouncementRow({ announcement, onOpen }: { announcement: Announcement; onOpen: () => void }) {
  const fullName = `${announcement.published_by.first_name} ${announcement.published_by.last_name}`;
  return (
    <button type="button" onClick={onOpen} className="flex min-h-14 w-full items-start justify-between gap-2 border-b border-border px-1 py-2 text-left last:border-b-0 hover:bg-surface-muted">
      <div className="min-w-0 flex-1">
        <p className="text-base font-semibold text-text" style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
          {announcement.title}
        </p>
        <div className="mt-1 flex items-center gap-1.5">
          <Avatar name={fullName} photoUrl={announcement.published_by.avatar_url} size={24} />
          <span className="text-[13px] text-text-muted">{fullName} · {formatDateShort(announcement.published_at)}</span>
        </div>
        {announcement.read_summary ? (
          <p className="mt-0.5 text-[13px] text-text-muted">
            Lu par {announcement.read_summary.read_count} sur {announcement.read_summary.total}
          </p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {!announcement.is_read_by_me ? (
          <span className="flex items-center gap-1 text-[13px] text-primary-text">
            <span aria-hidden="true" className="h-2 w-2 rounded-full bg-primary" />
            Non lu
          </span>
        ) : null}
        {announcement.pinned ? (
          <span className="text-text-muted">
            <PinIcon />
          </span>
        ) : null}
      </div>
    </button>
  );
}

/** Page « Communiqués » (fil-public-communication.md, PARTIE B). */
export function CommuniquesPage() {
  const branding = useClubBranding();
  const queryClient = useQueryClient();
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [openId, setOpenId] = useState<number | null>(null);
  // Lien depuis une notification de communiqué (`?communique=<id>`).
  useDeepLink("communique", setOpenId);
  const [publishOpen, setPublishOpen] = useState(false);

  const pinnedQuery = useQuery({ queryKey: ["social", "announcements", "pinned"], queryFn: () => listAnnouncements({ pinned: true }) });
  const allQuery = useQuery({ queryKey: ["social", "announcements", "all", limit], queryFn: () => listAnnouncements({ limit }) });

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const canManage =
    (allQuery.data?.results.some((a) => a.read_summary !== null) ?? false) ||
    getAccueilAccess(profileQuery.data?.roles).canPublishAnnouncement;
  const unreadCount = allQuery.data?.results.filter((a) => !a.is_read_by_me).length ?? 0;

  function invalidate(): void {
    void queryClient.invalidateQueries({ queryKey: ["social", "announcements"] });
  }

  return (
    <div className="mx-auto max-w-[800px] space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-text">Communiqués</h1>
          <p className="text-sm text-text-muted">
            {branding?.name ?? ""} · {unreadCount > 0 ? `${unreadCount} non lu(s)` : "Tout est lu"}
          </p>
        </div>
        {canManage ? (
          <Button variant="primary" size="sm" onClick={() => setPublishOpen(true)}>
            Publier un communiqué
          </Button>
        ) : null}
      </header>

      {pinnedQuery.data && pinnedQuery.data.results.length > 0 ? (
        <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
          <h2 className="mb-2 text-sm font-semibold text-text">Épinglés</h2>
          {pinnedQuery.data.results.map((a) => (
            <AnnouncementRow key={a.id} announcement={a} onOpen={() => setOpenId(a.id)} />
          ))}
        </section>
      ) : null}

      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <h2 className="mb-2 text-sm font-semibold text-text">Tous les communiqués</h2>
        {allQuery.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} variant="row" />
            ))}
          </div>
        ) : allQuery.isError ? (
          <EmptyState variant="error" message="Impossible de charger les communiqués." actionLabel="Réessayer" onAction={() => void allQuery.refetch()} />
        ) : allQuery.data && allQuery.data.results.length > 0 ? (
          <>
            {allQuery.data.results.map((a) => (
              <AnnouncementRow key={a.id} announcement={a} onOpen={() => setOpenId(a.id)} />
            ))}
            {allQuery.data.next_offset !== null ? (
              <Button variant="secondary" size="sm" className="mt-2" onClick={() => setLimit((n) => n + PAGE_SIZE)}>
                Voir plus
              </Button>
            ) : null}
          </>
        ) : (
          <EmptyState
            message="Aucun communiqué pour l'instant."
            actionLabel={canManage ? "Publier un communiqué" : undefined}
            onAction={canManage ? () => setPublishOpen(true) : undefined}
          />
        )}
      </section>

      {openId !== null ? <AnnouncementDetailModal announcementId={openId} onClose={() => setOpenId(null)} onChanged={invalidate} /> : null}
      {publishOpen ? (
        <PublishAnnouncementModal
          onClose={() => setPublishOpen(false)}
          onPublished={() => {
            setPublishOpen(false);
            invalidate();
          }}
        />
      ) : null}
    </div>
  );
}
