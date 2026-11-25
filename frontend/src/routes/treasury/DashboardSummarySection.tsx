import { useQuery } from "@tanstack/react-query";
import { getDashboardSummary } from "../../api/treasury";
import { EmptyState, Skeleton } from "../../design-system";
import { formatAmount } from "./money";

export const DASHBOARD_SUMMARY_QUERY_KEY = ["treasury", "dashboard-summary"] as const;

interface KpiTileProps {
  label: string;
  value: string;
  help?: string;
  danger?: boolean;
}

function KpiTile({ label, value, help, danger = false }: KpiTileProps) {
  return (
    <div className="rounded-lg bg-surface p-3 shadow-card">
      <p className="text-xs text-text-muted">{label}</p>
      <p className={["mt-1 text-lg font-semibold tabular-nums", danger ? "text-status-danger-fg" : "text-text"].join(" ")}>
        {value}
      </p>
      {help ? <p className="mt-1 text-xs text-text-muted">{help}</p> : null}
    </div>
  );
}

/**
 * Indicateurs du tableau de bord (CDC 4.4.6 ; fiche tresorerie-tableau-de-bord
 * §3.1). Les quatre chiffres sont calculés par l'API : l'interface les met
 * seulement en forme, avec la devise renvoyée par l'API.
 */
export function DashboardSummarySection() {
  const query = useQuery({ queryKey: DASHBOARD_SUMMARY_QUERY_KEY, queryFn: () => getDashboardSummary() });

  if (query.isLoading) {
    return (
      <div role="status" aria-label="Chargement des indicateurs" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="rounded-lg bg-surface p-3 shadow-card">
            <Skeleton variant="kpi" />
          </div>
        ))}
      </div>
    );
  }
  if (query.isError || !query.data) {
    return (
      <EmptyState
        variant="error"
        message="Impossible de charger les indicateurs."
        actionLabel="Réessayer"
        onAction={() => void query.refetch()}
      />
    );
  }

  const summary = query.data;
  const rate = Number(summary.collection_rate);
  const rateLabel = Number.isNaN(rate) ? `${summary.collection_rate} %` : `${Math.round(rate)} %`;
  const debtors = summary.members_in_debt;
  return (
    <section aria-label="Indicateurs" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <KpiTile label="Encaissé du mois" value={formatAmount(summary.collected, summary.currency)} />
      <KpiTile label="Taux de recouvrement" value={rateLabel} />
      <KpiTile
        label="Total des dettes"
        value={formatAmount(summary.total_debts, summary.currency)}
        danger={Number(summary.total_debts) > 0}
        help={debtors > 0 ? `${debtors} joueur${debtors > 1 ? "s" : ""} en dette` : undefined}
      />
      <KpiTile
        label="Caisse disponible"
        value={formatAmount(summary.available_cash, summary.currency)}
        help="Encaissements moins dépenses libérées"
      />
    </section>
  );
}
