import { useQuery } from "@tanstack/react-query";
import { getContributeInfo, getSocialAssistanceScales } from "../../api/treasury";
import { EmptyState, Modal } from "../../design-system";
import { formatAmount } from "../treasury/money";

export interface AssistanceScalesModalProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Consultation des barèmes d'assistance sociale du club (CDC 4.5.3 : lecture
 * par tout membre actif). Montants, délais et devise viennent de l'API.
 */
export function AssistanceScalesModal({ open, onClose }: AssistanceScalesModalProps) {
  const scalesQuery = useQuery({
    queryKey: ["treasury", "social-assistance-scales"],
    queryFn: getSocialAssistanceScales,
    enabled: open,
  });
  const contributeQuery = useQuery({ queryKey: ["treasury", "contribute-info"], queryFn: getContributeInfo, enabled: open });
  const currency = contributeQuery.data?.currency;
  const scales = scalesQuery.data ?? [];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Barèmes d'assistance sociale"
      size="md"
      loading={scalesQuery.isLoading}
      cancelLabel="Fermer"
    >
      {scalesQuery.isError ? (
        <EmptyState
          variant="error"
          message="Impossible de charger les barèmes."
          actionLabel="Réessayer"
          onAction={() => void scalesQuery.refetch()}
        />
      ) : scales.length === 0 ? (
        <EmptyState message="Le club n'a pas encore défini de barème d'assistance." />
      ) : (
        <ul className="divide-y divide-border">
          {scales.map((scale) => (
            <li key={scale.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="text-text">{scale.event_type_label}</span>
              <span className="text-right text-text">
                <span className="tabular-nums">{currency ? formatAmount(scale.amount, currency) : scale.amount}</span>
                <span className="block text-xs text-text-muted">Délai : {scale.processing_days} jours</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
