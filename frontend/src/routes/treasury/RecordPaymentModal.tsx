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
  Modal,
  MoneyField,
  PinPrompt,
  PlayerSearch,
  SegmentedControl,
  StatusBadge,
  TextField,
  useToast,
  type PlayerSearchResult,
} from "../../design-system";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { formatAmount, formatMonthYear, todayIsoDate } from "./money";
import { formatPinError } from "./pinErrors";

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

  const [pinOpen, setPinOpen] = useState(false);
  const [pinSubmitting, setPinSubmitting] = useState(false);
  const [pinError, setPinError] = useState<string | undefined>(undefined);

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
      setPinError(undefined);
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
    open && Boolean(player) && contributionTypeId !== "" && Number(debouncedAmount.replace(",", ".")) > 0;

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
        amount: debouncedAmount.replace(",", "."),
        paid_on: paidOn,
      }),
    enabled: previewEnabled,
  });

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
    const numericAmount = Number(amount.replace(",", "."));
    if (!amount || Number.isNaN(numericAmount) || numericAmount <= 0) {
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

  function handleConfirm(): void {
    const nextErrors = validate();
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    setSubmitError(null);
    setPinError(undefined);
    setPinOpen(true);
  }

  async function submitPayment(pin: string): Promise<void> {
    if (!player || contributionTypeId === "") return;
    setPinSubmitting(true);
    setPinError(undefined);
    try {
      const payment = await createPayment({
        membership_id: Number(player.id),
        contribution_type_id: Number(contributionTypeId),
        amount: amount.replace(",", "."),
        paid_on: paidOn,
        method,
        reference: reference.trim(),
        attachment,
        pin,
      });
      setPinOpen(false);
      onRecorded();
      showToast(`Paiement enregistré. Reçu n° ${payment.receipt_number} envoyé à ${player.firstName}.`);
      onClose();
    } catch (error) {
      if (error instanceof ApiError && (error.status === 400 || error.status === 423) && error.raw &&
        typeof error.raw === "object" && ("attempts_remaining" in (error.raw as object) || "locked_until" in (error.raw as object))) {
        setPinError(formatPinError(error));
      } else {
        // Erreur métier (gel des écritures, type archivé…) : la modale de
        // paiement reprend la main avec le bandeau d'erreur du corps.
        setPinOpen(false);
        setSubmitError(apiErrorMessage(error));
      }
    } finally {
      setPinSubmitting(false);
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

      <PinPrompt
        open={pinOpen}
        description={
          player ? `Valider le paiement de ${formatAmount(amount || "0", currency)} pour ${player.firstName} ${player.lastName}.` : ""
        }
        isSubmitting={pinSubmitting}
        error={pinError}
        onSubmit={(pin) => void submitPayment(pin)}
        onClose={() => setPinOpen(false)}
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
