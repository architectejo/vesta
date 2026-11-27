import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { listClubPlayers, toPlayerSearchResult, type ClubPlayerListItem } from "../../api/clubs";
import { addToComposition, type CompositionEntry } from "../../api/sport";
import { getTreasuryCapabilities } from "../../api/treasury";
import {
  Avatar,
  Banner,
  Button,
  EmptyState,
  FilterChips,
  Loader,
  Modal,
  NumberField,
  SegmentedControl,
  useToast,
  type PlayerSearchResult,
} from "../../design-system";
import { OFFLINE_ACTION_MESSAGE, useOnlineStatus } from "../logistics/useOnlineStatus";
import { CashRegisterFlow } from "../treasury/CashRegisterModal";
import { ELIGIBILITY_POLL_MS, useEligibility, visiblePollInterval } from "./useEligibility";
import {
  ALL_POSITIONS_LABEL,
  POSITION_FILTER_OPTIONS,
  compareByPositionThenName,
  groupByPosition,
  matchesPositionFilter,
  type PositionFilter,
} from "./positionGroups";

const POSITION_OPTIONS = [
  { value: "goalkeeper", label: "Gardien" },
  { value: "defender", label: "Défenseur" },
  { value: "midfielder", label: "Milieu" },
  { value: "forward", label: "Attaquant" },
] as const;

/** Effectif de la modale : inscrits ET en attente d'adhésion (ces derniers grisés, §4.1). */
export const COMPOSE_ROSTER_QUERY_KEY = ["clubs", "players", "compose-roster"] as const;

/** Texte de repli quand l'API d'éligibilité n'a pas fourni de motif (403, réseau). */
const GENERIC_REASON = "Non sélectionnable (dette, suspension, inaptitude ou adhésion en attente)";
const GENERIC_REASON_INLINE = "dette, suspension, inaptitude ou adhésion en attente";

interface DraftRow {
  role: "starter" | "substitute";
  position: string;
  jerseyNumber: number | null;
}

export interface MatchComposeModalProps {
  open: boolean;
  matchId: number;
  existing: CompositionEntry[];
  onClose: () => void;
  onSaved: () => void;
}

function fullName(player: ClubPlayerListItem): string {
  return `${player.first_name} ${player.last_name}`;
}

/** Retire le point final du motif de l'API pour l'insérer dans une phrase. */
function inlineReason(reason: string): string {
  return reason.trim().replace(/[.\s]+$/, "");
}

async function loadComposeRoster(): Promise<ClubPlayerListItem[]> {
  // L'API ne filtre qu'un statut à la fois : inscrits + en attente d'adhésion.
  // Les joueurs en attente reviennent avec `is_unavailable` (motif via
  // l'éligibilité) : ils sont affichés grisés, jamais sélectionnables.
  const [active, pending] = await Promise.all([
    listClubPlayers({ status: "active" }),
    listClubPlayers({ status: "pending" }),
  ]);
  const seen = new Set(active.map((p) => p.membership_id));
  return [...active, ...pending.filter((p) => !seen.has(p.membership_id))];
}

/**
 * « Composer l'équipe » (docs/ecrans/sport-feuille-de-match.md §4.1 et §4.1 bis).
 *
 * Non-sélection (CLAUDE.md règle 5) : un joueur est grisé si l'effectif le dit
 * indisponible (`is_unavailable`) OU si `GET /sport/eligibility/` le dit non
 * éligible ; le motif est le texte de l'API, jamais recalculé ici. Le contrôle
 * réel reste le service `add_to_composition`, dont l'erreur s'affiche sur la ligne.
 *
 * Régularisation sur place (4.8) : effectif et éligibilité sont relus toutes les
 * 15 s tant que la modale est ouverte (polling, suspendu onglet caché). Un
 * joueur coché qui devient non sélectionnable est décoché avec un bandeau ; un
 * joueur qui redevient sélectionnable est annoncé par un toast.
 */
export function MatchComposeModal({ open, matchId, existing, onClose, onSaved }: MatchComposeModalProps) {
  const { showToast } = useToast();
  const online = useOnlineStatus();
  const [search, setSearch] = useState("");
  const [positionFilter, setPositionFilter] = useState<PositionFilter>("");
  const [drafts, setDrafts] = useState<Record<number, DraftRow>>({});
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});
  const [removedNotices, setRemovedNotices] = useState<Record<number, string>>({});
  const [infoId, setInfoId] = useState<number | null>(null);
  const [cashPlayer, setCashPlayer] = useState<PlayerSearchResult | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const rosterQuery = useQuery({
    queryKey: COMPOSE_ROSTER_QUERY_KEY,
    queryFn: loadComposeRoster,
    enabled: open,
    refetchInterval: visiblePollInterval(ELIGIBILITY_POLL_MS),
  });

  const eligibility = useEligibility(open, { pollMs: ELIGIBILITY_POLL_MS });

  // « Encaisser » : capacité calculée par l'API (Trésorier ou adjoint), jamais
  // déduite d'un rôle ici. Un échec laisse simplement le lien absent.
  const capabilitiesQuery = useQuery({
    queryKey: ["treasury", "capabilities"],
    queryFn: () => getTreasuryCapabilities(),
    enabled: open,
    retry: false,
  });
  const canCollect = capabilitiesQuery.data?.capabilities.can_record_payments ?? false;
  const currency = capabilitiesQuery.data?.currency ?? "";

  const roster = rosterQuery.data;
  const alreadyComposed = useMemo(() => new Set(existing.map((e) => e.membership_id)), [existing]);
  // Non sélectionnable si l'effectif OU l'éligibilité groupée le disent :
  // deux réponses de l'API, aucune règle évaluée ici.
  const blockedIds = useMemo<ReadonlySet<number>>(
    () =>
      new Set(
        (roster ?? [])
          .filter((p) => p.is_unavailable || eligibility.get(p.membership_id)?.eligible === false)
          .map((p) => p.membership_id),
      ),
    [roster, eligibility],
  );

  const reasonOf = useCallback(
    (membershipId: number): string => {
      const item = eligibility.get(membershipId);
      return item && !item.eligible ? item.reason.trim() : "";
    },
    [eligibility],
  );

  // Transitions entre deux rafraîchissements (§4.1 bis) : comparaison avec
  // l'état précédent, jamais au premier chargement.
  const previousBlockedRef = useRef<ReadonlySet<number> | null>(null);
  useEffect(() => {
    if (!open || !roster) {
      previousBlockedRef.current = null;
      return;
    }
    const previous = previousBlockedRef.current;
    previousBlockedRef.current = blockedIds;
    if (!previous || previous === blockedIds) return;

    const byId = new Map(roster.map((p) => [p.membership_id, p] as const));
    const newlyBlocked = [...blockedIds].filter((id) => !previous.has(id));
    const unblocked = [...previous].filter((id) => !blockedIds.has(id) && byId.has(id));

    const removed = newlyBlocked.filter((id) => drafts[id] && !alreadyComposed.has(id));
    if (removed.length > 0) {
      setDrafts((current) => {
        const next = { ...current };
        for (const id of removed) delete next[id];
        return next;
      });
    }
    if (removed.length > 0 || unblocked.length > 0) {
      setRemovedNotices((current) => {
        const next = { ...current };
        for (const id of unblocked) delete next[id];
        for (const id of removed) {
          const player = byId.get(id)!;
          const reason = inlineReason(reasonOf(id)) || GENERIC_REASON_INLINE;
          next[id] = `${fullName(player)} n'est plus sélectionnable : ${reason}. Il a été retiré de votre sélection.`;
        }
        return next;
      });
    }
    for (const id of unblocked) {
      if (alreadyComposed.has(id)) continue;
      showToast(`${fullName(byId.get(id)!)} est désormais sélectionnable.`);
    }
  }, [open, roster, blockedIds, drafts, alreadyComposed, showToast, reasonOf]);

  // Fermeture : les bandeaux et le panneau d'information ne survivent pas.
  useEffect(() => {
    if (!open) {
      setRemovedNotices({});
      setInfoId(null);
      setCashPlayer(null);
    }
  }, [open]);

  // §4.1 : sélectionnables d'abord (par poste puis nom), non sélectionnables
  // ensuite (eux aussi par poste puis nom). Un joueur déjà composé n'est pas
  // grisé : il reste parmi les sélectionnables, comme à l'affichage.
  const isBlockedRow = (p: ClubPlayerListItem): boolean =>
    blockedIds.has(p.membership_id) && !alreadyComposed.has(p.membership_id);
  const sorted = [...(roster ?? [])].sort(
    (a, b) =>
      Number(isBlockedRow(a)) - Number(isBlockedRow(b)) ||
      compareByPositionThenName({ position: a.position, name: fullName(a) }, { position: b.position, name: fullName(b) }),
  );
  // La puce de poste et la recherche se combinent ; les intertitres ne
  // comptent que les lignes visibles.
  const query = search.trim().toLowerCase();
  const filtered = sorted.filter((player) => {
    if (!matchesPositionFilter(player.position, positionFilter)) return false;
    if (!query) return true;
    return fullName(player).toLowerCase().includes(query) || String(player.jersey_number ?? "").includes(query);
  });
  const visibleSelectable = filtered.filter((p) => !isBlockedRow(p));
  const visibleBlocked = filtered.filter(isBlockedRow);
  const positionLabel = POSITION_FILTER_OPTIONS.find((o) => o.value === positionFilter)?.label;
  const noneSelectable =
    (roster ?? []).length > 0 &&
    (roster ?? []).every((p) => blockedIds.has(p.membership_id) || alreadyComposed.has(p.membership_id));

  function toggle(player: ClubPlayerListItem): void {
    setDrafts((current) => {
      const next = { ...current };
      if (next[player.membership_id]) {
        delete next[player.membership_id];
      } else {
        next[player.membership_id] = {
          role: "starter",
          position: player.position,
          jerseyNumber: player.jersey_number,
        };
      }
      return next;
    });
  }

  function updateDraft(membershipId: number, patch: Partial<DraftRow>): void {
    setDrafts((current) => ({ ...current, [membershipId]: { ...current[membershipId]!, ...patch } }));
  }

  async function handleSubmit(): Promise<void> {
    setSubmitting(true);
    const errors: Record<number, string> = {};
    for (const [idStr, draft] of Object.entries(drafts)) {
      const membershipId = Number(idStr);
      if (alreadyComposed.has(membershipId)) continue;
      if (blockedIds.has(membershipId)) continue;
      if (draft.position === "") {
        errors[membershipId] = "Choisissez le poste du jour.";
        continue;
      }
      if (draft.jerseyNumber == null) {
        errors[membershipId] = "Indiquez un numéro du jour.";
        continue;
      }
      try {
        await addToComposition(matchId, {
          membership_id: membershipId,
          role: draft.role,
          position: draft.position,
          jersey_number: draft.jerseyNumber,
        });
      } catch (error) {
        errors[membershipId] = error instanceof ApiError ? error.detail : "Enregistrement impossible.";
      }
    }
    setRowErrors(errors);
    setSubmitting(false);
    if (Object.keys(errors).length === 0) {
      setDrafts({});
      onSaved();
    }
  }

  const selectedCount = Object.keys(drafts).length;
  const starterCount = Object.values(drafts).filter((d) => d.role === "starter").length;
  const notices = Object.entries(removedNotices);

  function renderList() {
    if (rosterQuery.isLoading) {
      return <Loader loading variant="list" count={6} />;
    }
    if (rosterQuery.isError) {
      return (
        <EmptyState
          variant="error"
          message="Impossible de charger l'effectif."
          actionLabel="Réessayer"
          onAction={() => void rosterQuery.refetch()}
        />
      );
    }
    if ((roster ?? []).length === 0) {
      return <EmptyState message="Aucun joueur dans l'effectif." />;
    }
    if (filtered.length === 0) {
      const message = query
        ? positionLabel
          ? `Aucun joueur ne correspond à « ${search.trim()} » dans « ${positionLabel} ».`
          : `Aucun joueur ne correspond à « ${search.trim()} ».`
        : `Aucun joueur dans « ${positionLabel ?? ALL_POSITIONS_LABEL} ».`;
      return <EmptyState variant="no-results" message={message} />;
    }
    // Sous « Tous » : un intertitre par poste (demande du client, remarques.md),
    // puis les non sélectionnables à la fin (§4.1). Sous une puce : liste
    // simple, non sélectionnables toujours en fin.
    const showHeadings = positionFilter === "";
    const sections: Array<{ key: string; label: string | null; items: ClubPlayerListItem[] }> = showHeadings
      ? groupByPosition(visibleSelectable, (p) => p.position).map((g) => ({ key: g.key, label: g.label, items: g.items }))
      : [{ key: "selectable", label: null, items: visibleSelectable }];
    if (visibleBlocked.length > 0) {
      sections.push({ key: "blocked", label: showHeadings ? "Ne peuvent pas être composés" : null, items: visibleBlocked });
    }
    return (
      <div className="space-y-2">
        {sections.map((section) => (
          <section key={section.key} aria-label={section.label ?? undefined}>
            {section.label ? (
              <h3 className="border-b border-border pb-1 pt-1 text-[13px] font-semibold text-text-muted">
                {section.label} ({section.items.length})
              </h3>
            ) : null}
            <ul className="divide-y divide-border">{section.items.map(renderRow)}</ul>
          </section>
        ))}
      </div>
    );
  }

  function renderRow(player: ClubPlayerListItem) {
    const composed = alreadyComposed.has(player.membership_id);
    // §4.1 bis : un joueur en dette, suspendu, inapte ou en attente
    // n'est jamais cochable (CLAUDE.md règle 5). Le motif est le texte
    // de l'API ; le service de composition reste le contrôle réel.
    const blocked = blockedIds.has(player.membership_id) && !composed;
    const reason = reasonOf(player.membership_id);
    const draft = drafts[player.membership_id];
    const error = rowErrors[player.membership_id];
    const infoOpen = blocked && infoId === player.membership_id;
    const name = fullName(player);
    const identity = (
      <>
        <Avatar name={name} photoUrl={player.photo} size={40} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm text-text">
            {name}
            {composed ? " (déjà composé)" : ""}
          </span>
          <span className="block truncate text-xs text-text-muted">{player.position_label}</span>
          {blocked ? (
            // 14 px : information critique (§4.1 bis, 10.2 n° 31).
            <span className="block text-sm text-status-danger-fg">{reason || GENERIC_REASON}</span>
          ) : null}
        </span>
      </>
    );
    return (
      <li key={player.membership_id} className="py-2">
        <div className="flex items-center gap-3">
          {/* Zone tactile de 44 px autour de la case (§4.1, B7). */}
          <label
            className={[
              "flex h-11 w-11 shrink-0 items-center justify-center",
              blocked ? "opacity-60" : "cursor-pointer",
            ].join(" ")}
          >
            <input
              type="checkbox"
              className="h-5 w-5 shrink-0"
              checked={(Boolean(draft) || composed) && !blocked}
              disabled={composed || blocked}
              aria-disabled={composed || blocked}
              onChange={() => toggle(player)}
              aria-label={`Sélectionner ${name}`}
            />
          </label>
          {blocked ? (
            // Toucher le reste de la ligne : panneau d'information seul
            // (§4.1 bis), jamais « Titulaire » ni « Remplaçant ».
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center gap-3 text-left opacity-60"
              aria-expanded={infoOpen}
              aria-label={`Pourquoi ${name} n'est pas sélectionnable`}
              onClick={() => setInfoId(infoOpen ? null : player.membership_id)}
            >
              {identity}
            </button>
          ) : (
            <div className="flex min-w-0 flex-1 items-center gap-3">{identity}</div>
          )}
        </div>
        {infoOpen ? (
          <div
            role="note"
            className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-md bg-surface-muted px-3 py-2 text-sm text-text"
          >
            <span>
              {name} ne peut pas être sélectionné : {reason ? inlineReason(reason) : GENERIC_REASON_INLINE}
            </span>
            {canCollect ? (
              <Button size="sm" variant="secondary" onClick={() => setCashPlayer(toPlayerSearchResult(player))}>
                Encaisser
              </Button>
            ) : null}
          </div>
        ) : null}
        {draft && !composed && !blocked ? (
          <div className="mt-2 flex flex-wrap items-end gap-3 pl-7">
            <SegmentedControl
              label="Rôle"
              value={draft.role}
              onChange={(v) => updateDraft(player.membership_id, { role: v })}
              options={[
                { value: "starter", label: "Titulaire" },
                { value: "substitute", label: "Remplaçant" },
              ]}
            />
            <label className="block text-sm font-medium text-text">
              Poste du jour
              <select
                className="mt-1 h-control-md rounded-sm border border-border-strong bg-surface px-2 text-base"
                value={draft.position}
                onChange={(e) => updateDraft(player.membership_id, { position: e.target.value })}
              >
                {draft.position === "" ? (
                  <option value="" disabled>
                    Choisir un poste
                  </option>
                ) : null}
                {POSITION_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <NumberField
              label="N° du jour"
              value={draft.jerseyNumber}
              onChange={(v) => updateDraft(player.membership_id, { jerseyNumber: v })}
              min={1}
              max={99}
            />
          </div>
        ) : null}
        {error ? <p className="mt-1 pl-7 text-xs text-status-danger-fg">{error}</p> : null}
      </li>
    );
  }

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="Composer l'équipe"
        size="lg"
        isSubmitting={submitting}
        confirmLabel="Enregistrer"
        confirmDisabled={selectedCount === 0 || !online}
        onConfirm={() => void handleSubmit()}
      >
        <div className="space-y-3">
          {notices.map(([id, message]) => (
            <Banner key={id} variant="danger">
              {message}
            </Banner>
          ))}
          {!online ? <Banner variant="warning">{OFFLINE_ACTION_MESSAGE}</Banner> : null}
          <input
            type="text"
            placeholder="Nom ou numéro"
            aria-label="Nom ou numéro"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9 w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text placeholder:text-text-muted"
          />
          {/* Puces de poste (§4.1) : défilent horizontalement à 360 px. */}
          <FilterChips
            label="Filtrer par poste"
            value={positionFilter}
            onChange={setPositionFilter}
            options={POSITION_FILTER_OPTIONS}
            allLabel={ALL_POSITIONS_LABEL}
          />
          <p className="text-xs text-text-muted">
            {starterCount} titulaires · {selectedCount - starterCount} remplaçants
          </p>
          {noneSelectable ? (
            <p className="text-sm text-text-muted">Aucun joueur n'est sélectionnable pour l'instant.</p>
          ) : null}
          {renderList()}
        </div>
      </Modal>

      {canCollect ? (
        <CashRegisterFlow
          open={cashPlayer !== null}
          level={2}
          currency={currency}
          initialPlayer={cashPlayer}
          onClose={() => setCashPlayer(null)}
        />
      ) : null}
    </>
  );
}
