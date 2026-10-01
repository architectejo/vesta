import { useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import { getMyProfile } from "../../api/clubs";
import { listMovements } from "../../api/logistics";
import {
  getExpense,
  getExpenseSummary,
  refuseExpense,
  releaseExpense,
  releaseExpenseWithDerogation,
  uploadExpenseReceipt,
  downloadExpenseAttachment,
  type TreasuryCapabilities,
} from "../../api/treasury";
import { Banner, Button, Modal, PinPrompt, StatusBadge, TextArea, useToast } from "../../design-system";
import { getMaterialAccess } from "../logistics/materielAccess";
import { AttachmentLink } from "./AttachmentLink";
import { expenseStatusKey } from "./expenseLabels";
import { formatAmount, formatDateFr } from "./money";
import { formatPinError } from "./pinErrors";
import { ReceiptUploadModal } from "./ReceiptUploadModal";

const EXPENSE_QUERY_KEY_PREFIX = ["treasury", "expense"] as const;
const EXPENSE_SUMMARY_QUERY_KEY = ["treasury", "expense-summary"] as const;

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.";
}

export interface ExpenseDetailModalProps {
  expenseId: number | null;
  capabilities: TreasuryCapabilities;
  onClose: () => void;
  /** Après refus, libération, dérogation ou dépôt du justificatif : rafraîchit les listes. */
  onChanged: () => void;
}

type PendingAction = "release" | "derogation" | null;

/**
 * Modale « Détail de la dépense » (fiche `tresorerie-depenses-assistance.md`
 * §3.3 ; CDC 4.5.2, 7.2). Les cinq branches dépendent du statut renvoyé par
 * l'API et des capacités du rôle courant (`TreasuryCapabilities`), jamais
 * d'une matrice recopiée dans l'interface.
 */
export function ExpenseDetailModal({ expenseId, capabilities, onClose, onChanged }: ExpenseDetailModalProps) {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const open = expenseId !== null;

  const [refuseOpen, setRefuseOpen] = useState(false);
  const [refuseReason, setRefuseReason] = useState("");
  const [refuseError, setRefuseError] = useState<string | undefined>(undefined);
  const [refusing, setRefusing] = useState(false);

  const [derogationOpen, setDerogationOpen] = useState(false);
  const [derogationReason, setDerogationReason] = useState("");
  const [derogationReasonError, setDerogationReasonError] = useState<string | undefined>(undefined);

  const [pinAction, setPinAction] = useState<PendingAction>(null);
  const [pinSubmitting, setPinSubmitting] = useState(false);
  const [pinError, setPinError] = useState<string | undefined>(undefined);

  const [receiptOpen, setReceiptOpen] = useState(false);
  const [receiptSubmitting, setReceiptSubmitting] = useState(false);
  const [receiptError, setReceiptError] = useState<string | undefined>(undefined);

  const [actionError, setActionError] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (!open) {
      setRefuseOpen(false);
      setRefuseReason("");
      setRefuseError(undefined);
      setDerogationOpen(false);
      setDerogationReason("");
      setDerogationReasonError(undefined);
      setPinAction(null);
      setPinError(undefined);
      setReceiptOpen(false);
      setReceiptError(undefined);
      setActionError(undefined);
    }
  }, [open]);

  const expenseQuery = useQuery({
    queryKey: [...EXPENSE_QUERY_KEY_PREFIX, expenseId],
    queryFn: () => getExpense(expenseId as number),
    enabled: open,
  });
  const expense = expenseQuery.data;

  const summaryQuery = useQuery({
    queryKey: EXPENSE_SUMMARY_QUERY_KEY,
    queryFn: () => getExpenseSummary(),
    enabled: open && expense?.status === "pending",
  });

  // Section « Matériel acheté » (fiche `logistique.md` §5.1) : lecture seule,
  // visible pour le Président, le Vice-président et le Trésorier (accès en
  // lecture au matériel), masquée pour le Trésorier adjoint. Le lien est
  // porté par le mouvement de stock (`StockMovement.expense`), lu ici via le
  // registre du matériel filtré par dépense -- aucun champ dédié n'est
  // exposé côté `apps.treasury` pour cette liaison.
  const profileQuery = useQuery({
    queryKey: ["profile", "me"],
    queryFn: getMyProfile,
    staleTime: 60_000,
    enabled: open,
  });
  const materialAccess = getMaterialAccess(profileQuery.data?.roles);
  const purchasedMaterialQuery = useQuery({
    queryKey: ["logistics", "movements", "expense", expenseId],
    queryFn: () => listMovements({ expense: expenseId as number }),
    enabled: open && materialAccess.canReadMaterial,
  });
  const purchasedMovements = purchasedMaterialQuery.data?.results ?? [];

  /** Après une action réussie : rafraîchit le détail affiché et les listes de la page. */
  function afterAction(): void {
    setActionError(undefined);
    onChanged();
    void expenseQuery.refetch();
  }

  async function handleRefuse(): Promise<void> {
    if (!refuseReason.trim()) {
      setRefuseError("Indiquez le motif du refus.");
      return;
    }
    if (!expense) return;
    setRefusing(true);
    setRefuseError(undefined);
    try {
      await refuseExpense(expense.id, refuseReason.trim());
      setRefuseOpen(false);
      const submitterName = expense.created_by.name ?? "Le saisisseur";
      afterAction();
      showToast(`Dépense refusée. ${submitterName} a été prévenu.`);
    } catch (error) {
      setRefuseError(apiErrorMessage(error));
    } finally {
      setRefusing(false);
    }
  }

  function openRelease(): void {
    setPinError(undefined);
    setPinAction("release");
  }

  function openDerogation(): void {
    setDerogationReason("");
    setDerogationReasonError(undefined);
    setDerogationOpen(true);
  }

  function confirmDerogationReason(): void {
    if (!derogationReason.trim()) {
      setDerogationReasonError("Le motif de la dérogation est obligatoire.");
      return;
    }
    setDerogationOpen(false);
    setPinError(undefined);
    setPinAction("derogation");
  }

  async function submitPin(pin: string): Promise<void> {
    if (!expense) return;
    setPinSubmitting(true);
    setPinError(undefined);
    try {
      if (pinAction === "release") {
        await releaseExpense(expense.id, pin);
        setPinAction(null);
        afterAction();
        showToast("Dépense libérée. Le justificatif est attendu sous peu.");
      } else if (pinAction === "derogation") {
        await releaseExpenseWithDerogation(expense.id, derogationReason.trim(), pin);
        setPinAction(null);
        afterAction();
        showToast("Dépense libérée par dérogation.");
      }
    } catch (error) {
      if (
        error instanceof ApiError &&
        (error.status === 400 || error.status === 423) &&
        error.raw &&
        typeof error.raw === "object" &&
        ("attempts_remaining" in (error.raw as object) || "locked_until" in (error.raw as object))
      ) {
        setPinError(formatPinError(error));
      } else {
        setPinAction(null);
        setActionError(apiErrorMessage(error));
      }
    } finally {
      setPinSubmitting(false);
    }
  }

  async function handleReceiptSubmit(file: File): Promise<void> {
    if (!expense) return;
    setReceiptSubmitting(true);
    setReceiptError(undefined);
    try {
      await uploadExpenseReceipt(expense.id, file);
      setReceiptOpen(false);
      afterAction();
      showToast("Justificatif envoyé.");
    } catch (error) {
      setReceiptError(apiErrorMessage(error));
    } finally {
      setReceiptSubmitting(false);
    }
  }

  const canValidate = capabilities.can_validate_expenses;
  const canDerogate = capabilities.can_derogate;
  const canUploadReceipt = capabilities.can_upload_expense_receipts;

  const blocked = Boolean(expense?.status === "pending" && summaryQuery.data && !summaryQuery.data.can_release);

  function renderBody(): ReactNode {
    if (!expense) return null;
    return (
      <div className="space-y-4">
        {actionError ? <Banner variant="danger">{actionError}</Banner> : null}

        <div className="space-y-2 rounded-md bg-surface-muted p-3 text-sm">
          <div className="flex items-center justify-between gap-2">
            <span className="text-text-muted">Bénéficiaire</span>
            <span className="text-text">{expense.beneficiary_name}</span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-text-muted">Motif</span>
            <span className="text-right text-text">{expense.reason || "—"}</span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-text-muted">Date</span>
            <span className="text-text">{formatDateFr(expense.expense_date)}</span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-text-muted">Saisie par</span>
            <span className="text-text">
              {expense.created_by.name ?? "—"} · {formatDateFr(expense.created_at.slice(0, 10))}
            </span>
          </div>
          {expense.released_at ? (
            <div className="flex items-center justify-between gap-2">
              <span className="text-text-muted">Libérée le</span>
              <span className="text-text">
                {formatDateFr(expense.released_at.slice(0, 10))}
                {expense.released_by?.name ? ` par ${expense.released_by.name}` : ""}
              </span>
            </div>
          ) : null}
          {expense.refusal_reason ? (
            <div className="flex items-center justify-between gap-2">
              <span className="text-text-muted">Motif du refus</span>
              <span className="text-right text-text">{expense.refusal_reason}</span>
            </div>
          ) : null}
          {expense.derogation ? (
            <div className="flex items-center justify-between gap-2">
              <span className="text-text-muted">Motif de la dérogation</span>
              <span className="text-right text-text">{expense.derogation.reason}</span>
            </div>
          ) : null}
        </div>

        <div>
          <p className="mb-2 text-sm font-medium text-text">Justificatif</p>
          {expense.attachments.length === 0 ? (
            <p className="text-sm text-text-muted">Aucun justificatif pour l'instant.</p>
          ) : (
            <div className="space-y-2">
              {expense.attachments.map((attachment) => (
                <AttachmentLink
                  key={attachment.id}
                  label={`Voir ${attachment.kind_label.toLowerCase()} (${formatDateFr(attachment.uploaded_at.slice(0, 10))})`}
                  download={() => downloadExpenseAttachment(attachment.id)}
                />
              ))}
            </div>
          )}
        </div>

        {materialAccess.canReadMaterial && purchasedMovements.length > 0 ? (
          <div>
            <p className="mb-2 text-sm font-medium text-text">Matériel acheté</p>
            <div className="space-y-2">
              {purchasedMovements.map((movement) => (
                <div key={movement.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="text-text">
                    {movement.article.name} · {movement.quantity} {movement.article.unit} · entré le{" "}
                    {formatDateFr(movement.movement_date)}
                  </span>
                  <button
                    type="button"
                    className="shrink-0 font-medium text-primary-text hover:underline"
                    onClick={() => {
                      onClose();
                      navigate(`/materiel?mouvement=${movement.id}`);
                    }}
                  >
                    Voir dans le matériel
                  </button>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {expense.status === "pending" && blocked ? (
          <Banner variant="danger">{summaryQuery.data?.reason}</Banner>
        ) : null}

        {expense.status === "released" || expense.status === "unjustified" ? (
          <Banner variant={expense.is_overdue ? "danger" : "warning"}>
            {expense.is_overdue
              ? `Délai dépassé le ${expense.justification_deadline ? formatDateFr(expense.justification_deadline) : ""}`
              : `À justifier avant le ${expense.justification_deadline ? formatDateFr(expense.justification_deadline) : ""}`}
          </Banner>
        ) : null}
      </div>
    );
  }

  function renderFooter(): ReactNode {
    if (!expense) return undefined;

    if (expense.status === "pending" && canValidate) {
      return (
        <div className="flex w-full flex-wrap items-center justify-end gap-2">
          <Button variant="secondary" size="md" onClick={onClose}>
            Fermer
          </Button>
          <Button variant="secondary" size="md" onClick={() => setRefuseOpen(true)}>
            Refuser
          </Button>
          {blocked && canDerogate ? (
            <Button variant="primary" size="md" onClick={openDerogation}>
              Libérer par dérogation
            </Button>
          ) : null}
          <Button variant="primary" size="md" disabled={blocked} onClick={openRelease}>
            Valider et libérer
          </Button>
        </div>
      );
    }

    if ((expense.status === "released" || expense.status === "unjustified") && canUploadReceipt) {
      return (
        <div className="flex w-full items-center justify-end gap-2">
          <Button variant="secondary" size="md" onClick={onClose}>
            Fermer
          </Button>
          <Button variant="primary" size="md" onClick={() => setReceiptOpen(true)}>
            Ajouter le justificatif
          </Button>
        </div>
      );
    }

    return (
      <div className="flex w-full items-center justify-end">
        <Button variant="secondary" size="md" onClick={onClose}>
          Fermer
        </Button>
      </div>
    );
  }

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={expense ? `Dépense · ${expense.category.name}` : "Dépense"}
        subtitle={expense ? formatAmount(expense.amount, expense.currency) : undefined}
        size="lg"
        loading={expenseQuery.isLoading}
        footer={renderFooter()}
      >
        {expenseQuery.isError ? (
          <p role="alert" className="text-sm text-status-danger-fg">
            Impossible de charger ce détail. Réessayez.
          </p>
        ) : expense ? (
          <div className="space-y-4">
            <StatusBadge status={expenseStatusKey(expense.status)} />
            {renderBody()}
          </div>
        ) : null}
      </Modal>

      <Modal
        open={refuseOpen}
        onClose={() => setRefuseOpen(false)}
        title="Refuser la dépense"
        size="sm"
        level={2}
        isDirty={refuseReason.trim() !== ""}
        isSubmitting={refusing}
        confirmLabel="Refuser la dépense"
        confirmLoadingLabel="Enregistrement…"
        onConfirm={() => void handleRefuse()}
      >
        <TextArea label="Motif du refus" value={refuseReason} onChange={setRefuseReason} error={refuseError} />
      </Modal>

      <Modal
        open={derogationOpen}
        onClose={() => setDerogationOpen(false)}
        title="Libérer par dérogation"
        size="sm"
        level={2}
        isDirty={derogationReason.trim() !== ""}
        confirmLabel="Continuer"
        onConfirm={confirmDerogationReason}
      >
        <TextArea
          label="Motif de la dérogation"
          value={derogationReason}
          onChange={setDerogationReason}
          error={derogationReasonError}
          help="La dérogation sera journalisée et signalée à la prochaine assemblée générale."
        />
      </Modal>

      <PinPrompt
        open={pinAction !== null}
        title="Confirmer avec votre code PIN"
        description={
          pinAction === "derogation"
            ? "Saisissez votre code PIN pour confirmer la dérogation."
            : `Saisissez votre code PIN pour libérer cette dépense de ${expense ? formatAmount(expense.amount, expense.currency) : ""}.`
        }
        isSubmitting={pinSubmitting}
        error={pinError}
        onSubmit={(pin) => void submitPin(pin)}
        onClose={() => setPinAction(null)}
      />

      <ReceiptUploadModal
        open={receiptOpen}
        isSubmitting={receiptSubmitting}
        submitError={receiptError}
        onClose={() => setReceiptOpen(false)}
        onSubmit={(file) => void handleReceiptSubmit(file)}
        level={2}
      />
    </>
  );
}
