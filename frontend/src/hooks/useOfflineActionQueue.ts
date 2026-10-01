import { useCallback, useEffect, useRef, useState } from "react";

/**
 * File d'actions locale horodatée (CDC 6.6 : pointage, incidents, feuille
 * de match). Chaque action est écrite dans `localStorage` avec son heure
 * réelle de saisie (`createdAt`), puis rejouée dans l'ordre au retour du
 * réseau. Générique : chaque écran fournit son propre `processItem`
 * (appelle la bonne fonction `api/sport.ts`) et sa propre clé de stockage.
 *
 * Distinction volontaire entre les deux échecs possibles d'un envoi
 * (CLAUDE.md §5 : aucune règle métier ici, seulement de l'orchestration) :
 * - échec réseau (`ApiError.status === 0`) : l'action reste en file, on
 *   réessaiera plus tard, sans qu'aucune autre action ne soit tentée
 *   avant elle (ordre conservé) ;
 * - refus métier de l'API (400/403/409, ex. joueur devenu non
 *   sélectionnable) : l'action est retirée de la file et `onRejected` est
 *   appelé avec le message renvoyé par l'API, jamais reconstruit ici.
 */

export interface QueueItem<TPayload> {
  id: string;
  createdAt: string;
  payload: TPayload;
}

interface ApiErrorLike {
  status: number;
  detail: string;
}

function isApiErrorLike(error: unknown): error is ApiErrorLike {
  return typeof error === "object" && error !== null && "status" in error && "detail" in error;
}

export interface UseOfflineActionQueueOptions<TPayload> {
  storageKey: string;
  processItem: (payload: TPayload) => Promise<void>;
  onRejected?: (payload: TPayload, message: string) => void;
  retryIntervalMs?: number;
}

export interface UseOfflineActionQueueResult<TPayload> {
  pendingCount: number;
  /** Actions encore en file, dans l'ordre — utile pour un affichage local
   * optimiste ou pour `SyncIndicator`. */
  items: QueueItem<TPayload>[];
  isOnline: boolean;
  isSyncing: boolean;
  /** Horodatage local (ce n'est qu'un repère d'affichage, jamais une règle). */
  enqueue: (payload: TPayload) => QueueItem<TPayload>;
  retryNow: () => void;
}

function readQueue<TPayload>(storageKey: string): QueueItem<TPayload>[] {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as QueueItem<TPayload>[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeQueue<TPayload>(storageKey: string, items: QueueItem<TPayload>[]): void {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(items));
  } catch {
    // Stockage indisponible (navigation privée, quota) : dégrade sans
    // planter — la file vit alors en mémoire pour la session en cours.
  }
}

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function useOfflineActionQueue<TPayload>({
  storageKey,
  processItem,
  onRejected,
  retryIntervalMs = 15_000,
}: UseOfflineActionQueueOptions<TPayload>): UseOfflineActionQueueResult<TPayload> {
  const [items, setItems] = useState<QueueItem<TPayload>[]>(() => readQueue<TPayload>(storageKey));
  const [isOnline, setIsOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  const [isSyncing, setIsSyncing] = useState(false);
  const processItemRef = useRef(processItem);
  processItemRef.current = processItem;
  const onRejectedRef = useRef(onRejected);
  onRejectedRef.current = onRejected;
  const flushingRef = useRef(false);
  const itemsRef = useRef(items);
  itemsRef.current = items;

  const persist = useCallback(
    (next: QueueItem<TPayload>[]) => {
      itemsRef.current = next;
      setItems(next);
      writeQueue(storageKey, next);
    },
    [storageKey],
  );

  const flush = useCallback(async () => {
    if (flushingRef.current) return;
    if (typeof navigator !== "undefined" && !navigator.onLine) return;
    flushingRef.current = true;
    setIsSyncing(true);
    try {
      // Traitement séquentiel : préserve l'ordre d'horodatage (important
      // pour le pointage, dont l'ordre d'arrivée alimente l'alternance
      // A/B, 10.2 n° 7).
      while (itemsRef.current.length > 0) {
        const [next, ...rest] = itemsRef.current;
        if (!next) break;
        try {
          await processItemRef.current(next.payload);
          persist(rest);
        } catch (error) {
          if (isApiErrorLike(error) && error.status !== 0) {
            // Refus métier : on retire l'action et on prévient l'appelant,
            // mais on continue avec les suivantes.
            persist(rest);
            onRejectedRef.current?.(next.payload, error.detail);
            continue;
          }
          // Échec réseau (ou inattendu) : on s'arrête, l'action reste en
          // tête de file pour la prochaine tentative.
          break;
        }
      }
    } finally {
      flushingRef.current = false;
      setIsSyncing(false);
    }
  }, [persist]);

  useEffect(() => {
    function handleOnline() {
      setIsOnline(true);
      void flush();
    }
    function handleOffline() {
      setIsOnline(false);
    }
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [flush]);

  useEffect(() => {
    void flush();
    const interval = window.setInterval(() => {
      if (itemsRef.current.length > 0) void flush();
    }, retryIntervalMs);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const enqueue = useCallback(
    (payload: TPayload): QueueItem<TPayload> => {
      const item: QueueItem<TPayload> = { id: newId(), createdAt: new Date().toISOString(), payload };
      persist([...itemsRef.current, item]);
      void flush();
      return item;
    },
    [persist, flush],
  );

  const retryNow = useCallback(() => {
    void flush();
  }, [flush]);

  return { pendingCount: items.length, items, isOnline, isSyncing, enqueue, retryNow };
}
