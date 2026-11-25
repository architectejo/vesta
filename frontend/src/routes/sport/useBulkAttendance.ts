import { useCallback, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  BULK_ATTENDANCE_MAX_ITEMS,
  bulkMarkAttendance,
  type BulkAttendanceInput,
  type BulkAttendanceItem,
  type BulkAttendanceResponse,
  type BulkAttendanceResult,
  type BulkExcuseReasonCode,
} from "../../api/sport";
import { useToast } from "../../design-system";
import { formatTime } from "./sportTime";

export type BulkEventKind = "session" | "match";

export interface BulkRequest {
  action: "arrive" | "excuse";
  /** ISO 8601 ; absent = maintenant (l'API prend l'heure du serveur). */
  arrivedAt?: string;
  reasonCode?: BulkExcuseReasonCode;
  reasonDetail?: string;
}

export interface BulkOfflineItem {
  membershipId: number;
  clientUuid: string;
  clientRecordedAt: string;
}

export interface BulkSummary {
  counts: BulkAttendanceResponse["counts"];
  results: BulkAttendanceResult[];
}

interface Options {
  kind: BulkEventKind;
  eventId: number;
  /** Rafraîchit la page après un envoi. */
  onChanged: () => void;
  /** File locale (6.6) pour le pointage d'arrivée hors connexion. */
  enqueueOffline?: (item: BulkOfflineItem) => void;
}

export function pluralPlayers(n: number): string {
  return `${n} joueur${n > 1 ? "s" : ""}`;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n > 1 ? "s" : ""}`;
}

/**
 * Sélection multiple et envoi groupé du pointage (docs/ecrans/
 * sport-pointage-selection-multiple.md). Aucune règle métier ici : l'API
 * décide du statut (Présent / En retard), des refus et du verrouillage.
 */
export function useBulkAttendance({ kind, eventId, onChanged, enqueueOffline }: Options) {
  const { showToast } = useToast();
  const [active, setActive] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);
  const [summary, setSummary] = useState<BulkSummary | null>(null);
  const inFlight = useRef(false);
  // Un client_uuid par joueur, généré une fois par lot et conservé tant que le
  // lot n'a pas reçu de réponse de l'API (nouvel essai après coupure réseau).
  const uuids = useRef(new Map<number, string>());
  const recordedAt = useRef<string | null>(null);

  const start = useCallback(() => setActive(true), []);
  const stop = useCallback(() => {
    setActive(false);
    setSelected([]);
    setError(undefined);
  }, []);

  const toggle = useCallback((id: number) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }, []);

  /** Ajoute, dans l'ordre d'affichage, les joueurs pas encore cochés. */
  const checkAll = useCallback((ids: number[]) => {
    setSelected((prev) => [...prev, ...ids.filter((id) => !prev.includes(id))]);
  }, []);
  const uncheckAll = useCallback(() => setSelected([]), []);

  function resetBatch() {
    uuids.current = new Map();
    recordedAt.current = null;
  }

  function buildItems(): BulkAttendanceItem[] {
    if (!recordedAt.current) recordedAt.current = new Date().toISOString();
    const stamp = recordedAt.current;
    return selected.map((membershipId, index) => {
      let uuid = uuids.current.get(membershipId);
      if (!uuid) {
        uuid = crypto.randomUUID();
        uuids.current.set(membershipId, uuid);
      }
      return {
        membership_id: membershipId,
        client_uuid: uuid,
        client_recorded_at: stamp,
        selection_rank: index + 1,
      };
    });
  }

  function finalize(responses: BulkAttendanceResponse[], request: BulkRequest, usedTime: string): number[] {
    const results = responses.flatMap((r) => r.results);
    const counts = responses.reduce(
      (acc, r) => ({
        created: acc.created + r.counts.created,
        skipped: acc.skipped + r.counts.skipped,
        refused: acc.refused + r.counts.refused,
      }),
      { created: 0, skipped: 0, refused: 0 },
    );
    resetBatch();
    onChanged();
    setError(undefined);
    const refusedIds = results.filter((r) => r.outcome === "refused").map((r) => r.membership_id);
    if (counts.skipped + counts.refused === 0) {
      showToast(
        request.action === "arrive"
          ? `${pluralPlayers(counts.created)} ${counts.created > 1 ? "pointés" : "pointé"} à ${formatTime(usedTime)}.`
          : `${plural(counts.created, "absence")} ${counts.created > 1 ? "excusées enregistrées" : "excusée enregistrée"}.`,
      );
      setActive(false);
      setSelected([]);
    } else {
      setSummary({ counts, results });
      // La sélection ne garde que les refusés, pour réessayer.
      setSelected(refusedIds);
      if (refusedIds.length === 0) setActive(false);
    }
    return refusedIds;
  }

  /** Renvoie true si la modale de confirmation peut se fermer. */
  const submit = useCallback(
    async (request: BulkRequest): Promise<boolean> => {
      if (inFlight.current || selected.length === 0) return false;
      inFlight.current = true;
      setSubmitting(true);
      setError(undefined);
      const items = buildItems();
      const usedTime = request.arrivedAt ?? recordedAt.current ?? new Date().toISOString();
      const responses: BulkAttendanceResponse[] = [];
      try {
        for (let i = 0; i < items.length; i += BULK_ATTENDANCE_MAX_ITEMS) {
          const body: BulkAttendanceInput = {
            action: request.action,
            items: items.slice(i, i + BULK_ATTENDANCE_MAX_ITEMS),
          };
          if (request.arrivedAt) body.arrived_at = request.arrivedAt;
          if (request.action === "excuse") {
            body.reason_code = request.reasonCode;
            if (request.reasonDetail?.trim()) body.reason_detail = request.reasonDetail.trim();
          }
          responses.push(await bulkMarkAttendance(kind, eventId, body));
        }
        finalize(responses, request, usedTime);
        return true;
      } catch (err) {
        if (responses.length > 0) {
          // Lots précédents déjà enregistrés : la suite reste cochée.
          const done = new Set(responses.flatMap((r) => r.results.map((x) => x.membership_id)));
          const refused = finalize(responses, request, usedTime);
          setSelected([...refused, ...items.filter((it) => !done.has(it.membership_id)).map((it) => it.membership_id)]);
          setActive(true);
          showToast("Une partie des pointages n'a pas pu être envoyée. Réessayez.");
          return true;
        }
        if (err instanceof ApiError && err.status === 0) {
          if (request.action === "arrive" && enqueueOffline) {
            for (const it of items) {
              enqueueOffline({
                membershipId: it.membership_id,
                clientUuid: it.client_uuid!,
                clientRecordedAt: request.arrivedAt ?? it.client_recorded_at!,
              });
            }
            showToast(
              `${plural(items.length, "pointage")} ${items.length > 1 ? "enregistrés" : "enregistré"} sur ce téléphone. Ils seront envoyés au retour du réseau.`,
            );
            resetBatch();
            setActive(false);
            setSelected([]);
            return true;
          }
          setError("Vous êtes hors connexion. Réessayez au retour du réseau.");
        } else if (err instanceof ApiError && err.status === 409 && err.code === "event_locked") {
          showToast(
            kind === "session"
              ? "La séance vient d'être verrouillée. Rien n'a été enregistré."
              : "Le match vient d'être verrouillé. Rien n'a été enregistré.",
          );
          onChanged();
          resetBatch();
          setActive(false);
          setSelected([]);
          return true;
        } else if (err instanceof ApiError && err.status === 403) {
          setError(`Vous n'avez plus le droit de pointer ${kind === "session" ? "cette séance" : "ce match"}.`);
          onChanged();
        } else if (err instanceof ApiError) {
          setError(err.detail);
        } else {
          setError("Pointage non enregistré. Réessayez.");
        }
        return false;
      } finally {
        inFlight.current = false;
        setSubmitting(false);
      }
    },
    // buildItems/finalize lisent des refs et l'état courant : recréés avec `selected`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selected, kind, eventId, enqueueOffline, onChanged],
  );

  return {
    active,
    selected,
    submitting,
    error,
    summary,
    clearSummary: () => setSummary(null),
    clearError: () => setError(undefined),
    start,
    stop,
    toggle,
    checkAll,
    uncheckAll,
    submit,
  };
}

export type BulkAttendanceState = ReturnType<typeof useBulkAttendance>;
