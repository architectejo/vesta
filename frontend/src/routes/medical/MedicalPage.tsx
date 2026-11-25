import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { getMyProfile, listClubPlayers } from "../../api/clubs";
import {
  listInjuriesToComplete,
  listRecentInjuries,
  listUnfitAndRestricted,
  type FitnessListItem,
  type InjuryListItem,
} from "../../api/medical";
import {
  Avatar,
  Button,
  DataTable,
  EmptyState,
  Loader,
  StatusBadge,
  type DataTableColumn,
} from "../../design-system";
import { canAccessMedicalPage } from "../sport/sportAccess";
import { HealthRecordModal } from "./HealthRecordModal";
import { InjuryDetailModal } from "./InjuryDetailModal";
import { InjuryReportModal } from "./InjuryReportModal";
import { PresidentFitnessModal } from "./PresidentFitnessModal";
import { formatDateFrLong, formatTimeFr, todayIsoDate } from "./medicalFormat";
import { fitnessReturnText, fitnessStatusKey, injuryEventLabel, injuryStatusKey } from "./medicalLabels";

const PAGE_STEP = 5;

function hasRole(profile: { roles: Array<{ role: string }> } | undefined, role: string): boolean {
  return profile?.roles.some((r) => r.role === role) ?? false;
}

/** Page « Médical » (medical.md §3). Route `/medical`. */
export function MedicalPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [reportOpen, setReportOpen] = useState(false);
  const [toCompleteLimit, setToCompleteLimit] = useState(PAGE_STEP);
  const [unfitLimit, setUnfitLimit] = useState(PAGE_STEP);
  const [selectedInjury, setSelectedInjury] = useState<InjuryListItem | null>(null);
  const [selectedRecordMembershipId, setSelectedRecordMembershipId] = useState<number | null>(null);
  const [selectedPresidentTarget, setSelectedPresidentTarget] = useState<FitnessListItem | null>(null);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const isDoctor = hasRole(profileQuery.data, "doctor");
  const isCoach = hasRole(profileQuery.data, "coach") || hasRole(profileQuery.data, "assistant_coach");
  const isPresident = hasRole(profileQuery.data, "president");

  // Le vrai contrôle d'accès vient de l'API (`CanAccessMedicalPage`, mêmes
  // rôles que ce garde) : cette requête sert aussi de sonde d'accès —
  // un 403 affiche l'état vide unique du §3, jamais reconstruit ici.
  const roleAllowed = canAccessMedicalPage(profileQuery.data?.roles);
  const unfitQuery = useQuery({
    queryKey: ["medical", "page", "unfit"],
    queryFn: listUnfitAndRestricted,
    enabled: !profileQuery.isLoading && roleAllowed,
  });

  const toCompleteQuery = useQuery({
    queryKey: ["medical", "page", "to-complete", toCompleteLimit],
    queryFn: () => listInjuriesToComplete({ limit: toCompleteLimit }),
    enabled: isDoctor,
  });

  const recentQuery = useQuery({
    queryKey: ["medical", "page", "recent-injuries"],
    queryFn: listRecentInjuries,
    enabled: isDoctor,
  });

  const rosterQuery = useQuery({
    queryKey: ["clubs", "players", "active"],
    queryFn: () => listClubPlayers({ status: "active" }),
    enabled: isDoctor || isPresident,
  });

  const accessDenied =
    (!profileQuery.isLoading && !profileQuery.isError && !roleAllowed) ||
    (unfitQuery.isError && unfitQuery.error instanceof ApiError && unfitQuery.error.status === 403);

  function invalidateAll(): void {
    void queryClient.invalidateQueries({ queryKey: ["medical"] });
  }

  const rosterFitness = useMemo(() => {
    const map = new Map<number, FitnessListItem>();
    for (const item of unfitQuery.data?.results ?? []) map.set(item.membership_id, item);
    return map;
  }, [unfitQuery.data]);

  // §3.1/§3.4 exigent avatar + nom sur chaque ligne de blessure, mais
  // `serialize_injury_list_item` (backend) ne renvoie que `membership_id`
  // (gap signalé au compte rendu) : nom/photo/numéro recomposés ici à
  // partir de l'effectif actif déjà chargé pour la section « Effectif ».
  // Un joueur parti avant d'avoir été retiré de l'effectif actif resterait
  // sans nom (repli « Joueur n° {id} ») — limite acceptée.
  const playerLookup = useMemo(() => {
    const map = new Map<number, { name: string; photo: string | null; jerseyNumber: number | null }>();
    for (const player of rosterQuery.data ?? []) {
      map.set(player.membership_id, {
        name: `${player.first_name} ${player.last_name}`,
        photo: player.photo,
        jerseyNumber: player.jersey_number,
      });
    }
    return map;
  }, [rosterQuery.data]);

  const effectifRows = useMemo(() => {
    return (rosterQuery.data ?? []).map((player) => {
      const fitness = rosterFitness.get(player.membership_id);
      return {
        membership_id: player.membership_id,
        name: `${player.first_name} ${player.last_name}`,
        photo: player.photo,
        jersey_number: player.jersey_number,
        fitness_status: fitness?.fitness_status ?? ("fit" as const),
        fitness_return_date: fitness?.fitness_return_date ?? null,
        fitness_return_date_label: fitness?.fitness_return_date_label ?? null,
      };
    });
  }, [rosterQuery.data, rosterFitness]);

  if (profileQuery.isLoading || (roleAllowed && unfitQuery.isLoading)) {
    return <Loader loading variant="page" />;
  }

  if (accessDenied) {
    return (
      <EmptyState
        message="Vous n'avez pas accès à cette page."
        actionLabel="Retour à l'accueil"
        onAction={() => navigate("/")}
      />
    );
  }

  const clubName = profileQuery.data?.club.name ?? "";
  const canReportInjury = isDoctor || isCoach;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">Médical</h1>
          <p className="text-sm text-text-muted">
            {clubName} · Situation au {formatDateFrLong(todayIsoDate())}
          </p>
        </div>
        {canReportInjury ? (
          <Button variant="primary" size="sm" onClick={() => setReportOpen(true)}>
            Déclarer une blessure
          </Button>
        ) : null}
      </header>

      {isDoctor ? (
        <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-text">Blessures à compléter</h2>
            <span className="text-xs text-text-muted">{toCompleteQuery.data?.results.length ?? 0}</span>
          </div>
          {toCompleteQuery.isLoading ? (
            <Loader loading variant="list" count={2} />
          ) : toCompleteQuery.isError ? (
            <EmptyState variant="error" message="Impossible de charger cette section." actionLabel="Réessayer" onAction={() => void toCompleteQuery.refetch()} />
          ) : (toCompleteQuery.data?.results.length ?? 0) === 0 ? (
            <EmptyState message="Aucune blessure à compléter." />
          ) : (
            <>
              <ul className="divide-y divide-border">
                {toCompleteQuery.data!.results.map((item) => (
                  <ToCompleteRow
                    key={item.id}
                    item={item}
                    player={playerLookup.get(item.membership_id)}
                    onOpen={() => setSelectedInjury(item)}
                  />
                ))}
              </ul>
              {toCompleteQuery.data!.results.length >= toCompleteLimit && toCompleteQuery.data!.next_offset ? (
                <div className="mt-2 text-center">
                  <Button variant="secondary" size="sm" onClick={() => setToCompleteLimit((l) => l + PAGE_STEP)}>
                    Voir plus
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </section>
      ) : null}

      {isDoctor || isCoach || isPresident ? (
        <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
          <h2 className="mb-3 text-base font-semibold text-text">Inaptes et restrictions</h2>
          {unfitQuery.isError ? (
            <EmptyState variant="error" message="Impossible de charger cette section." actionLabel="Réessayer" onAction={() => void unfitQuery.refetch()} />
          ) : (unfitQuery.data?.results.length ?? 0) === 0 ? (
            <EmptyState message="Tous les joueurs sont aptes." />
          ) : (
            <>
              <ul className="divide-y divide-border">
                {unfitQuery.data!.results.slice(0, unfitLimit).map((item) => (
                  <UnfitRow
                    key={item.membership_id}
                    item={item}
                    role={isDoctor ? "doctor" : isPresident ? "president" : "coach"}
                    onOpen={() => {
                      if (isDoctor) setSelectedRecordMembershipId(item.membership_id);
                      else if (isPresident) setSelectedPresidentTarget(item);
                    }}
                  />
                ))}
              </ul>
              {unfitQuery.data!.results.length > unfitLimit ? (
                <div className="mt-2 text-center">
                  <Button variant="secondary" size="sm" onClick={() => setUnfitLimit((l) => l + 10)}>
                    Voir plus
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </section>
      ) : null}

      {isDoctor || isPresident ? (
        <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
          <h2 className="mb-3 text-base font-semibold text-text">Effectif</h2>
          <EffectifTable
            rows={effectifRows}
            loading={rosterQuery.isLoading}
            role={isDoctor ? "doctor" : "president"}
            onOpenDoctor={(id) => setSelectedRecordMembershipId(id)}
            onOpenPresident={(row) =>
              setSelectedPresidentTarget({
                membership_id: row.membership_id,
                name: row.name,
                jersey_number: row.jersey_number,
                fitness_status: row.fitness_status,
                fitness_return_date: row.fitness_return_date,
                fitness_return_date_label: row.fitness_return_date_label,
              })
            }
          />
          <p className="mt-2 text-xs text-text-muted">
            Les colonnes « Fiche » et « Dossier complet » nécessitent un point d'accès API supplémentaire (encore
            absent) : elles ne sont pas affichées pour l'instant.
          </p>
        </section>
      ) : null}

      {isDoctor ? (
        <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
          <h2 className="mb-3 text-base font-semibold text-text">Dernières blessures</h2>
          {recentQuery.isLoading ? (
            <Loader loading variant="list" count={2} />
          ) : recentQuery.isError ? (
            <EmptyState variant="error" message="Impossible de charger cette section." actionLabel="Réessayer" onAction={() => void recentQuery.refetch()} />
          ) : (recentQuery.data?.results.length ?? 0) === 0 ? (
            <EmptyState
              message="Aucune blessure déclarée."
              actionLabel={canReportInjury ? "Déclarer une blessure" : undefined}
              onAction={canReportInjury ? () => setReportOpen(true) : undefined}
            />
          ) : (
            <ul className="divide-y divide-border">
              {recentQuery.data!.results.map((item) => (
                <ToCompleteRow
                  key={item.id}
                  item={item}
                  player={playerLookup.get(item.membership_id)}
                  onOpen={() => setSelectedInjury(item)}
                />
              ))}
            </ul>
          )}
        </section>
      ) : null}

      <InjuryReportModal
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        onReported={invalidateAll}
      />

      {selectedInjury !== null ? (
        <InjuryDetailModal
          open
          injuryId={selectedInjury.id}
          mode="doctor"
          playerName={playerLookup.get(selectedInjury.membership_id)?.name ?? `Joueur n° ${selectedInjury.membership_id}`}
          onClose={() => setSelectedInjury(null)}
          onChanged={invalidateAll}
        />
      ) : null}

      {selectedRecordMembershipId !== null ? (
        <HealthRecordModal
          open
          membershipId={selectedRecordMembershipId}
          onClose={() => setSelectedRecordMembershipId(null)}
          onChanged={invalidateAll}
        />
      ) : null}

      {selectedPresidentTarget ? (
        <PresidentFitnessModal
          open
          membershipId={selectedPresidentTarget.membership_id}
          playerName={selectedPresidentTarget.name}
          fitnessStatus={selectedPresidentTarget.fitness_status}
          fitnessReturnDate={selectedPresidentTarget.fitness_return_date}
          fitnessReturnDateLabel={selectedPresidentTarget.fitness_return_date_label}
          onClose={() => setSelectedPresidentTarget(null)}
        />
      ) : null}
    </div>
  );
}

function ToCompleteRow({
  item,
  player,
  onOpen,
}: {
  item: InjuryListItem;
  player?: { name: string; photo: string | null };
  onOpen: () => void;
}) {
  const name = player?.name ?? `Joueur n° ${item.membership_id}`;
  return (
    <li>
      <button type="button" onClick={onOpen} className="flex w-full items-center gap-3 py-2 text-left">
        <Avatar name={name} photoUrl={player?.photo} size={40} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-text">{name}</span>
          <span className="block truncate text-xs text-text-muted">
            Déclarée le {formatDateFrLong(item.reported_at)} à {formatTimeFr(item.reported_at)} ·{" "}
            {injuryEventLabel(item)}
          </span>
        </span>
        <StatusBadge status={injuryStatusKey(item)} />
      </button>
    </li>
  );
}

function UnfitRow({
  item,
  role,
  onOpen,
}: {
  item: FitnessListItem;
  role: "doctor" | "coach" | "president";
  onOpen: () => void;
}) {
  const clickable = role !== "coach";
  const content = (
    <>
      <Avatar name={item.name} size={40} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-text">
          {item.name} · n° {item.jersey_number ?? "—"}
        </span>
        <span className="block truncate text-xs text-text-muted">
          {fitnessReturnText({
            fitness_status: item.fitness_status,
            fitness_return_date: item.fitness_return_date,
            fitness_return_date_label: item.fitness_return_date_label,
            showOverdue: role === "doctor",
          })}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-2">
        <StatusBadge status={fitnessStatusKey(item.fitness_status)} />
        {item.badge_injured ? <StatusBadge status="injured" /> : null}
      </span>
    </>
  );
  if (!clickable) {
    return <li className="flex items-center gap-3 py-2">{content}</li>;
  }
  return (
    <li>
      <button type="button" onClick={onOpen} className="flex w-full items-center gap-3 py-2 text-left">
        {content}
      </button>
    </li>
  );
}

interface EffectifRow {
  membership_id: number;
  name: string;
  photo: string | null;
  jersey_number: number | null;
  fitness_status: FitnessListItem["fitness_status"];
  fitness_return_date: string | null;
  fitness_return_date_label: string | null;
}

function EffectifTable({
  rows,
  loading,
  role,
  onOpenDoctor,
  onOpenPresident,
}: {
  rows: EffectifRow[];
  loading: boolean;
  role: "doctor" | "president";
  onOpenDoctor: (membershipId: number) => void;
  onOpenPresident: (row: EffectifRow) => void;
}) {
  const columns: Array<DataTableColumn<EffectifRow>> = [
    {
      key: "player",
      header: "Joueur",
      widthPx: 180,
      render: (row) => (
        <span className="flex items-center gap-2">
          <Avatar name={row.name} photoUrl={row.photo} size={24} />
          <span className="truncate">{row.name}</span>
        </span>
      ),
    },
    { key: "number", header: "N°", render: (row) => row.jersey_number ?? "—" },
    {
      key: "fitness",
      header: "Aptitude",
      render: (row) => <StatusBadge status={fitnessStatusKey(row.fitness_status)} />,
    },
    {
      key: "return",
      header: "Retour prévu",
      render: (row) =>
        fitnessReturnText({
          fitness_status: row.fitness_status,
          fitness_return_date: row.fitness_return_date,
          fitness_return_date_label: row.fitness_return_date_label,
        }) || "—",
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows}
      getRowId={(row) => row.membership_id}
      loading={loading}
      onRowClick={(row) => (role === "doctor" ? onOpenDoctor(row.membership_id) : onOpenPresident(row))}
      getSearchableText={(row) => row.name}
      searchPlaceholder="Rechercher un joueur"
      resultLabel="joueurs"
      stickyFirstColumn
      emptyState={<EmptyState message="Aucun joueur dans le club." />}
    />
  );
}
