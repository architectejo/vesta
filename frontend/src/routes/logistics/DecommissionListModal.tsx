import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listDecommissions, type DecommissionStatus } from "../../api/logistics";
import { EmptyState, Loader, Modal, SegmentedControl } from "../../design-system";
import { DecommissionRows } from "./DecommissionList";

type StatusFilter = DecommissionStatus | "all";

const STATUS_OPTIONS: Array<{ value: StatusFilter; label: string }> = [
  { value: "pending", label: "En attente" },
  { value: "done", label: "Déclassés" },
  { value: "cancelled", label: "Annulés" },
  { value: "all", label: "Tous" },
];

export interface DecommissionListModalProps {
  open: boolean;
  onClose: () => void;
  onOpenDecommission: (id: number) => void;
}

/** Liste complète des déclassements (spec B4 §3.1, « Voir plus »), filtrée par l'API. */
export function DecommissionListModal({ open, onClose, onOpenDecommission }: DecommissionListModalProps) {
  const [status, setStatus] = useState<StatusFilter>("pending");

  useEffect(() => {
    if (open) setStatus("pending");
  }, [open]);

  const query = useQuery({
    queryKey: ["logistics", "decommissions", "list", status],
    queryFn: () => listDecommissions(status === "all" ? {} : { status }),
    enabled: open,
  });
  const rows = query.data?.results ?? [];

  return (
    <Modal open={open} onClose={onClose} title="Déclassements" size="lg" cancelLabel="Fermer" hideFooter={false}>
      <div className="space-y-4">
        <SegmentedControl label="Statut" value={status} onChange={setStatus} options={STATUS_OPTIONS} wrapOnMobile />
        {query.isLoading ? (
          <Loader loading variant="list" count={3} />
        ) : query.isError ? (
          <EmptyState
            variant="error"
            message="Impossible de charger les déclassements."
            actionLabel="Réessayer"
            onAction={() => void query.refetch()}
          />
        ) : rows.length === 0 ? (
          <EmptyState message="Aucun élément à déclasser." />
        ) : (
          <DecommissionRows rows={rows} onOpen={onOpenDecommission} />
        )}
      </div>
    </Modal>
  );
}
