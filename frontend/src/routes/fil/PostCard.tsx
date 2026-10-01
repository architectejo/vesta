import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deletePost, togglePostLike, type Post } from "../../api/social";
import { Avatar, ConfirmDialog, IconButton, useToast } from "../../design-system";
import { PostImagesGrid } from "./PostImagesGrid";
import { ReportPostModal } from "./ReportPostModal";

const KIND_LABEL: Partial<Record<Post["post_kind"], string>> = {
  auto_result: "Résultat de match",
  auto_transfer: "Transfert",
  auto_new_player: "Nouveau joueur",
};

const LONG_TEXT_THRESHOLD = 320;

function formatDateHeure(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const day = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
  const time = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(date);
  return `${day} · ${time}`;
}

/** Rend le texte d'une publication : retours à la ligne respectés, liens
 * cliquables (nouvel onglet), aucun HTML interprété (A4.3). */
function PostBody({ text, expanded }: { text: string; expanded: boolean }) {
  const parts = text.split(/(https?:\/\/\S+)/g);
  return (
    <p
      className={["whitespace-pre-wrap text-base text-text", expanded ? "" : "line-clamp-6"].join(" ")}
      style={{ overflowWrap: "anywhere" }}
    >
      {parts.map((part, i) =>
        /^https?:\/\//.test(part) ? (
          <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="text-primary-text underline">
            {part}
          </a>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </p>
  );
}

export function PostCard({ post, onOpen, onChanged }: { post: Post; onOpen: () => void; onChanged: () => void }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [menuOpen, setMenuOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const likeMutation = useMutation({
    mutationFn: () => togglePostLike(post.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["social", "posts"] }),
    onError: () => showToast("Votre « J'aime » n'a pas été enregistré."),
  });

  async function handleDelete(): Promise<void> {
    setDeleting(true);
    try {
      await deletePost(post.id);
      showToast("Publication supprimée.");
      onChanged();
    } catch {
      showToast("Connexion impossible. Vérifiez votre réseau et réessayez.");
    } finally {
      setDeleting(false);
      setDeleteOpen(false);
    }
  }

  const fullName = `${post.author.first_name} ${post.author.last_name}`;
  const isAutomatic = post.post_kind !== "manual";
  const displayName = isAutomatic ? post.club_name : fullName;
  const isLong = post.body.length > LONG_TEXT_THRESHOLD;

  return (
    <article className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
      <div className="flex items-start gap-2">
        <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left">
          <div className="flex items-center gap-2">
            <Avatar name={displayName} photoUrl={isAutomatic ? null : post.author.avatar_url} size={40} />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-text">{displayName}</p>
              <p className="text-xs text-text-muted">{formatDateHeure(post.created_at)}</p>
              {isAutomatic ? <p className="text-xs text-text-muted">{KIND_LABEL[post.post_kind]}</p> : null}
            </div>
          </div>
        </button>
        <div className="relative shrink-0">
          <IconButton
            aria-label="Plus d'actions"
            onClick={() => setMenuOpen((v) => !v)}
            icon={
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
                <circle cx="5" cy="12" r="1.5" />
                <circle cx="12" cy="12" r="1.5" />
                <circle cx="19" cy="12" r="1.5" />
              </svg>
            }
          />
          {menuOpen ? (
            <div role="menu" className="absolute right-0 z-10 mt-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated">
              <button
                type="button"
                role="menuitem"
                disabled={post.is_reported_by_me}
                className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted disabled:opacity-60"
                onClick={() => {
                  setMenuOpen(false);
                  setReportOpen(true);
                }}
              >
                {post.is_reported_by_me ? "Signalée" : "Signaler la publication"}
              </button>
              {post.can_delete ? (
                <button
                  type="button"
                  role="menuitem"
                  className="block w-full px-3 py-2 text-left text-sm text-status-danger-fg hover:bg-surface-muted"
                  onClick={() => {
                    setMenuOpen(false);
                    setDeleteOpen(true);
                  }}
                >
                  Supprimer la publication
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <div className="mt-2 flex items-center gap-1 rounded-sm bg-surface-muted px-2 py-1 text-xs text-text-muted">
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.5}>
          {post.visibility === "public" ? (
            <circle cx="12" cy="12" r="9" />
          ) : (
            <>
              <rect x="5" y="11" width="14" height="9" rx="1.5" />
              <path d="M8 11V8a4 4 0 018 0v3" />
            </>
          )}
        </svg>
        <span>{post.visibility === "public" ? "Publique" : "Club"}</span>
      </div>

      {post.body ? (
        <div className="mt-2">
          <PostBody text={post.body} expanded={expanded || !isLong} />
          {isLong && !expanded ? (
            <button type="button" className="mt-1 text-xs font-medium text-primary-text hover:underline" onClick={() => setExpanded(true)}>
              Lire la suite
            </button>
          ) : null}
        </div>
      ) : null}

      {post.images.length > 0 ? (
        <div className="mt-2">
          <PostImagesGrid post={post} />
        </div>
      ) : null}

      <div className="mt-2 flex h-11 items-center gap-4">
        <button
          type="button"
          aria-pressed={post.is_liked_by_me}
          disabled={likeMutation.isPending}
          onClick={() => likeMutation.mutate()}
          className={["flex items-center gap-1 text-sm", post.is_liked_by_me ? "text-primary-text" : "text-text-muted"].join(" ")}
        >
          J'aime{post.like_count > 0 ? ` · ${post.like_count}` : ""}
        </button>
        <button type="button" onClick={onOpen} className="flex items-center gap-1 text-sm text-text-muted">
          Commenter{post.comment_count > 0 ? ` · ${post.comment_count}` : ""}
        </button>
      </div>

      {post.recent_comments.length > 0 ? (
        <div className="mt-1 space-y-1 border-t border-border pt-2">
          {post.recent_comments.map((comment) => (
            <div key={comment.id} className="flex items-start gap-2">
              <Avatar name={`${comment.author.first_name} ${comment.author.last_name}`} photoUrl={comment.author.avatar_url} size={24} />
              <p className="min-w-0 flex-1 text-sm text-text">
                <span className="font-semibold">{comment.author.first_name} {comment.author.last_name}</span>{" "}
                <span className="line-clamp-2">{comment.body}</span>
              </p>
            </div>
          ))}
          {post.comment_count > 2 ? (
            <button type="button" onClick={onOpen} className="text-xs font-medium text-primary-text hover:underline">
              Voir les {post.comment_count} commentaires
            </button>
          ) : null}
        </div>
      ) : null}

      <ReportPostModal open={reportOpen} postId={post.id} onClose={() => setReportOpen(false)} onReported={onChanged} />

      <ConfirmDialog
        open={deleteOpen}
        title="Supprimer cette publication ?"
        description="Elle disparaîtra du fil pour tout le monde, avec ses commentaires et ses « J'aime »."
        confirmLabel="Supprimer"
        loading={deleting}
        onConfirm={() => void handleDelete()}
        onCancel={() => setDeleteOpen(false)}
      />
    </article>
  );
}
