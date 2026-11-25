import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getMembershipApplication, getMyProfile } from "../../../api/clubs";
import { Button } from "../../../design-system";
import { useInvalidateApplications } from "./MembershipFollowUpCard";
import { MembershipDecisionModal } from "./MembershipDecisionModal";
import { MembershipFeePaymentModal } from "./MembershipFeePaymentModal";
import { SponsorSignatureModal } from "./SponsorSignatureModal";

type Open = "sign" | "decide" | "fee" | null;

/**
 * Boutons d'adhésion du pied de la « Fiche du joueur » d'un joueur « En
 * attente » (club-comite-bureau.md §4.7). Un bouton n'apparaît que si l'API a
 * accepté de servir le dossier (sinon aucun bouton) et selon le rôle de
 * l'utilisateur ; l'API reste seule juge à l'exécution.
 */
export function MembershipActions({ membershipId }: { membershipId: number }) {
  const [open, setOpen] = useState<Open>(null);
  const invalidate = useInvalidateApplications();

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile });
  const applicationQuery = useQuery({
    queryKey: ["membership-application", membershipId],
    queryFn: () => getMembershipApplication(membershipId),
    retry: false,
  });

  const application = applicationQuery.data;
  const profile = profileQuery.data;
  if (!application || !profile) return null;

  const roles = profile.roles.map((r) => r.role);
  const isPresident = roles.includes("president");
  const isTreasurer = roles.includes("treasurer") || roles.includes("assistant_treasurer");
  const isSponsor = application.sponsor?.membership_id === profile.membership_id;
  const active = application.resolved_at === null && application.membership_status === "pending";

  const canSign =
    active && isSponsor && application.sponsor_decision === "pending" && application.generated_at !== null;
  const canDecide = active && isPresident && application.sponsor_decision === "refused";
  const canPayFee = active && isTreasurer && !application.membership_fee_paid && application.sponsor_decision !== "refused";

  function done(): void {
    setOpen(null);
    invalidate();
  }

  return (
    <>
      {canPayFee ? (
        <Button variant="secondary" size="md" onClick={() => setOpen("fee")}>
          Enregistrer les frais d'adhésion
        </Button>
      ) : null}
      {canDecide ? (
        <Button variant="primary" size="md" onClick={() => setOpen("decide")}>
          Décider de l'adhésion
        </Button>
      ) : null}
      {canSign ? (
        <Button variant="primary" size="md" onClick={() => setOpen("sign")}>
          Signer la fiche d'adhésion
        </Button>
      ) : null}

      {open === "sign" ? (
        <SponsorSignatureModal application={application} level={2} onClose={() => setOpen(null)} onDone={done} />
      ) : null}
      {open === "decide" ? (
        <MembershipDecisionModal application={application} level={2} onClose={() => setOpen(null)} onDone={done} />
      ) : null}
      {open === "fee" ? (
        <MembershipFeePaymentModal application={application} level={2} onClose={() => setOpen(null)} onDone={done} />
      ) : null}
    </>
  );
}
