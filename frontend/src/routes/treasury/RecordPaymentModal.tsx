import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchActiveClubPlayers } from "../../api/clubs";
import { ApiError } from "../../api/client";
import {
  createPayment,
  getContributionTypes,
  previewPayment,
  type ContributionType,
  type PaymentMethod,
  type PaymentPreview,
} from "../../api/treasury";
import {
  Banner,
  ConfirmDialog,
  Modal,
  MoneyField,
  PlayerSearch,
  SegmentedControl,
  StatusBadge,
  TextField,
  useToast,
  type PlayerSearchResult,
} from "../../design-system";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { CLIENT_UUID_CONFLICT_MESSAGE, useClientUuid } from "../../hooks/useClientUuid";
import { formatAmount, formatMonthYear, isPositiveAmount, todayIsoDate, toApiAmount } from "./money";

const CONTRIBUTION_TYPES_QUERY_KEY = ["treasury", "contribution-types"] as const;

const METHOD_OPTIONS: Array<{ value: PaymentMethod; label: string }> = [
  { value: "cash", label: "Espèces" },
  { value: "mobile_money", label: "Mobile money" },
  { value: "payment_link", label: "Lien de paiement" },
];

const ALLOCATION_STATUS_LABELS: Record<string, string> = {
  paid: "Payé",
  partial: "Partiel",
};

/**
 * Choisit un type de cotisation par défaut : la première cotisation
 * obligatoire mensuelle active. **Simplification signalée en compte rendu** :
 * l'API ne fournit pas encore, pour la recherche générale de joueurs, le
 * type de cotisation par défaut du joueur choisi (contrairement à la
 * recherche de la Caisse Terrain Express, qui l'expose) ; à corriger côté
 * `backend-dev` si un point d'accès dédié est ajouté.
 */
function pickDefaultContributionTypeId(types: ContributionType[]): number | undefined {
  return types.find((type) => type.nature === "mandatory" && type.periodicity === "monthly")?.id;
}

const MAX_CONFIRM_LINES = 6;

interface FormErrors {
  player?: string;
  type?: string;
  amount?: string;
  reference?: string;
  paidOn?: string;
}

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.detail
    : "Une erreur est survenue de notre côté. Réessayez dans un instant.";
}

export interface RecordPaymentModalProps {
  open: boolean;
  currency: string;
  onClose: () => void;
  /** Après un enregistrement réussi (invalidation des listes de la page). */
  onRecorded: () => void;
  /**
   * Joueur et type préremplis (ex. depuis la modale « Détail du mois » de la
   * grille des cotisations, fiche `tresorerie-grille-cotisations.md` §4.1).
   * Restent modifiables : seules les valeurs initiales changent.
   */
  initialPlayer?: PlayerSearchResult;
  initialContributionTypeId?: number;
  /** Niveau d'empilement de la modale (3.2) : `2` quand elle s'ouvre par-dessus une modale de détail. */
  level?: 1 | 2;
}

/**
 * Modale « Enregistrer un paiement » (fiche `tresorerie-tableau-de-bord.md`
 * §4.1 ; CDC 4.4.3, 4.4.4). L'aperçu de répartition et le nouveau solde sont
 * calculés exclusivement par l'API (`payments/preview/`), jamais dans
 * l'interface (CLAUDE.md §2 « Interface »).
 */
export function RecordPaymentModal({
  open,
  currency,
  onClose,
  onRecorded,
  initialPlayer,
  initialContributionTypeId,
  level = 1,
}: RecordPaymentModalProps) {
  const { showToast } = useToast();
  const clientUuid = useClientUuid();

  const [player, setPlayer] = useState<PlayerSearchResult | null>(initialPlayer ?? null);
  const [contributionTypeId, setContributionTypeId] = useState<number | "">(initialContributionTypeId ?? "");
  const [defaultApplied, setDefaultApplied] = useState(initialContributionTypeId !== undefined);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<PaymentMethod>("cash");
  const [reference, setReference] = useState("");
  const [paidOn, setPaidOn] = useState(todayIsoDate());
  const [attachment, setAttachment] = useState<File | null>(null);
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmSubmitting, setConfirmSubmitting] = useState(false);

  const typesQuery = useQuery({
    queryKey: CONTRIBUTION_TYPES_QUERY_KEY,
    queryFn: () => getContributionTypes(),
    enabled: open,
  });
  const types = useMemo(
    () => (typesQuery.data ?? []).filter((type) => type.status === "active"),
    [typesQuery.data],
  );

  useEffect(() => {
    if (!open) {
      setPlayer(initialPlayer ?? null);
      setContributionTypeId(initialContributionTypeId ?? "");
      setDefaultApplied(initialContributionTypeId !== undefined);
      setAmount("");
      setMethod("cash");
      setReference("");
      setPaidOn(todayIsoDate());
      setAttachment(null);
      setErrors({});
      setSubmitError(null);
      setConfirmOpen(false);
      clientUuid.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Défaut : type mensuel (simplification ci-dessus), appliqué une seule
  // fois dès que la liste est chargée.
  useEffect(() => {
    if (!open || defaultApplied || types.length === 0) return;
    const defaultId = pickDefaultContributionTypeId(types);
    if (defaultId !== undefined) setContributionTypeId(defaultId);
    setDefaultApplied(true);
  }, [open, defaultApplied, types]);

  const debouncedAmount = useDebouncedValue(amount, 250);
  const previewEnabled =
    open && Boolean(player) && contributionTypeId !== "" && isPositiveAmount(debouncedAmount);

  const previewQuery = useQuery<PaymentPreview>({
    queryKey: [
      "treasury",
      "payment-preview",
      player?.id,
      contributionTypeId,
      debouncedAmount,
      paidOn,
    ],
    queryFn: () =>
      previewPayment({
        membership_id: Number(player!.id),
        contribution_type_id: Number(contributionTypeId),
        amount: toApiAmount(debouncedAmount),
        paid_on: paidOn,
      }),
    enabled: previewEnabled,
  });

  // Répartition rappelée dans la confirmation (CDC 4.4.4) : uniquement celle
  // de l'aperçu de l'API, jamais déduite ici ; rien si l'aperçu est absent,
  // en erreur, périmé (montant en cours de saisie) ou si le type est libre.
  const previewData = previewQuery.data;
  const confirmAllocations =
    previewEnabled &&
    !previewQuery.isError &&
    previewData &&
    !previewData.is_free_type &&
    amount === debouncedAmount
      ? previewData.allocations
      : [];

  // Un joueur ou un type prérempli (§4.1 de la fiche de la grille des
  // cotisations) ne rend pas la modale « modifiée » tant que la personne n'a
  // rien changé : sinon fermer une modale ouverte pré-remplie déclencherait
  // toujours la confirmation d'abandon.
  const isDirty = Boolean(
    (player && player.id !== initialPlayer?.id) ||
      amount ||
      reference ||
      attachment ||
      (contributionTypeId !== "" && contributionTypeId !== initialContributionTypeId),
  );

  function validate(): FormErrors {
    const next: FormErrors = {};
    if (!player) next.player = "Choisissez un joueur.";
    if (contributionTypeId === "") next.type = "Choisissez un type de cotisation.";
    if (!isPositiveAmount(amount)) {
      next.amount = "Saisissez un montant supérieur à 0.";
    }
    if (method !== "cash" && !reference.trim()) {
      next.reference = "Indiquez la référence de la transaction.";
    }
    if (!paidOn) {
      next.paidOn = "Ce champ est obligatoire.";
    } else if (paidOn > todayIsoDate()) {
      next.paidOn = "La date ne peut pas être dans le futur.";
    }
    return next;
  }

  function inputSignature(): string {
    return JSON.stringify([
      player?.id,
      contributionTypeId,
      toApiAmount(amount),
      method,
      reference.trim(),
      paidOn,
      attachment ? [attachment.name, attachment.size, attachment.lastModified] : null,
    ]);
  }

  function handleConfirm(): void {
    const nextErrors = validate();
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    setSubmitError(null);
    // Un UUID par tentative : créé à l'ouverture de la confirmation, conservé
    // pour un nouvel essai tant que la saisie ne change pas.
    clientUuid.get(inputSignature());
    setConfirmOpen(true);
  }

  async function submitPayment(): Promise<void> {
    if (!player || contributionTypeId === "") return;
    if (confirmSubmitting) return;
    setConfirmSubmitting(true);
    try {
      const payment = await createPayment({
        membership_id: Number(player.id),
        contribution_type_id: Number(contributionTypeId),
        amount: toApiAmount(amount),
        paid_on: paidOn,
        method,
        reference: reference.trim(),
        attachment,
        client_uuid: clientUuid.get(inputSignature()),
      });
      clientUuid.reset();
      setConfirmOpen(false);
      onRecorded();
      showToast(`Paiement enregistré. Reçu n° ${payment.receipt_number} envoyé à ${player.firstName}.`);
      onClose();
    } catch (error) {
      // Erreur métier (gel des écritures, type archivé…) : la modale de
      // paiement reprend la main avec le bandeau d'erreur du corps.
      setConfirmOpen(false);
      setSubmitError(
        error instanceof ApiError && error.status === 409 && error.code === "client_uuid_conflict"
          ? CLIENT_UUID_CONFLICT_MESSAGE
          : apiErrorMessage(error),
      );
    } finally {
      setConfirmSubmitting(false);
    }
  }

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="Enregistrer un paiement"
        size="md"
        level={level}
        isDirty={isDirty}
        confirmLabel="Enregistrer"
        onConfirm={handleConfirm}
      >
        <div className="space-y-4">
          {submitError ? <Banner variant="danger">{submitError}</Banner> : null}

          <div>
            <label className="mb-1 block text-sm font-medium text-text" htmlFor="record-payment-player">
              Joueur
            </label>
            <PlayerSearch
              value={player}
              onChange={setPlayer}
              searchPlayers={searchActiveClubPlayers}
              ariaLabel="Nom ou numéro du joueur"
            />
            {errors.player ? <p className="mt-1 text-xs text-status-danger-fg">{errors.player}</p> : null}
          </div>

          <label className="block text-sm font-medium text-text">
            Type de cotisation
            <select
              id="record-payment-type"
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
              value={contributionTypeId}
              onChange={(event) => setContributionTypeId(Number(event.target.value))}
              disabled={typesQuery.isLoading}
            >
              <option value="" disabled>
                Choisissez un type
              </option>
              {types.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.name}
                  {type.amount ? ` — ${formatAmount(type.amount, currency)}` : ""}
                </option>
              ))}
            </select>
            {errors.type ? <p className="mt-1 text-xs text-status-danger-fg">{errors.type}</p> : null}
          </label>

          <MoneyField
            label="Montant"
            currency={currency}
            value={amount}
            onChange={setAmount}
            error={errors.amount}
          />

          <SegmentedControl
            label="Mode"
            value={method}
            onChange={setMethod}
            options={METHOD_OPTIONS}
          />

          {method !== "cash" ? (
            <TextField
              label="Référence"
              value={reference}
              onChange={setReference}
              error={errors.reference}
            />
          ) : null}

          <TextField
            label="Date"
            type="date"
            value={paidOn}
            onChange={setPaidOn}
            max={todayIsoDate()}
            error={errors.paidOn}
          />

          <div>
            <label className="mb-1 block text-sm font-medium text-text" htmlFor="record-payment-attachment">
              Pièce jointe <span className="font-normal text-text-muted">(facultatif)</span>
            </label>
            <input
              id="record-payment-attachment"
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.pdf"
              onChange={(event) => setAttachment(event.target.files?.[0] ?? null)}
              className="block w-full text-sm text-text"
            />
          </div>

          <PaymentPreviewPanel
            enabled={previewEnabled}
            query={previewQuery}
            currency={currency}
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmOpen}
        danger={false}
        title={`Valider ce paiement de ${formatAmount(amount || "0", currency)} ?`}
        description={
          player ? (
            <div className="space-y-2 text-base">
              <p>
                Le paiement de {player.firstName} {player.lastName} sera enregistré et un reçu lui sera
                envoyé. Il ne pourra plus être supprimé, seulement annulé.
              </p>
              {confirmAllocations.length > 0 ? (
                <div>
                  <p className="font-medium text-text">Répartition</p>
                  <ul className="mt-1 space-y-1 text-sm" data-testid="confirm-allocations">
                    {confirmAllocations.slice(0, MAX_CONFIRM_LINES).map((line) => (
                      <li key={line.period} className="flex justify-between gap-2">
                        <span>{formatMonthYear(line.period)}</span>
                        <span className="tabular-nums">{formatAmount(line.amount, currency)}</span>
                      </li>
                    ))}
                  </ul>
                  {confirmAllocations.length > MAX_CONFIRM_LINES ? (
                    <p className="mt-1 text-sm">
                      et {confirmAllocations.length - MAX_CONFIRM_LINES} autres
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : undefined
        }
        confirmLabel="Valider"
        loadingLabel="Validation…"
        loading={confirmSubmitting}
        onConfirm={() => void submitPayment()}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}

interface PaymentPreviewPanelProps {
  enabled: boolean;
  query: ReturnType<typeof useQuery<PaymentPreview>>;
  currency: string;
}

function PaymentPreviewPanel({ enabled, query, currency }: PaymentPreviewPanelProps) {
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
    return (
      <p className="text-sm text-status-danger-fg">
        Aperçu indisponible. Vérifiez les champs.
      </p>
    );
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

  const afterStatusKey = preview.after.is_in_good_standing ? "in_good_standing" : "in_debt";

  return (
    <div className="space-y-3 rounded-md bg-surface-muted p-3">
      <p className="text-sm font-medium text-text">Répartition</p>
      <ul className="space-y-1 text-sm text-text">
        {preview.allocations.map((line) => (
          <li key={line.period} className="flex justify-between gap-2">
            <span>{formatMonthYear(line.period)}</span>
            <span className="tabular-nums">{formatAmount(line.amount, currency)}</span>
            <span>{ALLOCATION_STATUS_LABELS[line.status] ?? line.status}</span>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2 text-sm">
        <span>
          Solde actuel : {formatAmount(preview.current.balance, currency)} → Nouveau solde :{" "}
          {formatAmount(preview.after.balance, currency)}
        </span>
        <StatusBadge
          status={afterStatusKey}
          detail={afterStatusKey === "in_debt" ? formatAmount(preview.after.amount_due, currency) : undefined}
        />
      </div>
    </div>
  );
}
