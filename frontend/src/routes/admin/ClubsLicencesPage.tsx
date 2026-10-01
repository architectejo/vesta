import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { listLicences } from "../../api/licences";
import type { Licence } from "../../api/licences";
import { DataTable, EmptyState, StatusBadge } from "../../design-system";
import type { StatusKey } from "../../design-system";
import { ClubDetailModal } from "./ClubDetailModal";

const LICENCE_STATUS_KEY: Record<Licence["status"], StatusKey> = {
  trial: "licence_trial",
  active: "licence_active",
  expired: "licence_expired_grace",
  suspended: "licence_suspended",
  terminated: "licence_terminated",
};

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Tous les statuts" },
  { value: "trial", label: "Essai" },
  { value: "active", label: "Active" },
  { value: "expired", label: "Expirée" },
  { value: "suspended", label: "Suspendue" },
  { value: "terminated", label: "Résiliée" },
];

/**
 * Écran « Clubs et licences » (superuser-espace.md §3.2).
 *
 * Point ouvert signalé au compte rendu : les colonnes « Joueurs » et
 * « Dernière activité » de la spec ne sont pas affichées — absentes de
 * `LicenceSerializer` (voir `ClubDetailModal` pour le détail). L'action
 * d'en-tête « Attribuer une licence » n'est pas proposée non plus : chaque
 * club reçoit déjà sa licence d'essai à sa création
 * (`apps.clubs.club_creation`), il n'existe donc pas de club « sans
 * licence » à qui en attribuer une depuis cette page ; « Activer »/
 * « Prolonger » restent disponibles depuis le détail de chaque club.
 */
export function ClubsLicencesPage() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<Licence | null>(null);

  const licencesQuery = useQuery({
    queryKey: ["licences", status],
    queryFn: () => listLicences({ status: status || undefined }),
  });

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-text">Clubs et licences</h1>
      </header>

      {licencesQuery.isError ? (
        <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void licencesQuery.refetch()} />
      ) : (
        <DataTable<Licence>
          columns={[
            { key: "club", header: "Club", render: (row) => row.club_name, widthPx: 200 },
            { key: "start", header: "Début", render: (row) => row.start_date },
            { key: "end", header: "Fin", render: (row) => row.end_date, sortAccessor: (row) => row.end_date },
            {
              key: "status",
              header: "Statut",
              render: (row) => <StatusBadge status={LICENCE_STATUS_KEY[row.status]} />,
            },
          ]}
          rows={licencesQuery.data ?? []}
          getRowId={(row) => row.id}
          onRowClick={setSelected}
          loading={licencesQuery.isLoading}
          getSearchableText={(row) => row.club_name}
          searchPlaceholder="Rechercher un club"
          resultLabel="clubs"
          stickyFirstColumn
          filtersSlot={
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="h-control-sm rounded-sm border border-border-strong bg-surface px-2 text-sm text-text"
              aria-label="Statut de licence"
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          }
          emptyState={<EmptyState message="Aucun club sur la plateforme." />}
        />
      )}

      {selected ? (
        <ClubDetailModal
          licence={selected}
          onClose={() => setSelected(null)}
          onChanged={() => {
            setSelected(null);
            void queryClient.invalidateQueries({ queryKey: ["licences"] });
          }}
        />
      ) : null}
    </div>
  );
}
