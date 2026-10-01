import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  downloadAnnouncementImage,
  getAnnouncement,
  markAnnouncementRead,
  setAnnouncementPinned,
} from "../../../api/social";
import { AuthenticatedImage, Button, EmptyState, Modal, Skeleton, useToast } from "../../../design-system";
import { ReadReceiptsModal } from "./ReadReceiptsModal";

function formatDateShort(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}

/** Modale « Communiqué » (détail) — club-accueil.md §5.1, précisée par
 * fil-public-communication.md B4. */
export function AnnouncementDetailModal({
  announcementId,
  onClose,
  onChanged,
}: {
  announcementId: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [menuOpen, setMenuOpen] = useState(false);
  const [receiptsOpen, setReceiptsOpen] = useState(false);
  const [markingRead, setMarkingRead] = useState(false);

  const query = useQuery({
    queryKey: ["social", "announcement", announcementId],
    queryFn: () => getAnnouncement(announcementId),
  });
  const announcement = query.data;
  const canManage = announcement?.read_summary !== null && announcement?.read_summary !== undefined;

  function invalidate(): void {
    void queryClient.invalidateQueries({ queryKey: ["social", "announcement", announcementId] });
    onChanged();
  }

  async function handleMarkRead(): Promise<void> {
    setMarkingRead(true);
    try {
      await markAnnouncementRead(announcementId);
      showToast("Lecture confirmée.");
      invalidate();
    } catch {
      showToast("Connexion impossible. Vérifiez votre réseau et réessayez.");
    } finally {
      setMarkingRead(false);
    }
  }

  async function handleTogglePin(): Promise<void> {
    if (!announcement) return;
    const nextPinned = !announcement.pinned;
    try {
      await setAnnouncementPinned(announcementId, nextPinned);
      showToast(
        nextPinned
          ? "Communiqué épinglé en tête de l'accueil."
          : "Communiqué désépinglé. Il n'apparaît plus sur l'accueil.",
      );
      invalidate();
    } catch {
      showToast("Connexion impossible. Vérifiez votre réseau et réessayez.");
    }
  }

  function handleShareWhatsapp(): void {
    if (!announcement) return;
    const link = `${window.location.origin}/club/communiques?id=${announcement.id}`;
    const text = encodeURIComponent(`${announcement.title} — ${link}`);
    window.open(`https://wa.me/?text=${text}`, "_blank", "noopener,noreferrer");
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={announcement?.title ?? "Communiqué"}
      subtitle={
        announcement
          ? `Publié par ${announcement.published_by.first_name} ${announcement.published_by.last_name} le ${formatDateShort(announcement.published_at)}`
          : undefined
      }
      size="md"
      loading={query.isLoading}
      isSubmitting={markingRead}
      footer={
        <div className="flex w-full flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={onClose}>
              Fermer
            </Button>
            {announcement ? (
              <Button variant="secondary" size="sm" onClick={handleShareWhatsapp}>
                Partager sur WhatsApp
              </Button>
            ) : null}
            {announcement && canManage ? (
              <div className="relative">
                <Button variant="secondary" size="sm" onClick={() => setMenuOpen((v) => !v)}>
                  …
                </Button>
                {menuOpen ? (
                  <div role="menu" className="absolute bottom-full right-0 z-10 mb-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated">
                    <button
                      type="button"
                      role="menuitem"
                      className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                      onClick={() => {
                        setMenuOpen(false);
                        void handleTogglePin();
                      }}
                    >
                      {announcement.pinned ? "Désépingler" : "Épingler"}
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                      onClick={() => {
                        setMenuOpen(false);
                        setReceiptsOpen(true);
                      }}
                    >
                      Voir les accusés de lecture
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          {announcement ? (
            !announcement.is_read_by_me ? (
              <Button variant="primary" size="sm" loading={markingRead} loadingLabel="Enregistrement…" onClick={() => void handleMarkRead()}>
                J'ai lu
              </Button>
            ) : (
              <span className="text-xs text-text-muted">Lu le {formatDateShort(announcement.published_at)}</span>
            )
          ) : null}
        </div>
      }
    >
      {query.isError ? (
        <EmptyState variant="error" message="Impossible de charger les communiqués." actionLabel="Réessayer" onAction={() => void query.refetch()} />
      ) : announcement ? (
        <div className="space-y-3">
          <p className="whitespace-pre-wrap text-base text-text">{announcement.body}</p>
          {announcement.images.length > 0 ? (
            <div className="grid grid-cols-2 gap-1">
              {announcement.images.map((image) => (
                <AuthenticatedImage
                  key={image.id}
                  cacheKey={image.id}
                  download={() => downloadAnnouncementImage(image.id)}
                  alt=""
                  className="h-32 w-full rounded-md object-cover"
                />
              ))}
            </div>
          ) : null}
        </div>
      ) : query.isLoading ? (
        <Skeleton variant="card" />
      ) : null}

      {receiptsOpen && announcement ? (
        <ReadReceiptsModal announcementId={announcement.id} title={announcement.title} onClose={() => setReceiptsOpen(false)} />
      ) : null}
    </Modal>
  );
}
