import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  addComment,
  deleteComment,
  deletePost,
  getPost,
  listComments,
  togglePostLike,
} from "../../api/social";
import { ApiError } from "../../api/client";
import {
  Avatar,
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  IconDelete,
  IconMore,
  Modal,
  Skeleton,
  TextArea,
  useToast,
} from "../../design-system";
import { useClosingState } from "../../hooks/useClosingState";
import { PostImagesGrid } from "./PostImagesGrid";
import { ReportPostModal } from "./ReportPostModal";

const COMMENT_PAGE_SIZE = 10;
const MAX_COMMENT = 1000;

function formatDateHeure(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const day = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
  const time = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(date);
  return `${day} · ${time}`;
}

/** Modale « Publication » (détail et commentaires) — A5.2. */
export function PostDetailModal({
  postId,
  onClose,
  onChanged,
}: {
  postId: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [menuOpen, setMenuOpen] = useState(false);
  const { mounted: menuMounted, dataState: menuDataState, onAnimationEnd: onMenuAnimationEnd } =
    useClosingState(menuOpen, 200);
  const [reportOpen, setReportOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteCommentId, setDeleteCommentId] = useState<number | null>(null);
  const [deletingComment, setDeletingComment] = useState(false);
  const [commentBody, setCommentBody] = useState("");
  const [commentLimit, setCommentLimit] = useState(COMMENT_PAGE_SIZE);
  const [commentError, setCommentError] = useState<string | null>(null);
  const [sendingComment, setSendingComment] = useState(false);

  const postQuery = useQuery({
    queryKey: ["social", "post", postId],
    queryFn: () => getPost(postId),
  });

  const commentsQuery = useQuery({
    queryKey: ["social", "post", postId, "comments", commentLimit],
    queryFn: () => listComments(postId, { limit: commentLimit }),
    enabled: Boolean(postQuery.data),
    refetchInterval: () => (document.visibilityState === "hidden" ? false : 30_000),
  });

  const isNotFound = postQuery.error instanceof ApiError && postQuery.error.status === 404;

  const likeMutation = useMutation({
    mutationFn: () => togglePostLike(postId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["social", "post", postId] });
      onChanged();
    },
    onError: () => showToast("Votre « J'aime » n'a pas été enregistré."),
  });

  async function handleDelete(): Promise<void> {
    setDeleting(true);
    try {
      await deletePost(postId);
      showToast("Publication supprimée.");
      onChanged();
      onClose();
    } catch {
      showToast("Connexion impossible. Vérifiez votre réseau et réessayez.");
    } finally {
      setDeleting(false);
    }
  }

  async function handleSendComment(): Promise<void> {
    if (!commentBody.trim()) return;
    setCommentError(null);
    setSendingComment(true);
    try {
      await addComment(postId, commentBody.trim());
      setCommentBody("");
      // Le fil (compteur « Commenter », derniers commentaires de la carte)
      // doit refléter le nouveau commentaire dès la fermeture de la modale.
      onChanged();
      await queryClient.invalidateQueries({ queryKey: ["social", "post", postId] });
      await queryClient.invalidateQueries({ queryKey: ["social", "post", postId, "comments"] });
    } catch {
      setCommentError("Non envoyé");
    } finally {
      setSendingComment(false);
    }
  }

  async function handleDeleteComment(commentId: number): Promise<void> {
    setDeletingComment(true);
    try {
      await deleteComment(commentId);
      showToast("Commentaire supprimé.");
      onChanged();
      await queryClient.invalidateQueries({ queryKey: ["social", "post", postId] });
      await queryClient.invalidateQueries({ queryKey: ["social", "post", postId, "comments"] });
      setDeleteCommentId(null);
    } catch {
      showToast("Connexion impossible. Vérifiez votre réseau et réessayez.");
    } finally {
      setDeletingComment(false);
    }
  }

  const post = postQuery.data;

  return (
    <Modal
      open
      onClose={onClose}
      title={post ? (post.post_kind !== "manual" ? `Publication de ${post.club_name}` : `Publication de ${post.author.first_name} ${post.author.last_name}`) : "Publication"}
      subtitle={post ? `${formatDateHeure(post.created_at)} · ${post.visibility === "public" ? "Publique" : "Club"}` : undefined}
      size="md"
      loading={postQuery.isLoading}
      hideFooter
    >
      {postQuery.isError ? (
        isNotFound ? (
          <EmptyState message="Cette publication n'existe plus." actionLabel="Fermer" onAction={onClose} />
        ) : (
          <EmptyState variant="error" message="Impossible de charger la publication." actionLabel="Réessayer" onAction={() => void postQuery.refetch()} />
        )
      ) : post ? (
        <div className="flex h-full flex-col">
          <div className="flex-1 space-y-3 overflow-y-auto">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <Avatar name={`${post.author.first_name} ${post.author.last_name}`} photoUrl={post.author.avatar_url} size={40} />
              </div>
              <div className="relative">
                <IconButton
                  onClick={() => setMenuOpen((v) => !v)}
                  aria-label="Plus d'actions"
                  icon={<IconMore aria-hidden="true" className="h-5 w-5" />}
                />
                {menuMounted ? (
                  <div
                    role="menu"
                    data-state={menuDataState}
                    onAnimationEnd={onMenuAnimationEnd}
                    className="vesta-anim-menu absolute right-0 z-10 mt-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated"
                  >
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

            {post.body ? <p className="whitespace-pre-wrap text-base text-text" style={{ overflowWrap: "anywhere" }}>{post.body}</p> : null}
            <PostImagesGrid post={post} />

            <div className="flex h-11 items-center gap-4 border-t border-b border-border">
              <button
                type="button"
                aria-pressed={post.is_liked_by_me}
                onClick={() => likeMutation.mutate()}
                className={["flex min-h-control-sm items-center gap-1 text-sm", post.is_liked_by_me ? "text-primary-text" : "text-text-muted"].join(" ")}
              >
                J'aime{post.like_count > 0 ? ` · ${post.like_count}` : ""}
              </button>
              <span className="text-sm text-text-muted">Commenter{post.comment_count > 0 ? ` · ${post.comment_count}` : ""}</span>
            </div>

            <div>
              <p className="mb-2 text-sm font-semibold text-text">Commentaires ({post.comment_count})</p>
              {commentsQuery.isLoading ? (
                <Skeleton variant="row" />
              ) : commentsQuery.data && commentsQuery.data.results.length > 0 ? (
                <div className="space-y-2">
                  {commentsQuery.data.next_offset !== null ? (
                    <button
                      type="button"
                      className="inline-flex min-h-control-sm items-center text-xs font-medium text-primary-text hover:underline"
                      onClick={() => setCommentLimit((n) => n + COMMENT_PAGE_SIZE)}
                    >
                      Commentaires précédents
                    </button>
                  ) : null}
                  {commentsQuery.data.results.map((comment) => (
                    <div key={comment.id} className="flex items-start gap-2">
                      <Avatar name={`${comment.author.first_name} ${comment.author.last_name}`} photoUrl={comment.author.avatar_url} size={32} />
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] font-semibold text-text">{comment.author.first_name} {comment.author.last_name}</p>
                        <p className="text-sm text-text">{comment.body}</p>
                        <p className="text-[13px] text-text-muted">{formatDateHeure(comment.created_at)}</p>
                      </div>
                      <IconButton
                        aria-label="Supprimer le commentaire"
                        className="shrink-0 text-text-muted hover:text-status-danger-fg"
                        icon={<IconDelete aria-hidden="true" className="h-4 w-4" />}
                        onClick={() => setDeleteCommentId(comment.id)}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState message="Aucun commentaire. Soyez le premier à réagir." />
              )}
            </div>
          </div>

          <div className="sticky -bottom-4 z-[5] -mx-4 -mb-4 mt-3 flex items-end gap-2 border-t border-border bg-surface px-4 py-3">
            <div className="flex-1">
              <TextArea
                label="Écrire un commentaire…"
                value={commentBody}
                onChange={(v) => setCommentBody(v.slice(0, MAX_COMMENT))}
                rows={1}
                maxLength={MAX_COMMENT}
                showCount={commentBody.length > 900}
                containerClassName="sr-only-label"
              />
              {commentError ? <p className="text-xs text-status-danger-fg">{commentError}</p> : null}
            </div>
            <Button
              variant="primary"
              size="md"
              disabled={!commentBody.trim()}
              loading={sendingComment}
              onClick={() => void handleSendComment()}
            >
              Envoyer
            </Button>
          </div>
        </div>
      ) : null}

      {post ? (
        <>
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
          <ConfirmDialog
            open={deleteCommentId !== null}
            title="Supprimer ce commentaire ?"
            confirmLabel="Supprimer"
            loading={deletingComment}
            onConfirm={() => {
              if (deleteCommentId !== null) void handleDeleteComment(deleteCommentId);
            }}
            onCancel={() => setDeleteCommentId(null)}
          />
        </>
      ) : null}
    </Modal>
  );
}
