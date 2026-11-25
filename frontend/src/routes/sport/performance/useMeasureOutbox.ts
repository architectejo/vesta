import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../../api/client";
import {
  bulkPerformanceResults,
  type BulkPerformanceItem,
  type BulkPerformanceResponse,
} from "../../../api/performance";
import { useOfflineActionQueue } from "../../../hooks/useOfflineActionQueue";
import type { PendingMeasureBatch, RefusedMeasure } from "./measureTypes";

/** File des lots de mesures en attente d'envoi (CDC 6.6), partagée par tous les écrans de la séance. */
export const MEASURE_QUEUE_KEY = "vesta.offline.performance-measures";
/** Mesures refusées par l'API pour un joueur : gardées sur le téléphone pour être réessayées. */
export const REFUSED_MEASURES_KEY = "vesta.performance.refused-measures";

export type SubmitOutcome = { kind: "queued" } | { kind: "sent"; response: BulkPerformanceResponse };

function readRefused(): RefusedMeasure[] {
  try {
    const raw = window.localStorage.getItem(REFUSED_MEASURES_KEY);
    const parsed = raw ? (JSON.parse(raw) as RefusedMeasure[]) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeRefused(entries: RefusedMeasure[]): void {
  try {
    window.localStorage.setItem(REFUSED_MEASURES_KEY, JSON.stringify(entries));
  } catch {
    // Stockage indisponible : la liste vit alors en mémoire pour la session.
  }
}

function toRefused(batch: PendingMeasureBatch, item: BulkPerformanceItem, message: string): RefusedMeasure {
  const id = item.client_uuid ?? crypto.randomUUID();
  const meta = batch.meta[item.client_uuid ?? ""];
  return {
    id,
    eventId: batch.eventId,
    testId: batch.body.test_id,
    testName: batch.testName,
    name: meta?.name ?? `Joueur ${item.membership_id}`,
    label: meta?.label ?? "",
    message,
    item,
    method: batch.body.method,
    startMode: batch.body.start_mode,
    lotUuid: batch.body.client_uuid,
  };
}

/**
 * Envoi des mesures avec file hors connexion (6.6) : réutilise
 * `useOfflineActionQueue` du pointage. Un échec réseau met le lot en file avec
 * ses `client_uuid` (rien n'est dupliqué au renvoi) ; un refus de l'API pour un
 * joueur (inapte, non pointé, fenêtre fermée…) garde la mesure localement avec
 * le message du serveur, sans bloquer les autres joueurs.
 */
export function useMeasureOutbox() {
  const queryClient = useQueryClient();
  const [refused, setRefused] = useState<RefusedMeasure[]>(() => readRefused());
  const refusedRef = useRef(refused);

  const persistRefused = useCallback((next: RefusedMeasure[]) => {
    refusedRef.current = next;
    setRefused(next);
    writeRefused(next);
  }, []);

  const addRefused = useCallback(
    (entries: RefusedMeasure[]) => {
      const ids = new Set(entries.map((entry) => entry.id));
      persistRefused([...refusedRef.current.filter((entry) => !ids.has(entry.id)), ...entries]);
    },
    [persistRefused],
  );

  const refresh = useCallback(
    (eventId: number) => {
      void queryClient.invalidateQueries({ queryKey: ["sport", "performance"] });
      void queryClient.invalidateQueries({ queryKey: ["sport", "session-stats", eventId] });
    },
    [queryClient],
  );

  /** Range les refus par joueur d'une réponse de l'API dans la liste locale. */
  const absorb = useCallback(
    (batch: PendingMeasureBatch, response: BulkPerformanceResponse) => {
      const entries: RefusedMeasure[] = [];
      batch.body.items.forEach((item, index) => {
        const candidate = response.results[index];
        const result =
          candidate && candidate.membership_id === item.membership_id
            ? candidate
            : response.results.find((r) => r.membership_id === item.membership_id && r.outcome === "refused");
        if (result?.outcome === "refused") entries.push(toRefused(batch, item, result.message));
      });
      if (entries.length > 0) addRefused(entries);
      refresh(batch.eventId);
    },
    [addRefused, refresh],
  );

  const queue = useOfflineActionQueue<PendingMeasureBatch>({
    storageKey: MEASURE_QUEUE_KEY,
    processItem: async (batch) => {
      const response = await bulkPerformanceResults(batch.eventId, batch.body);
      absorb(batch, response);
    },
    // Refus du lot entier (droit retiré, test archivé…) : on garde chaque mesure localement.
    onRejected: (batch, message) => {
      addRefused(batch.body.items.map((item) => toRefused(batch, item, message)));
      refresh(batch.eventId);
    },
  });
  const enqueue = queue.enqueue;

  const submit = useCallback(
    async (batch: PendingMeasureBatch): Promise<SubmitOutcome> => {
      if (typeof navigator !== "undefined" && !navigator.onLine) {
        enqueue(batch);
        return { kind: "queued" };
      }
      try {
        const response = await bulkPerformanceResults(batch.eventId, batch.body);
        absorb(batch, response);
        return { kind: "sent", response };
      } catch (error) {
        if (error instanceof ApiError && error.status === 0) {
          enqueue(batch);
          return { kind: "queued" };
        }
        throw error;
      }
    },
    [absorb, enqueue],
  );

  const retryRefused = useCallback(
    (id: string) => {
      const entry = refusedRef.current.find((candidate) => candidate.id === id);
      if (!entry) return;
      persistRefused(refusedRef.current.filter((candidate) => candidate.id !== id));
      enqueue({
        eventId: entry.eventId,
        testName: entry.testName,
        body: {
          test_id: entry.testId,
          method: entry.method,
          start_mode: entry.startMode,
          client_uuid: entry.lotUuid,
          items: [entry.item],
        },
        meta: { [id]: { name: entry.name, label: entry.label } },
      });
    },
    [enqueue, persistRefused],
  );

  const discardRefused = useCallback(
    (id: string) => persistRefused(refusedRef.current.filter((candidate) => candidate.id !== id)),
    [persistRefused],
  );

  return {
    submit,
    refused,
    retryRefused,
    discardRefused,
    pendingBatches: queue.items,
    pendingCount: queue.pendingCount,
    isOnline: queue.isOnline,
    isSyncing: queue.isSyncing,
    retryNow: queue.retryNow,
  };
}

export type MeasureOutbox = ReturnType<typeof useMeasureOutbox>;
