import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  listAttendance,
  markAttendance,
  removeAttendance,
  type Assembly,
} from "../../../api/assemblies";
import { useDebouncedValue } from "../../../hooks/useDebouncedValue";
import { Banner, Button, ConfirmDialog, EmptyState, Skeleton, useToast } from "../../../design-system";

type ViewFilter = "all" | "present" | "unchecked";

/** Onglet « Présences » (assemblees-page-ag.md §4.2). Le pointage d'AG ne
 * fait pas partie des actions hors connexion (6.6) : sans réseau, les
 * boutons sont désactivés. */
export function AttendanceTab({ assembly }: { assembly: Assembly }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [filter, setFilter] = useState<ViewFilter>("unchecked");
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, 250);
  const [pendingIds, setPendingIds] = useState<Set<number>>(new Set());
  const [toRemove, setToRemove] = useState<{ membershipId: number; name: string } | null>(null);
  const [removing, setRemoving] = useState(false);
  const online = typeof navigator === "undefined" ? true : navigator.onLine;

  const query = useQuery({
    queryKey: ["assemblies", assembly.id, "attendance", filter, debouncedSearch],
    queryFn: () => listAttendance(assembly.id, { filter, q: debouncedSearch || undefined }),
  });

  function invalidate(): void {
    void queryClient.invalidateQueries({ queryKey: ["assemblies", assembly.id, "attendance"] });
    void queryClient.invalidateQueries({ queryKey: ["assembly", assembly.id] });
    void queryClient.invalidateQueries({ queryKey: ["assemblies"] });
  }

  async function handleMark(membershipId: number, name: string): Promise<void> {
    setPendingIds((s) => new Set(s).add(membershipId));
    try {
      await markAttendance(assembly.id, membershipId);
      invalidate();
    } catch {
      showToast(`La présence de ${name} n'a pas été enregistrée. Réessayez.`);
    } finally {
      setPendingIds((s) => {
        const next = new Set(s);
        next.delete(membershipId);
        return next;
      });
    }
  }

  async function handleRemoveConfirmed(): Promise<void> {
    if (!toRemove) return;
    setRemoving(true);
    try {
      await removeAttendance(assembly.id, toRemove.membershipId);
      invalidate();
      setToRemove(null);
    } catch {
      showToast(`La présence de ${toRemove.name} n'a pas été enregistrée. Réessayez.`);
    } finally {
      setRemoving(false);
    }
  }

  const quorum = assembly.quorum;

  return (
    <div className="space-y-3">
      <Banner variant={quorum.reached ? "success" : "warning"}>
        {quorum.present} présents sur {quorum.total} joueurs actifs ({quorum.percentage} %) · Quorum requis :{" "}
        {quorum.threshold} % — {quorum.reached ? "atteint" : "non atteint"}
      </Banner>

      {!online ? <Banner variant="info">Cette action nécessite une connexion.</Banner> : null}

      <div className="relative">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Nom ou numéro"
          aria-label="Nom ou numéro"
          className="h-control-sm w-full rounded-sm border border-border-strong bg-surface px-3 text-sm text-text placeholder:text-text-muted sm:w-64"
        />
      </div>

      <div role="group" aria-label="Filtre des présences" className="flex flex-wrap gap-1">
        {(
          [
            { value: "all" as const, label: `Tous (${query.data?.counts.all ?? 0})` },
            { value: "unchecked" as const, label: `Non pointés (${query.data?.counts.unchecked ?? 0})` },
            { value: "present" as const, label: `Présents (${query.data?.counts.present ?? 0})` },
          ]
        ).map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={filter === option.value}
            onClick={() => setFilter(option.value)}
            className={[
              "h-control-sm rounded-sm border px-3 text-sm font-medium",
              filter === option.value
                ? "border-primary bg-primary text-on-primary"
                : "border-border-strong bg-surface text-text hover:bg-surface-muted",
            ].join(" ")}
          >
            {option.label}
          </button>
        ))}
      </div>

      {query.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} variant="row" />
          ))}
        </div>
      ) : query.isError ? (
        <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void query.refetch()} />
      ) : query.data && query.data.results.length > 0 ? (
        <ul className="divide-y divide-border">
          {query.data.results.map((row) => {
            const fullName = `${row.first_name} ${row.last_name}`;
            const isPending = pendingIds.has(row.membership_id);
            return (
              <li key={row.membership_id} className="flex min-h-14 items-center justify-between gap-2 py-2">
                <button
                  type="button"
                  className="min-w-0 flex-1 truncate text-left text-sm text-text disabled:opacity-60"
                  disabled={!row.present}
                  onClick={() => row.present && setToRemove({ membershipId: row.membership_id, name: fullName })}
                >
                  {row.jersey_number != null ? `n° ${row.jersey_number} · ` : ""}
                  {fullName}
                </button>
                {row.present ? (
                  <span className="shrink-0 text-xs text-status-success-fg">Présent</span>
                ) : (
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={!online || isPending}
                    loading={isPending}
                    onClick={() => void handleMark(row.membership_id, fullName)}
                  >
                    Présent
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <EmptyState
          message={
            debouncedSearch
              ? `Aucun joueur ne correspond à « ${debouncedSearch} ».`
              : filter === "unchecked"
                ? "Tous les joueurs ont été pointés."
                : filter === "present"
                  ? "Aucun présent pour l'instant."
                  : "Aucun joueur."
          }
        />
      )}

      <ConfirmDialog
        open={toRemove !== null}
        title="Retirer la présence ?"
        description={toRemove ? `${toRemove.name} ne sera plus compté comme présent à cette assemblée.` : undefined}
        confirmLabel="Retirer"
        loading={removing}
        onConfirm={() => void handleRemoveConfirmed()}
        onCancel={() => setToRemove(null)}
      />
    </div>
  );
}
