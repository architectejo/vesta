import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { getMyProfile } from "../../api/clubs";
import { getExpenseSummary, getTreasuryCapabilities } from "../../api/treasury";
import { Banner, Loader } from "../../design-system";
import { getAccueilAccess } from "./accueilAccess";
import { CommuniquesCard } from "./CommuniquesCard";
import { DerniersResultatsCard } from "./DerniersResultatsCard";
import { MaSituationCard } from "./MaSituationCard";
import { ProchainRendezVousCard } from "./ProchainRendezVousCard";
import { VestiaireDuJourCard } from "./VestiaireDuJourCard";

const TODAY_LONG = new Intl.DateTimeFormat("fr-FR", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
}).format(new Date());

/** Bandeau « Dépense non justifiée » (club-accueil.md §4, Trésorier,
 * adjoint, Président). Même source que `DepensesPage` : `can_read_expenses`
 * décide, jamais une liste de rôles recopiée dans l'interface. */
function UnjustifiedExpenseBanner({ canRead }: { canRead: boolean }) {
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["treasury", "expense-summary"],
    queryFn: getExpenseSummary,
    enabled: canRead,
  });
  const summary = query.data;
  if (!canRead || !summary || summary.can_release || summary.blocking_expense_ids.length === 0) return null;
  const firstBlockingId = summary.blocking_expense_ids[0];
  return (
    <Banner
      variant="danger"
      action={
        firstBlockingId !== undefined ? (
          <button
            type="button"
            className="-my-2 shrink-0 py-2 font-medium underline"
            onClick={() => navigate(`/tresorerie/depenses?depense=${firstBlockingId}`)}
          >
            Voir la dépense
          </button>
        ) : undefined
      }
    >
      {summary.reason}
    </Banner>
  );
}

/**
 * Écran d'accueil (docs/ecrans/club-accueil.md). Les cartes « À faire » et
 * « Raccourcis » sont volontairement absentes (§3, §4, §8 de la spec,
 * décision client du 25/09/2026 : reportées après le Lot 5).
 *
 * Voir le compte rendu de la tâche pour les écarts documentés par carte
 * (notamment « Ma situation » et « Prochain rendez-vous », qui dépendent
 * de données que l'API n'expose pas encore entièrement).
 */
export function AccueilPage() {
  const profileQuery = useQuery({
    queryKey: ["profile", "me"],
    queryFn: getMyProfile,
    staleTime: 60_000,
  });
  const capabilitiesQuery = useQuery({
    queryKey: ["treasury", "capabilities"],
    queryFn: getTreasuryCapabilities,
  });

  const profile = profileQuery.data;
  const access = getAccueilAccess(profile?.roles);
  const canReadExpenses = capabilitiesQuery.data?.capabilities.can_read_expenses ?? false;

  return (
    <div className="space-y-4">
      <header>
        {profileQuery.isLoading ? (
          <Loader loading variant="list" count={1} />
        ) : (
          <>
            <h1 className="text-xl font-semibold text-text">
              Bonjour, {profile?.identity.first_name ?? ""}
            </h1>
            <p className="text-sm text-text-muted">
              {profile?.club.name} · {TODAY_LONG}
            </p>
          </>
        )}
      </header>

      {!navigator.onLine ? <Banner variant="info">Vous êtes hors connexion.</Banner> : null}
      <UnjustifiedExpenseBanner canRead={canReadExpenses} />

      {profileQuery.isLoading ? (
        <Loader loading variant="list" listSkeleton="card" count={4} />
      ) : profileQuery.isError || !profile ? (
        <Banner variant="danger">Impossible de charger votre profil. Rechargez la page.</Banner>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12 lg:items-start">
          <div className="order-1 lg:order-none lg:col-span-8 lg:col-start-1 lg:row-start-1">
            <CommuniquesCard canPublish={access.canPublishAnnouncement} />
          </div>
          <div className="order-2 lg:order-none lg:col-span-8 lg:col-start-1 lg:row-start-2">
            <VestiaireDuJourCard isPresident={access.isPresident} />
          </div>
          <div className="order-3 lg:order-none lg:col-span-4 lg:col-start-9 lg:row-start-1">
            <MaSituationCard membershipId={profile.membership_id} />
          </div>
          <div className="order-4 lg:order-none lg:col-span-4 lg:col-start-9 lg:row-start-2">
            <ProchainRendezVousCard membershipId={profile.membership_id} isCoach={access.isCoach} />
          </div>
          <div className="order-5 lg:order-none lg:col-span-8 lg:col-start-1 lg:row-start-3">
            <DerniersResultatsCard />
          </div>
        </div>
      )}
    </div>
  );
}
