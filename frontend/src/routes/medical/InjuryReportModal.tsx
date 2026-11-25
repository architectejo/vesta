import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listMatches, listSessions } from "../../api/sport";
import { searchActiveClubPlayers } from "../../api/clubs";
import { ApiError } from "../../api/client";
import { reportInjury, type InjuryReportInput } from "../../api/medical";
import {
  Banner,
  IconLock,
  Modal,
  NumberField,
  PlayerSearch,
  TextArea,
  useToast,
  type PlayerSearchResult,
} from "../../design-system";
import { nowTimeHHMM, todayIsoDate } from "./medicalFormat";

interface TodayEventOption {
  id: number;
  kind: "session" | "match";
  label: string;
}

/** Séances et matchs du jour (medical.md §4.1 : « Select court des séances
 * et matchs du jour »). Filtrage côté client sur la date du jour, faute
 * d'un paramètre de date sur `listSessions`/`listMatches` — pas de règle
 * métier, seulement une comparaison de date d'affichage. */
function useTodayEvents(enabled: boolean) {
  const sessionsQuery = useQuery({
    queryKey: ["sport", "sessions", "recent-for-injury"],
    queryFn: () => listSessions({ limit: 10 }),
    enabled,
  });
  const matchesQuery = useQuery({
    queryKey: ["sport", "matches", "recent-for-injury"],
    queryFn: () => listMatches({ limit: 10 }),
    enabled,
  });
  const today = todayIsoDate();
  const options: TodayEventOption[] = [
    ...(sessionsQuery.data?.results ?? [])
      .filter((s) => s.event_date === today)
      .map((s) => ({ id: s.id, kind: "session" as const, label: `Séance du ${s.event_date}` })),
    ...(matchesQuery.data?.results ?? [])
      .filter((m) => m.event_date === today)
      .map((m) => ({ id: m.id, kind: "match" as const, label: `Match contre ${m.opponent}` })),
  ];
  return { options, isLoading: sessionsQuery.isLoading || matchesQuery.isLoading };
}

export interface InjuryReportContext {
  eventId: number;
  eventKind: "session" | "match";
  /** « Séance du {date} » / « Match contre {adversaire} », déjà composé par
   * la page hôte (séance/match), jamais reconstruit ici. */
  eventLabel: string;
}

export interface InjuryOfflineSupport {
  isOnline: boolean;
  enqueue: (payload: InjuryReportInput) => void;
}

export interface InjuryReportModalProps {
  open: boolean;
  onClose: () => void;
  /** Absent : ouverte depuis la page Médical (connexion obligatoire,
   * sélection libre de l'évènement). Présent : ouverte depuis une séance ou
   * un match (évènement présélectionné en lecture seule, hors connexion
   * possible via `offline`). */
  context?: InjuryReportContext;
  offline?: InjuryOfflineSupport;
  onReported: () => void;
}

type EventChoice = "" | "none" | `session:${number}` | `match:${number}`;

/**
 * « Déclarer une blessure » (medical.md §4.1, CDC 4.12 étape 1). Même
 * modale partout (page Médical, Bilan d'une séance, Blessures d'un match).
 */
export function InjuryReportModal({ open, onClose, context, offline, onReported }: InjuryReportModalProps) {
  const { showToast } = useToast();
  const [player, setPlayer] = useState<PlayerSearchResult | null>(null);
  const [eventChoice, setEventChoice] = useState<EventChoice>("");
  const [time, setTime] = useState(nowTimeHHMM());
  const [minute, setMinute] = useState<number | null>(null);
  const [circumstances, setCircumstances] = useState("");
  const [errors, setErrors] = useState<{ player?: string; event?: string; moment?: string; circumstances?: string }>({});
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  const { options: todayEvents, isLoading: eventsLoading } = useTodayEvents(open && !context);

  useEffect(() => {
    if (!open) return;
    setPlayer(null);
    setEventChoice(context ? `${context.eventKind}:${context.eventId}` : "");
    setTime(nowTimeHHMM());
    setMinute(null);
    setCircumstances("");
    setErrors({});
    setSubmitError(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, context?.eventId]);

  // Depuis la page Médical (pas de `context`), la modale exige une
  // connexion (medical.md §4.1) : pas de file hors connexion possible.
  const pageModeOffline = !context && typeof navigator !== "undefined" && !navigator.onLine;

  const selectedIsMatch = context
    ? context.eventKind === "match"
    : eventChoice.startsWith("match:");
  const selectedEventId = context
    ? context.eventId
    : eventChoice === "" || eventChoice === "none"
      ? null
      : Number(eventChoice.split(":")[1]);

  function validate(): boolean {
    const next: typeof errors = {};
    if (!player) next.player = "Choisissez un joueur.";
    if (!context && eventChoice === "") next.event = "Indiquez quand la blessure est survenue.";
    if (selectedIsMatch) {
      if (minute === null || minute < 0 || minute > 130) next.moment = "Saisissez une minute entre 0 et 130.";
    } else if (!time) {
      next.moment = "L'heure doit être comprise dans la journée.";
    }
    if (!circumstances.trim()) next.circumstances = "Décrivez brièvement les circonstances.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(): Promise<void> {
    if (!validate() || !player) return;
    setSubmitError(undefined);

    if (pageModeOffline) {
      setSubmitError("Cette action nécessite une connexion.");
      return;
    }

    const payload: InjuryReportInput = {
      membership_id: Number(player.id),
      event_id: selectedEventId,
      circumstances: circumstances.trim(),
      ...(selectedIsMatch ? { occurred_minute: minute } : { occurred_time: `${time}:00` }),
    };

    if (context && offline && !offline.isOnline) {
      offline.enqueue(payload);
      showToast(`Blessure déclarée pour ${player.firstName} ${player.lastName}. Elle sera envoyée au retour du réseau.`);
      onReported();
      onClose();
      return;
    }

    setSubmitting(true);
    try {
      await reportInjury(payload);
      showToast("Blessure déclarée. Le Médecin a été prévenu.");
      onReported();
      onClose();
    } catch (error) {
      if (context && offline && error instanceof ApiError && error.status === 0) {
        offline.enqueue(payload);
        showToast(`Blessure déclarée pour ${player.firstName} ${player.lastName}. Elle sera envoyée au retour du réseau.`);
        onReported();
        onClose();
        return;
      }
      setSubmitError(error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Déclarer une blessure"
      size="md"
      isSubmitting={submitting}
      confirmLabel="Déclarer"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <div className="flex items-start gap-2 rounded-md bg-surface-muted p-3 text-sm text-text">
          <IconLock aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-text-muted" />
          <p>
            Le Médecin sera prévenu et complétera la fiche. Après l'envoi, seuls le Médecin et le joueur pourront
            relire ces informations. Le staff verra seulement l'aptitude et la date de retour.
          </p>
        </div>

        {pageModeOffline ? <Banner variant="warning">Cette action nécessite une connexion.</Banner> : null}

        <div>
          <label className="mb-1 block text-sm font-medium text-text">Joueur</label>
          <PlayerSearch value={player} onChange={setPlayer} searchPlayers={searchActiveClubPlayers} />
          {errors.player ? <p className="mt-1 text-xs text-status-danger-fg">{errors.player}</p> : null}
        </div>

        {context ? (
          <div>
            <label className="mb-1 block text-sm font-medium text-text">Séance ou match</label>
            <p className="flex h-control-md items-center rounded-sm border border-border-strong bg-surface-muted px-3 text-sm text-text">
              {context.eventLabel}
            </p>
          </div>
        ) : (
          <label className="block text-sm font-medium text-text">
            Séance ou match
            <select
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text"
              value={eventChoice}
              disabled={eventsLoading}
              onChange={(e) => setEventChoice(e.target.value as EventChoice)}
            >
              <option value="" disabled>
                Sélectionner…
              </option>
              <option value="none">Hors séance ou match</option>
              {todayEvents.map((event) => (
                <option key={`${event.kind}:${event.id}`} value={`${event.kind}:${event.id}`}>
                  {event.label}
                </option>
              ))}
            </select>
            {errors.event ? <p className="mt-1 text-xs text-status-danger-fg">{errors.event}</p> : null}
          </label>
        )}

        {selectedIsMatch ? (
          <NumberField label="Minute" value={minute} onChange={setMinute} min={0} max={130} error={errors.moment} />
        ) : (
          <label className="block text-sm font-medium text-text">
            Heure
            <input
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text"
            />
            {errors.moment ? <p className="mt-1 text-xs text-status-danger-fg">{errors.moment}</p> : null}
          </label>
        )}

        <TextArea
          label="Circonstances"
          value={circumstances}
          onChange={setCircumstances}
          placeholder="Ce qui s'est passé, en quelques mots."
          error={errors.circumstances}
        />

        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
