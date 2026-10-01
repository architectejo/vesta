import { useEffect, useRef, useSyncExternalStore, type PointerEvent as ReactPointerEvent } from "react";

/**
 * Bus de glisser-déposer au doigt/à la souris, en pointer events natifs
 * (docs/ecrans/sport-plan-tactique.md §5.2 ; consigne explicite de la
 * tâche : aucune dépendance de drag-and-drop ajoutée). Permet à plusieurs
 * zones indépendantes (deux terrains A/B, le banc du tableau noir, la zone
 * « Non répartis ») de s'échanger des pions sans état React partagé lourd :
 * chaque zone s'enregistre avec une clé, chaque pion déclenche un
 * déplacement, le bus résout la zone survolée au relâchement avec
 * `document.elementFromPoint`.
 *
 * Alternative obligatoire au glisser (docs/lot0/design-system.md §3.8) :
 * ce bus ne gère que l'amélioration « glisser » ; chaque écran fournit en
 * plus un geste de toucher (menu, modale) qui produit exactement le même
 * appel API — voir `sport-seance.md` §3.2 point 3 et
 * `sport-plan-tactique.md` §4.4/§5.2. Le clavier utilise cette même
 * alternative de toucher (Entrée), plutôt qu'un réordonnancement au
 * clavier bas niveau : simplification documentée dans le compte rendu de
 * la tâche.
 */

export interface PitchDragItem<T = unknown> {
  kind: string;
  data: T;
  label: string;
}

export interface PitchDropPoint {
  xPct: number;
  yPct: number;
}

type DropHandler = (item: PitchDragItem, point: PitchDropPoint) => void;

interface ZoneEntry {
  el: HTMLElement;
  onDrop: DropHandler;
}

interface DragSnapshot {
  dragging: PitchDragItem | null;
  pointer: { x: number; y: number };
}

const DRAG_THRESHOLD_PX = 8;

class PitchDragBus {
  private zones = new Map<string, ZoneEntry>();
  private snapshot: DragSnapshot = { dragging: null, pointer: { x: 0, y: 0 } };
  private subscribers = new Set<() => void>();

  registerZone(key: string, el: HTMLElement, onDrop: DropHandler): void {
    this.zones.set(key, { el, onDrop });
  }

  unregisterZone(key: string): void {
    this.zones.delete(key);
  }

  subscribe = (fn: () => void): (() => void) => {
    this.subscribers.add(fn);
    return () => this.subscribers.delete(fn);
  };

  getSnapshot = (): DragSnapshot => this.snapshot;

  private notify(): void {
    this.subscribers.forEach((fn) => fn());
  }

  start(item: PitchDragItem, x: number, y: number): void {
    this.snapshot = { dragging: item, pointer: { x, y } };
    this.notify();
  }

  move(x: number, y: number): void {
    if (!this.snapshot.dragging) return;
    this.snapshot = { ...this.snapshot, pointer: { x, y } };
    this.notify();
  }

  end(x: number, y: number): void {
    const item = this.snapshot.dragging;
    this.snapshot = { dragging: null, pointer: { x, y } };
    this.notify();
    if (!item) return;
    const target = typeof document !== "undefined" ? document.elementFromPoint(x, y) : null;
    let el: HTMLElement | null = target as HTMLElement | null;
    let matched: ZoneEntry | undefined;
    while (el) {
      const key = el.getAttribute("data-pitch-dropzone");
      if (key && this.zones.has(key)) {
        matched = this.zones.get(key);
        break;
      }
      el = el.parentElement;
    }
    if (!matched) return;
    const rect = matched.el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const xPct = Math.min(100, Math.max(0, ((x - rect.left) / rect.width) * 100));
    const yPct = Math.min(100, Math.max(0, ((y - rect.top) / rect.height) * 100));
    matched.onDrop(item, { xPct, yPct });
  }

  cancel(): void {
    this.snapshot = { dragging: null, pointer: this.snapshot.pointer };
    this.notify();
  }
}

export const pitchDragBus = new PitchDragBus();

/**
 * Filet de sécurité : `pitchDragBus` est un singleton de module, indépendant
 * du cycle de vie React. Si l'élément qui a capturé le pointeur disparaît du
 * DOM en plein geste (ex. la liste se re-rend après une actualisation en
 * tâche de fond pendant un glissement) ou si le geste est interrompu sans
 * `pointerup`/`pointercancel` propre (perte de focus de la fenêtre, capture
 * d'écran, changement d'onglet), plus aucun événement n'atteint le bon
 * gestionnaire et `dragging` reste bloqué indéfiniment : le fantôme flottant
 * (`PitchDragGhost`) reste alors affiché en permanence, à l'endroit où le
 * pointeur a été perdu — constat du client (une pastille sombre immobile au
 * centre d'un terrain, sans rapport avec un joueur réel). Ces écouteurs au
 * niveau de la fenêtre sont sans risque en usage normal : `end`/`cancel`
 * sont sans effet si aucun glissement n'est en cours.
 */
if (typeof window !== "undefined") {
  window.addEventListener("pointerup", (event) => {
    if (pitchDragBus.getSnapshot().dragging) pitchDragBus.end(event.clientX, event.clientY);
  });
  window.addEventListener("pointercancel", () => pitchDragBus.cancel());
  window.addEventListener("blur", () => pitchDragBus.cancel());
}

/** État de glissement en cours, pour afficher le fantôme flottant. */
export function usePitchDragState(): DragSnapshot {
  return useSyncExternalStore(pitchDragBus.subscribe, pitchDragBus.getSnapshot, pitchDragBus.getSnapshot);
}

/** Enregistre un élément comme cible de dépose (terrain, banc…). */
export function usePitchDropZone(key: string | null, onDrop: DropHandler): (el: HTMLElement | null) => void {
  const onDropRef = useRef(onDrop);
  onDropRef.current = onDrop;
  const elRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!key || !elRef.current) return undefined;
    const handler: DropHandler = (item, point) => onDropRef.current(item, point);
    pitchDragBus.registerZone(key, elRef.current, handler);
    return () => pitchDragBus.unregisterZone(key);
  }, [key]);

  return (el: HTMLElement | null) => {
    elRef.current = el;
  };
}

export interface UsePitchDraggableOptions<T> {
  item: PitchDragItem<T> | null;
  disabled?: boolean;
  onTap?: () => void;
}

export interface PitchDraggableHandlers {
  onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
  onPointerMove: (event: ReactPointerEvent<HTMLElement>) => void;
  onPointerUp: (event: ReactPointerEvent<HTMLElement>) => void;
  onPointerCancel: () => void;
}

/** Pointeur pion : glisser (amélioration) ou toucher simple (menu/modale). */
export function usePitchDraggable<T>({ item, disabled, onTap }: UsePitchDraggableOptions<T>): PitchDraggableHandlers {
  const startRef = useRef<{ x: number; y: number; moved: boolean; pointerId: number } | null>(null);

  function onPointerDown(event: ReactPointerEvent<HTMLElement>): void {
    if (disabled) return;
    startRef.current = { x: event.clientX, y: event.clientY, moved: false, pointerId: event.pointerId };
  }

  function onPointerMove(event: ReactPointerEvent<HTMLElement>): void {
    const start = startRef.current;
    if (!start || disabled) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (!pitchDragBus.getSnapshot().dragging && Math.hypot(dx, dy) > DRAG_THRESHOLD_PX && item) {
      start.moved = true;
      (event.target as Element).setPointerCapture?.(event.pointerId);
      pitchDragBus.start(item, event.clientX, event.clientY);
    }
    if (pitchDragBus.getSnapshot().dragging) {
      event.preventDefault();
      pitchDragBus.move(event.clientX, event.clientY);
    }
  }

  function onPointerUp(event: ReactPointerEvent<HTMLElement>): void {
    const start = startRef.current;
    startRef.current = null;
    if (!start) return;
    if (pitchDragBus.getSnapshot().dragging) {
      pitchDragBus.end(event.clientX, event.clientY);
    } else if (!start.moved) {
      onTap?.();
    }
  }

  function onPointerCancel(): void {
    startRef.current = null;
    pitchDragBus.cancel();
  }

  return { onPointerDown, onPointerMove, onPointerUp, onPointerCancel };
}
