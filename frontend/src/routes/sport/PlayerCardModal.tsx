import { useQuery } from "@tanstack/react-query";
import { getPlayerCard } from "../../api/clubs";
import { Avatar, EmptyState, Loader, Modal } from "../../design-system";

export interface PlayerCardModalProps {
  open: boolean;
  membershipId: number | null;
  onClose: () => void;
}

/**
 * « Voir la fiche du joueur », lien réutilisé par plusieurs écrans du Lot
 * 3 (panneau d'un pion, menu de composition…). S'appuie sur l'API déjà
 * livrée `GET /clubs/players/{id}/card/` (fiche publique, sans donnée
 * financière ni médicale) plutôt que de dupliquer un affichage.
 */
export function PlayerCardModal({ open, membershipId, onClose }: PlayerCardModalProps) {
  const query = useQuery({
    queryKey: ["clubs", "player-card", membershipId],
    queryFn: () => getPlayerCard(membershipId as number),
    enabled: open && membershipId != null,
  });

  return (
    <Modal open={open} onClose={onClose} title="Fiche du joueur" size="sm" hideFooter loading={query.isLoading}>
      {query.isError ? (
        <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void query.refetch()} />
      ) : query.data ? (
        <div className="flex items-center gap-3">
          <Avatar name={`${query.data.first_name} ${query.data.last_name}`} photoUrl={query.data.photo} size={72} />
          <div className="space-y-0.5">
            <p className="text-base font-medium text-text">
              {query.data.first_name} {query.data.last_name}
            </p>
            <p className="text-sm text-text-muted">
              {[query.data.jersey_number != null ? `n° ${query.data.jersey_number}` : null, query.data.position_label]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
        </div>
      ) : (
        <Loader loading variant="list" count={2} />
      )}
    </Modal>
  );
}
