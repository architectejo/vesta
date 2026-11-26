import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { getMyProfile } from "../../api/clubs";
import { createTacticalPlan, deleteTacticalPlan, listTacticalPlans, type TacticalPlanListItem } from "../../api/sport";
import { Button, ConfirmDialog, EmptyState, FORMATION_LABELS, Loader, StatusBadge, useToast } from "../../design-system";
import { useDeepLink } from "../../hooks/useDeepLink";
import { DuplicatePlanModal } from "./DuplicatePlanModal";
import { PlanDetailModal } from "./PlanDetailModal";
import { PlanFormModal } from "./PlanFormModal";
import { getSportAccess } from "./sportAccess";

const PLANS_QUERY_KEY = ["sport", "tactical-plans"] as const;

type PlanFilter = "all" | "published" | "draft";

function PlanRow({ plan, onOpen }: { plan: TacticalPlanListItem; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen} className="flex w-full min-h-14 items-center justify-between gap-3 py-2 text-left">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-text">{plan.name}</p>
        <p className="truncate text-xs text-text-muted">
          {FORMATION_LABELS[plan.formation]} · {plan.squad_size} joueurs ·{" "}
          {plan.match_id ? `Match n° ${plan.match_id}` : "Aucun match rattaché"}
        </p>
      </div>
      <StatusBadge status={plan.is_published ? "plan_published" : "lineup_draft"} />
    </button>
  );
}

/**
 * Onglet « Plans » du Vestiaire (docs/ecrans/sport-plan-tactique.md §3).
 * Coach et Assistant : création, duplication, suppression, édition. Les autres
 * rôles (Capitaine, Président, joueurs) consultent seulement les plans publiés.
 */
export function PlansLibrary() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [filter, setFilter] = useState<PlanFilter>("all");
  const [limit, setLimit] = useState(5);
  const [createOpen, setCreateOpen] = useState(false);
  const [detailPlanId, setDetailPlanId] = useState<number | null>(null);
  const [duplicateTarget, setDuplicateTarget] = useState<{ id: number; name: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; name: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Lien d'une notification « Plan publié » : ouvre le plan en lecture seule.
  useDeepLink("plan", setDetailPlanId);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const access = getSportAccess(profileQuery.data?.roles);

  const plansQuery = useQuery({
    queryKey: [...PLANS_QUERY_KEY, filter, limit],
    queryFn: () => listTacticalPlans({ status: filter === "all" ? undefined : filter, limit }),
  });

  const createMutation = useMutation({
    mutationFn: createTacticalPlan,
    onSuccess: (plan) => {
      void queryClient.invalidateQueries({ queryKey: PLANS_QUERY_KEY });
      setCreateOpen(false);
      showToast("Plan créé.");
      navigate(`/plans/${plan.id}/tableau`);
    },
  });

  async function handleDelete(): Promise<void> {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteTacticalPlan(deleteTarget.id);
      void queryClient.invalidateQueries({ queryKey: PLANS_QUERY_KEY });
      setDeleteTarget(null);
      setDetailPlanId(null);
      showToast("Plan supprimé.");
    } catch (err) {
      showToast(err instanceof ApiError ? err.detail : "Suppression impossible.");
    } finally {
      setDeleting(false);
    }
  }

  if (profileQuery.isLoading) return <Loader loading variant="page" />;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-text">Plans tactiques</h2>
          <p className="text-sm text-text-muted">
            {profileQuery.data?.club.name} · Saison {new Date().getFullYear()}
          </p>
        </div>
        {access.isCoach ? (
          <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
            Nouveau plan
          </Button>
        ) : null}
      </header>

      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        {access.isCoach ? (
          <div className="mb-3 flex gap-1">
            {(["all", "published", "draft"] as PlanFilter[]).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={filter === value}
                onClick={() => {
                  setFilter(value);
                  setLimit(5);
                }}
                className={[
                  "h-control-sm rounded-full border px-3 text-xs font-medium",
                  filter === value ? "border-primary bg-primary text-on-primary" : "border-border-strong bg-surface text-text",
                ].join(" ")}
              >
                {value === "all" ? "Tous" : value === "published" ? "Publiés" : "Brouillons"}
              </button>
            ))}
          </div>
        ) : null}

        {plansQuery.isLoading ? (
          <Loader loading variant="list" count={3} />
        ) : plansQuery.isError ? (
          <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void plansQuery.refetch()} />
        ) : (plansQuery.data?.results.length ?? 0) === 0 ? (
          <EmptyState
            message={access.isCoach ? "Aucun plan tactique pour l'instant." : "Aucun plan publié pour l'instant."}
            actionLabel={access.isCoach ? "Nouveau plan" : undefined}
            onAction={access.isCoach ? () => setCreateOpen(true) : undefined}
          />
        ) : (
          <>
            <div className="divide-y divide-border">
              {plansQuery.data!.results.map((plan) => (
                <PlanRow key={plan.id} plan={plan} onOpen={() => setDetailPlanId(plan.id)} />
              ))}
            </div>
            {plansQuery.data!.next_offset != null ? (
              <Button variant="ghost" size="sm" className="mt-2" onClick={() => setLimit((l) => l + 5)}>
                Voir plus
              </Button>
            ) : null}
          </>
        )}
      </section>

      <PlanFormModal
        open={createOpen}
        mode="create"
        onClose={() => setCreateOpen(false)}
        onSubmit={(input) => createMutation.mutateAsync(input).then(() => undefined)}
      />

      <PlanDetailModal
        open={detailPlanId !== null}
        planId={detailPlanId}
        isCoach={access.isCoach}
        ownMembershipId={profileQuery.data?.membership_id}
        onClose={() => setDetailPlanId(null)}
        onDuplicate={(plan) => setDuplicateTarget(plan)}
        onDelete={(plan) => setDeleteTarget(plan)}
      />

      <DuplicatePlanModal
        open={duplicateTarget !== null}
        planId={duplicateTarget?.id ?? null}
        planName={duplicateTarget?.name ?? ""}
        onClose={() => setDuplicateTarget(null)}
        onDuplicated={(newPlanId, skippedCount) => {
          setDuplicateTarget(null);
          setDetailPlanId(null);
          void queryClient.invalidateQueries({ queryKey: PLANS_QUERY_KEY });
          showToast(
            skippedCount > 0
              ? `Plan dupliqué. ${skippedCount} joueur(s) indisponible(s) n'ont pas été recopiés.`
              : "Plan dupliqué.",
          );
          navigate(`/plans/${newPlanId}/tableau`);
        }}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title={`Supprimer le plan « ${deleteTarget?.name ?? ""} » ?`}
        description="Il ne sera plus visible par les joueurs et ne pourra pas être récupéré."
        confirmLabel="Supprimer"
        loading={deleting}
        onConfirm={() => void handleDelete()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
