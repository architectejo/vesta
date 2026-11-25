import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listPendingPresidentDecisions,
  listPendingSponsorSignatures,
  type MembershipApplication,
} from "../../../api/clubs";
import { Avatar, EmptyState, Loader, StatusBadge, useToast } from "../../../design-system";
import { useDeepLink } from "../../../hooks/useDeepLink";
import { MembershipDecisionModal } from "./MembershipDecisionModal";
import { SponsorSignatureModal } from "./SponsorSignatureModal";
import { daysSince, personName } from "./applicationText";

export const APPLICATION_QUERY_KEYS = [
  ["applications"],
  ["membership-application"],
  ["club-players"],
  ["player-card"],
] as const;

/** Rafraîchit tout ce qui dépend d'un dossier d'adhésion après une action. */
export function useInvalidateApplications(): () => void {
  const queryClient = useQueryClient();
  return () => {
    for (const queryKey of APPLICATION_QUERY_KEYS) void queryClient.invalidateQueries({ queryKey });
  };
}

function ApplicationRow({
  application,
  detail,
  onClick,
}: {
  application: MembershipApplication;
  detail: React.ReactNode;
  onClick?: () => void;
}) {
  const content = (
    <>
      <span className="flex min-w-0 items-center gap-2">
        <Avatar name={personName(application.player)} photoUrl={application.player?.photo} size={32} />
        <span className="truncate text-sm text-text">{personName(application.player)}</span>
      </span>
      {detail}
    </>
  );
  return onClick ? (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-10 w-full items-center justify-between gap-2 py-2 text-left hover:bg-surface-muted"
    >
      {content}
    </button>
  ) : (
    <div className="flex min-h-10 w-full items-center justify-between gap-2 py-2">{content}</div>
  );
}

/**
 * Carte « Adhésions à traiter » : fiches à signer par le parrain connecté
 * (CDC 4.3 étape 4) et, pour le Président, parrainages refusés ou sans
 * réponse (CDC 4.3 cas limites ; 10.3 n° 71 : alerte seule si silence).
 */
export function MembershipFollowUpCard({
  isPresident,
  profileReady = true,
}: {
  isPresident: boolean;
  /** Faux tant que les rôles de l'utilisateur ne sont pas connus (évite un faux « plus d'action »). */
  profileReady?: boolean;
}) {
  const invalidate = useInvalidateApplications();
  const { showToast } = useToast();
  const [deepLinkedId, setDeepLinkedId] = useState<number | null>(null);
  const [signing, setSigning] = useState<MembershipApplication | null>(null);
  const [deciding, setDeciding] = useState<MembershipApplication | null>(null);

  const signaturesQuery = useQuery({ queryKey: ["applications", "to-sign"], queryFn: listPendingSponsorSignatures });
  const decisionsQuery = useQuery({
    queryKey: ["applications", "to-decide"],
    queryFn: listPendingPresidentDecisions,
    enabled: isPresident,
  });

  const signatures = signaturesQuery.data ?? [];
  const refused = decisionsQuery.data?.refused ?? [];
  const awaiting = decisionsQuery.data?.awaiting_sponsor ?? [];

  // Lien depuis une notification (`?adhesion=<id>`) : ouvre la modale adaptée
  // (signature du parrain, décision du Président) une fois les listes chargées.
  useDeepLink("adhesion", setDeepLinkedId);
  const listsReady = profileReady && signaturesQuery.isSuccess && (!isPresident || decisionsQuery.isSuccess);
  useEffect(() => {
    if (deepLinkedId === null || !listsReady) return;
    const toSign = signatures.find((a) => a.id === deepLinkedId);
    const toDecide = [...refused, ...awaiting].find((a) => a.id === deepLinkedId);
    if (toSign) setSigning(toSign);
    else if (toDecide) setDeciding(toDecide);
    else showToast("Cette adhésion ne demande plus d'action de votre part.");
    setDeepLinkedId(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLinkedId, listsReady]);
  const nothing =
    signaturesQuery.isSuccess &&
    signatures.length === 0 &&
    (!isPresident || (decisionsQuery.isSuccess && refused.length === 0 && awaiting.length === 0));

  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4" aria-label="Adhésions à traiter">
      <h2 className="text-base font-semibold text-text">Adhésions à traiter</h2>
      <div className="mt-2 space-y-3">
        {signaturesQuery.isLoading || (isPresident && decisionsQuery.isLoading) ? (
          <Loader loading variant="list" count={2} />
        ) : signaturesQuery.isError || (isPresident && decisionsQuery.isError) ? (
          <EmptyState
            variant="error"
            actionLabel="Réessayer"
            onAction={() => {
              void signaturesQuery.refetch();
              if (isPresident) void decisionsQuery.refetch();
            }}
          />
        ) : nothing ? (
          <EmptyState message="Aucune adhésion à traiter pour l'instant." />
        ) : (
          <>
            {signatures.length > 0 ? (
              <div>
                <h3 className="text-sm font-semibold text-text">Fiches à signer</h3>
                <div className="divide-y divide-border">
                  {signatures.map((application) => (
                    <ApplicationRow
                      key={application.id}
                      application={application}
                      detail={<StatusBadge status="pending" detail="À signer" />}
                      onClick={() => setSigning(application)}
                    />
                  ))}
                </div>
              </div>
            ) : null}
            {refused.length > 0 ? (
              <div>
                <h3 className="text-sm font-semibold text-text">Parrainages refusés</h3>
                <div className="divide-y divide-border">
                  {refused.map((application) => (
                    <ApplicationRow
                      key={application.id}
                      application={application}
                      detail={<StatusBadge status="refused" detail="Décision à prendre" />}
                      onClick={() => setDeciding(application)}
                    />
                  ))}
                </div>
              </div>
            ) : null}
            {awaiting.length > 0 ? (
              <div>
                <h3 className="text-sm font-semibold text-text">Parrains sans réponse</h3>
                <div className="divide-y divide-border">
                  {awaiting.map((application) => {
                    const days = daysSince(application.president_alerted_at);
                    return (
                      <ApplicationRow
                        key={application.id}
                        application={application}
                        detail={
                          <StatusBadge
                            status="pending"
                            detail={days !== null ? `Sans réponse (alerte il y a ${days} j)` : "Sans réponse"}
                          />
                        }
                        onClick={() => setDeciding(application)}
                      />
                    );
                  })}
                </div>
              </div>
            ) : null}
          </>
        )}
      </div>

      {signing ? (
        <SponsorSignatureModal
          application={signing}
          onClose={() => setSigning(null)}
          onDone={() => {
            setSigning(null);
            invalidate();
          }}
        />
      ) : null}
      {deciding ? (
        <MembershipDecisionModal
          application={deciding}
          onClose={() => setDeciding(null)}
          onDone={() => {
            setDeciding(null);
            invalidate();
          }}
        />
      ) : null}
    </section>
  );
}
