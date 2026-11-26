import { useEffect, useRef, useState } from "react";
import { Banner, Button, Checkbox, ConfirmDialog, Modal, SegmentedControl, TextArea } from "../../design-system";
import type { BulkExcuseReasonCode } from "../../api/sport";
import { pluralPlayers, type BulkRequest, type BulkSummary } from "./useBulkAttendance";
import { combineDateTimeToIso, formatTime, nowTimeHHMM } from "./sportTime";

export interface BulkPlayer {
  id: number;
  name: string;
}

// ---------------------------------------------------------------------------
// En-tête de liste : case à trois états, Tout cocher / Tout décocher, Terminer
// ---------------------------------------------------------------------------

export function BulkHeaderBar({
  checkableIds,
  selected,
  onCheckAll,
  onUncheckAll,
  onStop,
  disabled,
}: {
  /** Lignes cochables visibles (filtre et recherche en cours). */
  checkableIds: number[];
  selected: number[];
  onCheckAll: (ids: number[]) => void;
  onUncheckAll: () => void;
  onStop: () => void;
  disabled?: boolean;
}) {
  const checkedVisible = checkableIds.filter((id) => selected.includes(id)).length;
  const allChecked = checkableIds.length > 0 && checkedVisible === checkableIds.length;
  const boxRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (boxRef.current) boxRef.current.indeterminate = checkedVisible > 0 && !allChecked;
  }, [checkedVisible, allChecked]);

  return (
    <div className="sticky top-0 z-10 flex min-h-11 items-center justify-between gap-2 border-b border-border bg-surface py-1">
      <div className="flex items-center gap-1">
        <label className="flex h-11 w-11 items-center justify-center">
          <input
            ref={boxRef}
            type="checkbox"
            aria-label="Cocher ou décocher les joueurs affichés"
            className="h-5 w-5 rounded-sm border-border-strong text-primary"
            checked={allChecked}
            disabled={disabled || checkableIds.length === 0}
            onChange={() => (allChecked ? onUncheckAll() : onCheckAll(checkableIds))}
          />
        </label>
        {allChecked ? (
          <Button size="sm" variant="ghost" className="whitespace-nowrap" disabled={disabled} onClick={onUncheckAll}>
            Tout décocher
          </Button>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            className="whitespace-nowrap"
            disabled={disabled || checkableIds.length === 0}
            onClick={() => onCheckAll(checkableIds)}
          >
            Tout cocher ({checkableIds.length})
          </Button>
        )}
        {/* Spec §3.2 point 1 : un seul bouton « Tout cocher » / « Tout décocher ».
            Ce second bouton (sélection partielle) ne tient pas dans la barre de
            44 px à 360 px : les libellés passaient sur 2 à 3 lignes et sortaient
            de la barre (vérification visuelle B3). Il n'apparaît qu'à partir de 640 px. */}
        {selected.length > 0 && !allChecked ? (
          <Button size="sm" variant="ghost" className="whitespace-nowrap max-sm:hidden" disabled={disabled} onClick={onUncheckAll}>
            Tout décocher
          </Button>
        ) : null}
      </div>
      <Button size="sm" variant="ghost" className="whitespace-nowrap" disabled={disabled} onClick={onStop}>
        Terminer
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Barre d'actions collante
// ---------------------------------------------------------------------------

export function BulkActionBar({
  count,
  canExcuse,
  submitting,
  onArrive,
  onExcuse,
}: {
  count: number;
  canExcuse: boolean;
  submitting: boolean;
  onArrive: () => void;
  onExcuse: () => void;
}) {
  const none = count === 0;
  return (
    <div
      role="region"
      aria-label="Actions sur la sélection"
      className="sticky bottom-0 z-20 -mx-3 flex flex-wrap items-center justify-between gap-2 border-t border-border bg-surface px-3 py-2 sm:-mx-4 sm:px-4 pb-[max(0.5rem,env(safe-area-inset-bottom))]"
    >
      <p className="text-sm text-text" aria-live="polite">
        {count} sélectionné{count > 1 ? "s" : ""}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {canExcuse ? (
          <Button variant="secondary" disabled={none || submitting} onClick={onExcuse}>
            Absent excusé
          </Button>
        ) : null}
        <Button variant="primary" disabled={none || submitting} loading={submitting} onClick={onArrive}>
          Pointer l'arrivée ({count})
        </Button>
      </div>
      {none ? <span className="sr-only">Cochez au moins un joueur.</span> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Liste repliée « Voir les joueurs »
// ---------------------------------------------------------------------------

function PlayersFold({ players }: { players: BulkPlayer[] }) {
  return (
    <details className="text-sm">
      <summary className="min-h-control-sm cursor-pointer py-2 text-primary-text">Voir les joueurs</summary>
      <ol className="max-h-40 list-decimal space-y-0.5 overflow-y-auto pl-6 text-text">
        {players.map((p) => (
          <li key={p.id}>{p.name}</li>
        ))}
      </ol>
    </details>
  );
}

// ---------------------------------------------------------------------------
// Confirmation « Pointer N joueurs ? »
// ---------------------------------------------------------------------------

export function BulkConfirmModal({
  open,
  players,
  canSetTime,
  eventDate,
  lateCutoff,
  timeZone: tz,
  lateCountsAbsent,
  blockedCount = 0,
  submitting,
  error,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  players: BulkPlayer[];
  /** Nombre de joueurs cochés que l'API déclare non placables (dette,
   * suspension, inaptitude, attente d'adhésion) ; 0 ou absent = rien. */
  blockedCount?: number;
  /** `capabilities.can_set_arrival_time` renvoyé par l'API. */
  canSetTime: boolean;
  /** Date de l'événement (AAAA-MM-JJ), pour construire l'heure commune. */
  eventDate: string;
  /** Fuseau IANA du club : heure commune saisie et affichée à l'heure du club. */
  timeZone?: string;
  /** Heure limite « HH:MM » (séance) ou coup d'envoi (match). */
  lateCutoff?: string;
  lateCountsAbsent?: boolean;
  submitting: boolean;
  error?: string;
  onCancel: () => void;
  onConfirm: (request: BulkRequest) => void;
}) {
  const [customOn, setCustomOn] = useState(false);
  const [time, setTime] = useState("");
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    if (!open) return;
    const current = new Date();
    setNow(current);
    setCustomOn(false);
    setTime(nowTimeHHMM(tz, current));
    // L'heure proposée suit le fuseau du club, connu après l'ouverture parfois.
  }, [open, tz]);

  // Heure commune saisie à l'heure du club (CLAUDE.md §7), envoyée en UTC.
  const arrivedAt = customOn && time ? new Date(combineDateTimeToIso(eventDate, time, tz)) : null;
  const effective = arrivedAt && !Number.isNaN(arrivedAt.getTime()) ? arrivedAt : now;
  const effectiveHm = nowTimeHHMM(tz, effective);
  const afterCutoff = Boolean(lateCutoff) && effectiveHm > lateCutoff!.slice(0, 5);

  return (
    <ConfirmDialog
      open={open}
      title={`Pointer ${pluralPlayers(players.length)} ?`}
      confirmLabel={`Pointer (${players.length})`}
      loadingLabel="Pointage…"
      danger={false}
      loading={submitting}
      error={error}
      onCancel={onCancel}
      onConfirm={() =>
        onConfirm({
          action: "arrive",
          arrivedAt: customOn && arrivedAt && !Number.isNaN(arrivedAt.getTime()) ? arrivedAt.toISOString() : undefined,
        })
      }
      description={
        <div className="space-y-2">
          <p className="text-text">
            Heure enregistrée : {customOn ? effectiveHm : formatTime(now.toISOString(), tz)}
            {customOn ? "" : " (heure de ce téléphone)"}.
          </p>
          {afterCutoff ? (
            <Banner variant="warning">
              Il est plus de {lateCutoff!.slice(0, 5)} : ces joueurs seront enregistrés en retard
              {lateCountsAbsent ? ", et comptés absents" : ""} selon la règle du club.
            </Banner>
          ) : null}
          {blockedCount > 0 ? (
            <Banner variant="warning">
              {blockedCount} de ces joueurs ne pourront pas être placés dans une équipe.
            </Banner>
          ) : null}
          <p>Ordre d'arrivée retenu : l'ordre dans lequel vous les avez cochés.</p>
          <p className="font-medium text-text">Un pointage ne peut pas être retiré ensuite.</p>
          {canSetTime ? (
            <div className="space-y-1">
              <Checkbox checked={customOn} onChange={setCustomOn} label="Indiquer une autre heure d'arrivée" />
              {customOn ? (
                <label className="block text-sm font-medium text-text">
                  Heure d'arrivée commune
                  <input
                    type="time"
                    value={time}
                    onChange={(e) => setTime(e.target.value)}
                    className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
                  />
                  <span className="mt-1 block text-xs font-normal text-text-muted">
                    Utile si le groupe est arrivé avant que vous ayez pu le pointer.
                  </span>
                </label>
              ) : null}
            </div>
          ) : null}
          <PlayersFold players={players} />
        </div>
      }
    />
  );
}

// ---------------------------------------------------------------------------
// Absences excusées groupées
// ---------------------------------------------------------------------------

const REASONS: Array<{ value: BulkExcuseReasonCode; label: string }> = [
  { value: "injured", label: "Blessé" },
  { value: "travel", label: "Voyage" },
  { value: "other", label: "Autre" },
];

export function BulkExcuseModal({
  open,
  players,
  submitting,
  error,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  players: BulkPlayer[];
  submitting: boolean;
  error?: string;
  onCancel: () => void;
  onConfirm: (request: BulkRequest) => void;
}) {
  const [reason, setReason] = useState<BulkExcuseReasonCode | null>(null);
  const [detail, setDetail] = useState("");
  const [reasonError, setReasonError] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (open) {
      setReason(null);
      setDetail("");
      setReasonError(undefined);
    }
  }, [open]);

  function handleConfirm() {
    if (!reason) {
      setReasonError("Choisissez un motif.");
      return;
    }
    onConfirm({ action: "excuse", reasonCode: reason, reasonDetail: detail });
  }

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={`Marquer ${players.length} absence${players.length > 1 ? "s" : ""} excusée${players.length > 1 ? "s" : ""}`}
      size="sm"
      isSubmitting={submitting}
      confirmLabel={`Marquer excusés (${players.length})`}
      confirmLoadingLabel="Enregistrement…"
      onConfirm={handleConfirm}
    >
      <div className="space-y-3">
        <p className="text-xs text-text-muted">
          Une absence excusée reste une absence ; elle est distinguée dans les statistiques.
        </p>
        <SegmentedControl
          label="Motif"
          value={reason}
          onChange={(v) => {
            setReason(v);
            setReasonError(undefined);
          }}
          options={REASONS}
          error={reasonError}
        />
        <TextArea
          label="Précision"
          optional
          value={detail}
          onChange={setDetail}
          maxLength={200}
          help="Ce texte est le même pour tous les joueurs cochés. N'y écrivez aucun détail médical."
        />
        <PlayersFold players={players} />
        {error ? (
          <p role="alert" className="text-sm text-status-danger-fg">
            {error}
          </p>
        ) : null}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Résultat détaillé
// ---------------------------------------------------------------------------

export function BulkResultModal({
  summary,
  nameOf,
  onClose,
}: {
  summary: BulkSummary | null;
  nameOf: (membershipId: number) => string;
  onClose: () => void;
}) {
  const open = summary !== null;
  const counts = summary?.counts ?? { created: 0, skipped: 0, refused: 0 };
  const problems = (summary?.results ?? []).filter((r) => r.outcome !== "created");
  const parts = [
    `${counts.created} pointé${counts.created > 1 ? "s" : ""}`,
    counts.skipped > 0 ? `${counts.skipped} déjà pointé${counts.skipped > 1 ? "s" : ""}` : null,
    counts.refused > 0 ? `${counts.refused} refusé${counts.refused > 1 ? "s" : ""}` : null,
  ].filter(Boolean);

  return (
    <Modal open={open} onClose={onClose} title="Résultat du pointage groupé" size="sm" hideFooter>
      <div className="space-y-3">
        <p className="text-sm font-medium text-text">{parts.join(", ")}</p>
        {problems.length > 0 ? (
          <ul className="divide-y divide-border">
            {problems.map((r) => (
              <li key={r.membership_id} className="py-2 text-sm">
                <p className="text-text">{nameOf(r.membership_id)}</p>
                <p className={r.outcome === "refused" ? "text-status-danger-fg" : "text-text-muted"}>{r.message}</p>
              </li>
            ))}
          </ul>
        ) : null}
        {counts.refused > 0 ? (
          <p className="text-xs text-text-muted">Les joueurs refusés restent cochés pour que vous puissiez réessayer.</p>
        ) : null}
        <Button variant="primary" className="w-full" onClick={onClose}>
          Fermer
        </Button>
      </div>
    </Modal>
  );
}
