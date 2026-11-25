import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { searchAccounts } from "../../api/auth";
import type { AccountSearchResult } from "../../api/auth";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { Avatar, DataTable, EmptyState } from "../../design-system";
import { UserDetailModal } from "./UserDetailModal";

/**
 * Écran « Utilisateurs » (superuser-espace.md §3.3).
 *
 * Point ouvert signalé au compte rendu : ni « Dernière connexion » ni un
 * filtre « Club » (`ClubSearch`) ne sont câblés — `search_accounts` ne
 * renvoie pas de date de dernière connexion, et il n'existe pas de point
 * d'accès de liste des clubs à faire suggérer par un `ClubSearch` (seule
 * `GET /licences/` en donne indirectement la liste ; ce n'est pas son
 * rôle). La recherche texte (email, prénom, nom) et le filtre « Rôle »
 * sont, eux, pleinement fonctionnels.
 */
export function UsersPage() {
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const debouncedQuery = useDebouncedValue(query, 300);
  const [selected, setSelected] = useState<AccountSearchResult | null>(null);

  const accountsQuery = useQuery({
    queryKey: ["superuser-accounts", debouncedQuery, role],
    queryFn: () => searchAccounts({ query: debouncedQuery, role: role || undefined }),
  });

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-text">Utilisateurs</h1>
      </header>

      {accountsQuery.isError ? (
        <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void accountsQuery.refetch()} />
      ) : (
        <DataTable<AccountSearchResult>
          columns={[
            {
              key: "user",
              header: "Utilisateur",
              widthPx: 200,
              render: (row) => (
                <span className="flex items-center gap-2">
                  <Avatar name={`${row.first_name} ${row.last_name}`} size={24} />
                  {row.first_name} {row.last_name}
                </span>
              ),
            },
            { key: "email", header: "Identifiant", render: (row) => row.email },
            {
              key: "clubs",
              header: "Club",
              render: (row) => row.clubs.map((c) => c.club_name).join(", ") || "—",
            },
            {
              key: "roles",
              header: "Rôles",
              render: (row) => row.clubs.flatMap((c) => c.roles).join(", ") || "—",
            },
            {
              key: "state",
              header: "État",
              render: (row) => (
                <span className={row.is_active ? "text-status-success-fg" : "text-status-danger-fg"}>
                  {row.is_active ? "Actif" : "Désactivé"}
                </span>
              ),
            },
          ]}
          rows={accountsQuery.data ?? []}
          getRowId={(row) => row.id}
          onRowClick={setSelected}
          loading={accountsQuery.isLoading}
          resultLabel="utilisateurs"
          stickyFirstColumn
          filtersSlot={
            <>
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Nom ou email"
                aria-label="Nom ou email"
                className="h-control-sm rounded-sm border border-border-strong bg-surface px-2 text-sm text-text"
              />
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                aria-label="Rôle"
                className="h-control-sm rounded-sm border border-border-strong bg-surface px-2 text-sm text-text"
              >
                <option value="">Tous les rôles</option>
                <option value="president">Président</option>
                <option value="vice_president">Vice-président</option>
                <option value="treasurer">Trésorier</option>
                <option value="coach">Coach</option>
                <option value="assistant_coach">Assistant du Coach</option>
                <option value="captain">Capitaine</option>
                <option value="doctor">Médecin</option>
              </select>
            </>
          }
          emptyState={<EmptyState message="Aucun utilisateur." />}
        />
      )}

      {selected ? <UserDetailModal account={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}
