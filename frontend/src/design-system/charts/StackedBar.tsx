import type { StatusFamily } from "../components/statusMap";
import { formatNumber, isNumber, patternCss, seriesStyle } from "./chartUtils";
import { ChartFigure, type ChartCommonProps } from "./ChartParts";

export interface StackedBarSegment {
  label: string;
  value: number;
  /**
   * Famille de statut (vert, orange, rouge, violet, gris) pour une répartition
   * de statuts ; sans famille, la couleur de série correspondant à la position.
   */
  family?: StatusFamily;
}

export interface StackedBarProps extends ChartCommonProps {
  segments: StackedBarSegment[];
  /** Toucher / Entrée / Espace sur un segment ou sa ligne de légende. */
  onSelect?: (index: number, segment: StackedBarSegment) => void;
}

function segmentColor(segment: StackedBarSegment, index: number): string {
  return segment.family ? `var(--color-status-${segment.family}-dot)` : seriesStyle(index).color;
}

function segmentPattern(index: number) {
  // Motif par position : plein, hachures, points, quadrillage, puis plein.
  return seriesStyle(index).pattern;
}

/**
 * Barre horizontale à 100 % (jamais de camembert). Chaque segment est écrit
 * dans la légende (libellé, nombre, pourcentage) : la couleur ne porte jamais
 * seule l'information, et le motif du segment suit sa position.
 */
export function StackedBar({ segments, onSelect, title, summary, height = 28, ...common }: StackedBarProps) {
  const safe = segments.map((s) => ({ ...s, value: isNumber(s.value) ? Math.max(0, s.value) : 0 }));
  const total = safe.reduce((sum, s) => sum + s.value, 0);
  const percent = (value: number) => `${formatNumber((value / (total || 1)) * 100)} %`;
  const describe = (s: StackedBarSegment & { value: number }) =>
    `${s.label} : ${formatNumber(s.value)} (${percent(s.value)})`;

  const autoSummary = summary ?? `${title}. Total ${formatNumber(total)}. ${safe.map(describe).join(" ; ")}.`;

  return (
    <ChartFigure
      {...common}
      title={title}
      summary={autoSummary}
      height={height}
      isEmpty={total === 0}
      table={{
        caption: title,
        columns: ["Statut", "Nombre", "Part"],
        rows: safe.map((s) => [s.label, formatNumber(s.value), percent(s.value)]),
      }}
    >
      <div
        role={onSelect ? "group" : "img"}
        aria-label={autoSummary}
        className="flex w-full overflow-hidden rounded-sm border border-border-strong"
        style={{ height }}
      >
        {safe.map((s, index) => {
          if (s.value === 0) return null;
          const style = { flexGrow: s.value, flexBasis: 0, ...patternCss(segmentPattern(index), segmentColor(s, index)) };
          const separator = "border-r-2 border-surface last:border-r-0";
          return onSelect ? (
            <button
              key={index}
              type="button"
              aria-label={describe(s)}
              onClick={() => onSelect(index, s)}
              className={[separator, "min-w-[6px] focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus"].join(" ")}
              style={style}
            />
          ) : (
            <div key={index} className={[separator, "min-w-[6px]"].join(" ")} style={style} />
          );
        })}
      </div>
      <ul className="mt-2 grid grid-cols-1 gap-0.5 text-sm text-text">
        {safe.map((s, index) => {
          const content = (
            <>
              <span
                aria-hidden="true"
                className="inline-block h-3.5 w-4 shrink-0 rounded-[2px] border border-border-strong"
                style={patternCss(segmentPattern(index), segmentColor(s, index))}
              />
              <span className="min-w-0 flex-1">{s.label}</span>
              <span className="font-semibold tabular-nums">{formatNumber(s.value)}</span>
              <span className="w-14 text-right text-xs tabular-nums text-text-muted">{percent(s.value)}</span>
            </>
          );
          return (
            <li key={index}>
              {onSelect ? (
                <button
                  type="button"
                  onClick={() => onSelect(index, s)}
                  className="flex min-h-[36px] w-full items-center gap-2 rounded-sm px-1 text-left hover:bg-surface-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"
                >
                  {content}
                </button>
              ) : (
                <div className="flex min-h-[28px] items-center gap-2 px-1">{content}</div>
              )}
            </li>
          );
        })}
      </ul>
    </ChartFigure>
  );
}
