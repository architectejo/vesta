import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getMyProfile } from "../../api/clubs";
import {
  getAvailability,
  listClubOffers,
  listMarket,
  listMyOffers,
  listThreads,
  setAvailability,
  type ClubBrief,
  type TransferOffer,
} from "../../api/mercato";
import {
  Avatar,
  Banner,
  Button,
  DataTable,
  EmptyState,
  Loader,
  SegmentedControl,
  StatusBadge,
  Tabs,
  useToast,
  type ClubSearchResult,
  type PlayerSearchResult,
} from "../../design-system";
import { ConversationModal } from "./ConversationModal";
import { EcrireAUnClubModal } from "./EcrireAUnClubModal";
import { FaireUneOffreModal } from "./FaireUneOffreModal";
import { FichePubliqueModal } from "./FichePubliqueModal";
import { getMercatoAccess } from "./mercatoAccess";
import { offerStatusKey } from "./mercatoLabels";
import { OfferDetailModal } from "./OfferDetailModal";
import { WelcomeModal } from "./WelcomeModal";

const PAGE_STEP = 5;

/** Page « Mercato » (fiche `docs/ecrans/mercato.md`, CDC 4.14). */
export function MercatoPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [myOffersLimit, setMyOffersLimit] = useState(PAGE_STEP);
  const [threadsLimit, setThreadsLimit] = useState(PAGE_STEP);
  const [offersTab, setOffersTab] = useState<"sent" | "received">("sent");

  const [publicPlayerId, setPublicPlayerId] = useState<number | null>(null);
  const [offerModal, setOfferModal] = useState<{ id: number; asPlayer: boolean } | null>(null);
  const [makeOfferPlayer, setMakeOfferPlayer] = useState<PlayerSearchResult | null | undefined>(undefined);
  const [writeToClub, setWriteToClub] = useState<{
    club: ClubSearchResult | null;
    aboutPlayer?: string;
    offerId?: number | null;
  } | null>(null);
  const [conversationThreadId, setConversationThreadId] = useState<number | null>(null);
  const [welcomeOffer, setWelcomeOffer] = useState<TransferOffer | null>(null);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const access = getMercatoAccess(profileQuery.data?.roles);
  const clubId = profileQuery.data?.club.id;

  const availabilityQuery = useQuery({ queryKey: ["mercato", "availability"], queryFn: getAvailability });
  const myOffersQuery = useQuery({ queryKey: ["mercato", "my-offers"], queryFn: listMyOffers });

  const marketQuery = useQuery({
    queryKey: ["mercato", "market"],
    queryFn: () => listMarket(),
    enabled: access.canReadMarket,
  });

  const sentOffersQuery = useQuery({
    queryKey: ["mercato", "club-offers", "sent"],
    queryFn: () => listClubOffers({ direction: "sent" }),
    enabled: access.canReadMarket,
  });
  const receivedOffersQuery = useQuery({
    queryKey: ["mercato", "club-offers", "received"],
    queryFn: () => listClubOffers({ direction: "received" }),
    enabled: access.canReadMarket,
  });
  const clubOffersQuery = offersTab === "sent" ? sentOffersQuery : receivedOffersQuery;

  const threadsQuery = useQuery({
    queryKey: ["mercato", "threads"],
    queryFn: listThreads,
    enabled: access.canMakeOfferOrMessage,
  });

  function invalidateOffers(): void {
    void queryClient.invalidateQueries({ queryKey: ["mercato", "my-offers"] });
    void queryClient.invalidateQueries({ queryKey: ["mercato", "club-offers"] });
    void queryClient.invalidateQueries({ queryKey: ["mercato", "market"] });
  }

  async function handleAvailabilityChange(value: "on" | "off"): Promise<void> {
    try {
      await setAvailability(value === "on");
      void availabilityQuery.refetch();
      showToast(value === "on" ? "Vous êtes maintenant sur le marché." : "Vous êtes fermé aux offres.");
    } catch {
      // Échec : retour à la valeur précédente (relecture serveur, la valeur
      // affichée vient toujours de `availabilityQuery.data`, jamais d'un état
      // local optimiste) + toast (fiche §6).
      void availabilityQuery.refetch();
      showToast("Modification non enregistrée. Réessayez.");
    }
  }

  if (profileQuery.isLoading) return <Loader loading variant="page" />;

  const clubName = profileQuery.data?.club.name ?? "";
  const myBlockedOffer = myOffersQuery.data?.results.find((o) => o.status === "blocked_debt");

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">Mercato</h1>
          <p className="text-sm text-text-muted">{clubName}</p>
        </div>
        {access.canMakeOfferOrMessage ? (
          <div className="flex items-center gap-2">
            <Button variant="primary" size="sm" onClick={() => setMakeOfferPlayer(null)}>
              Faire une offre
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setWriteToClub({ club: null })}>
              Écrire à un club
            </Button>
          </div>
        ) : null}
      </header>

      {myBlockedOffer ? (
        <Banner
          variant="danger"
          action={
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setOfferModal({ id: myBlockedOffer.id, asPlayer: true })}>
                Voir l'offre
              </Button>
            </div>
          }
        >
          Votre transfert vers {myBlockedOffer.target_club.name} est bloqué : régularisez {myBlockedOffer.debt_amount}{" "}
          auprès de {myBlockedOffer.origin_club.name} pour obtenir votre quitus.
        </Banner>
      ) : null}

      {/* Ma disponibilité */}
      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <h2 className="mb-2 text-base font-semibold text-text">Ma disponibilité</h2>
        {availabilityQuery.isLoading ? (
          <Loader loading variant="list" count={1} />
        ) : (
          <>
            <SegmentedControl
              label="Ma disponibilité"
              value={availabilityQuery.data?.is_on_transfer_market ? "on" : "off"}
              onChange={(value) => void handleAvailabilityChange(value)}
              options={[
                { value: "off", label: "Fermé aux offres" },
                { value: "on", label: "Sur le marché" },
              ]}
            />
            <p className="mt-2 text-xs text-text-muted">
              Sur le marché, les dirigeants des autres clubs peuvent voir votre fiche publique et vous faire une
              offre.
            </p>
          </>
        )}
      </section>

      {/* Mes offres */}
      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <h2 className="mb-3 text-base font-semibold text-text">Mes offres</h2>
        {myOffersQuery.isLoading ? (
          <Loader loading variant="list" count={2} />
        ) : myOffersQuery.isError ? (
          <EmptyState
            variant="error"
            message="Impossible de charger vos offres."
            actionLabel="Réessayer"
            onAction={() => void myOffersQuery.refetch()}
          />
        ) : (myOffersQuery.data?.results.length ?? 0) === 0 ? (
          <EmptyState
            message="Aucune offre reçue."
            description={
              !availabilityQuery.data?.is_on_transfer_market
                ? "Passez « Sur le marché » pour que les autres clubs puissent vous faire une offre."
                : undefined
            }
          />
        ) : (
          <>
            <ul className="divide-y divide-border">
              {myOffersQuery.data!.results.slice(0, myOffersLimit).map((offer) => (
                <li key={offer.id}>
                  <button
                    type="button"
                    onClick={() => setOfferModal({ id: offer.id, asPlayer: true })}
                    className="flex w-full items-center justify-between gap-2 py-2 text-left"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <Avatar name={offer.target_club.name} photoUrl={offer.target_club.logo} size={24} />
                      <span className="min-w-0">
                        <span className="block truncate text-sm text-text">{offer.target_club.name}</span>
                        <span className="block text-xs text-text-muted">
                          {new Date(offer.created_at).toLocaleDateString("fr-FR")}
                        </span>
                        {offer.status === "blocked_debt" && offer.debt_amount ? (
                          <span className="block text-[14px] text-status-danger-fg">
                            À régulariser : {offer.debt_amount}
                          </span>
                        ) : null}
                      </span>
                    </span>
                    <StatusBadge status={offerStatusKey(offer.status)} />
                  </button>
                </li>
              ))}
            </ul>
            {myOffersQuery.data!.results.length > myOffersLimit ? (
              <div className="mt-2 text-center">
                <Button size="sm" variant="secondary" onClick={() => setMyOffersLimit((l) => l + PAGE_STEP)}>
                  Voir plus
                </Button>
              </div>
            ) : null}
          </>
        )}
      </section>

      {/* Marché */}
      {access.canReadMarket ? (
        <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
          <h2 className="mb-3 text-base font-semibold text-text">Marché</h2>
          <DataTable
            columns={[
              {
                key: "player",
                header: "Joueur",
                widthPx: 200,
                render: (row) => (
                  <span className="flex items-center gap-2">
                    <Avatar name={`${row.first_name} ${row.last_name}`} photoUrl={row.photo} size={24} />
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-text">
                        {row.first_name} {row.last_name}
                      </span>
                      {row.is_own_club ? <span className="block text-[13px] text-text-muted">Votre club</span> : null}
                    </span>
                  </span>
                ),
              },
              { key: "position", header: "Poste", render: (row) => row.position_label },
              { key: "age", header: "Âge", align: "right", render: (row) => row.age ?? "—" },
              {
                key: "club",
                header: "Club",
                render: (row) => (
                  <span className="flex items-center gap-2">
                    <Avatar name={row.club.name} photoUrl={row.club.logo} size={24} />
                    {row.club.name}
                  </span>
                ),
              },
              { key: "rating", header: "Note moyenne", align: "right", render: (row) => row.average_rating ?? "—" },
            ]}
            rows={marketQuery.data?.results ?? []}
            getRowId={(row) => row.membership_id}
            loading={marketQuery.isLoading}
            onRowClick={(row) => (row.is_own_club ? undefined : setPublicPlayerId(row.membership_id))}
            getSearchableText={(row) => `${row.first_name} ${row.last_name}`}
            searchPlaceholder="Rechercher un joueur"
            resultLabel="joueurs"
            emptyState={<EmptyState message="Aucun joueur sur le marché pour l'instant." />}
          />
        </section>
      ) : null}

      {/* Offres du club */}
      {access.canReadMarket ? (
        <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
          <h2 className="mb-3 text-base font-semibold text-text">Offres du club</h2>
          <Tabs
            label="Offres du club"
            value={offersTab}
            onChange={setOffersTab}
            items={[
              { value: "sent", label: `Envoyées · ${sentOffersQuery.data?.count ?? 0}` },
              { value: "received", label: `Reçues pour nos joueurs · ${receivedOffersQuery.data?.count ?? 0}` },
            ]}
          />
          <div className="mt-3">
            <DataTable
              columns={[
                {
                  key: "player",
                  header: "Joueur",
                  widthPx: 180,
                  render: (row: TransferOffer) => `${row.player.first_name} ${row.player.last_name}`,
                },
                {
                  key: "club",
                  header: "Club",
                  render: (row: TransferOffer) => (offersTab === "sent" ? row.origin_club.name : row.target_club.name),
                },
                {
                  key: "date",
                  header: "Date",
                  render: (row: TransferOffer) => new Date(row.created_at).toLocaleDateString("fr-FR"),
                },
                {
                  key: "status",
                  header: "Statut",
                  render: (row: TransferOffer) => <StatusBadge status={offerStatusKey(row.status)} />,
                },
              ]}
              rows={clubOffersQuery.data?.results ?? []}
              getRowId={(row) => row.id}
              loading={clubOffersQuery.isLoading}
              onRowClick={(row) => setOfferModal({ id: row.id, asPlayer: false })}
              getSearchableText={(row) => `${row.player.first_name} ${row.player.last_name}`}
              searchPlaceholder="Rechercher un joueur"
              resultLabel="offres"
              emptyState={
                <EmptyState
                  message={offersTab === "sent" ? "Aucune offre envoyée." : "Aucune offre reçue pour vos joueurs."}
                  actionLabel={offersTab === "sent" ? "Faire une offre" : undefined}
                  onAction={offersTab === "sent" ? () => setMakeOfferPlayer(null) : undefined}
                />
              }
            />
          </div>
        </section>
      ) : null}

      {/* Messagerie entre clubs */}
      {access.canMakeOfferOrMessage ? (
        <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-text">Messagerie entre clubs</h2>
            <Button size="sm" variant="secondary" onClick={() => setWriteToClub({ club: null })}>
              Écrire à un club
            </Button>
          </div>
          {threadsQuery.isLoading ? (
            <Loader loading variant="list" count={2} />
          ) : (threadsQuery.data?.results.length ?? 0) === 0 ? (
            <EmptyState message="Aucune conversation." actionLabel="Écrire à un club" onAction={() => setWriteToClub({ club: null })} />
          ) : (
            <>
              <ul className="divide-y divide-border">
                {threadsQuery.data!.results.slice(0, threadsLimit).map((thread) => (
                  <li key={thread.id}>
                    <button
                      type="button"
                      onClick={() => setConversationThreadId(thread.id)}
                      className="flex w-full items-center justify-between gap-2 py-2 text-left"
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <Avatar name={thread.other_club.name} photoUrl={thread.other_club.logo} size={32} />
                        <span className="min-w-0">
                          <span className="block truncate text-sm text-text">{thread.other_club.name}</span>
                          <span className="block truncate text-xs text-text-muted">{thread.subject || "Échange entre dirigeants"}</span>
                        </span>
                      </span>
                      {thread.unread_count > 0 ? <StatusBadge status="unread" /> : null}
                    </button>
                  </li>
                ))}
              </ul>
              {threadsQuery.data!.results.length > threadsLimit ? (
                <div className="mt-2 text-center">
                  <Button size="sm" variant="secondary" onClick={() => setThreadsLimit((l) => l + PAGE_STEP)}>
                    Voir plus
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </section>
      ) : null}

      <FichePubliqueModal
        membershipId={publicPlayerId}
        canOffer={access.canMakeOfferOrMessage}
        onClose={() => setPublicPlayerId(null)}
        onMakeOffer={(membershipId) => {
          const row = marketQuery.data?.results.find((r) => r.membership_id === membershipId);
          setPublicPlayerId(null);
          if (row) {
            setMakeOfferPlayer({
              id: row.membership_id,
              firstName: row.first_name,
              lastName: row.last_name,
              number: row.jersey_number,
              photoUrl: row.photo,
            });
          }
        }}
        onWriteToClub={(clubIdOfPlayer) => {
          const row = marketQuery.data?.results.find((r) => r.club.id === clubIdOfPlayer);
          setPublicPlayerId(null);
          setWriteToClub({ club: row ? { id: row.club.id, name: row.club.name, logo: row.club.logo } : null });
        }}
      />

      <FaireUneOffreModal
        open={makeOfferPlayer !== undefined}
        initialPlayer={makeOfferPlayer ?? null}
        ownClubName={clubName}
        onClose={() => setMakeOfferPlayer(undefined)}
        onSent={(playerName) => {
          setMakeOfferPlayer(undefined);
          invalidateOffers();
          showToast(`Offre envoyée à ${playerName}. Son club a été prévenu.`);
        }}
      />

      <EcrireAUnClubModal
        open={writeToClub !== null}
        lockedClub={writeToClub?.club ?? null}
        aboutOfferPlayerName={writeToClub?.aboutPlayer}
        transferOfferId={writeToClub?.offerId}
        onClose={() => setWriteToClub(null)}
        onSent={(clubNameSent) => {
          setWriteToClub(null);
          void queryClient.invalidateQueries({ queryKey: ["mercato", "threads"] });
          showToast(`Message envoyé à ${clubNameSent}.`);
        }}
      />

      <OfferDetailModal
        offerId={offerModal?.id ?? null}
        viewerIsTargetPlayer={offerModal?.asPlayer ?? false}
        viewerClubId={clubId}
        onClose={() => setOfferModal(null)}
        onWriteToClub={(clubIdToWrite, offerId) => {
          setOfferModal(null);
          const offer =
            sentOffersQuery.data?.results.find((o) => o.id === offerId) ??
            receivedOffersQuery.data?.results.find((o) => o.id === offerId);
          const club: ClubBrief | undefined =
            offer?.origin_club.id === clubIdToWrite ? offer?.origin_club : offer?.target_club;
          setWriteToClub({
            club: club ? { id: club.id, name: club.name, logo: club.logo } : { id: clubIdToWrite, name: "", logo: null },
            offerId,
            aboutPlayer: offer ? `${offer.player.first_name} ${offer.player.last_name}` : undefined,
          });
        }}
        onOpenPublicPlayer={(membershipId) => {
          setOfferModal(null);
          setPublicPlayerId(membershipId);
        }}
        onCompletedForPlayer={(offer) => {
          setOfferModal(null);
          setWelcomeOffer(offer);
          invalidateOffers();
        }}
      />

      <WelcomeModal open={welcomeOffer !== null} offer={welcomeOffer} onContinue={() => window.location.assign("/")} />

      <ConversationModal
        thread={threadsQuery.data?.results.find((t) => t.id === conversationThreadId) ?? null}
        viewerClubId={clubId}
        onClose={() => setConversationThreadId(null)}
        onOpenOffer={(offerId) => {
          setConversationThreadId(null);
          setOfferModal({ id: offerId, asPlayer: false });
        }}
      />
    </div>
  );
}
