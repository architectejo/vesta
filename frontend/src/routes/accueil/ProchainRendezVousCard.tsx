import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { getLockerRoom, type MatchDetail, type SessionDetail } from "../../api/sport";
import { Button, EmptyState, Modal, Skeleton, useToast } from "../../design-system";
import { CreateSessionModal } from "../sport/CreateSessionModal";
import { formatDateLong, formatNextEventLabel } from "../sport/sportTime";

function convocationLabel(match: MatchDetail, membershipId: number): string | null {
  if (!match.is_composition_published) return null;
  if (match.starters.some((s) => s.membership_id === membershipId)) return "Vous êtes convoqué : titulaire";
  if (match.substitutes.some((s) => s.membership_id === membershipId)) return "Vous êtes convoqué : remplaçant";
  return "Vous n'êtes pas convoqué pour ce match.";
}

function RendezVousDetailModal({
  session,
  match,
  membershipId,
  onClose,
}: {
  session: SessionDetail | null;
  match: MatchDetail | null;
  membershipId: number;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const title = session ? "Séance" : match ? `Match contre ${match.opponent}` : "Rendez-vous";
  const convocation = match ? convocationLabel(match, membershipId) : null;

  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      subtitle={session ? formatDateLong(session.event_date) : match ? formatDateLong(match.event_date) : undefined}
      size="sm"
      footer={
        <div className="flex w-full flex-wrap items-center justify-between gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Fermer
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate(session ? `/seances/${session.id}` : `/matchs/${match?.id}`)}
          >
            {session ? "Ouvrir la séance" : "Ouvrir le match"}
          </Button>
        </div>
      }
    >
      <div className="space-y-2 text-sm text-text">
        {session ? (
          <>
            <p>Rassemblement à {session.gathering_time.slice(0, 5)}</p>
            <p>Heure limite d'arrivée : {session.late_arrival_cutoff.slice(0, 5)}</p>
            {session.location ? <p>Lieu : {session.location}</p> : null}
          </>
        ) : match ? (
          <>
            <p>Coup d'envoi à {match.kickoff_time.slice(0, 5)}</p>
            {match.location ? <p>Lieu : {match.location}</p> : null}
            {convocation ? <p className="font-medium">{convocation}</p> : null}
          </>
        ) : null}
      </div>
    </Modal>
  );
}

/**
 * Carte « Prochain rendez-vous » (club-accueil.md §4 point 5, états §6).
 *
 * Point ouvert partiellement résolu (voir compte rendu) : `listSessions`/
 * `listMatches` restent triées par date décroissante, sans filtre « à
 * venir » ni tri croissant, et mélangent toujours passé et futur -- cette
 * carte ne charge donc toujours pas elle-même « le » prochain événement en
 * parcourant ces listes, ce que CLAUDE.md interdirait (donnée métier triée
 * côté interface). Elle réutilise l'événement du jour déjà chargé par
 * `getLockerRoom` (même source que « Vestiaire du jour »). Ce qui a changé :
 * `getLockerRoom` renvoie désormais aussi `next_event`, le prochain
 * événement à venir calculé par l'API quand rien n'a lieu aujourd'hui ; la
 * carte affiche cette précision au lieu de rester silencieuse au-delà
 * d'aujourd'hui.
 */
export function ProchainRendezVousCard({ membershipId, isCoach }: { membershipId: number; isCoach: boolean }) {
  const [detailOpen, setDetailOpen] = useState(false);
  const [createSessionOpen, setCreateSessionOpen] = useState(false);
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["sport", "locker-room"], queryFn: getLockerRoom, refetchInterval: 30_000 });

  const data = query.data;
  const session = data?.session ?? null;
  const match = data?.match ?? null;

  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
      <h2 className="text-base font-semibold text-text">Prochain rendez-vous</h2>

      <div className="mt-2">
        {query.isLoading ? (
          <Skeleton variant="row" />
        ) : query.isError ? (
          <EmptyState
            variant="error"
            message="Impossible de charger le prochain rendez-vous."
            actionLabel="Réessayer"
            onAction={() => void query.refetch()}
          />
        ) : session || match ? (
          <button
            type="button"
            onClick={() => setDetailOpen(true)}
            className="w-full rounded-md border border-border p-2 text-left hover:bg-surface-muted"
          >
            <p className="text-sm font-medium text-text">
              {session ? "Séance aujourd'hui" : `Match aujourd'hui contre ${match?.opponent}`}
            </p>
            <p className="text-xs text-text-muted">
              {session
                ? `Rassemblement ${session.gathering_time.slice(0, 5)}${session.location ? ` · ${session.location}` : ""}`
                : match
                  ? `Coup d'envoi ${match.kickoff_time.slice(0, 5)}${match.location ? ` · ${match.location}` : ""}`
                  : ""}
            </p>
          </button>
        ) : (
          <EmptyState
            message="Aucune séance ni aucun match prévu aujourd'hui."
            description={data?.next_event ? `Prochain rendez-vous : ${formatNextEventLabel(data.next_event)}` : undefined}
            actionLabel={isCoach ? "Créer une séance" : undefined}
            onAction={isCoach ? () => setCreateSessionOpen(true) : undefined}
          />
        )}
      </div>

      {detailOpen && (session || match) ? (
        <RendezVousDetailModal
          session={session}
          match={match}
          membershipId={membershipId}
          onClose={() => setDetailOpen(false)}
        />
      ) : null}

      <CreateSessionModal
        open={createSessionOpen}
        onClose={() => setCreateSessionOpen(false)}
        onCreated={() => {
          setCreateSessionOpen(false);
          void queryClient.invalidateQueries({ queryKey: ["sport", "locker-room"] });
          showToast("Séance créée. Les joueurs ont été prévenus.");
        }}
      />
    </section>
  );
}
