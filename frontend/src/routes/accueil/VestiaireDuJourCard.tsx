import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { getLockerRoom, type SessionDetail, type TeamAssignmentItem } from "../../api/sport";
import { Avatar, Button, EmptyState, PitchBoard, Skeleton } from "../../design-system";
import { pitchPinsForTeam } from "../sport/pinLayout";

/** Joueurs présents mais non placés sur le terrain (`is_on_field: false`) :
 * même logique que `BenchStrip` de `VestiairePage.tsx`, réduite à de
 * simples avatars 32 px (carte compacte, club-accueil.md §4 point 2). */
function CompactBench({ items }: { items: TeamAssignmentItem[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-1 flex flex-wrap gap-1">
      {items.map((item) => (
        <li key={item.id} title={item.player.name}>
          <Avatar name={item.player.name} photoUrl={item.player.photo} size={32} />
        </li>
      ))}
    </ul>
  );
}

/** Compact (carte d'accueil) : deux terrains réduits, équipe A puis B, aux
 * vraies positions des joueurs sur le terrain (`x_coord`/`y_coord`,
 * `is_on_field`), comme `VestiairePage.tsx` (vue « Équipes A/B »). */
function CompactTeamsBoard({ session }: { session: SessionDetail }) {
  if (session.team_a.length === 0 && session.team_b.length === 0) {
    return <EmptyState message="Personne n'est encore pointé." />;
  }
  const teams = [
    { label: "A" as const, color: session.team_a_color, members: session.team_a },
    { label: "B" as const, color: session.team_b_color, members: session.team_b },
  ];
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {teams.map((team) => (
        <div key={team.label} className="min-w-0">
          <PitchBoard
            mode="readonly"
            ariaLabel={`Équipe ${team.label}`}
            pins={pitchPinsForTeam(team.members, team.color)}
            pinsDraggable={false}
          />
          <CompactBench items={team.members.filter((item) => !item.is_on_field)} />
        </div>
      ))}
    </div>
  );
}

/** Carte « Vestiaire du jour » (club-accueil.md §4 point 2, CDC 4.7).
 * Masquée s'il n'y a ni séance ni match aujourd'hui (§6). Réutilise
 * directement `getLockerRoom`, déjà utilisée par `VestiairePage`. */
export function VestiaireDuJourCard({ isPresident }: { isPresident: boolean }) {
  const navigate = useNavigate();
  const query = useQuery({ queryKey: ["sport", "locker-room"], queryFn: getLockerRoom, refetchInterval: 30_000 });

  if (query.isLoading) {
    return (
      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <h2 className="text-base font-semibold text-text">Vestiaire du jour</h2>
        <div className="mt-2">
          <Skeleton variant="pitch" />
        </div>
      </section>
    );
  }

  if (query.isError) {
    return (
      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <h2 className="text-base font-semibold text-text">Vestiaire du jour</h2>
        <div className="mt-2">
          <EmptyState
            variant="error"
            message="Impossible de charger le vestiaire."
            actionLabel="Réessayer"
            onAction={() => void query.refetch()}
          />
        </div>
      </section>
    );
  }

  const data = query.data;
  if (!data || (!data.session && !data.match)) {
    // Carte masquée s'il n'y a ni séance ni match aujourd'hui (§6).
    return null;
  }

  const session = data.session;
  const match = data.match;
  const counts = session?.counts ?? match?.attendance_counts ?? null;
  const present = counts?.present ?? 0;
  const label = session
    ? "Séance"
    : match
      ? `Match contre ${match.opponent}`
      : "";
  const team = data.my_situation?.team ?? null;

  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
      <h2 className="text-base font-semibold text-text">Vestiaire du jour</h2>

      {isPresident && session ? (
        <div className="mt-2 space-y-2">
          <p className="text-sm text-text">
            {label} · {present} présent{present > 1 ? "s" : ""}
          </p>
          <CompactTeamsBoard session={session} />
        </div>
      ) : (
        <p className="mt-2 text-sm text-text">
          {label} · {present} présent{present > 1 ? "s" : ""}
          {team ? ` · Vous êtes en équipe ${team}` : ""}
        </p>
      )}

      <Button variant="ghost" size="sm" className="mt-2" onClick={() => navigate("/vestiaire")}>
        Ouvrir le vestiaire
      </Button>
    </section>
  );
}
