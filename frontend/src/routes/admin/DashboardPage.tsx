import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { listLicences } from "../../api/licences";
import { EmptyState, Loader } from "../../design-system";

const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;

function KpiTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-surface p-3 shadow-card">
      <p className="text-xs text-text-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-text">{value}</p>
    </div>
  );
}

/**
 * Tableau de bord Superuser (superuser-espace.md §3.1) — **version minimale
 * assumée**, signalée au compte rendu : aucun endpoint d'agrégation dédié
 * n'existe. Les deux indicateurs ci-dessous (« Clubs actifs », « Licences
 * à échéance sous 30 jours ») sont calculés côté client à partir d'un
 * **unique** appel déjà existant (`GET /licences/`), sans en assembler
 * plusieurs. L'indicateur « Anomalies en cours » (5.5) exige un calcul en
 * direct sur le journal d'activité qui n'est pas exposé par l'API : il
 * n'est pas affiché, plutôt que d'inventer une valeur.
 */
export function DashboardPage() {
  const licencesQuery = useQuery({ queryKey: ["licences", ""], queryFn: () => listLicences() });

  const activeClubs = licencesQuery.data?.filter((l) => l.status === "active").length ?? 0;
  const dueSoon = useMemo(() => {
    const now = Date.now();
    return (
      licencesQuery.data?.filter((l) => {
        const end = new Date(l.end_date).getTime();
        return end >= now && end - now <= THIRTY_DAYS_MS;
      }).length ?? 0
    );
  }, [licencesQuery.data]);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-text">Tableau de bord</h1>
        <p className="text-sm text-text-muted">
          Plateforme Vesta · {new Date().toLocaleDateString("fr-FR", { dateStyle: "long" })}
        </p>
      </header>

      {licencesQuery.isLoading ? (
        <Loader loading variant="list" count={3} />
      ) : licencesQuery.isError ? (
        <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void licencesQuery.refetch()} />
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <KpiTile label="Clubs actifs" value={activeClubs} />
          <KpiTile label="Licences à échéance sous 30 jours" value={dueSoon} />
          <div className="rounded-lg bg-surface p-3 shadow-card">
            <p className="text-xs text-text-muted">Anomalies en cours</p>
            <p className="mt-1 text-sm text-text-muted">
              Indisponible : aucun point d'accès de calcul en direct n'existe encore côté API.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
