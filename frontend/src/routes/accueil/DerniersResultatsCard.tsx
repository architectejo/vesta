import { useQueries, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { getMatch, listMatches, type MatchDetail } from "../../api/sport";
import { Button, EmptyState, Modal, Skeleton } from "../../design-system";

const PAGE_SIZE = 5;

function formatDateShort(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}

type Outcome = "Victoire" | "Nul" | "Défaite";

function outcomeOf(match: MatchDetail): { outcome: Outcome; ourScore: number; theirScore: number } | null {
  if (!match.sheet) return null;
  const ourScore = match.venue === "home" ? match.sheet.score_home : match.sheet.score_away;
  const theirScore = match.venue === "home" ? match.sheet.score_away : match.sheet.score_home;
  const outcome: Outcome = ourScore > theirScore ? "Victoire" : ourScore < theirScore ? "Défaite" : "Nul";
  return { outcome, ourScore, theirScore };
}

const OUTCOME_CLASS: Record<Outcome, string> = {
  Victoire: "text-status-success-fg",
  Nul: "text-text-muted",
  Défaite: "text-status-danger-fg",
};

function MatchResultDetailModal({ matchId, onClose }: { matchId: number; onClose: () => void }) {
  const navigate = useNavigate();
  const query = useQuery({ queryKey: ["sport", "match", matchId], queryFn: () => getMatch(matchId) });
  const match = query.data;
  const result = match ? outcomeOf(match) : null;

  return (
    <Modal
      open
      onClose={onClose}
      title={match ? `Match contre ${match.opponent}` : "Match"}
      subtitle={match ? formatDateLong(match.event_date) : undefined}
      size="sm"
      loading={query.isLoading}
      footer={
        <div className="flex w-full flex-wrap items-center justify-between gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Fermer
          </Button>
          <Button variant="primary" size="sm" onClick={() => navigate(`/matchs/${matchId}`)}>
            Ouvrir le match
          </Button>
        </div>
      }
    >
      {match && result ? (
        <div className="space-y-3 text-sm text-text">
          <p className={`text-lg font-semibold tabular-nums ${OUTCOME_CLASS[result.outcome]}`}>
            {result.outcome} · {result.ourScore}-{result.theirScore}
          </p>
          {match.sheet && match.sheet.goals.length > 0 ? (
            <ul className="space-y-1">
              {match.sheet.goals.map((goal) => (
                <li key={goal.id} className="text-text-muted">
                  {goal.minute !== null ? `${goal.minute}' · ` : ""}
                  {goal.scorer?.name ?? "Buteur inconnu"}
                  {goal.assist ? ` (passe : ${goal.assist.name})` : ""}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : query.isError ? (
        <EmptyState variant="error" message="Impossible de charger ce match." actionLabel="Réessayer" onAction={() => void query.refetch()} />
      ) : null}
    </Modal>
  );
}

function formatDateLong(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(date);
}

/**
 * Carte « Derniers résultats » (club-accueil.md §4 point 7, CDC 3.3).
 *
 * Écart documenté (voir compte rendu) : `listMatches` (triée par date
 * décroissante) ne renvoie pas le score -- seul `getMatch` (détail) le
 * renvoie (`sheet.score_home`/`score_away`). Cette carte récupère donc le
 * détail de chaque match récent (fenêtre élargie à chaque « Voir plus »)
 * et ne garde que ceux déjà joués (`sheet !== null`), sans jamais calculer
 * ni deviner un score : chaque valeur affichée vient de `getMatch`.
 */
export function DerniersResultatsCard() {
  const [displayLimit, setDisplayLimit] = useState(PAGE_SIZE);
  const [openMatchId, setOpenMatchId] = useState<number | null>(null);
  const windowSize = displayLimit + PAGE_SIZE;

  const listQuery = useQuery({
    queryKey: ["accueil", "matches", "window", windowSize],
    queryFn: () => listMatches({ limit: windowSize }),
  });

  const candidateIds = listQuery.data?.results.map((m) => m.id) ?? [];
  const detailResults = useQueries({
    queries: candidateIds.map((id) => ({
      queryKey: ["sport", "match", id],
      queryFn: () => getMatch(id),
      enabled: listQuery.isSuccess,
    })),
  });

  const loadingDetails = detailResults.some((r) => r.isLoading);
  const playedMatches = detailResults
    .map((r) => r.data)
    .filter((m): m is MatchDetail => Boolean(m && m.sheet !== null));

  const visible = playedMatches.slice(0, displayLimit);
  const canSeeMore =
    playedMatches.length > displayLimit || (listQuery.data?.next_offset != null && !loadingDetails);

  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
      <h2 className="text-base font-semibold text-text">Derniers résultats</h2>

      <div className="mt-2">
        {listQuery.isLoading || (loadingDetails && visible.length === 0) ? (
          <div className="space-y-2">
            <Skeleton variant="row" />
            <Skeleton variant="row" />
            <Skeleton variant="row" />
          </div>
        ) : listQuery.isError ? (
          <EmptyState
            variant="error"
            message="Impossible de charger les résultats."
            actionLabel="Réessayer"
            onAction={() => void listQuery.refetch()}
          />
        ) : visible.length === 0 ? (
          <EmptyState message="Aucun match joué pour l'instant." />
        ) : (
          <ul className="divide-y divide-border">
            {visible.map((match) => {
              const result = outcomeOf(match);
              if (!result) return null;
              return (
                <li key={match.id}>
                  <button
                    type="button"
                    onClick={() => setOpenMatchId(match.id)}
                    className="flex min-h-12 w-full items-center justify-between gap-2 py-2 text-left hover:bg-surface-muted"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-text">
                        {formatDateShort(match.event_date)} · vs {match.opponent}
                      </span>
                    </span>
                    <span className={`shrink-0 text-sm font-medium tabular-nums ${OUTCOME_CLASS[result.outcome]}`}>
                      {result.outcome} {result.ourScore}-{result.theirScore}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {canSeeMore ? (
        <Button variant="ghost" size="sm" className="mt-2" onClick={() => setDisplayLimit((n) => n + PAGE_SIZE)}>
          Voir plus
        </Button>
      ) : null}

      {openMatchId !== null ? (
        <MatchResultDetailModal matchId={openMatchId} onClose={() => setOpenMatchId(null)} />
      ) : null}
    </section>
  );
}
