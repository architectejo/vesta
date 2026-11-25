import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getMyProfile } from "../../api/clubs";
import { useDeepLink } from "../../hooks/useDeepLink";
import {
  getSocialAssistanceRequests,
  getTreasuryCapabilities,
  type SocialAssistanceEventType,
  type SocialAssistanceRequest,
  type SocialAssistanceRequestStatus,
} from "../../api/treasury";
import { Button, DataTable, EmptyState, Loader, StatusBadge, type DataTableColumn } from "../../design-system";
import { AssistanceRequestDetailModal } from "./AssistanceRequestDetailModal";
import { formatAmount, formatDateFr } from "./money";

const CAPABILITIES_QUERY_KEY = ["treasury", "capabilities"] as const;
const TREATED_STATUSES: SocialAssistanceRequestStatus[] = ["approved", "rejected"];
const PAGE_STEP = 20;
const EXPANDED_THRESHOLD = 30;

function eligibilityBadge(request: SocialAssistanceRequest) {
  return request.eligible_at_submission ? (
    <StatusBadge status="assistance_eligible" />
  ) : (
    <StatusBadge
      status="assistance_not_eligible"
      detail={formatAmount(request.amount_to_regularize_at_submission, request.currency)}
    />
  );
}

interface PendingRowProps {
  request: SocialAssistanceRequest;
  onOpen: (id: number) => void;
}

function PendingRow({ request, onOpen }: PendingRowProps) {
  return (
    <button
      type="button"
      onClick={() => onOpen(request.id)}
      className="flex w-full flex-wrap items-center justify-between gap-2 py-3 text-left first:pt-0 last:pb-0"
    >
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-text">{request.player_name}</span>
        <span className="block truncate text-xs text-text-muted">
          {request.event_type_label} · {formatDateFr(request.event_date)} · Reçue le{" "}
          {formatDateFr(request.submitted_at.slice(0, 10))}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-2">
        <span className="tabular-nums text-sm text-text">
          {formatAmount(request.planned_amount, request.currency)}
        </span>
        {eligibilityBadge(request)}
      </span>
    </button>
  );
}

function TreatedRow({ request, onOpen }: PendingRowProps) {
  return (
    <button
      type="button"
      onClick={() => onOpen(request.id)}
      className="flex w-full flex-wrap items-center justify-between gap-2 py-3 text-left first:pt-0 last:pb-0"
    >
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-text">{request.player_name}</span>
        <span className="block truncate text-xs text-text-muted">
          {request.event_type_label} · {formatDateFr(request.event_date)}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-2">
        <span className="tabular-nums text-sm text-text">
          {formatAmount(request.planned_amount, request.currency)}
        </span>
        <StatusBadge status={request.status === "approved" ? "assistance_approved" : "assistance_rejected"} />
      </span>
    </button>
  );
}

const EVENT_FILTER_OPTIONS: Array<{ value: SocialAssistanceEventType; label: string }> = [
  { value: "birth", label: "Naissance" },
  { value: "marriage", label: "Mariage" },
  { value: "death", label: "Décès" },
];

const STATUS_FILTER_OPTIONS: Array<{ value: SocialAssistanceRequestStatus; label: string }> = [
  { value: "submitted", label: "Envoyée" },
  { value: "approved", label: "Approuvée" },
  { value: "rejected", label: "Refusée" },
];

interface AllRequestsTableProps {
  onOpen: (id: number) => void;
}

/** Vue élargie au-delà de 30 demandes (§4.1), même simplification que la
 * page Dépenses : l'ensemble des demandes est récupéré en une fois. */
function AllRequestsTable({ onOpen }: AllRequestsTableProps) {
  const [eventFilter, setEventFilter] = useState<SocialAssistanceEventType | "">("");
  const [statusFilter, setStatusFilter] = useState<SocialAssistanceRequestStatus | "">("");

  const allQuery = useQuery({
    queryKey: ["treasury", "social-assistance-requests", "all"],
    queryFn: () => getSocialAssistanceRequests({ limit: 500 }),
  });

  const rows = useMemo(() => {
    let items = allQuery.data?.results ?? [];
    if (eventFilter) items = items.filter((item) => item.event_type === eventFilter);
    if (statusFilter) items = items.filter((item) => item.status === statusFilter);
    return items;
  }, [allQuery.data, eventFilter, statusFilter]);

  const columns: Array<DataTableColumn<SocialAssistanceRequest>> = [
    { key: "player", header: "Joueur", render: (row) => row.player_name ?? "—" },
    { key: "event", header: "Événement", render: (row) => row.event_type_label },
    { key: "event_date", header: "Date de l'événement", render: (row) => formatDateFr(row.event_date) },
    {
      key: "amount",
      header: "Montant prévu",
      align: "right",
      render: (row) => formatAmount(row.planned_amount, row.currency),
    },
    {
      key: "eligibility",
      header: "Éligibilité",
      render: (row) =>
        row.eligible_at_submission ? (
          <StatusBadge status="assistance_eligible" />
        ) : (
          <StatusBadge status="assistance_not_eligible" />
        ),
    },
    {
      key: "status",
      header: "Statut",
      render: (row) =>
        row.status === "submitted" ? (
          <StatusBadge status="pending" />
        ) : (
          <StatusBadge status={row.status === "approved" ? "assistance_approved" : "assistance_rejected"} />
        ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows}
      getRowId={(row) => row.id}
      loading={allQuery.isLoading}
      onRowClick={(row) => onOpen(row.id)}
      getSearchableText={(row) => row.player_name ?? ""}
      searchPlaceholder="Rechercher un joueur"
      resultLabel="demandes"
      filtersSlot={
        <>
          <label className="text-sm text-text">
            <span className="sr-only">Événement</span>
            <select
              value={eventFilter}
              onChange={(event) => setEventFilter(event.target.value as SocialAssistanceEventType | "")}
              className="h-control-sm rounded-sm border border-border-strong bg-surface px-2 text-sm text-text"
            >
              <option value="">Tous les événements</option>
              {EVENT_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-text">
            <span className="sr-only">Statut</span>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as SocialAssistanceRequestStatus | "")}
              className="h-control-sm rounded-sm border border-border-strong bg-surface px-2 text-sm text-text"
            >
              <option value="">Tous les statuts</option>
              {STATUS_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </>
      }
      emptyState={<EmptyState message="Aucune demande ne correspond à ces filtres." />}
    />
  );
}

/**
 * Écran « Assistance sociale » (fiche
 * `docs/ecrans/tresorerie-depenses-assistance.md` §4 ; CDC 4.5.3). Réservé
 * au traitement des demandes (Président, Vice-président ;
 * `can_process_assistance_requests`) : les joueurs suivent leurs propres
 * demandes depuis « Mon profil ».
 */
export function AssistanceSocialePage() {
  const queryClient = useQueryClient();

  const [pendingLimit, setPendingLimit] = useState(PAGE_STEP);
  const [treatedLimit, setTreatedLimit] = useState(PAGE_STEP);
  const [expandedView, setExpandedView] = useState(false);
  const [detailRequestId, setDetailRequestId] = useState<number | null>(null);

  // Lien depuis une notification de demande d'assistance (`?demande=<id>`).
  useDeepLink("demande", setDetailRequestId);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const capabilitiesQuery = useQuery({ queryKey: CAPABILITIES_QUERY_KEY, queryFn: getTreasuryCapabilities });
  const capabilities = capabilitiesQuery.data?.capabilities;
  const canProcess = capabilities?.can_process_assistance_requests ?? false;

  const pendingQuery = useQuery({
    queryKey: ["treasury", "social-assistance-requests", "pending", pendingLimit],
    queryFn: () => getSocialAssistanceRequests({ status: ["submitted"], limit: pendingLimit }),
    enabled: canProcess,
  });
  const treatedQuery = useQuery({
    queryKey: ["treasury", "social-assistance-requests", "treated", treatedLimit],
    queryFn: () => getSocialAssistanceRequests({ status: TREATED_STATUSES, limit: treatedLimit }),
    enabled: canProcess,
  });

  const totalRequests = (pendingQuery.data?.count ?? 0) + (treatedQuery.data?.count ?? 0);

  function invalidateLists(): void {
    void queryClient.invalidateQueries({ queryKey: ["treasury", "social-assistance-requests"] });
  }

  function handleSeeMore(section: "pending" | "treated"): void {
    if (totalRequests > EXPANDED_THRESHOLD) {
      setExpandedView(true);
      return;
    }
    if (section === "pending") setPendingLimit((l) => l + PAGE_STEP);
    else setTreatedLimit((l) => l + PAGE_STEP);
  }

  if (profileQuery.isLoading || capabilitiesQuery.isLoading) return <Loader loading variant="page" />;
  if (profileQuery.isError || capabilitiesQuery.isError) {
    return (
      <EmptyState
        variant="error"
        actionLabel="Réessayer"
        onAction={() => {
          void profileQuery.refetch();
          void capabilitiesQuery.refetch();
        }}
      />
    );
  }
  if (!canProcess || !capabilities) {
    return (
      <EmptyState
        message="Vous n'avez pas accès à cette page."
        description="Suivez vos propres demandes depuis « Mon profil »."
      />
    );
  }

  const clubName = profileQuery.data?.club.name ?? "";

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-text">Assistance sociale</h1>
        <p className="text-sm text-text-muted">{clubName}</p>
      </header>

      {expandedView ? (
        <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
          <h2 className="mb-3 text-base font-semibold text-text">Toutes les demandes</h2>
          <AllRequestsTable onOpen={setDetailRequestId} />
        </section>
      ) : (
        <>
          <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
            <h2 className="mb-3 text-base font-semibold text-text">À traiter</h2>
            {pendingQuery.isLoading ? (
              <Loader loading variant="list" count={5} />
            ) : pendingQuery.isError ? (
              <EmptyState
                variant="error"
                message="Impossible de charger les demandes d'assistance."
                actionLabel="Réessayer"
                onAction={() => void pendingQuery.refetch()}
              />
            ) : (pendingQuery.data?.results.length ?? 0) === 0 ? (
              <EmptyState message="Aucune demande d'assistance à traiter." />
            ) : (
              <>
                <div className="divide-y divide-border">
                  {pendingQuery.data!.results.map((request) => (
                    <PendingRow key={request.id} request={request} onOpen={setDetailRequestId} />
                  ))}
                </div>
                {pendingQuery.data!.results.length < pendingQuery.data!.count ? (
                  <div className="mt-2 text-center">
                    <Button variant="secondary" size="sm" onClick={() => handleSeeMore("pending")}>
                      Voir plus
                    </Button>
                  </div>
                ) : null}
              </>
            )}
          </section>

          <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
            <h2 className="mb-3 text-base font-semibold text-text">Demandes traitées</h2>
            {treatedQuery.isLoading ? (
              <Loader loading variant="list" count={5} />
            ) : treatedQuery.isError ? (
              <EmptyState
                variant="error"
                message="Impossible de charger les demandes traitées."
                actionLabel="Réessayer"
                onAction={() => void treatedQuery.refetch()}
              />
            ) : (treatedQuery.data?.results.length ?? 0) === 0 ? (
              <EmptyState message="Aucune demande traitée pour l'instant." />
            ) : (
              <>
                <div className="divide-y divide-border">
                  {treatedQuery.data!.results.map((request) => (
                    <TreatedRow key={request.id} request={request} onOpen={setDetailRequestId} />
                  ))}
                </div>
                {treatedQuery.data!.results.length < treatedQuery.data!.count ? (
                  <div className="mt-2 text-center">
                    <Button variant="secondary" size="sm" onClick={() => handleSeeMore("treated")}>
                      Voir plus
                    </Button>
                  </div>
                ) : null}
              </>
            )}
          </section>
        </>
      )}

      <AssistanceRequestDetailModal
        requestId={detailRequestId}
        capabilities={capabilities}
        onClose={() => setDetailRequestId(null)}
        onChanged={invalidateLists}
      />
    </div>
  );
}
