import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import {
  closeCashSession,
  createCashPayment,
  getContributionTypes,
  getCurrentCashSession,
  openCashSession,
  previewCashPayment,
  searchCashSessionPlayers,
  toCashPlayerSearchResult,
  type CashSession,
  type CashSessionPlayer,
  type PaymentPreview,
} from "../../api/treasury";
import {
  Avatar,
  Banner,
  Button,
  ConfirmDialog,
  EmptyState,
  Modal,
  MoneyField,
  PinPrompt,
  PlayerSearch,
  StatusBadge,
  useToast,
  type PlayerSearchResult,
  type StatusKey,
} from "../../design-system";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { formatAmount, formatMonthYear, toApiAmount } from "./money";
import { formatPinError } from "./pinErrors";

const CASH_SESSION_QUERY_KEY = ["treasury", "cash-session-current"] as const;
const CONTRIBUTION_TYPES_QUERY_KEY = ["treasury", "contribution-types"] as const;

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.detail
    : "Une erreur est survenue de notre côté. Réessayez dans un instant.";
}

function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    function handleOnline() {
      setOnline(true);
    }
    function handleOffline() {
      setOnline(false);
    }
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);
  return online;
}

function statusKeyFromGoodStanding(isInGoodStanding: boolean): StatusKey {
  return isInGoodStanding ? "in_good_standing" : "in_debt";
}

export interface CashRegisterFlowProps {
  open: boolean;
  currency: string;
  onClose: () => void;
}

/**
 * Orchestre la Caisse Terrain Express (fiche `tresorerie-tableau-de-bord.md`
 * §4.2 et §4.2 bis ; CDC 4.4.5, 10.2 n° 22) : vérifie d'abord s'il existe une
 * session de caisse en cours, puis ouvre soit « Ouvrir une session de
 * caisse », soit directement la caisse.
 *
 * **Simplification signalée en compte rendu** : le mode hors connexion
 * complet (file d'actions locale horodatée, envoi différé, `SyncIndicator`)
 * n'est pas implémenté ici ; seul le cas en ligne fonctionne de bout en bout.
 */
export function CashRegisterFlow({ open, currency, onClose }: CashRegisterFlowProps) {
  const queryClient = useQueryClient();
  const [justOpened, setJustOpened] = useState<CashSession | null>(null);

  const sessionQuery = useQuery({
    queryKey: CASH_SESSION_QUERY_KEY,
    queryFn: getCurrentCashSession,
    enabled: open,
  });

  useEffect(() => {
    if (!open) setJustOpened(null);
  }, [open]);

  if (!open) return null;

  const session = justOpened ?? sessionQuery.data?.session ?? null;

  if (!session) {
    if (sessionQuery.isLoading) {
      return (
        <Modal open onClose={onClose} title="Caisse Terrain Express" size="xl" loading hideFooter>
          {null}
        </Modal>
      );
    }
    if (sessionQuery.isError) {
      return (
        <Modal open onClose={onClose} title="Caisse Terrain Express" size="xl" hideFooter>
          <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void sessionQuery.refetch()} />
        </Modal>
      );
    }
    return (
      <OpenCashSessionModal
        onClose={onClose}
        onOpened={(opened) => {
          setJustOpened(opened);
          void queryClient.invalidateQueries({ queryKey: CASH_SESSION_QUERY_KEY });
        }}
      />
    );
  }

  return (
    <CashRegisterModal
      session={session}
      currency={currency}
      onClose={onClose}
      onSessionClosed={() => {
        setJustOpened(null);
        void queryClient.invalidateQueries({ queryKey: CASH_SESSION_QUERY_KEY });
        onClose();
      }}
      onSessionRefresh={(nextSession) => setJustOpened(nextSession)}
    />
  );
}

// ---------------------------------------------------------------------------
// §4.2 bis « Ouvrir une session de caisse »
// ---------------------------------------------------------------------------

function OpenCashSessionModal({
  onClose,
  onOpened,
}: {
  onClose: () => void;
  onOpened: (session: CashSession) => void;
}) {
  const { showToast } = useToast();
  const online = useOnlineStatus();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);

  async function handleSubmit(pin: string): Promise<void> {
    setSubmitting(true);
    setError(undefined);
    try {
      const { session } = await openCashSession(pin);
      showToast("Session de caisse ouverte jusqu'à minuit.");
      onOpened(session);
    } catch (err) {
      setError(formatPinError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PinPrompt
      open
      title="Ouvrir une session de caisse"
      description={
        <>
          <p>
            Vous allez ouvrir une session de caisse valable jusqu'à minuit (heure du club). Pendant
            cette session, vos encaissements en espèces ne demanderont plus votre code PIN, y compris
            hors connexion. Ouvrez-la avant d'aller au terrain si le réseau y est faible.
          </p>
          {!online ? (
            <Banner variant="warning" className="mt-3">
              Connexion requise pour ouvrir une session de caisse. Réessayez quand le réseau revient.
            </Banner>
          ) : null}
        </>
      }
      confirmLabel="Ouvrir la session"
      confirmLoadingLabel="Vérification…"
      isSubmitting={submitting}
      disabled={!online}
      error={error}
      onSubmit={(pin) => void handleSubmit(pin)}
      onClose={onClose}
    />
  );
}

// ---------------------------------------------------------------------------
// §4.2 « Caisse Terrain Express »
// ---------------------------------------------------------------------------

interface CashRegisterModalProps {
  session: CashSession;
  currency: string;
  onClose: () => void;
  onSessionClosed: () => void;
  onSessionRefresh: (session: CashSession) => void;
}

function CashRegisterModal({
  session,
  currency,
  onClose,
  onSessionClosed,
  onSessionRefresh,
}: CashRegisterModalProps) {
  const { showToast } = useToast();

  const [player, setPlayer] = useState<PlayerSearchResult | null>(null);
  const [selectedRaw, setSelectedRaw] = useState<CashSessionPlayer | null>(null);
  const [contributionTypeId, setContributionTypeId] = useState<number | null>(null);
  const [amount, setAmount] = useState("");
  const [amountError, setAmountError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<{ inGoodStanding: boolean; amountDue: string } | null>(null);
  const [confirmCloseOpen, setConfirmCloseOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const lastResultsRef = useRef<Map<string | number, CashSessionPlayer>>(new Map());

  const typesQuery = useQuery({
    queryKey: CONTRIBUTION_TYPES_QUERY_KEY,
    queryFn: () => getContributionTypes(),
  });
  const types = useMemo(
    () => (typesQuery.data ?? []).filter((type) => type.status === "active"),
    [typesQuery.data],
  );

  function selectPlayer(selected: PlayerSearchResult | null): void {
    setPlayer(selected);
    setSelectedRaw(selected ? (lastResultsRef.current.get(selected.id) ?? null) : null);
    setOutcome(null);
    setSubmitError(null);
    setAmount("");
    setAmountError(undefined);
    setContributionTypeId(null);
  }

  const searchPlayers = useMemo(
    () =>
      async (query: string): Promise<PlayerSearchResult[]> => {
        const { results } = await searchCashSessionPlayers(session.id, query);
        const map = new Map<string | number, CashSessionPlayer>();
        for (const result of results) map.set(result.membership_id, result);
        lastResultsRef.current = map;
        return results.map(toCashPlayerSearchResult);
      },
    [session.id],
  );

  const debouncedAmount = useDebouncedValue(amount, 250);
  const previewEnabled = Boolean(player) && Number(toApiAmount(debouncedAmount)) > 0;

  const previewQuery = useQuery<PaymentPreview>({
    queryKey: ["treasury", "cash-payment-preview", session.id, player?.id, contributionTypeId, debouncedAmount],
    queryFn: () =>
      previewCashPayment(session.id, {
        membership_id: Number(player!.id),
        amount: toApiAmount(debouncedAmount),
        contribution_type_id: contributionTypeId,
      }),
    enabled: previewEnabled,
  });

  async function handleCollect(): Promise<void> {
    if (!player) return;
    const numericAmount = Number(toApiAmount(amount));
    if (!amount || Number.isNaN(numericAmount) || numericAmount <= 0) {
      setAmountError("Saisissez un montant supérieur à 0.");
      return;
    }
    setAmountError(undefined);
    setSubmitError(null);
    setSubmitting(true);
    try {
      const payment = await createCashPayment(session.id, {
        membership_id: Number(player.id),
        amount: toApiAmount(amount),
        contribution_type_id: contributionTypeId,
        client_uuid: crypto.randomUUID(),
        client_recorded_at: new Date().toISOString(),
      });
      showToast(`Encaissement enregistré. Reçu n° ${payment.receipt_number}.`);
      if (payment.player_status) {
        setOutcome({
          inGoodStanding: payment.player_status.is_in_good_standing,
          amountDue: payment.player_status.amount_due,
        });
      }
      onSessionRefresh({
        ...session,
        payments_count: session.payments_count + 1,
        payments_total: String(Number(session.payments_total) + numericAmount),
      });
    } catch (error) {
      setSubmitError(apiErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCloseSession(): Promise<void> {
    setClosing(true);
    try {
      await closeCashSession(session.id);
      showToast("Session de caisse fermée.");
      setConfirmCloseOpen(false);
      onSessionClosed();
    } catch (error) {
      setSubmitError(apiErrorMessage(error));
      setConfirmCloseOpen(false);
    } finally {
      setClosing(false);
    }
  }

  const expired = session.status === "expired";

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title="Caisse Terrain Express"
        size="xl"
        footer={
          <>
            {outcome ? (
              <Button variant="secondary" className="flex-1 sm:flex-none" onClick={() => selectPlayer(null)}>
                Encaisser pour un autre joueur
              </Button>
            ) : null}
            <Button variant="secondary" className="flex-1 sm:flex-none" onClick={onClose}>
              Quitter la caisse
            </Button>
            {!outcome ? (
              <Button
                variant="primary"
                className="flex-1 sm:flex-none"
                disabled={!player || expired}
                loading={submitting}
                loadingLabel="Encaissement…"
                onClick={() => void handleCollect()}
              >
                Encaisser
              </Button>
            ) : null}
          </>
        }
      >
        <div className="space-y-4">
          <Banner
            variant={expired ? "warning" : "success"}
            action={
              expired ? (
                <Button size="sm" variant="ghost" onClick={onClose}>
                  Ouvrir une session
                </Button>
              ) : (
                <Button size="sm" variant="ghost" onClick={() => setConfirmCloseOpen(true)}>
                  Fermer la session
                </Button>
              )
            }
          >
            {expired ? (
              "Session de caisse expirée à minuit. Ouvrez une nouvelle session pour continuer."
            ) : (
              <>
                <span>Session de caisse ouverte jusqu'à minuit.</span>
                <br />
                <span className="text-xs">
                  {session.payments_count} encaissement{session.payments_count > 1 ? "s" : ""} ·{" "}
                  {formatAmount(session.payments_total, currency)}
                </span>
              </>
            )}
          </Banner>

          {submitError ? <Banner variant="danger">{submitError}</Banner> : null}

          <div>
            <label className="mb-1 block text-sm font-medium text-text" htmlFor="cash-register-player">
              Joueur
            </label>
            <PlayerSearch
              value={player}
              onChange={selectPlayer}
              searchPlayers={searchPlayers}
              ariaLabel="Nom ou numéro du joueur"
              disabled={expired}
            />
          </div>

          {player ? (
            <div className="rounded-md bg-surface-muted p-3">
              <div className="flex items-center gap-3">
                <Avatar name={`${player.firstName} ${player.lastName}`} photoUrl={player.photoUrl} size={72} />
                <div className="min-w-0 flex-1 space-y-0.5">
                  <p className="truncate text-base font-medium text-text">
                    {player.firstName} {player.lastName}
                  </p>
                  {player.number != null ? (
                    <p className="text-sm text-text-muted">n° {player.number}</p>
                  ) : null}
                  {selectedRaw ? (
                    <p className="text-sm text-text-muted">
                      Solde : {formatAmount(selectedRaw.balance, selectedRaw.currency)}
                    </p>
                  ) : null}
                  {selectedRaw ? (
                    <StatusBadge status={statusKeyFromGoodStanding(selectedRaw.is_in_good_standing)} />
                  ) : null}
                </div>
                <Button size="sm" variant="ghost" onClick={() => selectPlayer(null)}>
                  Changer
                </Button>
              </div>
            </div>
          ) : null}

          {player ? (
            <div className="space-y-3">
              <MoneyField
                label="Montant en espèces"
                currency={currency}
                value={amount}
                onChange={setAmount}
                error={amountError}
                disabled={expired}
              />
              <label className="block text-sm font-medium text-text">
                Type
                <select
                  className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
                  value={contributionTypeId ?? ""}
                  onChange={(event) =>
                    setContributionTypeId(event.target.value ? Number(event.target.value) : null)
                  }
                  disabled={expired || typesQuery.isLoading}
                >
                  <option value="">Sa cotisation mensuelle</option>
                  {types.map((type) => (
                    <option key={type.id} value={type.id}>
                      {type.name}
                    </option>
                  ))}
                </select>
              </label>

              <CashPreviewPanel enabled={previewEnabled} query={previewQuery} currency={currency} />

              {outcome ? (
                <Banner variant={outcome.inGoodStanding ? "success" : "warning"}>
                  {outcome.inGoodStanding
                    ? `${player.firstName} est en ordre. Il peut être composé.`
                    : `${player.firstName} reste en dette : ${formatAmount(outcome.amountDue, currency)}.`}
                </Banner>
              ) : null}
            </div>
          ) : null}

          <p className="text-xs text-text-muted">Quitter la caisse ne ferme pas la session.</p>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmCloseOpen}
        title="Fermer la session de caisse ?"
        description="Pour encaisser à nouveau, il faudra ouvrir une nouvelle session avec votre code PIN."
        confirmLabel="Fermer la session"
        loading={closing}
        onConfirm={() => void handleCloseSession()}
        onCancel={() => setConfirmCloseOpen(false)}
      />
    </>
  );
}

interface CashPreviewPanelProps {
  enabled: boolean;
  query: ReturnType<typeof useQuery<PaymentPreview>>;
  currency: string;
}

function CashPreviewPanel({ enabled, query, currency }: CashPreviewPanelProps) {
  if (!enabled) return null;

  if (query.isLoading) {
    return (
      <div className="space-y-2" aria-busy="true" aria-live="polite">
        <div className="h-4 w-full animate-pulse rounded bg-skeleton" />
        <div className="h-4 w-full animate-pulse rounded bg-skeleton" />
        <div className="h-4 w-2/3 animate-pulse rounded bg-skeleton" />
      </div>
    );
  }

  if (query.isError) {
    return <p className="text-sm text-status-danger-fg">Aperçu indisponible. Vérifiez les champs.</p>;
  }

  const preview = query.data;
  if (!preview) return null;

  if (preview.is_free_type) {
    return (
      <p className="rounded-md bg-surface-muted p-3 text-sm text-text">
        Cotisation libre : ce paiement n'entre pas dans le solde.
      </p>
    );
  }

  const afterKey = statusKeyFromGoodStanding(preview.after.is_in_good_standing);

  return (
    <div className="space-y-3 rounded-md bg-surface-muted p-3">
      <p className="text-sm font-medium text-text">Répartition</p>
      <ul className="space-y-1 text-sm text-text">
        {preview.allocations.map((line) => (
          <li key={line.period} className="flex justify-between gap-2">
            <span>{formatMonthYear(line.period)}</span>
            <span className="tabular-nums">{formatAmount(line.amount, currency)}</span>
            <span>{line.status === "paid" ? "Payé" : "Partiel"}</span>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2 text-sm">
        <span>Nouveau solde : {formatAmount(preview.after.balance, currency)}</span>
        <StatusBadge
          status={afterKey}
          detail={afterKey === "in_debt" ? formatAmount(preview.after.amount_due, currency) : undefined}
        />
      </div>
    </div>
  );
}
