import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getSocialAssistanceRequests, type SocialAssistanceRequest } from "../../api/treasury";
import { Button, EmptyState, Skeleton, StatusBadge } from "../../design-system";
import { formatAmount, formatDateFr } from "../treasury/money";
import { AssistanceScalesModal } from "./AssistanceScalesModal";
import { MyAssistanceRequestModal } from "./MyAssistanceRequestModal";
import { RequestAssistanceModal } from "./RequestAssistanceModal";

const PAGE_SIZE = 5;
const MY_REQUESTS_KEY = ["treasury", "social-assistance-requests", "mine"] as const;

function requestStatusKey(request: SocialAssistanceRequest) {
  if (request.status === "submitted") return "pending" as const;
  if (request.status === "approved") return "assistance_approved" as const;
  if (request.status === "rejected") return "assistance_rejected" as const;
  return request.eligible_at_submission ? ("assistance_eligible" as const) : ("assistance_not_eligible" as const);
}

/**
 * Carte « Assistance sociale » de « Mon profil » (comptes-mon-profil.md §3
 * point 3 ; CDC 4.5.3, 3.3) : 5 dernières demandes du joueur, « Voir plus »,
 * clic = modale de détail, « Demander une assistance », barèmes en lecture.
 */
export function AssistanceCard() {
  const queryClient = useQueryClient();
  const [requestOpen, setRequestOpen] = useState(false);
  const [scalesOpen, setScalesOpen] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);

  const query = useInfiniteQuery({
    queryKey: MY_REQUESTS_KEY,
    queryFn: ({ pageParam }) => getSocialAssistanceRequests({ mine: true, limit: PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
  });
  const items = query.data?.pages.flatMap((page) => page.results) ?? [];

  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4" aria-label="Assistance sociale">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-text">Assistance sociale</h2>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setScalesOpen(true)}>
            Voir les barèmes
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setRequestOpen(true)}>
            Demander une assistance
          </Button>
        </div>
      </div>

      {query.isLoading ? (
        <div role="status" aria-label="Chargement des demandes" className="mt-2 space-y-3">
          {[0, 1].map((index) => (
            <Skeleton key={index} variant="row" />
          ))}
        </div>
      ) : query.isError ? (
        <EmptyState
          variant="error"
          message="Impossible de charger vos demandes d'assistance."
          actionLabel="Réessayer"
          onAction={() => void query.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState message="Aucune demande d'assistance." />
      ) : (
        <>
          <ul className="mt-2 divide-y divide-border">
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => setDetailId(item.id)}
                  className="flex w-full items-center gap-2 py-2 text-left"
                  aria-label={`Demande d'assistance : ${item.event_type_label}, ${formatDateFr(item.event_date)}`}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-text">{item.event_type_label}</span>
                    <span className="block text-xs text-text-muted">{formatDateFr(item.event_date)}</span>
                  </span>
                  <span className="text-sm tabular-nums text-text">{formatAmount(item.planned_amount, item.currency)}</span>
                  <StatusBadge status={requestStatusKey(item)} />
                </button>
              </li>
            ))}
          </ul>
          {query.hasNextPage ? (
            <div className="pt-2 text-center">
              <Button
                variant="ghost"
                size="sm"
                loading={query.isFetchingNextPage}
                loadingLabel="Chargement…"
                onClick={() => void query.fetchNextPage()}
              >
                Voir plus
              </Button>
            </div>
          ) : null}
        </>
      )}

      <RequestAssistanceModal
        open={requestOpen}
        onClose={() => setRequestOpen(false)}
        onSubmitted={() => void queryClient.invalidateQueries({ queryKey: MY_REQUESTS_KEY })}
      />
      <AssistanceScalesModal open={scalesOpen} onClose={() => setScalesOpen(false)} />
      <MyAssistanceRequestModal requestId={detailId} onClose={() => setDetailId(null)} />
    </section>
  );
}
