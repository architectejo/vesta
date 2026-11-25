import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { listPosts, type PostScope } from "../../api/social";
import { useDeepLink } from "../../hooks/useDeepLink";
import { Button, EmptyState, SegmentedControl, Skeleton, useClubBranding } from "../../design-system";
import { NewPostModal } from "./NewPostModal";
import { PostCard } from "./PostCard";
import { PostDetailModal } from "./PostDetailModal";

const PAGE_SIZE = 10;

/** Page « Fil d'actualité » (fil-public-communication.md, PARTIE A). */
export function FilPage() {
  const branding = useClubBranding();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const scope: PostScope = searchParams.get("portee") === "tous" ? "tous" : "mon_club";
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [newPostOpen, setNewPostOpen] = useState(false);
  const [openPostId, setOpenPostId] = useState<number | null>(null);
  useDeepLink("publication", setOpenPostId);

  const query = useQuery({
    queryKey: ["social", "posts", scope, limit],
    queryFn: () => listPosts({ portee: scope, limit }),
    refetchInterval: () => (document.visibilityState === "hidden" ? false : 30_000),
  });

  function setScope(next: PostScope): void {
    setLimit(PAGE_SIZE);
    const params = new URLSearchParams(searchParams);
    if (next === "tous") params.set("portee", "tous");
    else params.delete("portee");
    setSearchParams(params, { replace: false });
  }

  function invalidate(): void {
    void queryClient.invalidateQueries({ queryKey: ["social", "posts"] });
  }

  return (
    <div className="mx-auto max-w-[640px] space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-text">Fil d'actualité</h1>
          <p className="text-sm text-text-muted">{branding?.name ?? ""} · Actualités du club et des autres clubs</p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setNewPostOpen(true)}>
          Publier
        </Button>
      </header>

      <SegmentedControl
        label="Portée"
        value={scope}
        onChange={setScope}
        options={[
          { value: "mon_club", label: "Mon club" },
          { value: "tous", label: "Tous les clubs" },
        ]}
      />

      {query.isLoading ? (
        <div className="space-y-4">
          <Skeleton variant="card" />
          <Skeleton variant="card" />
          <Skeleton variant="card" />
        </div>
      ) : query.isError ? (
        <EmptyState variant="error" message="Impossible de charger le fil." actionLabel="Réessayer" onAction={() => void query.refetch()} />
      ) : query.data && query.data.results.length > 0 ? (
        <>
          <div className="space-y-4">
            {query.data.results.map((post) => (
              <PostCard key={post.id} post={post} onOpen={() => setOpenPostId(post.id)} onChanged={invalidate} />
            ))}
          </div>
          {query.data.next_offset !== null ? (
            <Button
              variant="secondary"
              size="sm"
              loading={query.isFetching}
              loadingLabel="Chargement…"
              onClick={() => setLimit((n) => n + PAGE_SIZE)}
            >
              Voir plus
            </Button>
          ) : null}
        </>
      ) : (
        <EmptyState
          message={scope === "mon_club" ? "Aucune publication pour l'instant." : "Aucune publication publique pour l'instant."}
          actionLabel="Publier"
          onAction={() => setNewPostOpen(true)}
        />
      )}

      {newPostOpen ? (
        <NewPostModal
          onClose={() => setNewPostOpen(false)}
          onCreated={() => {
            setNewPostOpen(false);
            invalidate();
          }}
        />
      ) : null}

      {openPostId !== null ? (
        <PostDetailModal postId={openPostId} onClose={() => setOpenPostId(null)} onChanged={invalidate} />
      ) : null}
    </div>
  );
}
