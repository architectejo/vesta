import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import {
  getClubIdentity,
  getMyProfile,
  listClubPlayers,
  listRoles,
  revokeRole,
  toPlayerSearchResult,
} from "../../api/clubs";
import type {
  ClubPlayerListItem,
  ClubPlayerMembershipStatus,
  ClubPlayerPosition,
  MembershipRole,
} from "../../api/clubs";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import {
  Avatar,
  Button,
  ConfirmDialog,
  DataTable,
  EmptyState,
  IconUpload,
  Loader,
  StatusBadge,
  useToast,
} from "../../design-system";
import type { FilterChip } from "../../design-system";
import { AssistantCoachSection } from "./AssistantCoachSection";
import { AddPlayerModal } from "./AddPlayerModal";
import { MembershipFollowUpCard } from "./adhesion/MembershipFollowUpCard";
import { ClubIdentityModal } from "./ClubIdentityModal";
import { ImportPlayersModal } from "./ImportPlayersModal";
import { MEMBERSHIP_STATUS_KEY, PlayerCardModal } from "./PlayerCardModal";
import { PresidencyHandoverModal } from "./PresidencyHandoverModal";
import { RecruitersModal } from "./RecruitersModal";
import { RoleModal } from "./RoleModal";

const POSITION_FILTER_OPTIONS: Array<{ value: ClubPlayerPosition | ""; label: string }> = [
  { value: "", label: "Tous les postes" },
  { value: "goalkeeper", label: "Gardien" },
  { value: "defender", label: "Défenseur" },
  { value: "midfielder", label: "Milieu" },
  { value: "forward", label: "Attaquant" },
];

const STATUS_FILTER_OPTIONS: Array<{ value: ClubPlayerMembershipStatus | ""; label: string }> = [
  { value: "", label: "Tous les statuts" },
  { value: "pending", label: "En attente" },
  { value: "active", label: "Inscrit" },
  { value: "departed", label: "Parti" },
];

const ROLE_FILTER_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Tous les rôles" },
  { value: "president", label: "Président" },
  { value: "vice_president", label: "Vice-président" },
  { value: "secretary", label: "Secrétaire" },
  { value: "sports_director", label: "Directeur sportif" },
  { value: "treasurer", label: "Trésorier" },
  { value: "assistant_treasurer", label: "Trésorier adjoint" },
  { value: "steward", label: "Intendant" },
  { value: "coach", label: "Coach" },
  { value: "assistant_coach", label: "Assistant du Coach" },
  { value: "captain", label: "Capitaine" },
  { value: "doctor", label: "Médecin" },
  { value: "player_recruiter", label: "Joueur autorisé à ajouter des joueurs" },
];

function optionLabel<T extends string>(options: Array<{ value: T | ""; label: string }>, value: T | ""): string {
  return options.find((opt) => opt.value === value)?.label ?? value;
}

const BUREAU_ROLES: Array<{ role: string; label: string; hint?: string }> = [
  { role: "vice_president", label: "Vice-président" },
  { role: "secretary", label: "Secrétaire", hint: "Communiqués, préparation des AG, archives." },
  { role: "sports_director", label: "Directeur sportif" },
  { role: "treasurer", label: "Trésorier" },
  { role: "assistant_treasurer", label: "Trésorier adjoint" },
  { role: "steward", label: "Intendant" },
  { role: "doctor", label: "Médecin" },
];

function Card({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-text">{title}</h2>
        {action}
      </div>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function RoleRow({
  label,
  holderName,
  hint,
  onClick,
}: {
  label: string;
  holderName: string | null;
  hint?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-between gap-2 py-2 text-left hover:bg-surface-muted"
    >
      <span className="text-xs text-text-muted">{label}</span>
      <span className="flex min-w-0 flex-col items-end">
        {holderName ? (
          <span className="flex items-center gap-2 text-sm text-text">
            <Avatar name={holderName} size={24} />
            {holderName}
          </span>
        ) : (
          <span className="text-sm text-text-muted">Poste vacant</span>
        )}
        {hint ? <span className="text-[13px] text-text-muted">{hint}</span> : null}
      </span>
    </button>
  );
}

/**
 * Écran « Comité et bureau » (docs/ecrans/club-comite-bureau.md).
 *
 * Point ouvert restant, signalé au compte rendu : les noms des titulaires de
 * rôle sont obtenus en combinant `GET /clubs/roles/` (qui ne renvoie que des
 * `membership_id`) avec la liste unique `GET /clubs/players/`. L'Effectif (§3.6), lui, utilise
 * directement `GET /clubs/players/` (une seule requête, filtres et
 * recherche en paramètres de requête, tri déjà garanti par l'API).
 */
export function ComiteBureauPage() {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [identityModalOpen, setIdentityModalOpen] = useState(false);
  const [addPlayerOpen, setAddPlayerOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [activeRole, setActiveRole] = useState<{ role: string; label: string } | null>(null);
  const [revokingRecruiter, setRevokingRecruiter] = useState<MembershipRole | null>(null);
  const [revoking, setRevoking] = useState(false);
  const [presidencyModalOpen, setPresidencyModalOpen] = useState(false);
  const [recruitersModalOpen, setRecruitersModalOpen] = useState(false);
  const [selectedMembershipId, setSelectedMembershipId] = useState<number | null>(null);

  const [playersSearchInput, setPlayersSearchInput] = useState("");
  const [playersPosition, setPlayersPosition] = useState<ClubPlayerPosition | "">("");
  const [playersStatus, setPlayersStatus] = useState<ClubPlayerMembershipStatus | "">("");
  const [playersRole, setPlayersRole] = useState<string>("");
  const debouncedPlayersSearch = useDebouncedValue(playersSearchInput, 300);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile });
  const identityQuery = useQuery({ queryKey: ["club-identity"], queryFn: getClubIdentity });
  const rolesQuery = useQuery({ queryKey: ["roles"], queryFn: listRoles });

  const isPresident = profileQuery.data?.roles.some((r) => r.role === "president") ?? false;
  const isCoach = profileQuery.data?.roles.some((r) => r.role === "coach") ?? false;

  // Les noms viennent de l'effectif (une seule requête de liste, partagée avec
  // le tableau « Effectif » quand aucun filtre n'est posé) : jamais une
  // requête par titulaire de rôle.
  const rosterQuery = useQuery({
    queryKey: ["club-players", "", "", "", ""],
    queryFn: () => listClubPlayers(),
  });

  const nameById = useMemo(() => {
    const map = new Map<number, string>();
    (rosterQuery.data ?? []).forEach((p) => map.set(p.membership_id, `${p.first_name} ${p.last_name}`));
    return map;
  }, [rosterQuery.data]);

  const cardById = useMemo(() => {
    const map = new Map<number, ReturnType<typeof toPlayerSearchResult>>();
    (rosterQuery.data ?? []).forEach((p) => map.set(p.membership_id, toPlayerSearchResult(p)));
    return map;
  }, [rosterQuery.data]);

  const playersQuery = useQuery({
    queryKey: [
      "club-players",
      debouncedPlayersSearch,
      playersPosition,
      playersStatus,
      playersRole,
    ],
    queryFn: () =>
      listClubPlayers({
        search: debouncedPlayersSearch || undefined,
        position: playersPosition || undefined,
        status: playersStatus || undefined,
        role: playersRole || undefined,
      }),
  });

  function findRole(role: string): MembershipRole | undefined {
    return rolesQuery.data?.find((r) => r.role === role);
  }

  function refetchAll(): void {
    void queryClient.invalidateQueries({ queryKey: ["roles"] });
    void queryClient.invalidateQueries({ queryKey: ["club-identity"] });
    void queryClient.invalidateQueries({ queryKey: ["club-players"] });
  }

  const playersFilterChips: FilterChip[] = [
    playersSearchInput
      ? { label: `Recherche : ${playersSearchInput}`, onRemove: () => setPlayersSearchInput("") }
      : null,
    playersPosition
      ? {
          label: `Poste : ${optionLabel(POSITION_FILTER_OPTIONS, playersPosition)}`,
          onRemove: () => setPlayersPosition(""),
        }
      : null,
    playersStatus
      ? {
          label: `Statut : ${optionLabel(STATUS_FILTER_OPTIONS, playersStatus)}`,
          onRemove: () => setPlayersStatus(""),
        }
      : null,
    playersRole
      ? { label: `Rôle : ${optionLabel(ROLE_FILTER_OPTIONS, playersRole)}`, onRemove: () => setPlayersRole("") }
      : null,
  ].filter((chip): chip is FilterChip => chip !== null);

  function clearPlayersFilters(): void {
    setPlayersSearchInput("");
    setPlayersPosition("");
    setPlayersStatus("");
    setPlayersRole("");
  }

  async function handleRemoveRecruiter(): Promise<void> {
    if (!revokingRecruiter) return;
    setRevoking(true);
    try {
      await revokeRole({ role_id: revokingRecruiter.id });
      showToast("Autorisation retirée.");
      setRevokingRecruiter(null);
      refetchAll();
    } finally {
      setRevoking(false);
    }
  }

  const president = findRole("president");
  const coach = findRole("coach");
  const assistantCoach = findRole("assistant_coach");
  const captain = findRole("captain");
  const recruiters = (rolesQuery.data ?? []).filter((r) => r.role === "player_recruiter");
  const recruitersForModal: Array<{ role: MembershipRole; player: ReturnType<typeof toPlayerSearchResult> }> =
    recruiters
      .map((role) => {
        const player = cardById.get(role.membership_id);
        return player ? { role, player } : null;
      })
      .filter(
        (entry): entry is { role: MembershipRole; player: ReturnType<typeof toPlayerSearchResult> } =>
          entry !== null,
      );
  // Garde-fou : n'ouvre la modale qu'une fois la fiche de chaque titulaire
  // chargée, pour ne jamais risquer de révoquer par erreur un recruteur dont
  // la carte est encore en cours de chargement (cf. filtre ci-dessus).
  const recruitersDataReady = recruitersForModal.length === recruiters.length;
  const canAddPlayers =
    isPresident || (profileQuery.data?.roles.some((r) => r.role === "player_recruiter") ?? false);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-text">Comité et bureau</h1>
          <p className="text-sm text-text-muted">{identityQuery.data?.name ?? profileQuery.data?.club.name}</p>
        </div>
        {canAddPlayers ? (
          <div className="flex items-center gap-2">
            <Button variant="primary" size="sm" onClick={() => setAddPlayerOpen(true)}>
              Ajouter un joueur
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={<IconUpload aria-hidden="true" className="h-4 w-4" />}
              onClick={() => setImportOpen(true)}
            >
              Importer (CSV)
            </Button>
          </div>
        ) : null}
      </header>

      <Card
        title="Identité du club"
        action={
          isPresident ? (
            <Button variant="ghost" size="sm" onClick={() => setIdentityModalOpen(true)}>
              Modifier
            </Button>
          ) : undefined
        }
      >
        {identityQuery.isLoading ? (
          <Loader loading variant="list" count={2} />
        ) : identityQuery.isError || !identityQuery.data ? (
          <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void identityQuery.refetch()} />
        ) : (
          <div className="flex items-center gap-3">
            <Avatar name={identityQuery.data.name} photoUrl={identityQuery.data.logo} size={40} />
            <div>
              <p className="text-sm font-medium text-text">{identityQuery.data.name}</p>
              <p className="text-xs text-text-muted">
                {identityQuery.data.city}, {identityQuery.data.country} · {identityQuery.data.currency} ·{" "}
                {identityQuery.data.timezone}
              </p>
              {isPresident ? (
                <p className="text-xs text-text-muted">
                  Lien de paiement : {identityQuery.data.payment_link_url ? "configuré" : "non configuré"}
                </p>
              ) : null}
            </div>
          </div>
        )}
      </Card>

      <Card
        title="Président"
        action={
          isPresident && president ? (
            <Button variant="ghost" size="sm" onClick={() => setPresidencyModalOpen(true)}>
              Transmettre la présidence
            </Button>
          ) : undefined
        }
      >
        {rolesQuery.isLoading ? (
          <Loader loading variant="list" count={1} />
        ) : president ? (
          <div className="flex items-center gap-2">
            <Avatar name={nameById.get(president.membership_id) ?? "?"} size={40} />
            <div>
              <p className="text-sm text-text">{nameById.get(president.membership_id) ?? "…"}</p>
              <p className="text-xs text-text-muted">
                Président depuis le {new Date(president.appointed_at).toLocaleDateString("fr-FR")}
              </p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-text-muted">Poste vacant.</p>
        )}
      </Card>

      <Card title="Bureau">
        {rolesQuery.isLoading ? (
          <Loader loading variant="list" count={6} />
        ) : (
          <div className="divide-y divide-border">
            {BUREAU_ROLES.map(({ role, label, hint }) => {
              const roleData = findRole(role);
              return (
                <RoleRow
                  key={role}
                  label={label}
                  hint={hint}
                  holderName={roleData ? (nameById.get(roleData.membership_id) ?? "…") : null}
                  onClick={() => setActiveRole({ role, label })}
                />
              );
            })}
          </div>
        )}
      </Card>

      <Card title="Encadrement sportif">
        <div className="divide-y divide-border">
          <RoleRow
            label="Coach"
            holderName={coach ? (nameById.get(coach.membership_id) ?? "…") : null}
            onClick={() => setActiveRole({ role: "coach", label: "Coach" })}
          />
          <RoleRow
            label="Capitaine"
            holderName={captain ? (nameById.get(captain.membership_id) ?? "…") : null}
            onClick={() => setActiveRole({ role: "captain", label: "Capitaine" })}
          />
        </div>
      </Card>

      <AssistantCoachSection
        assistant={assistantCoach}
        assistantName={assistantCoach ? (nameById.get(assistantCoach.membership_id) ?? null) : null}
        loading={rolesQuery.isLoading || profileQuery.isLoading}
        canManage={isCoach}
        onChanged={refetchAll}
      />

      <Card
        title="Joueurs autorisés à ajouter des joueurs"
        action={
          isPresident ? (
            <Button
              variant="ghost"
              size="sm"
              disabled={!recruitersDataReady}
              onClick={() => setRecruitersModalOpen(true)}
            >
              Gérer
            </Button>
          ) : undefined
        }
      >
        {recruiters.length === 0 ? (
          <p className="text-sm text-text-muted">Seul le Président peut ajouter des joueurs.</p>
        ) : (
          <ul className="space-y-1">
            {recruiters.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="flex items-center gap-2">
                  <Avatar name={nameById.get(r.membership_id) ?? "?"} size={24} />
                  {nameById.get(r.membership_id) ?? "…"}
                </span>
                {isPresident ? (
                  <button
                    type="button"
                    onClick={() => setRevokingRecruiter(r)}
                    className="inline-flex min-h-control-sm items-center text-xs font-medium text-status-danger-fg hover:underline"
                  >
                    Retirer
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <MembershipFollowUpCard isPresident={isPresident} profileReady={!profileQuery.isLoading} />

      <Card title="Effectif">
        {playersQuery.isError ? (
          <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void playersQuery.refetch()} />
        ) : (
          <DataTable<ClubPlayerListItem>
            columns={[
              {
                key: "player",
                header: "Joueur",
                widthPx: 200,
                render: (row) => (
                  <span className="flex min-w-0 items-center gap-2">
                    <Avatar name={`${row.first_name} ${row.last_name}`} photoUrl={row.photo} size={32} />
                    <span className="truncate text-text">
                      {row.first_name} {row.last_name}
                    </span>
                  </span>
                ),
              },
              { key: "number", header: "N°", render: (row) => row.jersey_number ?? "—" },
              { key: "position", header: "Poste", render: (row) => row.position_label || "—" },
              {
                key: "roles",
                header: "Rôles",
                render: (row) =>
                  row.roles.length > 0 ? (
                    <span className="flex flex-wrap gap-1">
                      {row.roles.map((role) => (
                        <span
                          key={role.role}
                          className="rounded-full bg-surface-muted px-2 py-0.5 text-xs text-text"
                        >
                          {role.label}
                        </span>
                      ))}
                    </span>
                  ) : (
                    <span className="text-text-muted">—</span>
                  ),
              },
              {
                key: "status",
                header: "Statut",
                render: (row) => (
                  <StatusBadge
                    status={MEMBERSHIP_STATUS_KEY[row.membership_status] ?? "pending"}
                    detail={row.membership_status_label}
                  />
                ),
              },
            ]}
            rows={playersQuery.data ?? []}
            getRowId={(row) => row.membership_id}
            onRowClick={(row) => setSelectedMembershipId(row.membership_id)}
            loading={playersQuery.isLoading}
            resultLabel="joueurs"
            stickyFirstColumn
            filtersSlot={
              <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
                <input
                  type="search"
                  value={playersSearchInput}
                  onChange={(e) => setPlayersSearchInput(e.target.value)}
                  placeholder="Rechercher un joueur"
                  aria-label="Rechercher un joueur"
                  className="h-control-sm w-full rounded-sm border border-border-strong bg-surface px-3 text-sm text-text placeholder:text-text-muted sm:w-56"
                />
                <select
                  value={playersPosition}
                  onChange={(e) => setPlayersPosition(e.target.value as ClubPlayerPosition | "")}
                  aria-label="Poste"
                  className="h-control-sm w-full rounded-sm border border-border-strong bg-surface px-2 text-sm text-text sm:w-auto"
                >
                  {POSITION_FILTER_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <select
                  value={playersStatus}
                  onChange={(e) => setPlayersStatus(e.target.value as ClubPlayerMembershipStatus | "")}
                  aria-label="Statut"
                  className="h-control-sm w-full rounded-sm border border-border-strong bg-surface px-2 text-sm text-text sm:w-auto"
                >
                  {STATUS_FILTER_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <select
                  value={playersRole}
                  onChange={(e) => setPlayersRole(e.target.value)}
                  aria-label="Rôle"
                  className="h-control-sm w-full rounded-sm border border-border-strong bg-surface px-2 text-sm text-text sm:w-auto"
                >
                  {ROLE_FILTER_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            }
            activeFilterChips={playersFilterChips}
            onClearFilters={playersFilterChips.length > 0 ? clearPlayersFilters : undefined}
            emptyState={
              <EmptyState
                message="Aucun joueur dans le club."
                actionLabel={canAddPlayers ? "Ajouter un joueur" : undefined}
                onAction={canAddPlayers ? () => setAddPlayerOpen(true) : undefined}
              />
            }
          />
        )}
      </Card>

      {identityModalOpen && identityQuery.data ? (
        <ClubIdentityModal
          identity={identityQuery.data}
          canEditDebtTolerance={isPresident}
          onClose={() => setIdentityModalOpen(false)}
          onUpdated={() => {
            setIdentityModalOpen(false);
            refetchAll();
          }}
        />
      ) : null}

      {activeRole ? (
        <RoleModal
          roleKey={activeRole.role}
          roleLabel={activeRole.label}
          role={findRole(activeRole.role) ?? null}
          holderName={
            findRole(activeRole.role) ? (nameById.get(findRole(activeRole.role)!.membership_id) ?? null) : null
          }
          canManage={activeRole.role === "captain" ? isCoach : isPresident}
          onClose={() => setActiveRole(null)}
          onChanged={() => {
            setActiveRole(null);
            refetchAll();
          }}
        />
      ) : null}

      {addPlayerOpen ? (
        <AddPlayerModal
          onClose={() => setAddPlayerOpen(false)}
          onAdded={() => {
            setAddPlayerOpen(false);
            refetchAll();
          }}
        />
      ) : null}
      {importOpen ? (
        <ImportPlayersModal onClose={() => setImportOpen(false)} onImported={refetchAll} />
      ) : null}

      {presidencyModalOpen ? (
        <PresidencyHandoverModal
          onClose={() => setPresidencyModalOpen(false)}
          onTransferred={() => {
            setPresidencyModalOpen(false);
            refetchAll();
          }}
        />
      ) : null}

      {recruitersModalOpen && recruitersDataReady ? (
        <RecruitersModal
          recruiters={recruitersForModal}
          onClose={() => setRecruitersModalOpen(false)}
          onChanged={() => {
            setRecruitersModalOpen(false);
            refetchAll();
          }}
        />
      ) : null}

      {selectedMembershipId !== null ? (
        <PlayerCardModal membershipId={selectedMembershipId} onClose={() => setSelectedMembershipId(null)} />
      ) : null}

      <ConfirmDialog
        open={Boolean(revokingRecruiter)}
        title="Retirer cette autorisation ?"
        description="Ce joueur ne pourra plus ajouter de nouveaux joueurs."
        confirmLabel="Retirer"
        loading={revoking}
        onConfirm={() => void handleRemoveRecruiter()}
        onCancel={() => setRevokingRecruiter(null)}
      />
    </div>
  );
}
