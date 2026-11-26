import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getBoardDashboard, isCardError, type BoardPeriodQuery } from "../../../api/clubBoardDashboard";
import { ApiError } from "../../../api/client";
import { getMyProfile } from "../../../api/clubs";
import {
  Banner,
  Button,
  EmptyState,
  Loader,
  PeriodPicker,
  currentMonth,
  type PeriodValue,
} from "../../../design-system";
import { BoardCardsGrid, type CardEnv, type CardOpenKey } from "./BoardCards";
import { BoardDetailModal } from "./BoardDetailModal";
import { periodKey } from "./format";

const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;
/** Jeton d'URL de la saison courante du club (l'API la résout sans identifiant). */
const CURRENT_SEASON = "courante";
/** Rafraîchissement toutes les 5 minutes tant que l'onglet est actif (fiche §7 ; pas de temps réel, CDC 6.5). */
const REFRESH_MS = 5 * 60_000;

function formatTime(timestamp: number): string {
  return new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(new Date(timestamp));
}

export function BoardDashboardPage() {
  const [params, setParams] = useSearchParams();
  const [openKey, setOpenKey] = useState<CardOpenKey | null>(null);

  const thisMonth = currentMonth();
  const monthParam = params.get("mois");
  const seasonParam = params.get("saison");
  const month = monthParam && MONTH_PATTERN.test(monthParam) ? monthParam : thisMonth;
  const value: PeriodValue =
    seasonParam !== null
      ? { mode: "season", seasonId: seasonParam || CURRENT_SEASON }
      : { mode: "month", month };

  // Rien dans la requête = mois courant du club (décidé par l'API, pas par le navigateur).
  let periodQuery: BoardPeriodQuery | null = null;
  if (value.mode === "season") {
    periodQuery = { mode: "season", seasonId: value.seasonId === CURRENT_SEASON ? null : value.seasonId };
  } else if (month !== thisMonth) {
    periodQuery = { mode: "month", month };
  }

  const query = useQuery({
    queryKey: ["board-dashboard", "cards", periodKey(periodQuery)],
    queryFn: () => getBoardDashboard(periodQuery),
    staleTime: 30_000,
    // Le changement de période (page ou modale) garde l'affichage en place pendant le chargement.
    placeholderData: keepPreviousData,
    refetchInterval: REFRESH_MS,
    refetchOnWindowFocus: true,
  });
  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });

  function changePeriod(next: PeriodValue) {
    const nextParams = new URLSearchParams(params);
    nextParams.delete("mois");
    nextParams.delete("saison");
    if (next.mode === "season") nextParams.set("saison", next.seasonId);
    else if (next.month !== thisMonth) nextParams.set("mois", next.month);
    setParams(nextParams, { replace: true });
  }

  const data = query.data;
  const seasonLabel = data?.period.mode === "season" ? data.period.label.replace(/^Saison\s+/, "") : "en cours";
  // L'API ne fournit pas (encore) la liste des saisons : seule la saison choisie est proposée.
  const seasons = [{ id: value.mode === "season" ? value.seasonId : CURRENT_SEASON, label: seasonLabel }];
  const pickerProps = { value, onChange: changePeriod, seasons };

  if (query.isLoading) return <Loader loading variant="page" />;

  if (query.isError && !data) {
    const forbidden = query.error instanceof ApiError && query.error.status === 403;
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold text-text">Tableau de bord du club</h1>
        {forbidden ? (
          <EmptyState message="Cette page est réservée au Président et au Vice-président." />
        ) : (
          <EmptyState
            variant="error"
            message="Impossible de charger le tableau de bord."
            actionLabel="Réessayer"
            onAction={() => void query.refetch()}
          />
        )}
        <p>
          <Link to="/" className="text-sm font-medium text-primary-text hover:underline">
            Retour à l'accueil
          </Link>
        </p>
      </div>
    );
  }

  if (!data) return null;

  const env: CardEnv = {
    currency: data.currency,
    periodLabel: data.period.label,
    periodMode: data.period.mode,
    onRetry: () => void query.refetch(),
    retrying: query.isFetching,
  };
  const clubName = profileQuery.data?.club.name ?? "";
  // Fiche §3 « Bandeaux » : une dépense non justifiée bloque les libérations
  // (alerte rouge, CDC 4.5.2). Le texte vient de l'API, jamais recomposé ici.
  const expenses = data.expenses_by_category;
  const releaseBlockedReason =
    expenses && !isCardError(expenses) && expenses.release_blocked ? expenses.release_blocked_reason : null;
  const context = [clubName, data.period.label, `Mis à jour à ${formatTime(query.dataUpdatedAt)}`]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="space-y-3">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-text">Tableau de bord du club</h1>
        <p className="text-sm text-text-muted">
          {context} ·{" "}
          <Link to="/" className="font-medium text-primary-text hover:underline">
            Voir l'accueil
          </Link>
        </p>
      </header>

      <div className="sticky top-0 z-10 -mx-3 bg-bg px-3 py-1 sm:-mx-4 sm:px-4 md:static md:mx-0 md:px-0">
        <PeriodPicker {...pickerProps} />
      </div>

      {releaseBlockedReason ? <Banner variant="danger">{releaseBlockedReason}</Banner> : null}

      {query.isError ? (
        <p role="status" className="flex flex-wrap items-center gap-2 text-sm text-status-warning-fg">
          Mise à jour impossible · {formatTime(Date.now())}
          <Button size="sm" variant="secondary" onClick={() => void query.refetch()}>
            Réessayer
          </Button>
        </p>
      ) : null}

      <BoardCardsGrid data={data} env={env} onOpen={setOpenKey} />

      {openKey ? (
        <BoardDetailModal
          cardKey={openKey}
          currency={data.currency}
          periodLabel={data.period.label}
          period={periodQuery}
          picker={pickerProps}
          onClose={() => setOpenKey(null)}
        />
      ) : null}
    </div>
  );
}
