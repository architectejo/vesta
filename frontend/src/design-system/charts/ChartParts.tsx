import { useId, useLayoutEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { EmptyState } from "../components/EmptyState";
import { Loader } from "../components/Loader";
import { patternCss, seriesStyle, type SeriesPattern } from "./chartUtils";

export type ChartState = "ready" | "loading" | "error";

/** Propriétés communes à tous les graphiques. */
export interface ChartCommonProps {
  /** Nom du graphique (`aria-label` de la figure). */
  title: string;
  /** Résumé de lecture pour lecteur d'écran (`sr-only`). Un résumé est généré par défaut. */
  summary?: string;
  state?: ChartState;
  /** Message affiché quand il n'y a aucune donnée. */
  emptyMessage?: string;
  errorMessage?: string;
  onRetry?: () => void;
  /** Hauteur du graphique en px (160 dans une carte, 220 dans une modale). */
  height?: number;
  className?: string;
}

export interface ChartTable {
  caption?: string;
  columns: string[];
  rows: Array<Array<string | number | null>>;
}

export interface ChartLegendItem {
  label: string;
  /** Index de série (couleur, tracé, motif). */
  seriesIndex: number;
  kind: "line" | "bar";
}

interface ChartFigureProps extends ChartCommonProps {
  summary: string;
  isEmpty: boolean;
  legend?: ChartLegendItem[];
  /** Ligne de référence décrite au-dessus du tracé (jamais écrite sur le tracé). */
  referenceText?: string;
  table?: ChartTable;
  children: ReactNode;
}

function LegendSwatch({ item }: { item: ChartLegendItem }) {
  const style = seriesStyle(item.seriesIndex);
  if (item.kind === "line") {
    return (
      <svg width="24" height="10" aria-hidden="true" focusable="false">
        <line
          x1="0"
          y1="5"
          x2="24"
          y2="5"
          stroke={style.color}
          strokeWidth="2.5"
          strokeDasharray={style.dash}
        />
      </svg>
    );
  }
  return (
    <span
      aria-hidden="true"
      className="inline-block h-3 w-4 rounded-[2px] border"
      style={{ ...patternCss(style.pattern, style.color), borderColor: style.color }}
    />
  );
}

export function ChartLegend({ items }: { items: ChartLegendItem[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text">
      {items.map((item) => (
        <li key={`${item.seriesIndex}-${item.label}`} className="inline-flex items-center gap-1.5">
          <LegendSwatch item={item} />
          <span>{item.label}</span>
        </li>
      ))}
    </ul>
  );
}

function ChartDataTable({ table }: { table: ChartTable }) {
  return (
    <details className="mt-2">
      <summary className="inline-flex min-h-[36px] cursor-pointer items-center rounded-sm text-sm font-medium text-primary-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus">
        Voir les données
      </summary>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs text-text">
          {table.caption ? <caption className="sr-only">{table.caption}</caption> : null}
          <thead>
            <tr>
              {table.columns.map((column) => (
                <th
                  key={column}
                  scope="col"
                  className="border-b border-border px-2 py-1.5 font-semibold"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) =>
                  cellIndex === 0 ? (
                    <th
                      key={cellIndex}
                      scope="row"
                      className="border-b border-border px-2 py-1.5 font-medium"
                    >
                      {cell ?? "—"}
                    </th>
                  ) : (
                    <td key={cellIndex} className="border-b border-border px-2 py-1.5 tabular-nums">
                      {cell ?? "—"}
                    </td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/**
 * Cadre commun : `<figure>` + `<figcaption>` (résumé sr-only), états
 * chargement / vide / erreur, légende textuelle et tableau de données
 * repliable (alternative textuelle).
 */
export function ChartFigure({
  title,
  summary,
  state = "ready",
  isEmpty,
  emptyMessage,
  errorMessage,
  onRetry,
  height = 160,
  className = "",
  legend,
  referenceText,
  table,
  children,
}: ChartFigureProps) {
  let body: ReactNode;
  if (state === "loading") {
    body = (
      <div style={{ minHeight: height }}>
        <Loader loading variant="list" listSkeleton="chart" count={1} onRetry={onRetry} />
      </div>
    );
  } else if (state === "error") {
    body = (
      <EmptyState
        variant="error"
        message={errorMessage ?? "Impossible de charger ce graphique."}
        actionLabel="Réessayer"
        onAction={onRetry}
      />
    );
  } else if (isEmpty) {
    body = <EmptyState message={emptyMessage ?? "Aucune donnée sur la période."} />;
  } else {
    body = (
      <>
        {referenceText ? (
          <p className="mb-1 flex items-center gap-1.5 text-xs text-text">
            <svg width="24" height="10" aria-hidden="true" focusable="false">
              <line x1="0" y1="5" x2="24" y2="5" stroke="var(--color-text-muted)" strokeWidth="1.5" strokeDasharray="1 4" strokeLinecap="round" />
            </svg>
            <span>{referenceText}</span>
          </p>
        ) : null}
        <div className="vesta-chart-enter">{children}</div>
        {legend ? <ChartLegend items={legend} /> : null}
        {table ? <ChartDataTable table={table} /> : null}
      </>
    );
  }

  return (
    <figure aria-label={title} className={["m-0 w-full min-w-0", className].join(" ")}>
      {body}
      <figcaption className="sr-only">{summary}</figcaption>
    </figure>
  );
}

interface ChartHitProps {
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  onSelect?: () => void;
  children: ReactNode;
}

/**
 * Zone interactive d'un graphique : `role="button"`, Entrée / Espace,
 * focus visible, cible >= 36 px (garantie par l'appelant). Sans `onSelect`,
 * simple groupe sans rôle.
 */
export function ChartHit({ x, y, width, height, label, onSelect, children }: ChartHitProps) {
  if (!onSelect) return <g>{children}</g>;
  const onKeyDown = (event: KeyboardEvent<SVGGElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect();
    }
  };
  return (
    <g
      role="button"
      tabIndex={0}
      aria-label={label}
      className="vesta-chart-hit"
      onClick={onSelect}
      onKeyDown={onKeyDown}
    >
      <rect className="vesta-chart-hit__rect" x={x} y={y} width={width} height={height} rx={6} />
      {children}
    </g>
  );
}

/** Identifiant unique (sans deux-points) pour les motifs SVG d'une instance. */
export function usePatternId(): string {
  return `vc${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
}

/** Définitions des motifs de surface (hachures, points, quadrillage). */
export function PatternDefs({ id }: { id: string }) {
  const overlay = "var(--color-surface)";
  return (
    <defs>
      <pattern
        id={`${id}-stripes`}
        width="5"
        height="5"
        patternUnits="userSpaceOnUse"
        patternTransform="rotate(45)"
      >
        <rect width="2" height="5" fill={overlay} />
      </pattern>
      <pattern id={`${id}-dots`} width="5" height="5" patternUnits="userSpaceOnUse">
        <circle cx="2.5" cy="2.5" r="1.2" fill={overlay} />
      </pattern>
      <pattern id={`${id}-cross`} width="5" height="5" patternUnits="userSpaceOnUse">
        <rect width="5" height="1" fill={overlay} />
        <rect width="1" height="5" fill={overlay} />
      </pattern>
    </defs>
  );
}

interface SeriesRectProps {
  x: number;
  y: number;
  width: number;
  height: number;
  seriesIndex: number;
  patternId: string;
}

/** Rectangle de série : couleur + motif (jamais la couleur seule). */
export function SeriesRect({ x, y, width, height, seriesIndex, patternId }: SeriesRectProps) {
  const style = seriesStyle(seriesIndex);
  const pattern: SeriesPattern = style.pattern;
  const safeWidth = Math.max(0, width);
  const safeHeight = Math.max(0, height);
  return (
    <>
      <rect
        x={x}
        y={y}
        width={safeWidth}
        height={safeHeight}
        fill={style.color}
        stroke={style.color}
        strokeWidth={1}
        rx={2}
      />
      {pattern !== "solid" ? (
        <rect
          x={x}
          y={y}
          width={safeWidth}
          height={safeHeight}
          fill={`url(#${patternId}-${pattern})`}
          rx={2}
        />
      ) : null}
    </>
  );
}


/**
 * Cadre défilant horizontalement d'un graphique : à l'ouverture (et quand la
 * largeur change) il se cale à DROITE, pour que la fin des données (période
 * la plus récente) soit visible. Dès que l'utilisateur défile lui-même
 * (toucher, molette, clavier), le calage automatique s'arrête.
 */
export function ScrollFrame({
  contentWidth,
  frameWidth,
  label,
  children,
}: {
  contentWidth: number;
  frameWidth: number;
  label: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const touched = useRef(false);
  const scrolls = contentWidth > frameWidth;

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node || !scrolls || touched.current) return;
    node.scrollLeft = node.scrollWidth - node.clientWidth;
  }, [contentWidth, frameWidth, scrolls]);

  const markTouched = () => {
    touched.current = true;
  };

  return (
    <div
      ref={ref}
      className={scrolls ? "overflow-x-auto" : undefined}
      tabIndex={scrolls ? 0 : undefined}
      role={scrolls ? "region" : undefined}
      aria-label={scrolls ? `${label} (défilement horizontal)` : undefined}
      onTouchStart={markTouched}
      onWheel={markTouched}
      onKeyDown={markTouched}
      onPointerDown={markTouched}
    >
      {children}
    </div>
  );
}
