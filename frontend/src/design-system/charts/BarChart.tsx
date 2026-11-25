import {
  approxTextWidth,
  formatAxisNumber,
  formatNumber,
  isNumber,
  niceScale,
  withUnit,
} from "./chartUtils";
import {
  ChartFigure,
  ChartHit,
  PatternDefs,
  ScrollFrame,
  SeriesRect,
  usePatternId,
  type ChartCommonProps,
  type ChartLegendItem,
} from "./ChartParts";
import { useElementWidth } from "./useElementWidth";

export interface BarChartSeries {
  name: string;
  /** Une valeur par catégorie ; `null` = pas de donnée (aucune barre). */
  values: Array<number | null>;
}

export interface BarChartProps extends ChartCommonProps {
  categories: string[];
  /** 1 à 4 séries. Plusieurs séries : groupées, ou empilées avec `stacked`. */
  series: BarChartSeries[];
  orientation?: "vertical" | "horizontal";
  stacked?: boolean;
  unit?: string;
  /** Ligne de repère (orientation verticale seulement), ex. le montant dû. */
  reference?: { value: number; label: string };
  formatValue?: (value: number) => string;
  /** Toucher / Entrée / Espace sur une catégorie (groupe de barres ou ligne). */
  onSelect?: (categoryIndex: number) => void;
}

const MAX_SERIES = 4;
const MARGIN_TOP = 22;
const MARGIN_RIGHT = 12;
const LINE_HEIGHT = 14;

function splitLabel(label: string): string[] {
  const words = label.split(" ");
  if (words.length < 2) return [label];
  return [words[0] ?? "", words.slice(1).join(" ")];
}

/**
 * Barres SVG, verticales ou horizontales, simples, groupées ou empilées.
 * Les séries se distinguent par la couleur ET le motif (plein, hachures,
 * points, quadrillage) ; légende textuelle sous 2 séries ou plus. Les
 * étiquettes ne sont jamais tronquées ni pivotées : la largeur de colonne
 * s'adapte et le graphique défile dans son cadre au-delà du cadre.
 */
export function BarChart({
  categories,
  series,
  orientation = "vertical",
  stacked = false,
  unit,
  reference,
  formatValue,
  onSelect,
  title,
  summary,
  height = 160,
  ...common
}: BarChartProps) {
  const [setElement, width] = useElementWidth<HTMLDivElement>();
  const patternId = usePatternId();
  const used = series.slice(0, MAX_SERIES);
  const count = categories.length;
  const multi = used.length > 1;
  const fmt = (value: number) => withUnit(formatValue ? formatValue(value) : formatNumber(value), unit);

  const valueAt = (s: number, c: number): number | null => {
    const value = used[s]?.values[c];
    return isNumber(value) ? value : null;
  };
  const hasData = used.some((s) => s.values.slice(0, count).some(isNumber));
  const isEmpty = count === 0 || !hasData;

  const legend: ChartLegendItem[] = used.map((s, index) => ({ label: s.name, seriesIndex: index, kind: "bar" }));

  const categorySummary = (c: number): string =>
    used
      .map((s, si) => {
        const value = valueAt(si, c);
        return `${multi ? `${s.name} ` : ""}${value === null ? "aucune valeur" : fmt(value)}`;
      })
      .join(", ");

  const totalOf = (c: number): number =>
    used.reduce((sum, _s, si) => sum + Math.max(0, valueAt(si, c) ?? 0), 0);

  const autoSummary =
    summary ??
    `${title}. ${count} catégorie${count > 1 ? "s" : ""}${stacked ? ", barres empilées" : ""}. ` +
      categories
        .map((label, c) => `${label} : ${stacked && multi ? `total ${fmt(totalOf(c))} (${categorySummary(c)})` : categorySummary(c)}.`)
        .join(" ");

  const table = {
    caption: title,
    columns: ["Catégorie", ...used.map((s) => s.name), ...(stacked && multi ? ["Total"] : [])],
    rows: categories.map((label, c) => [
      label,
      ...used.map((_s, si) => {
        const value = valueAt(si, c);
        return value === null ? null : fmt(value);
      }),
      ...(stacked && multi ? [fmt(totalOf(c))] : []),
    ]),
  };

  let svg = null;
  if (!isEmpty) {
    const allValues = used.flatMap((_s, si) =>
      categories.map((_c, c) => valueAt(si, c)).filter(isNumber),
    );
    const dataMax = stacked ? Math.max(...categories.map((_c, c) => totalOf(c))) : Math.max(...allValues);
    const dataMin = stacked ? 0 : Math.min(0, ...allValues);
    const ariaProps = onSelect
      ? ({ role: "group", "aria-label": autoSummary } as const)
      : ({ role: "img", "aria-label": autoSummary } as const);

    if (orientation === "horizontal") {
      const scale = niceScale(0, Math.max(0, dataMax), 4);
      const valueTexts = categories.map((_c, c) => (stacked ? fmt(totalOf(c)) : used.map((_s, si) => valueAt(si, c)).filter(isNumber).map(fmt).join(" ")));
      const grouped = !stacked && multi;
      const barH = grouped ? 18 : 22;
      const rowH = Math.max(44, 20 + (grouped ? used.length * (barH + 2) : barH) + 10);
      const reserve = Math.min(
        width * 0.4,
        Math.max(40, ...(grouped ? used.flatMap((_s, si) => categories.map((_c, c) => approxTextWidth(fmt(valueAt(si, c) ?? 0)))) : valueTexts.map((t) => approxTextWidth(t)))) + 8,
      );
      const plotW = width - 4 - reserve;
      const totalH = rowH * count + 4;
      const sx = (value: number) => (Math.max(0, value) / (scale.max || 1)) * plotW;

      svg = (
        <svg width={width} height={totalH} viewBox={`0 0 ${width} ${totalH}`} className="block max-w-full" {...ariaProps}>
          <PatternDefs id={patternId} />
          <line x1={2} x2={2} y1={0} y2={totalH} stroke="var(--color-border-strong)" strokeWidth={1} />
          {categories.map((label, c) => {
            const top = c * rowH;
            return (
              <ChartHit
                key={c}
                x={0}
                y={top}
                width={width}
                height={rowH}
                label={`${label} : ${stacked && multi ? `total ${fmt(totalOf(c))}` : categorySummary(c)}`}
                onSelect={onSelect ? () => onSelect(c) : undefined}
              >
                <text x={6} y={top + 16} fontSize={12} fontWeight={600} fill="var(--color-text)">
                  {label}
                </text>
                {stacked
                  ? (() => {
                      let offset = 0;
                      return used.map((_s, si) => {
                        const value = Math.max(0, valueAt(si, c) ?? 0);
                        if (value === 0) return null;
                        const w = sx(value);
                        const rect = (
                          <SeriesRect key={si} x={2 + offset} y={top + 22} width={Math.max(1, w)} height={barH} seriesIndex={si} patternId={patternId} />
                        );
                        offset += w;
                        return rect;
                      });
                    })()
                  : used.map((_s, si) => {
                      const value = valueAt(si, c);
                      if (value === null) return null;
                      const y = top + 22 + si * (barH + 2);
                      return (
                        <g key={si}>
                          <SeriesRect x={2} y={y} width={Math.max(1, sx(value))} height={barH} seriesIndex={si} patternId={patternId} />
                          {grouped ? (
                            <text x={4 + sx(value) + 4} y={y + barH - 5} fontSize={12} fontWeight={600} fill="var(--color-text)">
                              {fmt(value)}
                            </text>
                          ) : null}
                        </g>
                      );
                    })}
                {!grouped ? (
                  <text
                    x={2 + sx(stacked ? totalOf(c) : (valueAt(0, c) ?? 0)) + 6}
                    y={top + 22 + barH - 6}
                    fontSize={12}
                    fontWeight={600}
                    fill="var(--color-text)"
                  >
                    {valueTexts[c]}
                  </text>
                ) : null}
              </ChartHit>
            );
          })}
        </svg>
      );
    } else {
      const lo = Math.min(0, dataMin);
      const hi = Math.max(dataMax, reference?.value ?? dataMax);
      const scale = niceScale(lo, hi, 4);
      const tickLabels = scale.ticks.map(formatAxisNumber);
      const left = Math.max(30, Math.max(...tickLabels.map((t) => approxTextWidth(t))) + 10);
      const labelLines = categories.map(splitLabel);
      const widestLine = Math.max(...labelLines.flat().map((l) => approxTextWidth(l)));
      const maxLines = Math.max(...labelLines.map((l) => l.length));
      const bottom = 10 + LINE_HEIGHT * maxLines;
      const valueText = (c: number) =>
        approxTextWidth(stacked ? fmt(totalOf(c)) : "0000");
      const slotMin = Math.max(
        44,
        widestLine + 6,
        stacked || !multi ? 0 : used.length * 36 + 8,
        Math.max(...categories.map((_c, c) => valueText(c))) + 4,
      );
      const svgWidth = Math.max(width, left + MARGIN_RIGHT + count * slotMin);
      const plotW = svgWidth - left - MARGIN_RIGHT;
      const plotH = height - MARGIN_TOP - bottom;
      const band = plotW / count;
      const span = scale.max - scale.min || 1;
      const y = (v: number) => MARGIN_TOP + plotH * (1 - (v - scale.min) / span);
      const zeroY = y(0);

      svg = (
        <ScrollFrame contentWidth={svgWidth} frameWidth={width} label={title}>
          <svg width={svgWidth} height={height} viewBox={`0 0 ${svgWidth} ${height}`} className="block max-w-none" {...ariaProps}>
            <PatternDefs id={patternId} />
            {scale.ticks.map((tick, i) => (
              <g key={tick}>
                <line x1={left} x2={svgWidth - MARGIN_RIGHT} y1={y(tick)} y2={y(tick)} stroke="var(--color-border)" strokeWidth={1} />
                <text x={left - 6} y={y(tick) + 4} textAnchor="end" fontSize={12} fill="var(--color-text-muted)">
                  {tickLabels[i]}
                </text>
              </g>
            ))}
            <line x1={left} x2={svgWidth - MARGIN_RIGHT} y1={zeroY} y2={zeroY} stroke="var(--color-border-strong)" strokeWidth={1} />

            {categories.map((label, c) => {
              const cx = left + band * (c + 0.5);
              const groupW = stacked || !multi ? Math.min(40, band - 12) : Math.min(32 * used.length, band - 8);
              const eachW = stacked || !multi ? groupW : groupW / used.length;
              const startX = cx - groupW / 2;
              let stackTop = zeroY;
              return (
                <ChartHit
                  key={c}
                  x={left + band * c}
                  y={MARGIN_TOP - 10}
                  width={band}
                  height={plotH + 10 + bottom}
                  label={`${label} : ${stacked && multi ? `total ${fmt(totalOf(c))}` : categorySummary(c)}`}
                  onSelect={onSelect ? () => onSelect(c) : undefined}
                >
                  {used.map((_s, si) => {
                    const value = valueAt(si, c);
                    if (value === null) return null;
                    if (stacked) {
                      const positive = Math.max(0, value);
                      if (positive === 0) return null;
                      const h = (positive / span) * plotH;
                      const top = stackTop - h;
                      stackTop = top;
                      const text = fmt(positive);
                      return (
                        <g key={si}>
                          <SeriesRect x={startX} y={top} width={eachW} height={h} seriesIndex={si} patternId={patternId} />
                          {multi && h >= 18 ? (
                            <g>
                              <rect x={cx - approxTextWidth(text) / 2 - 3} y={top + h / 2 - 8} width={approxTextWidth(text) + 6} height={16} rx={3} fill="var(--color-surface)" />
                              <text x={cx} y={top + h / 2 + 4} textAnchor="middle" fontSize={12} fontWeight={600} fill="var(--color-text)">
                                {text}
                              </text>
                            </g>
                          ) : null}
                        </g>
                      );
                    }
                    const barX = startX + si * eachW + (multi ? 1 : 0);
                    const w = multi ? eachW - 2 : eachW;
                    const yv = y(value);
                    const top = Math.min(yv, zeroY);
                    const h = Math.max(Math.abs(zeroY - yv), value === 0 ? 0 : 1);
                    const labelY = value >= 0 ? yv - 5 : yv + 14;
                    return (
                      <g key={si}>
                        <SeriesRect x={barX} y={top} width={w} height={h} seriesIndex={si} patternId={patternId} />
                        <text x={barX + w / 2} y={labelY} textAnchor="middle" fontSize={12} fontWeight={600} fill="var(--color-text)">
                          {fmt(value)}
                        </text>
                      </g>
                    );
                  })}
                  {stacked && totalOf(c) > 0 ? (
                    <text x={cx} y={stackTop - 5} textAnchor="middle" fontSize={12} fontWeight={600} fill="var(--color-text)">
                      {fmt(totalOf(c))}
                    </text>
                  ) : null}
                  {labelLines[c]?.map((line, li) => (
                    <text key={li} x={cx} y={height - bottom + 14 + li * LINE_HEIGHT - 2} textAnchor="middle" fontSize={12} fill="var(--color-text-muted)">
                      {line}
                    </text>
                  ))}
                </ChartHit>
              );
            })}

            {reference ? (
              <g>
                <line
                  x1={left}
                  x2={svgWidth - MARGIN_RIGHT}
                  y1={y(reference.value)}
                  y2={y(reference.value)}
                  stroke="var(--color-text)"
                  strokeWidth={1.5}
                  strokeDasharray="6 3"
                />
                <text x={left + 2} y={y(reference.value) - 4} fontSize={12} fontWeight={600} fill="var(--color-text)">
                  {`${reference.label} ${fmt(reference.value)}`}
                </text>
              </g>
            ) : null}
          </svg>
        </ScrollFrame>
      );
    }
  }

  return (
    <ChartFigure
      {...common}
      title={title}
      summary={autoSummary}
      height={height}
      isEmpty={isEmpty}
      legend={multi ? legend : undefined}
      table={table}
    >
      <div ref={setElement} className="w-full">
        {svg}
      </div>
    </ChartFigure>
  );
}
