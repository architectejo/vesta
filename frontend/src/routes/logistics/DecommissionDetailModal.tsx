import { useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import {
  cancelDecommission,
  executeDecommission,
  getDecommission,
  type Decommission,
} from "../../api/logistics";
import {
  Button,
  ConfirmDialog,
  IconButton,
  IconMore,
  Modal,
  StatusBadge,
  TextArea,
  TextField,
} from "../../design-system";
import { useClosingState } from "../../hooks/useClosingState";
import { formatDateFr, formatDateTimeFr, todayIsoDate } from "./format";
import { decommissionStatusKey } from "./materielLabels";
import { MovementDetailModal } from "./MovementDetailModal";
import { UNLOCATED_LABEL } from "./HolderSearch";
import { OFFLINE_ACTION_MESSAGE, useOnlineStatus } from "./useOnlineStatus";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

export interface DecommissionDetailModalProps {
  decommissionId: number | null;
  canManage: boolean;
  level?: 1 | 2;
  onClose: () => void;
  /** Écriture réussie (sortie, annulation) : message du toast ; l'appelant invalide les données. */
  onChanged: (message: string) => void;
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-text-muted">{label}</span>
      <span className="text-right text-text">{children}</span>
    </div>
  );
}

/** « Déclassement » (détail), spec B4 §3.3. */
export function DecommissionDetailModal({
  decommissionId,
  canManage,
  level = 1,
  onClose,
  onChanged,
}: DecommissionDetailModalProps) {
  const open = decommissionId !== null;
  const query = useQuery({
    queryKey: ["logistics", "decommissions", "detail", decommissionId],
    queryFn: () => getDecommission(decommissionId as number),
    enabled: open,
  });
  const decommission: Decommission | undefined = query.data;

  const [menuOpen, setMenuOpen] = useState(false);
  const { mounted: menuMounted, dataState: menuDataState, onAnimationEnd } = useClosingState(menuOpen, 200);

  const [exitOpen, setExitOpen] = useState(false);
  const [exitDate, setExitDate] = useState(todayIsoDate());
  const [destination, setDestination] = useState("");
  const [exitErrors, setExitErrors] = useState<{ date?: string; destination?: string }>({});
  const [confirmExit, setConfirmExit] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [executeError, setExecuteError] = useState<string | undefined>(undefined);

  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelError, setCancelError] = useState<string | undefined>(undefined);
  const [cancelling, setCancelling] = useState(false);

  const [movementId, setMovementId] = useState<number | null>(null);
  const online = useOnlineStatus();

  useEffect(() => {
    if (!open) return;
    setMenuOpen(false);
    setExitOpen(false);
    setConfirmExit(false);
    setCancelOpen(false);
  }, [open, decommissionId]);

  function openExit(): void {
    setExitDate(todayIsoDate());
    setDestination("");
    setExitErrors({});
    setExecuteError(undefined);
    setExitOpen(true);
  }

  function handleContinue(): void {
    if (!decommission) return;
    const next: { date?: string; destination?: string } = {};
    if (!exitDate) next.date = "La date de sortie est obligatoire.";
    else if (exitDate > todayIsoDate()) next.date = "La date ne peut pas être dans le futur.";
    else if (exitDate < decommission.noted_on) next.date = "La date de sortie ne peut pas être antérieure au constat.";
    if (destination.trim().length > 120) next.destination = "La destination ne peut pas dépasser 120 caractères.";
    setExitErrors(next);
    if (Object.keys(next).length > 0) return;
    setExecuteError(undefined);
    setConfirmExit(true);
  }

  async function handleExecute(): Promise<void> {
    if (!decommission || !online) return;
    setExecuting(true);
    setExecuteError(undefined);
    try {
      const result = await executeDecommission(decommission.id, {
        exit_date: exitDate,
        destination: destination.trim() || undefined,
      });
      setConfirmExit(false);
      setExitOpen(false);
      void query.refetch();
      const { article } = decommission;
      onChanged(
        `${decommission.quantity} ${article.unit} sortis du stock. Stock de ${article.name} : ${result.in_stock} ${article.unit}.`,
      );
    } catch (error) {
      setExecuteError(apiErrorMessage(error));
    } finally {
      setExecuting(false);
    }
  }

  async function handleCancel(): Promise<void> {
    if (!decommission || !online) return;
    if (!cancelReason.trim()) {
      setCancelError("Indiquez le motif de l'annulation.");
      return;
    }
    setCancelling(true);
    setCancelError(undefined);
    try {
      await cancelDecommission(decommission.id, cancelReason.trim());
      setCancelOpen(false);
      void query.refetch();
      onChanged("Signalement annulé.");
    } catch (error) {
      setCancelError(apiErrorMessage(error));
    } finally {
      setCancelling(false);
    }
  }

  const isPending = decommission?.status === "pending";
  const unit = decommission?.article.unit ?? "";

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={decommission ? `Déclassement · ${decommission.article.name}` : "Déclassement"}
        subtitle={decommission ? `Signalé le ${formatDateFr(decommission.noted_on)}` : undefined}
        size="md"
        level={level}
        loading={query.isLoading}
        footer={
          <div className="flex w-full items-center justify-end gap-2">
            <Button variant="secondary" size="md" onClick={onClose}>
              Fermer
            </Button>
            {canManage && isPending ? (
              <Button
                variant="primary"
                size="md"
                onClick={openExit}
                disabled={!online}
                title={online ? undefined : OFFLINE_ACTION_MESSAGE}
              >
                Sortir du stock
              </Button>
            ) : null}
          </div>
        }
      >
        {query.isError ? (
          <p role="alert" className="text-sm text-status-danger-fg">
            {query.error instanceof ApiError && query.error.status === 404
              ? query.error.detail
              : "Impossible de charger ce détail. Réessayez."}
          </p>
        ) : decommission ? (
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <StatusBadge status={decommissionStatusKey(decommission.status)} />
              {canManage && isPending ? (
                <div className="relative">
                  <IconButton
                    aria-label="Plus d'actions"
                    onClick={() => setMenuOpen((v) => !v)}
                    icon={<IconMore aria-hidden="true" className="h-5 w-5" />}
                  />
                  {menuMounted ? (
                    <div
                      data-state={menuDataState}
                      onAnimationEnd={onAnimationEnd}
                      className="vesta-anim-menu absolute right-0 z-10 mt-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated"
                    >
                      <button
                        type="button"
                        disabled={!online}
                        title={online ? undefined : OFFLINE_ACTION_MESSAGE}
                        className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted disabled:opacity-60"
                        onClick={() => {
                          setMenuOpen(false);
                          setCancelReason("");
                          setCancelError(undefined);
                          setCancelOpen(true);
                        }}
                      >
                        Annuler le signalement
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
            <div className="space-y-2 rounded-md bg-surface-muted p-3">
              <DetailRow label="Article">{decommission.article.name}</DetailRow>
              <DetailRow label="Quantité">
                <span className="tabular-nums">
                  {decommission.quantity} {unit}
                </span>
              </DetailRow>
              <DetailRow label="Chez">{decommission.holder?.name ?? UNLOCATED_LABEL}</DetailRow>
              <DetailRow label="Motif">
                {decommission.reason_display}
                {decommission.reason_note ? ` — ${decommission.reason_note}` : ""}
              </DetailRow>
              <DetailRow label="Date du constat">{formatDateFr(decommission.noted_on)}</DetailRow>
            </div>
            {canManage && isPending && !online ? (
              <p className="text-sm text-text-muted">{OFFLINE_ACTION_MESSAGE}</p>
            ) : null}
            {decommission.noted_by?.name ? (
              <p className="text-xs text-text-muted">Signalé par {decommission.noted_by.name}</p>
            ) : null}
            {decommission.status === "done" && decommission.exit_date ? (
              <div className="rounded-md border border-border p-3">
                <p className="text-text">
                  Sorti le {formatDateFr(decommission.exit_date)}
                  {decommission.exit_destination ? ` · ${decommission.exit_destination}` : ""}
                  {decommission.executed_by?.name ? ` · par ${decommission.executed_by.name}` : ""}
                </p>
                {decommission.exit_movement_id ? (
                  <button
                    type="button"
                    onClick={() => setMovementId(decommission.exit_movement_id)}
                    className="mt-1 font-medium text-primary-text hover:underline"
                  >
                    Voir le mouvement
                  </button>
                ) : null}
              </div>
            ) : null}
            {decommission.status === "cancelled" ? (
              <p className="rounded-md border border-border p-3 text-text">
                Annulé
                {decommission.cancelled_at ? ` le ${formatDateTimeFr(decommission.cancelled_at)}` : ""}
                {decommission.cancelled_by?.name ? ` par ${decommission.cancelled_by.name}` : ""}
                {decommission.cancel_reason ? ` : ${decommission.cancel_reason}` : ""}
              </p>
            ) : null}
          </div>
        ) : null}
      </Modal>

      <Modal
        open={exitOpen}
        onClose={() => setExitOpen(false)}
        title="Sortir du stock"
        size="sm"
        level={2}
        isDirty={destination.trim() !== ""}
        confirmLabel="Continuer"
        confirmDisabled={!online}
        onConfirm={handleContinue}
      >
        <div className="space-y-4">
          {!online ? <p className="text-sm text-text-muted">{OFFLINE_ACTION_MESSAGE}</p> : null}
          <label className="block text-sm font-medium text-text">
            Date de sortie
            <input
              type="date"
              value={exitDate}
              min={decommission?.noted_on}
              max={todayIsoDate()}
              onChange={(e) => setExitDate(e.target.value)}
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
            />
            {exitErrors.date ? <p className="mt-1 text-xs text-status-danger-fg">{exitErrors.date}</p> : null}
          </label>
          <TextField
            label="Destination"
            optional
            value={destination}
            onChange={setDestination}
            maxLength={120}
            placeholder="Ex. : donné à l'école du quartier"
            error={exitErrors.destination}
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmExit}
        title={decommission ? `Sortir ${decommission.quantity} ${unit} de ${decommission.article.name} du stock ?` : ""}
        description={
          <>
            <span className="block">Cette sortie est définitive : elle ne pourra pas être supprimée.</span>
            {!online ? <span className="mt-2 block">{OFFLINE_ACTION_MESSAGE}</span> : null}
          </>
        }
        confirmLabel="Sortir du stock"
        confirmDisabled={!online}
        loading={executing}
        loadingLabel="Sortie…"
        error={executeError}
        onConfirm={() => void handleExecute()}
        onCancel={() => setConfirmExit(false)}
      />

      <ConfirmDialog
        open={cancelOpen}
        title="Annuler le signalement ?"
        description={
          <div className="space-y-3">
            <span className="block">Les pièces restent dans le stock.</span>
            <TextArea
              label="Motif"
              value={cancelReason}
              onChange={setCancelReason}
              maxLength={500}
            />
            {!online ? <span className="block">{OFFLINE_ACTION_MESSAGE}</span> : null}
          </div>
        }
        confirmLabel="Annuler le signalement"
        confirmDisabled={!online}
        loading={cancelling}
        loadingLabel="Annulation…"
        error={cancelError}
        onConfirm={() => void handleCancel()}
        onCancel={() => setCancelOpen(false)}
      />

      <MovementDetailModal movementId={movementId} level={2} onClose={() => setMovementId(null)} />
    </>
  );
}
