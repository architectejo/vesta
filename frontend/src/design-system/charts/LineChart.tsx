import {
  approxTextWidth,
  clamp,
  formatAxisNumber,
  formatNumber,
  isNumber,
  niceScale,
  seriesStyle,
  visibleLabelIndexes,
  withUnit,
} from "./chartUtils";
import {
  ChartFigure,
  ChartHit,
  ScrollFrame,
  type ChartCommonProps,
  type ChartLegendItem,
} from "./ChartParts";
import { useElementWidth } from "./useElementWidth";

export interface LineChartSeries {
  name: string;
  /** Une valeur par étiquette ; `null` = valeur absente (trou dans la courbe). */
  values: Array<number | null>;
}

export interface LineChartProps extends ChartCommonProps {
  /** Étiquettes de l'axe horizontal (une par point). */
  labels: string[];
  /** Une série, deux au plus (les suivantes sont ignorées). */
  series: LineChartSeries[];
  yMin?: number;
  yMax?: number;
  /** Unité écrite après les valeurs (« % », « $ »). */
  unit?: string;
  /** Ligne de référence en tirets (ex. moyenne). */
  reference?: { value: number; label: string };
  formatValue?: (value: number) => string;
  /** Toucher / Entrée / Espace sur un point (colonne). */
  onSelect?: (index: number) => void;
}

const MARGIN = { top: 24, right: 14, bottom: 26 };
const MIN_HIT_WIDTH = 36;

/**
 * Courbe SVG (docs/ecrans/club-tableau-de-bord-bureau.md §6). Échelle ronde,
 * trous pour les valeurs absentes, un seul point toléré, valeur finale
 * écrite, série 2 distinguée par le tracé (tirets) ET la forme du marqueur.
 */
export function LineChart({
  labels,
  series,
  yMin,
  yMax,
  unit,
  reference,
  formatValue,
  onSelect,
  title,
  summary,
  height = 160,
  ...common
}: LineChartProps) {
  const [setElement, width] = useElementWidth<HTMLDivElement>();
  const used = series.slice(0, 2);
  const count = labels.length;
  const fmt = (value: number) => withUnit(formatValue ? formatValue(value) : formatNumber(value), unit);

  const present = used.flatMap((s) => s.values.slice(0, count).filter(isNumber));
  const isEmpty = count === 0 || present.length === 0;

  const legend: ChartLegendItem[] = used.map((s, index) => ({
    label: s.name,
    seriesIndex: index,
    kind: "line",
  }));
  const referenceText = reference ? `${reference.label} ${fmt(reference.value)}` : null;

  const lastOf = (s: LineChartSeries): { index: number; value: number } | null => {
    for (let i = Math.min(count, s.values.length) - 1; i >= 0; i -= 1) {
      const value = s.values[i];
      if (isNumber(value)) return { index: i, value };
    }
    return null;
  };

  const autoSummary =
    summary ??
    `${title}. ${count} point${count > 1 ? "s" : ""}. ` +
      used
        .map((s) => {
          const last = lastOf(s);
          return last ? `${s.name} : dernière valeur ${fmt(last.value)} (${labels[last.index] ?? ""}).` : `${s.name} : aucune valeur.`;
        })
        .join(" ") +
      (reference ? ` ${reference.label} : ${fmt(reference.value)}.` : "");

  const table = {
    caption: title,
    columns: ["Période", ...used.map((s) => s.name)],
    rows: labels.map((label, index) => [
      label,
      ...used.map((s) => {
        const value = s.values[index];
        return isNumber(value) ? fmt(value) : null;
      }),
    ]),
  };

  let svg = null;
  if (!isEmpty) {
    const candidates = [...present, ...(reference ? [reference.value] : [])];
    const dataMin = Math.min(...candidates);
    const dataMax = Math.max(...candidates);
    const scale = niceScale(yMin ?? Math.min(0, dataMin), yMax ?? dataMax, 4);
    const domainMin = yMin ?? scale.min;
    const domainMax = yMax ?? scale.max;
    const span = domainMax - domainMin || 1;

    const tickLabels = scale.ticks.map(formatAxisNumber);
    const left = Math.max(30, Math.max(...tickLabels.map((t) => approxTextWidth(t))) + 10);
    // Cible tactile : en mode interactif, chaque colonne fait au moins 36 px
    // (la courbe défile alors dans son cadre au lieu de se comprimer).
    const minWidth = onSelect ? left + MARGIN.right + count * MIN_HIT_WIDTH : 0;
    const svgWidth = Math.max(width, minWidth);
    const plotW = svgWidth - left - MARGIN.right;
    const plotH = height - MARGIN.top - MARGIN.bottom;
    const band = plotW / count;
    const x = (i: number) => left + band * (i + 0.5);
    const y = (v: number) => MARGIN.top + plotH * (1 - (clamp(v, domainMin, domainMax) - domainMin) / span);

    const longest = Math.max(...labels.map((l) => approxTextWidth(l)));
    const shown = visibleLabelIndexes(count, band, longest);

    const ariaProps = onSelect
      ? ({ role: "group", "aria-label": autoSummary } as const)
      : ({ role: "img", "aria-label": autoSummary } as const);

    svg = (
      <ScrollFrame contentWidth={svgWidth} frameWidth={width} label={title}>
        <svg width={svgWidth} height={height} viewBox={`0 0 ${svgWidth} ${height}`} className="block max-w-none" {...ariaProps}>
          {scale.ticks.map((tick, i) => {
            if (tick < domainMin || tick > domainMax) return null;
            return (
              <g key={tick}>
                <line x1={left} x2={svgWidth - MARGIN.right} y1={y(tick)} y2={y(tick)} stroke="var(--color-border)" strokeWidth={1} />
                <text x={left - 6} y={y(tick) + 4} textAnchor="end" fontSize={12} fill="var(--color-text-muted)">
                  {tickLabels[i]}
                </text>
              </g>
            );
          })}

          {reference ? (
            <g>
              <line
                x1={left}
                x2={svgWidth - MARGIN.right}
                y1={y(reference.value)}
                y2={y(reference.value)}
                stroke="var(--color-text-muted)"
                strokeWidth={1.5}
                strokeDasharray="1 4"
                strokeLinecap="round"
              />
            </g>
          ) : null}

          {used.map((s, seriesIndex) => {
            const style = seriesStyle(seriesIndex);
            const segments: Array<Array<[number, number]>> = [];
            let current: Array<[number, number]> = [];
            for (let i = 0; i < count; i += 1) {
              const value = s.values[i];
              if (isNumber(value)) {
                current.push([x(i), y(value)]);
              } else if (current.length > 0) {
                segments.push(current);
                current = [];
              }
            }
            if (current.length > 0) segments.push(current);
            return (
              <g key={s.name + seriesIndex}>
                {segments
                  .filter((seg) => seg.length > 1)
                  .map((seg, segIndex) => (
                    <path
                      key={segIndex}
                      d={seg.map(([px, py], i) => `${i === 0 ? "M" : "L"}${px} ${py}`).join(" ")}
                      fill="none"
                      stroke={style.color}
                      strokeWidth={2.5}
                      strokeDasharray={style.dash}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                    />
                  ))}
                {s.values.slice(0, count).map((value, i) =>
                  isNumber(value) ? (
                    seriesIndex === 0 ? (
                      <circle key={i} data-point="" cx={x(i)} cy={y(value)} r={4} fill={style.color} stroke="var(--color-surface)" strokeWidth={1.5} />
                    ) : (
                      <rect key={i} data-point="" x={x(i) - 4} y={y(value) - 4} width={8} height={8} fill={style.color} stroke="var(--color-surface)" strokeWidth={1.5} />
                    )
                  ) : null,
                )}
                {(() => {
                  const last = lastOf(s);
                  if (!last) return null;
                  const px = x(last.index);
                  const anchor = px > svgWidth - MARGIN.right - 24 ? "end" : px < left + 24 ? "start" : "middle";
                  const py = seriesIndex === 0 ? y(last.value) - 9 : y(last.value) + 18;
                  return (
                    <text x={px} y={py} textAnchor={anchor} fontSize={12} fontWeight={600} fill="var(--color-text)">
                      {fmt(last.value)}
                    </text>
                  );
                })()}
              </g>
            );
          })}

          {labels.map((label, i) =>
            shown.has(i) ? (
              <text key={i} x={x(i)} y={height - 8} textAnchor="middle" fontSize={12} fill="var(--color-text-muted)">
                {label}
              </text>
            ) : null,
          )}

          {onSelect
            ? labels.map((label, i) => {
                const values = used
                  .map((s) => {
                    const value = s.values[i];
                    return `${used.length > 1 ? `${s.name} ` : ""}${isNumber(value) ? fmt(value) : "aucune valeur"}`;
                  })
                  .join(", ");
                return (
                  <ChartHit
                    key={i}
                    x={left + band * i}
                    y={MARGIN.top - 8}
                    width={band}
                    height={plotH + 16}
                    label={`${label} : ${values}`}
                    onSelect={() => onSelect(i)}
                  >
                    <g />
                  </ChartHit>
                );
              })
            : null}
        </svg>
      </ScrollFrame>
    );
  }

  return (
    <ChartFigure
      {...common}
      title={title}
      summary={autoSummary}
      height={height}
      isEmpty={isEmpty}
      legend={used.length > 1 ? legend : undefined}
      referenceText={isEmpty ? undefined : (referenceText ?? undefined)}
      table={table}
    >
      <div ref={setElement} className="w-full">
        {svg}
      </div>
    </ChartFigure>
  );
}
