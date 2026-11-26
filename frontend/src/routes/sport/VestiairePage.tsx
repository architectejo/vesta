import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getMyProfile } from "../../api/clubs";
import { getLockerRoom, type Formation, type MatchDetail, type SessionDetail, type TeamAssignmentItem } from "../../api/sport";
import {
  Avatar,
  Banner,
  Button,
  EmptyState,
  IconChevronDown,
  Loader,
  Modal,
  PitchBoard,
  PitchPin,
  SegmentedControl,
  StatusBadge,
  useToast,
} from "../../design-system";
import { CreateSessionModal } from "./CreateSessionModal";
import { pitchPinsForTeam, shortLabel } from "./pinLayout";
import { PlansLibrary } from "./PlansLibrary";
import { PlayerCardModal } from "./PlayerCardModal";
import { useTeamsPitchWidthStyle } from "./pitchSizing";
import { getSportAccess } from "./sportAccess";
import { formatDateLong, formatNextEventLabel, formatTime, useClubTimeZone } from "./sportTime";
import { TeamsBoard } from "./TeamsBoard";
import { useTeamFieldActions } from "./useTeamFieldActions";

type EventChoice = "session" | "match";
type TeamsView = "list" | "pitch";

function RendezVousCard({ session, match }: { session: SessionDetail | null; match: MatchDetail | null }) {
  const label = session
    ? `Séance · rassemblement ${session.gathering_time.slice(0, 5)} · limite ${session.late_arrival_cutoff.slice(0, 5)}${session.location ? ` · ${session.location}` : ""}`
    : match
      ? `Match contre ${match.opponent} · ${match.kickoff_time.slice(0, 5)}${match.location ? ` · ${match.location}` : ""}`
      : "";
  const counts = session?.counts ?? match?.attendance_counts ?? null;
  return (
    <section className="rounded-md border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-text">{label}</p>
        <StatusBadge status="session_open" />
      </div>
      {counts ? (
        <p className="mt-1 flex gap-3 text-sm">
          <span className="text-status-success-fg">{counts.present} présents</span>
          <span className="text-status-danger-fg">{counts.late} en retard</span>
        </p>
      ) : null}
    </section>
  );
}

function MaSituationCard({
  situation,
  session,
  match,
}: {
  situation: { attendance: SessionDetail["attendances"][number] | null; team: "A" | "B" | null; eligible: boolean; reason: string } | null;
  session: SessionDetail | null;
  match: MatchDetail | null;
}) {
  const tz = useClubTimeZone();
  if (!situation) return null;
  const cutoff = session?.late_arrival_cutoff;
  let text: string;
  if (!situation.attendance) {
    text = "Vous n'êtes pas encore pointé. Présentez-vous au Coach ou au Capitaine à votre arrivée.";
  } else if (situation.attendance.status === "excused_absent") {
    text = `Absence excusée${situation.attendance.excused_reason ? ` · ${situation.attendance.excused_reason}` : ""}`;
  } else if (!situation.eligible) {
    text = `Vous êtes pointé, mais vous ne pouvez pas jouer aujourd'hui : ${situation.reason}`;
  } else if (situation.attendance.status === "late_absent") {
    text = situation.team
      ? `Vous êtes arrivé à ${formatTime(situation.attendance.arrived_at, tz)}, après l'heure limite · Équipe ${situation.team}`
      : `Vous êtes arrivé à ${formatTime(situation.attendance.arrived_at, tz)}, après l'heure limite : vous êtes compté absent. Le Coach ou le Capitaine peut vous placer dans une équipe.`;
  } else {
    text = situation.team
      ? `Vous êtes pointé présent à ${formatTime(situation.attendance.arrived_at, tz)} · Équipe ${situation.team}`
      : `Vous êtes pointé présent à ${formatTime(situation.attendance.arrived_at, tz)}`;
  }
  void cutoff;
  return (
    <section className="rounded-md border border-border p-3">
      <h2 className="mb-2 text-sm font-semibold text-text">Ma situation</h2>
      <p className="text-sm text-text">{text}</p>
      {match?.is_composition_published ? (
        <p className="mt-1 text-sm text-text-muted">
          {match.starters.some((s) => s.membership_id === situation.attendance?.membership_id)
            ? "Vous êtes convoqué : titulaire"
            : match.substitutes.some((s) => s.membership_id === situation.attendance?.membership_id)
              ? "Vous êtes convoqué : remplaçant"
              : "Vous n'êtes pas convoqué pour ce match."}
        </p>
      ) : null}
    </section>
  );
}

function BenchStrip({ items }: { items: TeamAssignmentItem[] }) {
  if (items.length === 0) return null;
  return (
    <div className="rounded-md border border-dashed border-border-strong p-2">
      <p className="mb-1 text-xs font-medium text-text-muted">Banc ({items.length})</p>
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item.id} className="flex items-center gap-2">
            <Avatar name={item.player.name} photoUrl={item.player.photo} size={32} />
            <span className="truncate text-sm text-text tabular-nums">
              {item.player.jersey_number ?? ""} {item.player.name}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Carte « Équipes » (§3 point 3). Vue « Liste » : consultation pure pour
 * tous les rôles. Vue « Terrain » : consultation pure (info-bulle au
 * toucher) pour la plupart des rôles, mais **éditable** (formation,
 * glisser-déposer, échange entre équipes y compris depuis les bancs) pour
 * le Coach, le Capitaine et le Président — extension client du 30/09/2026,
 * qui s'écarte sciemment de `docs/ecrans/sport-vestiaire.md` §3 point 3
 * (« aucun glisser-déposer ni aucun menu d'action », « aucun bouton
 * "Passer en A/B" ») : voir le compte rendu de cette tâche. Pour les
 * autres rôles, le terrain reste strictement en lecture seule, à
 * l'identique du comportement précédent.
 */
function EquipesCard({
  session,
  canAssign,
  onAssign,
  onSetFormation,
  onPlacePlayer,
  onShowCard,
  myMembershipId = null,
}: {
  session: SessionDetail;
  /** Adhésion du joueur connecté (« Ma situation »), mise en avant dans la vue « Liste ». */
  myMembershipId?: number | null;
  canAssign: boolean;
  onAssign: (membershipId: number, team: "A" | "B") => void;
  onSetFormation: (team: "A" | "B", formation: Formation) => void;
  onPlacePlayer: (team: "A" | "B", membershipId: number, x: number | null, y: number | null) => void;
  onShowCard: (membershipId: number) => void;
}) {
  const [view, setView] = useState<TeamsView>("list");
  // Info-bulle au toucher d'un pion (§3 point 3), même pattern que
  // `PlanDetailModal.tsx` : une petite modale `sm` plutôt qu'un vrai
  // popover flottant, pour rester cohérent avec le reste de l'app. Utilisée
  // uniquement par les rôles qui ne peuvent pas modifier le terrain.
  const [tappedPlayer, setTappedPlayer] = useState<TeamAssignmentItem | null>(null);
  const pitchWidthStyle = useTeamsPitchWidthStyle();

  const teams = [
    { label: "A" as const, color: session.team_a_color, members: session.team_a },
    { label: "B" as const, color: session.team_b_color, members: session.team_b },
  ];

  return (
    <section className="rounded-md border border-border p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text">Équipes</h2>
        <SegmentedControl label="Vue" value={view} onChange={setView} options={[{ value: "list", label: "Liste" }, { value: "pitch", label: "Terrain" }]} />
      </div>
      {session.team_a.length === 0 && session.team_b.length === 0 ? (
        <EmptyState message="Personne n'est encore pointé. Les équipes apparaîtront au fil des arrivées." />
      ) : view === "list" ? (
        <div className="grid grid-cols-2 gap-3">
          {teams.map((team) => (
            <div key={team.label}>
              <p className="mb-1 flex items-center gap-1 text-xs font-medium text-text-muted">
                <span aria-hidden className="h-2 w-2 rounded-full" style={{ backgroundColor: team.color }} />
                Équipe {team.label} · {team.members.length}
              </p>
              {team.members.length === 0 ? (
                <p className="text-xs text-text-muted">Aucun joueur pour l'instant.</p>
              ) : (
                <ul className="space-y-1">
                  {team.members.map((item) => {
                    // §3 point 3 et §7 : lignes de 44 px, « Prénom N. » sur deux
                    // lignes au plus, jamais tronqué ; le joueur connecté est mis
                    // en avant (fond muted et mention « Vous »).
                    const isMe = myMembershipId !== null && item.membership_id === myMembershipId;
                    return (
                      <li
                        key={item.id}
                        aria-current={isMe ? "true" : undefined}
                        className={`flex min-h-11 items-center gap-2 rounded-sm ${isMe ? "bg-surface-muted" : ""}`}
                      >
                        <Avatar name={item.player.name} photoUrl={item.player.photo} size={32} />
                        <span className="min-w-0 break-words text-sm text-text" title={item.player.name}>
                          {item.player.jersey_number !== null ? <span className="tabular-nums">{item.player.jersey_number} </span> : null}
                          {shortLabel(item.player.name)}
                          {isMe ? <span className="block text-xs font-medium text-text-muted">Vous</span> : null}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          ))}
        </div>
      ) : canAssign ? (
        <TeamsBoard
          session={session}
          canAssign={canAssign}
          allowCrossTeamBenchDrop
          onAssign={onAssign}
          onSetFormation={onSetFormation}
          onPlacePlayer={onPlacePlayer}
          onShowCard={onShowCard}
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {teams.map((team) => (
            <div key={team.label} className="min-w-0 space-y-2">
              <p className="flex items-center gap-1 text-xs font-medium text-text-muted">
                <span aria-hidden className="h-2 w-2 rounded-full" style={{ backgroundColor: team.color }} />
                Équipe {team.label} · {team.members.length}
              </p>
              <div style={pitchWidthStyle}>
                <PitchBoard
                  mode="readonly"
                  ariaLabel={`Équipe ${team.label}`}
                  pins={pitchPinsForTeam(team.members, team.color)}
                  pinsDraggable={false}
                  onTapPin={(pin) => setTappedPlayer(team.members.find((item) => String(item.id) === pin.id) ?? null)}
                />
              </div>
              <BenchStrip items={team.members.filter((item) => !item.is_on_field)} />
            </div>
          ))}
        </div>
      )}

      <Modal
        open={tappedPlayer !== null}
        onClose={() => setTappedPlayer(null)}
        title={tappedPlayer?.player.name ?? ""}
        size="sm"
        hideFooter
      >
        {tappedPlayer ? (
          <p className="text-sm text-text">
            n° {tappedPlayer.player.jersey_number ?? "—"} · {tappedPlayer.player.position_label}
          </p>
        ) : null}
      </Modal>
    </section>
  );
}

function PresentsSansEquipeCard({ session }: { session: SessionDetail }) {
  const { to_place_manually, cannot_play } = session.unassigned;
  if (to_place_manually.length === 0 && cannot_play.length === 0) return null;
  return (
    <section className="rounded-md border border-border p-3">
      <h2 className="mb-2 text-sm font-semibold text-text">Présents sans équipe</h2>
      {to_place_manually.length > 0 ? (
        <div className="mb-2">
          <p className="mb-1 text-xs font-medium text-text-muted">En attente de placement ({to_place_manually.length})</p>
          <ul className="space-y-1">
            {to_place_manually.map((p) => (
              <li key={p.membership_id} className="flex items-center gap-2">
                <PitchPin
                  standalone
                  draggable={false}
                  interactive={false}
                  vertical
                  dragKind="pin"
                  pin={{
                    id: String(p.membership_id),
                    membershipId: p.membership_id,
                    label: shortLabel(p.name),
                    fullName: p.name,
                    number: p.jersey_number,
                    photoUrl: p.photo,
                    x: 0,
                    y: 0,
                  }}
                />
                <span className="min-w-0 break-words text-sm text-text">{p.name}</span>
                <StatusBadge status="late" />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {cannot_play.length > 0 ? (
        <div>
          <p className="mb-1 text-xs font-medium text-text-muted">Ne jouent pas aujourd'hui ({cannot_play.length})</p>
          <ul className="space-y-1">
            {cannot_play.map((p) => (
              <li key={p.membership_id} className="flex items-center gap-2">
                <PitchPin
                  standalone
                  draggable={false}
                  interactive={false}
                  vertical
                  dragKind="pin"
                  pin={{
                    id: String(p.membership_id),
                    membershipId: p.membership_id,
                    label: shortLabel(p.name),
                    fullName: p.name,
                    number: p.jersey_number,
                    photoUrl: p.photo,
                    locked: true,
                    x: 0,
                    y: 0,
                  }}
                />
                <span className="min-w-0 break-words text-sm text-text">{p.name}</span>
                <StatusBadge status="medical_unavailable" />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function PasEncorePointesCard({ session, canSee }: { session: SessionDetail; canSee: boolean }) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  if (!canSee) return null;
  // Approximation : nombre de « non pointés » fourni par le compteur
  // serveur (`counts.not_marked`) — la liste détaillée exige le
  // rapprochement avec l'effectif, déjà fait par la page Séance.
  const count = session.counts.not_marked;
  if (count === 0) return null;
  return (
    <section className="rounded-md border border-border p-3">
      <button
        type="button"
        className="flex min-h-control-sm items-center gap-1 text-sm text-text"
        onClick={() => setExpanded((v) => !v)}
      >
        {count} joueurs pas encore pointés
        <IconChevronDown
          aria-hidden="true"
          className={["h-4 w-4 transition-transform motion-safe:duration-150", expanded ? "rotate-180" : ""].join(" ")}
        />
      </button>
      {expanded ? (
        <Button size="sm" variant="ghost" className="mt-2" onClick={() => navigate(`/seances/${session.id}`)}>
          Ouvrir le pointage
        </Button>
      ) : null}
    </section>
  );
}

type VestiaireTab = "today" | "plans";

/**
 * Page « Vestiaire » (docs/ecrans/sport-vestiaire.md) : onglet « Aujourd'hui »
 * (vestiaire du jour) et onglet « Plans » (bibliothèque de plans tactiques).
 * L'onglet est mémorisé dans l'URL (`?onglet=plans`) et reste accessible les
 * jours sans événement.
 */
export function VestiairePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: VestiaireTab = searchParams.get("onglet") === "plans" ? "plans" : "today";

  function handleTabChange(next: VestiaireTab): void {
    const params = new URLSearchParams(searchParams);
    if (next === "plans") params.set("onglet", "plans");
    else params.delete("onglet");
    setSearchParams(params, { replace: true });
  }

  return (
    <div className="space-y-4">
      <SegmentedControl
        label="Section du vestiaire"
        value={tab}
        onChange={handleTabChange}
        options={[
          { value: "today", label: "Aujourd'hui" },
          { value: "plans", label: "Plans" },
        ]}
      />
      {tab === "plans" ? <PlansLibrary /> : <LockerRoomToday />}
    </div>
  );
}

/** Onglet « Aujourd'hui » : vestiaire du jour. */
function LockerRoomToday() {
  const navigate = useNavigate();
  const [choice, setChoice] = useState<EventChoice | null>(null);
  const [consignesOpen, setConsignesOpen] = useState(false);
  const [cardMembershipId, setCardMembershipId] = useState<number | null>(null);
  const [createSessionOpen, setCreateSessionOpen] = useState(false);
  const { showToast } = useToast();
  const queryClient = useQueryClient();

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const access = getSportAccess(profileQuery.data?.roles);

  const query = useQuery({
    queryKey: ["sport", "locker-room"],
    queryFn: getLockerRoom,
    refetchInterval: 30_000,
  });

  // Actions d'édition du terrain (extension client du 30/09/2026, point
  // ouvert ci-dessus). Le hook doit être appelé sans condition (règles des
  // hooks React) : avant que `query.data` soit connu, `sessionId` vaut 0 et
  // les fonctions renvoyées ne sont jamais invoquées (aucun bouton
  // d'édition n'est rendu avant que la séance du jour soit chargée).
  const teamFieldActions = useTeamFieldActions(query.data?.session?.id ?? 0, [["sport", "locker-room"]]);

  if (profileQuery.isLoading || query.isLoading) return <Loader loading variant="page" />;
  // Un rafraîchissement en échec (interrogation 30 s) garde la dernière
  // version reçue (§6 : « Aucun toast toutes les 30 s ») ; seule une page
  // qui n'a jamais rien reçu affiche l'état d'erreur.
  if (query.isError && !query.data) {
    return <EmptyState variant="error" message="Impossible de charger le vestiaire." actionLabel="Réessayer" onAction={() => void query.refetch()} />;
  }
  const data = query.data;
  if (!data) return null;

  if (!data.session && !data.match) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold text-text">Vestiaire du jour</h1>
        <EmptyState
          message="Aucune séance ni aucun match aujourd'hui."
          description={data.next_event ? `Prochain rendez-vous : ${formatNextEventLabel(data.next_event)}` : undefined}
          actionLabel={access.isCoach ? "Créer une séance" : undefined}
          onAction={access.isCoach ? () => setCreateSessionOpen(true) : undefined}
        />
        <CreateSessionModal
          open={createSessionOpen}
          onClose={() => setCreateSessionOpen(false)}
          onCreated={() => {
            setCreateSessionOpen(false);
            void queryClient.invalidateQueries({ queryKey: ["sport", "locker-room"] });
            showToast("Séance créée. Les joueurs ont été prévenus.");
          }}
        />
      </div>
    );
  }

  const effectiveChoice: EventChoice = choice ?? (data.session && data.match ? "session" : data.session ? "session" : "match");
  const activeSession = effectiveChoice === "session" ? data.session : null;
  const activeMatch = effectiveChoice === "match" ? data.match : null;
  const activeEventId = activeSession?.id ?? activeMatch?.id;
  const canOpenAttendance = access.canRecordAttendance;
  // Mêmes rôles que la page Séance (backend `CanAssignTeams` /
  // `TEAM_ASSIGNER_ROLES` : Coach, Capitaine, Président) ; verrouillage de
  // la séance respecté à l'identique.
  const canAssignTeams = access.canAssignTeams && Boolean(activeSession) && !activeSession?.is_locked;
  const eventDate = activeSession?.event_date ?? activeMatch?.event_date ?? null;
  // §3 : contexte « {nom du club} · {dimanche 27 septembre} ».
  const headerContext = [profileQuery.data?.club.name, eventDate ? formatDateLong(eventDate) : null].filter(Boolean).join(" · ");
  // « Mis à jour à {heure} » = heure de la dernière réponse reçue, pas du rendu.
  const updatedAt = new Date(query.dataUpdatedAt).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  const refreshFailed = query.isError;

  async function handleAssign(membershipId: number, team: "A" | "B"): Promise<void> {
    await teamFieldActions.handleAssign(activeSession, membershipId, team);
  }

  async function handleSetFormation(team: "A" | "B", formation: Formation): Promise<void> {
    await teamFieldActions.handleSetFormation(team, formation);
  }

  async function handlePlaceTeamPlayer(
    team: "A" | "B",
    membershipId: number,
    x: number | null,
    y: number | null,
  ): Promise<void> {
    await teamFieldActions.handlePlaceTeamPlayer(team, membershipId, x, y);
  }

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold text-text">Vestiaire du jour</h1>
            <p className="text-sm text-text-muted">{headerContext}</p>
          </div>
          {canOpenAttendance && activeEventId ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => navigate(activeSession ? `/seances/${activeEventId}` : `/matchs/${activeEventId}`)}
            >
              Ouvrir le pointage
            </Button>
          ) : null}
        </div>
        {refreshFailed ? (
          <p role="status" className="flex flex-wrap items-center gap-2 text-xs text-status-warning-fg">
            Mise à jour impossible · {new Date(query.errorUpdatedAt).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
            <button type="button" className="-my-2 py-2 font-medium text-primary-text hover:underline" onClick={() => void query.refetch()}>
              Réessayer
            </button>
          </p>
        ) : (
          <p className="text-xs text-text-muted">Mis à jour à {updatedAt}</p>
        )}
      </header>

      {!navigator.onLine ? <Banner variant="info">Vous êtes hors connexion. Vestiaire affiché : dernière version reçue.</Banner> : null}

      {data.session && data.match ? (
        <SegmentedControl
          label="Choix de l'événement"
          value={effectiveChoice}
          onChange={setChoice}
          options={[
            { value: "session", label: `Séance · ${data.session.gathering_time.slice(0, 5)}` },
            { value: "match", label: `Match · ${data.match.kickoff_time.slice(0, 5)}` },
          ]}
        />
      ) : null}

      <RendezVousCard session={activeSession} match={activeMatch} />
      {activeSession?.instructions ? (
        <button type="button" className="inline-flex min-h-control-sm items-center text-xs font-medium text-primary-text hover:underline" onClick={() => setConsignesOpen(true)}>
          Voir les consignes
        </button>
      ) : null}

      <MaSituationCard situation={data.my_situation} session={activeSession} match={activeMatch} />

      {activeSession ? (
        <>
          <EquipesCard
            session={activeSession}
            myMembershipId={data.my_situation?.attendance?.membership_id ?? null}
            canAssign={canAssignTeams}
            onAssign={(id, team) => void handleAssign(id, team)}
            onSetFormation={(team, formation) => void handleSetFormation(team, formation)}
            onPlacePlayer={(team, id, x, y) => void handlePlaceTeamPlayer(team, id, x, y)}
            onShowCard={setCardMembershipId}
          />
          <PresentsSansEquipeCard session={activeSession} />
          <PasEncorePointesCard session={activeSession} canSee={access.canRecordAttendance} />
        </>
      ) : activeMatch ? (
        <section className="rounded-md border border-border p-3">
          <h2 className="mb-2 text-sm font-semibold text-text">Présents ({activeMatch.attendances.length})</h2>
          {activeMatch.attendances.length === 0 ? (
            <EmptyState message="Personne n'est encore pointé." />
          ) : (
            <ul className="space-y-1">
              {activeMatch.attendances.map((a) => (
                <li key={a.id} className="flex items-center gap-2">
                  <Avatar name={a.player.name} photoUrl={a.player.photo} size={32} />
                  <span className="text-sm text-text">{a.player.name}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      <Modal open={consignesOpen} onClose={() => setConsignesOpen(false)} title="Consignes" size="sm" hideFooter>
        <p className="text-base text-text">{activeSession?.instructions}</p>
      </Modal>

      <PlayerCardModal open={cardMembershipId !== null} membershipId={cardMembershipId} onClose={() => setCardMembershipId(null)} />
    </div>
  );
}
