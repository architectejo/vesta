import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../../api/client";
import {
  archivePerformanceTest,
  getPerformanceLeaderboard,
  type LeaderboardPeriod,
  type LeaderboardRow,
  type PerformanceTest,
} from "../../../api/performance";
import {
  Avatar,
  BarChart,
  Button,
  ConfirmDialog,
  DataTable,
  EmptyState,
  Loader,
  Modal,
  SegmentedControl,
  useToast,
  type DataTableColumn,
} from "../../../design-system";
import { EvolutionModal } from "./EvolutionModal";
import { chartValue, formatLocalDate } from "./performanceFormat";
import { TestFormModal } from "./TestFormModal";

export interface LeaderboardModalProps {
  open: boolean;
  onClose: () => void;
  test: PerformanceTest;
  canManage: boolean;
}

/** « Classement : {test} » (C6.5) : dernière séance ou saison, évolution d'un joueur au clic. */
export function LeaderboardModal({ open, onClose, test, canManage }: LeaderboardModalProps) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState<LeaderboardPeriod>("last");
  const [chartOpen, setChartOpen] = useState(false);
  const [player, setPlayer] = useState<LeaderboardRow["player"] | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["sport", "performance", "leaderboard", test.id, period],
    queryFn: () => getPerformanceLeaderboard(test.id, period),
    enabled: open,
  });
  const rows = query.data?.results ?? [];
  const current = query.data?.test ?? test;

  const archive = useMutation({
    mutationFn: () => archivePerformanceTest(test.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["sport", "performance"] });
      showToast("Test archivé.");
      setArchiveOpen(false);
      onClose();
    },
    onError: (error) => setArchiveError(error instanceof ApiError ? error.detail : "Le test n'a pas pu être archivé. Réessayez."),
  });

  const columns: Array<DataTableColumn<LeaderboardRow>> = [
    { key: "rank", header: "Rang", widthPx: 56, sortAccessor: (row) => row.rank, render: (row) => row.rank },
    {
      key: "player",
      header: "Joueur",
      sortAccessor: (row) => row.player.name.toLowerCase(),
      render: (row) => (
        <span className="flex items-center gap-2">
          <Avatar name={row.player.name} photoUrl={row.player.photo} size={24} />
          <span className="break-words">{row.player.name}</span>
        </span>
      ),
    },
    { key: "best", header: "Meilleur résultat", render: (row) => <strong>{row.display}</strong> },
    {
      key: "derived",
      header: "Détail",
      render: (row) => row.derived.speed_display ?? row.derived.success_rate_display ?? "—",
    },
    { key: "date", header: "Date", sortAccessor: (row) => row.date, render: (row) => formatLocalDate(row.date) },
    { key: "count", header: "Mesures", sortAccessor: (row) => row.measures_count, render: (row) => row.measures_count },
    { key: "trend", header: "Tendance", render: (row) => row.trend?.text ?? "—" },
  ];

  const top = rows.slice(0, 10);

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={`Classement : ${current.name}`}
      subtitle={current.kind_text}
      footer={
        <>
          {canManage ? (
            <>
              <Button variant="ghost" onClick={() => setEditOpen(true)}>
                Modifier le test
              </Button>
              <Button variant="ghost" onClick={() => setArchiveOpen(true)}>
                Archiver le test
              </Button>
            </>
          ) : null}
          <Button variant="secondary" onClick={onClose}>
            Fermer
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <SegmentedControl<LeaderboardPeriod>
          label="Période"
          hideLabel
          value={period}
          onChange={setPeriod}
          options={[
            { value: "last", label: "Dernière séance" },
            { value: "season", label: "Saison" },
          ]}
        />
        {query.isLoading ? (
          <Loader loading variant="list" count={5} />
        ) : query.isError ? (
          <EmptyState
            variant="error"
            message={
              query.error instanceof ApiError && query.error.status === 403
                ? "Vous n'avez pas accès à ce classement."
                : "Impossible de charger le classement."
            }
            actionLabel="Réessayer"
            onAction={() => void query.refetch()}
          />
        ) : rows.length === 0 ? (
          <EmptyState message="Aucune mesure pour ce test sur cette période." />
        ) : (
          <>
            <div>
              <Button size="sm" variant="ghost" aria-expanded={chartOpen} onClick={() => setChartOpen((value) => !value)}>
                {chartOpen ? "Masquer le graphique" : "Voir le graphique"}
              </Button>
              {chartOpen ? (
                <BarChart
                  title="Les 10 premiers"
                  orientation="horizontal"
                  categories={top.map((row) => row.player.name)}
                  series={[
                    {
                      name: current.name,
                      values: top.map((row) => chartValue(current.kind, row) ?? 0),
                    },
                  ]}
                  formatValue={(value) => String(value).replace(".", ",")}
                />
              ) : null}
            </div>
            <DataTable
              columns={columns}
              rows={rows}
              getRowId={(row) => row.player.membership_id}
              onRowClick={(row) => setPlayer(row.player)}
              getSearchableText={(row) => `${row.player.name} ${row.player.jersey_number ?? ""}`}
              searchPlaceholder="Nom ou numéro"
              resultLabel="joueurs"
              pageSize={30}
            />
          </>
        )}
      </div>

      <EvolutionModal
        open={player !== null}
        level={2}
        onClose={() => setPlayer(null)}
        testId={test.id}
        testName={current.name}
        membershipId={player?.membership_id}
        playerName={player?.name}
      />
      <TestFormModal open={editOpen} level={2} test={current} onClose={() => setEditOpen(false)} />
      <ConfirmDialog
        open={archiveOpen}
        title={`Archiver le test « ${current.name} » ?`}
        description="Ses résultats restent consultables, mais il ne sera plus proposé pour de nouvelles mesures."
        confirmLabel="Archiver"
        loading={archive.isPending}
        loadingLabel="Archivage…"
        error={archiveError ?? undefined}
        onConfirm={() => {
          setArchiveError(null);
          archive.mutate();
        }}
        onCancel={() => {
          setArchiveOpen(false);
          setArchiveError(null);
        }}
      />
    </Modal>
  );
}
