import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useDeepLink } from "../../../hooks/useDeepLink";
import { listAssemblies, type Assembly } from "../../../api/assemblies";
import { getMyProfile } from "../../../api/clubs";
import { Button, EmptyState, IconButton, IconMore, Skeleton, StatusBadge } from "../../../design-system";
import { useClosingState } from "../../../hooks/useClosingState";
import { AssemblyDetailModal } from "./AssemblyDetailModal";
import { assemblyCardStatus, assemblyTypeLabel, formatDateLong, formatTimeShort } from "./assembliesFormat";
import { ConveneAssemblyWizard } from "./ConveneAssemblyWizard";
import { QuorumThresholdModal } from "./QuorumThresholdModal";

const CARD_STATUS_KEY = {
  convened: "ag_convened",
  cancelled: "cancelled",
  pv_to_sign: "ag_pv_to_sign",
  closed: "ag_closed",
} as const;

function AssemblyCard({ assembly, onOpen }: { assembly: Assembly; onOpen: () => void }) {
  const status = assemblyCardStatus(assembly);
  const decisions = assembly.decisions.slice(0, 2);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-lg border border-border bg-surface p-3 text-left shadow-card transition-colors hover:bg-surface-muted sm:p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-text">
            {formatDateLong(assembly.scheduled_date)} · {formatTimeShort(assembly.scheduled_time)}
          </p>
          <p className="mt-0.5 text-xs text-text-muted">
            {assemblyTypeLabel(assembly.assembly_type)}
            {assembly.location ? ` · ${assembly.location}` : ""}
          </p>
        </div>
        <StatusBadge status={CARD_STATUS_KEY[status]} />
      </div>
      {assembly.status === "scheduled" ? (
        <p className="mt-2 text-xs text-text-muted">
          {assembly.agenda_items.length} point{assembly.agenda_items.length > 1 ? "s" : ""} à l'ordre du jour
        </p>
      ) : decisions.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {decisions.map((decision) => (
            <li key={decision.id} className="truncate text-xs text-text-muted">
              {decision.outcome}
            </li>
          ))}
        </ul>
      ) : null}
    </button>
  );
}

/** Page « Assemblées générales » (docs/ecrans/assemblees-page-ag.md). */
export function AssembleesPage() {
  const [openAssemblyId, setOpenAssemblyId] = useState<number | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  // Lien depuis une notification de convocation ou de PV (`?assemblee=<id>`).
  useDeepLink("assemblee", setOpenAssemblyId);
  const [quorumOpen, setQuorumOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const { mounted: menuMounted, dataState: menuDataState, onAnimationEnd: onMenuAnimationEnd } =
    useClosingState(menuOpen, 200);
  const [pastLimit, setPastLimit] = useState(5);
  const [upcomingLimit, setUpcomingLimit] = useState(10);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });

  const upcomingQuery = useQuery({
    queryKey: ["assemblies", "scheduled", upcomingLimit],
    queryFn: () => listAssemblies({ status: "scheduled", limit: upcomingLimit }),
  });
  const pastQuery = useQuery({
    queryKey: ["assemblies", "held", pastLimit],
    queryFn: () => listAssemblies({ status: "held", limit: pastLimit }),
  });

  // « Convoquer » n'est affiché que si l'API l'autorise pour au moins une
  // assemblée existante (can_manage) ; à défaut (aucune AG créée encore),
  // on retombe sur les rôles Président/VP connus par le profil — seulement
  // pour l'affichage du bouton, jamais pour une décision métier (§2 de la
  // spec : « l'interface n'affiche un bouton que si le droit correspondant
  // est présent »). Le clic réel est toujours vérifié côté API.
  // Les deux sources sont cumulées (OU), jamais chaînées : une liste vide
  // renvoie `false` et non `undefined`, ce qui faisait disparaître le bouton
  // dès que « À venir » arrivait vide après l'avoir affiché via le profil.
  const apiAllowsManage =
    (upcomingQuery.data?.results.some((a) => a.can_manage) ?? false) ||
    (pastQuery.data?.results.some((a) => a.can_manage) ?? false);
  const roleAllowsManage =
    profileQuery.data?.roles.some((r) => r.role === "president" || r.role === "vice_president") ?? false;
  const canManage = apiAllowsManage || roleAllowsManage;
  // « Convoquer » (Président, VP, Secrétaire — 10.3 n° 170) : même principe,
  // mais piloté par `can_convene` renvoyé par l'API, jamais par une liste de
  // rôles recopiée ; le repli sur le profil ne sert qu'à l'affichage quand
  // aucune AG n'existe encore. Le « Seuil de quorum » reste lié à `canManage`
  // (le Secrétaire ne gère pas le quorum).
  const apiAllowsConvene =
    (upcomingQuery.data?.results.some((a) => a.can_convene) ?? false) ||
    (pastQuery.data?.results.some((a) => a.can_convene) ?? false);
  const roleAllowsConvene =
    profileQuery.data?.roles.some((r) => ["president", "vice_president", "secretary"].includes(r.role)) ?? false;
  const canConvene = apiAllowsConvene || roleAllowsConvene || canManage;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-text">Assemblées générales</h1>
          <p className="text-sm text-text-muted">{profileQuery.data?.club.name ?? ""}</p>
        </div>
        <div className="flex items-center gap-2">
          {canConvene ? (
            <Button variant="primary" size="sm" onClick={() => setWizardOpen(true)}>
              Convoquer une AG
            </Button>
          ) : null}
          {canManage ? (
            <div className="relative">
              <IconButton
                aria-label="Plus d'actions"
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((v) => !v)}
                icon={<IconMore aria-hidden="true" className="h-5 w-5" />}
              />
              {menuMounted ? (
                <div
                  role="menu"
                  data-state={menuDataState}
                  onAnimationEnd={onMenuAnimationEnd}
                  className="vesta-anim-menu absolute right-0 z-10 mt-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated"
                >
                  <button
                    type="button"
                    role="menuitem"
                    className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                    onClick={() => {
                      setMenuOpen(false);
                      setQuorumOpen(true);
                    }}
                  >
                    Seuil de quorum
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </header>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-text">À venir</h2>
        {upcomingQuery.isLoading ? (
          <Skeleton variant="card" />
        ) : upcomingQuery.isError ? (
          <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void upcomingQuery.refetch()} />
        ) : upcomingQuery.data && upcomingQuery.data.results.length > 0 ? (
          <>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
              {upcomingQuery.data.results.map((assembly) => (
                <AssemblyCard key={assembly.id} assembly={assembly} onOpen={() => setOpenAssemblyId(assembly.id)} />
              ))}
            </div>
            {upcomingQuery.data.next_offset !== null ? (
              <div className="mt-3">
                <Button variant="secondary" size="sm" onClick={() => setUpcomingLimit((n) => n + 10)}>
                  Voir plus
                </Button>
              </div>
            ) : null}
          </>
        ) : (
          <EmptyState
            message="Aucune assemblée prévue."
            actionLabel={canConvene ? "Convoquer une AG" : undefined}
            onAction={canConvene ? () => setWizardOpen(true) : undefined}
          />
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-text">Passées</h2>
        {pastQuery.isLoading ? (
          <div className="space-y-3">
            <Skeleton variant="card" />
            <Skeleton variant="card" />
            <Skeleton variant="card" />
          </div>
        ) : pastQuery.isError ? (
          <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void pastQuery.refetch()} />
        ) : pastQuery.data && pastQuery.data.results.length > 0 ? (
          <>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
              {pastQuery.data.results.map((assembly) => (
                <AssemblyCard key={assembly.id} assembly={assembly} onOpen={() => setOpenAssemblyId(assembly.id)} />
              ))}
            </div>
            {pastQuery.data.next_offset !== null ? (
              <div className="mt-3">
                <Button variant="secondary" size="sm" onClick={() => setPastLimit((n) => n + 5)}>
                  Voir plus
                </Button>
              </div>
            ) : null}
          </>
        ) : (
          <EmptyState message="Aucune assemblée tenue pour l'instant." />
        )}
      </section>

      {openAssemblyId !== null ? (
        <AssemblyDetailModal assemblyId={openAssemblyId} onClose={() => setOpenAssemblyId(null)} />
      ) : null}
      {wizardOpen ? (
        <ConveneAssemblyWizard
          onClose={() => setWizardOpen(false)}
          onCreated={(assembly) => {
            setWizardOpen(false);
            setOpenAssemblyId(assembly.id);
          }}
        />
      ) : null}
      {quorumOpen ? <QuorumThresholdModal onClose={() => setQuorumOpen(false)} /> : null}
    </div>
  );
}
