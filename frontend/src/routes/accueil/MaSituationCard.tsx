import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { getContributeInfo, getMyBalance } from "../../api/treasury";
import { listSuspensions } from "../../api/sport";
import { Button, EmptyState, Skeleton, StatusBadge } from "../../design-system";

/**
 * Carte « Ma situation » (club-accueil.md §4 point 4). Jamais d'état vide
 * (CLAUDE.md §2.2 : le solde est toujours calculé, 0 compris).
 *
 * Écart documenté (voir compte rendu) : la spec demande aussi « Prochaine
 * échéance : {montant} le {date} » et le badge d'aptitude (Blessé). Aucune
 * des deux n'est exposée par une API aujourd'hui :
 * - `/treasury/my-balance/` renvoie un solde et un montant dû, pas de date
 *   de prochaine échéance -- remplacé ici par la raison déjà formulée par
 *   l'API (même principe que CLAUDE.md §2.2 : « l'interface affiche la
 *   raison fournie par l'API »).
 * - l'aptitude du joueur n'est exposée que par la fiche de santé complète
 *   (`getHealthRecord`), qui journalise une consultation à chaque appel
 *   (`medical.record.viewed`, `apps.medical.services.view_health_record_as_player`).
 *   L'auto-charger à chaque passage par l'accueil journaliserait une
 *   « consultation » à chaque ouverture de l'application -- déjà écarté pour
 *   la même raison par `ProfilPage` (voir son commentaire d'en-tête).
 */
export function MaSituationCard({ membershipId }: { membershipId: number }) {
  const navigate = useNavigate();

  const balanceQuery = useQuery({ queryKey: ["treasury", "my-balance"], queryFn: getMyBalance });
  const suspensionsQuery = useQuery({
    queryKey: ["sport", "suspensions", "mine", membershipId],
    queryFn: () => listSuspensions({ membershipId, active: true }),
  });
  const contributeQuery = useQuery({ queryKey: ["treasury", "contribute-info"], queryFn: getContributeInfo });

  const loading = balanceQuery.isLoading || suspensionsQuery.isLoading;
  const isSuspended = (suspensionsQuery.data?.results.length ?? 0) > 0;
  const suspension = suspensionsQuery.data?.results[0];

  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
      <h2 className="text-base font-semibold text-text">Ma situation</h2>

      {loading ? (
        <div className="mt-2">
          <Skeleton variant="kpi" />
        </div>
      ) : balanceQuery.isError ? (
        <div className="mt-2">
          <EmptyState
            variant="error"
            message="Impossible de charger votre situation."
            actionLabel="Réessayer"
            onAction={() => void balanceQuery.refetch()}
          />
        </div>
      ) : balanceQuery.data ? (
        <div className="mt-2 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={balanceQuery.data.is_in_good_standing ? "in_good_standing" : "in_debt"} />
            {isSuspended ? (
              <StatusBadge
                status="suspended"
                detail={
                  suspension
                    ? `${suspension.matches_remaining} match${suspension.matches_remaining > 1 ? "s" : ""} restant${suspension.matches_remaining > 1 ? "s" : ""}`
                    : undefined
                }
              />
            ) : null}
          </div>
          <p className="text-xl font-semibold tabular-nums text-text">
            Solde : {balanceQuery.data.balance} {balanceQuery.data.currency}
          </p>
          <p className="text-sm text-text-muted">{balanceQuery.data.reason}</p>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            {contributeQuery.data?.payment_link_configured && contributeQuery.data.payment_link_url ? (
              <Button
                variant="primary"
                size="sm"
                onClick={() => window.open(contributeQuery.data?.payment_link_url ?? "", "_blank", "noopener,noreferrer")}
              >
                Contribuer
              </Button>
            ) : null}
            <Button variant="ghost" size="sm" onClick={() => navigate("/profil")}>
              Voir mon profil
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
