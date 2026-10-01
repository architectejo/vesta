import type { ExpenseCategory } from "../../api/treasury";
import { Button, Modal } from "../../design-system";
import { formatAmount } from "./money";
import { KebabMenu } from "./KebabMenu";

export interface ExpenseCategoryDetailModalProps {
  category: ExpenseCategory | null;
  currency: string;
  canEdit: boolean;
  onClose: () => void;
  onEdit: (category: ExpenseCategory) => void;
  onArchive: (category: ExpenseCategory) => void;
}

/**
 * Détail en lecture d'une catégorie de dépense (fiche
 * `tresorerie-depenses-assistance.md` §3.5). Pied « Fermer » / « Modifier » ;
 * menu « … » → « Archiver » (catégorie active seulement).
 */
export function ExpenseCategoryDetailModal({
  category,
  currency,
  canEdit,
  onClose,
  onEdit,
  onArchive,
}: ExpenseCategoryDetailModalProps) {
  const open = category !== null;
  const canArchive = canEdit && category?.status === "active";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={category?.name ?? "Catégorie de dépense"}
      size="sm"
      footer={
        category ? (
          <div className="flex w-full items-center justify-between gap-2">
            {canArchive ? (
              <KebabMenu items={[{ label: "Archiver", danger: true, onSelect: () => onArchive(category) }]} />
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button variant="secondary" size="md" onClick={onClose}>
                Fermer
              </Button>
              {canEdit ? (
                <Button variant="primary" size="md" onClick={() => onEdit(category)}>
                  Modifier
                </Button>
              ) : null}
            </div>
          </div>
        ) : undefined
      }
    >
      {category ? (
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-text-muted">Plafond</dt>
            <dd className="text-text">{category.ceiling ? formatAmount(category.ceiling, currency) : "Aucun"}</dd>
          </div>
          <div>
            <dt className="text-text-muted">Justificatif</dt>
            <dd className="text-text">{category.receipt_required ? "Obligatoire" : "Facultatif"}</dd>
          </div>
          <div>
            <dt className="text-text-muted">Réservation</dt>
            <dd className="text-text">
              {category.good_standing_only ? "Réservée aux membres en ordre" : "Ouverte à tout bénéficiaire"}
            </dd>
          </div>
          {category.status === "archived" ? <p className="text-xs text-text-muted">Catégorie archivée.</p> : null}
        </dl>
      ) : null}
    </Modal>
  );
}
