import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";

export interface TabItem<T extends string> {
  value: T;
  label: string;
}

export interface TabsProps<T extends string> {
  items: Array<TabItem<T>>;
  value: T;
  onChange: (value: T) => void;
  label: string;
}

/** Largeur du fondu d'indice de défilement, en px. */
const FADE_WIDTH = 24;

/**
 * Masque de fondu aux bords qui cachent encore des onglets. Un masque plutôt
 * qu'un dégradé coloré : la barre est posée tantôt sur une carte, tantôt sur
 * le fond de page (Séance), et le fondu doit rester juste dans les trois
 * thèmes sans connaître la couleur de dessous.
 */
function fadeMask(start: boolean, end: boolean): CSSProperties | undefined {
  if (!start && !end) return undefined;
  const from = start ? `transparent 0, #000 ${FADE_WIDTH}px` : "#000 0";
  const to = end ? `#000 calc(100% - ${FADE_WIDTH}px), transparent 100%` : "#000 100%";
  const image = `linear-gradient(to right, ${from}, ${to})`;
  return { maskImage: image, WebkitMaskImage: image };
}

/**
 * Onglets horizontaux (docs/lot0/design-system.md §3.1), 40 px, défilement
 * horizontal si trop nombreux.
 *
 * Vérification visuelle B7 (360 px) : la barre coupait le dernier onglet
 * (« Su[spendus] ») sans rien indiquer. Deux indices désormais :
 * - un fondu au bord droit (et au bord gauche une fois défilé) tant qu'il
 *   reste des onglets cachés de ce côté ; purement visuel, il n'intercepte
 *   aucun toucher et n'est pas annoncé aux lecteurs d'écran ;
 * - l'onglet actif est ramené dans la vue à chaque changement.
 * La navigation au clavier reste celle des boutons (Tab) ; le navigateur fait
 * défiler la ligne jusqu'à l'onglet qui reçoit le focus.
 */
export function Tabs<T extends string>({ items, value, onChange, label }: TabsProps<T>) {
  const listRef = useRef<HTMLDivElement>(null);
  const [overflow, setOverflow] = useState({ start: false, end: false });

  const measure = useCallback(() => {
    const el = listRef.current;
    if (!el) return;
    const maxScroll = el.scrollWidth - el.clientWidth;
    // 1 px de tolérance : les largeurs fractionnaires arrondissent mal.
    const next = { start: el.scrollLeft > 1, end: maxScroll - el.scrollLeft > 1 };
    setOverflow((prev) => (prev.start === next.start && prev.end === next.end ? prev : next));
  }, []);

  useLayoutEffect(() => {
    measure();
  }, [measure, items]);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    window.addEventListener("resize", measure);
    let observer: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => measure());
      observer.observe(el);
    }
    return () => {
      window.removeEventListener("resize", measure);
      observer?.disconnect();
    };
  }, [measure]);

  // Ramène l'onglet actif dans la vue, hors de la zone de fondu, sans faire
  // défiler la page verticalement (pas de `scrollIntoView`).
  useEffect(() => {
    const el = listRef.current;
    const active = el?.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]');
    if (!el || !active) return;
    const left = active.offsetLeft - el.offsetLeft;
    const right = left + active.offsetWidth;
    if (left - FADE_WIDTH < el.scrollLeft) {
      el.scrollLeft = Math.max(0, left - FADE_WIDTH);
    } else if (right + FADE_WIDTH > el.scrollLeft + el.clientWidth) {
      el.scrollLeft = right + FADE_WIDTH - el.clientWidth;
    }
    measure();
  }, [value, measure]);

  return (
    <div className="border-b border-border">
      <div
        ref={listRef}
        role="tablist"
        aria-label={label}
        onScroll={measure}
        data-overflow-start={overflow.start ? "" : undefined}
        data-overflow-end={overflow.end ? "" : undefined}
        style={fadeMask(overflow.start, overflow.end)}
        className="flex gap-4 overflow-x-auto"
      >
        {items.map((item) => {
          const active = item.value === value;
          return (
            <button
              key={item.value}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onChange(item.value)}
              className={[
                "h-10 shrink-0 whitespace-nowrap border-b-2 px-1 text-sm font-medium",
                active ? "border-primary text-text" : "border-transparent text-text-muted",
              ].join(" ")}
            >
              {item.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
