import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError } from "../../api/client";
import { getPlayerCard } from "../../api/clubs";
import {
  Button,
  EmptyState,
  Modal,
  PlayerTradingCard,
  Skeleton,
  StatusBadge,
  useClubBranding,
} from "../../design-system";
import type { StatusKey } from "../../design-system";
import { PlayerComparisonModal } from "./PlayerComparisonModal";

export const MEMBERSHIP_STATUS_KEY: Record<string, StatusKey> = {
  pending: "pending",
  active: "registered",
  departed: "left",
};

/** « Membre depuis mars 2024 » à partir d'une date « YYYY-MM-DD » (A3, A9). */
function formatJoinedMonthYear(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" }).format(date);
}

/**
 * Fiche publique d'un joueur, présentée comme une carte de joueur style
 * FC/FIFA (docs/ecrans/club-carte-joueur.md, partie A ; club-comite-bureau.md
 * §4.7 ; CDC 4.2). Identité, poste/numéro, statut d'adhésion, rôles.
 * Aucune donnée financière ni médicale, exactement comme le sert l'API
 * (`PlayerPublicCardSerializer`).
 */
export function PlayerCardModal({
  membershipId,
  onClose,
  isOwnCard = false,
}: {
  membershipId: number;
  onClose: () => void;
  /** `true` depuis « Mon profil » › « Voir ma carte de joueur » (A2, A9). */
  isOwnCard?: boolean;
}) {
  const branding = useClubBranding();
  const cardQuery = useQuery({
    queryKey: ["player-card", membershipId],
    queryFn: () => getPlayerCard(membershipId),
  });

  const card = cardQuery.data;
  const error = cardQuery.error;
  // Joueur introuvable (404, isolation multi-tenant) : message de l'API,
  // « Fermer » plutôt que « Réessayer » (A7 ; l'API renvoie déjà exactement
  // « Ce joueur n'existe pas dans ce club. »).
  const isNotFound = error instanceof ApiError && error.status === 404;
  const [comparisonOpen, setComparisonOpen] = useState(false);

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title={isOwnCard ? "Ma carte de joueur" : "Fiche du joueur"}
        size="lg"
        footer={
          <div className="flex w-full items-center justify-between gap-2">
            <Button variant="secondary" size="md" onClick={onClose}>
              Fermer
            </Button>
            {card ? (
              <Button variant="secondary" size="md" onClick={() => setComparisonOpen(true)}>
                Comparer
              </Button>
            ) : null}
          </div>
        }
        cancelLabel="Fermer"
      >
        {cardQuery.isLoading ? (
          <Skeleton variant="player-card" />
        ) : cardQuery.isError ? (
          isNotFound ? (
            <EmptyState variant="error" message={error.detail} actionLabel="Fermer" onAction={onClose} />
          ) : (
            <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void cardQuery.refetch()} />
          )
        ) : card ? (
          <div className="space-y-4 sm:grid sm:grid-cols-[280px_1fr] sm:items-start sm:gap-6 sm:space-y-0">
            <PlayerTradingCard
              firstName={card.first_name}
              lastName={card.last_name}
              photoUrl={card.photo}
              positionLabel={card.position_label}
              positionDetail={card.position_detail}
              jerseyNumber={card.jersey_number}
              clubLogoUrl={branding?.logoUrl ?? null}
              clubName={branding?.name ?? ""}
            />

            <div className="rounded-lg border border-border bg-surface p-3">
              {/*
               * Pas de `detail` ici : `card.membership_status_label` (servi
               * par l'API) répète toujours exactement le libellé que
               * `StatusBadge` affiche déjà via `status` (ex. « Inscrit »),
               * ce qui produisait le doublon « Inscrit · Inscrit » (même
               * anti-pattern déjà corrigé sur `ClubsLicencesPage`,
               * « Essai · Essai »). `detail` ne doit servir qu'à une
               * information distincte du statut lui-même.
               */}
              <StatusBadge status={MEMBERSHIP_STATUS_KEY[card.membership_status] ?? "pending"} />
              {card.joined_on ? (
                <p className="mt-2 text-sm text-text-muted">
                  Membre depuis {formatJoinedMonthYear(card.joined_on)}
                </p>
              ) : null}

              <h3 className="mt-3 text-sm font-semibold text-text">Rôles</h3>
              {card.roles.length === 0 ? (
                <p className="mt-1 text-sm text-text-muted">Aucun rôle particulier.</p>
              ) : (
                <ul className="mt-1 flex flex-wrap gap-1">
                  {card.roles.map((role) => (
                    <li
                      key={role.role}
                      className="flex h-6 items-center rounded-full bg-surface-muted px-2 text-xs text-text"
                    >
                      {role.label}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ) : null}
      </Modal>
      {comparisonOpen && card ? (
        <PlayerComparisonModal
          initialPlayer={{
            id: card.membership_id,
            firstName: card.first_name,
            lastName: card.last_name,
            number: card.jersey_number,
            position: card.position_label,
            photoUrl: card.photo,
          }}
          onClose={() => setComparisonOpen(false)}
        />
      ) : null}
    </>
  );
}
