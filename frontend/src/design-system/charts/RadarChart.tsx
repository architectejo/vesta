import { approxTextWidth, clamp, formatNumber, isNumber, seriesStyle, withUnit } from "./chartUtils";
import {
  ChartFigure,
  ChartHit,
  type ChartCommonProps,
  type ChartLegendItem,
} from "./ChartParts";
import { useElementWidth } from "./useElementWidth";

export interface RadarAxis {
  label: string;
  /** Valeur maximale de l'axe ; défaut : `maxValue`. */
  max?: number;
}

export interface RadarSeries {
  name: string;
  /** Une valeur par axe ; `null` = non évalué (compté 0 sur le tracé). */
  values: Array<number | null>;
}

export interface RadarChartProps extends ChartCommonProps {
  /** 3 à 8 axes (au-delà de 8, les suivants sont ignorés). */
  axes: RadarAxis[];
  /** 1 à 4 séries ; tracés plein, tirets, pointillés, tirets-points. */
  series: RadarSeries[];
  /** Maximum par défaut des axes (ex. 100, 10). */
  maxValue?: number;
  unit?: string;
  /** Toucher / Entrée / Espace sur le libellé d'un axe. */
  onSelect?: (axisIndex: number) => void;
}

const MIN_AXES = 3;
const MAX_AXES = 8;
const MAX_SERIES = 4;
const RINGS = [0.25, 0.5, 0.75, 1];
const LINE_HEIGHT = 14;

function splitLabel(label: string): string[] {
  const words = label.split(" ");
  if (words.length < 2) return [label];
  const middle = Math.ceil(words.length / 2);
  return [words.slice(0, middle).join(" "), words.slice(middle).join(" ")];
}

/**
 * Radar SVG (3 à 8 axes, 1 à 4 séries). Un polygone par série, tracé
 * différent (plein, tirets, pointillés, tirets-points), légende textuelle,
 * valeurs écrites quand il n'y a qu'une série, libellés d'axe complets.
 */
export function RadarChart({
  axes,
  series,
  maxValue = 100,
  unit,
  onSelect,
  title,
  summary,
  height = 240,
  ...common
}: RadarChartProps) {
  const [setElement, width] = useElementWidth<HTMLDivElement>();
  const usedAxes = axes.slice(0, MAX_AXES);
  const used = series.slice(0, MAX_SERIES);
  const count = usedAxes.length;
  const notEnough = count < MIN_AXES;
  const hasData = used.some((s) => s.values.slice(0, count).some(isNumber));
  const isEmpty = notEnough || used.length === 0 || !hasData;
  const fmt = (value: number) => withUnit(formatNumber(value), unit);

  const legend: ChartLegendItem[] = used.map((s, index) => ({ label: s.name, seriesIndex: index, kind: "line" }));
  const valueAt = (s: number, a: number): number => {
    const value = used[s]?.values[a];
    return isNumber(value) ? value : 0;
  };
  const describeSeries = (s: number): string =>
    usedAxes
      .map((axis, a) => {
        const value = used[s]?.values[a];
        return `${axis.label} ${isNumber(value) ? fmt(value) : "non évalué"}`;
      })
      .join(", ");

  const autoSummary =
    summary ?? `${title}. ${used.map((s, i) => `${s.name} : ${describeSeries(i)}.`).join(" ")}`;

  const table = {
    caption: title,
    columns: ["Critère", ...used.map((s) => s.name)],
    rows: usedAxes.map((axis, a) => [
      axis.label,
      ...used.map((s) => {
        const value = s.values[a];
        return isNumber(value) ? fmt(value) : null;
      }),
    ]),
  };

  let svg = null;
  if (!isEmpty) {
    const lines = usedAxes.map((axis) => splitLabel(axis.label));
    const longest = Math.max(...lines.flat().map((l) => approxTextWidth(l)));
    const padX = clamp(longest + 8, 40, width * 0.34);
    const padY = 14 + LINE_HEIGHT * 2;
    const radius = Math.max(40, Math.min((width - 2 * padX) / 2, (height - 2 * padY) / 2));
    const cx = width / 2;
    const cy = height / 2;
    const angle = (a: number) => -Math.PI / 2 + (2 * Math.PI * a) / count;
    const point = (a: number, ratio: number): [number, number] => [
      cx + radius * ratio * Math.cos(angle(a)),
      cy + radius * ratio * Math.sin(angle(a)),
    ];
    const ratioOf = (s: number, a: number) => {
      const max = usedAxes[a]?.max ?? maxValue;
      return clamp(valueAt(s, a) / (max || 1), 0, 1);
    };
    const ariaProps = onSelect
      ? ({ role: "group", "aria-label": autoSummary } as const)
      : ({ role: "img", "aria-label": autoSummary } as const);

    svg = (
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="block max-w-full" {...ariaProps}>
        {RINGS.map((ring) => (
          <polygon
            key={ring}
            points={usedAxes.map((_a, a) => point(a, ring).join(",")).join(" ")}
            fill="none"
            stroke="var(--color-border)"
            strokeWidth={1}
          />
        ))}
        {usedAxes.map((_axis, a) => {
          const [x, y] = point(a, 1);
          return <line key={a} x1={cx} y1={cy} x2={x} y2={y} stroke="var(--color-border)" strokeWidth={1} />;
        })}

        {used.map((s, si) => {
          const style = seriesStyle(si);
          const pts = usedAxes.map((_axis, a) => point(a, ratioOf(si, a)));
          return (
            <g key={s.name + si}>
              <polygon
                data-series=""
                points={pts.map((p) => p.join(",")).join(" ")}
                fill={style.color}
                fillOpacity={0.12}
                stroke={style.color}
                strokeWidth={2.5}
                strokeDasharray={style.dash}
                strokeLinejoin="round"
              />
              {pts.map(([x, y], a) =>
                si % 2 === 0 ? (
                  <circle key={a} cx={x} cy={y} r={3.5} fill={style.color} stroke="var(--color-surface)" strokeWidth={1} />
                ) : (
                  <rect key={a} x={x - 3.5} y={y - 3.5} width={7} height={7} fill={style.color} stroke="var(--color-surface)" strokeWidth={1} />
                ),
              )}
            </g>
          );
        })}

        {used.length === 1
          ? usedAxes.map((_axis, a) => {
              const value = used[0]?.values[a];
              if (!isNumber(value)) return null;
              const [x, y] = point(a, ratioOf(0, a));
              const dx = Math.cos(angle(a));
              const dy = Math.sin(angle(a));
              return (
                <text
                  key={a}
                  x={x - dx * 10}
                  y={y - dy * 10 + 4}
                  textAnchor="middle"
                  fontSize={12}
                  fontWeight={600}
                  fill="var(--color-text)"
                  stroke="var(--color-surface)"
                  strokeWidth={3}
                  paintOrder="stroke"
                >
                  {formatNumber(value)}
                </text>
              );
            })
          : null}

        {usedAxes.map((axis, a) => {
          const dx = Math.cos(angle(a));
          const dy = Math.sin(angle(a));
          const [x, y] = point(a, 1);
          const lx = x + dx * 10;
          const anchor = dx > 0.3 ? "start" : dx < -0.3 ? "end" : "middle";
          const rows = lines[a] ?? [axis.label];
          const blockH = rows.length * LINE_HEIGHT;
          const top = dy > 0.3 ? y + dy * 10 : dy < -0.3 ? y + dy * 10 - blockH : y - blockH / 2;
          const textW = Math.max(...rows.map((r) => approxTextWidth(r)));
          const hitW = Math.max(44, textW + 8);
          const hitH = Math.max(36, blockH + 8);
          const hitX = anchor === "start" ? lx - 4 : anchor === "end" ? lx - hitW + 4 : lx - hitW / 2;
          return (
            <ChartHit
              key={a}
              x={hitX}
              y={top + blockH / 2 - hitH / 2}
              width={hitW}
              height={hitH}
              label={`${axis.label}${used.length === 1 && isNumber(used[0]?.values[a]) ? ` : ${fmt(valueAt(0, a))}` : ""}`}
              onSelect={onSelect ? () => onSelect(a) : undefined}
            >
              {rows.map((row, ri) => (
                <text
                  key={ri}
                  x={lx}
                  y={top + LINE_HEIGHT * (ri + 1) - 3}
                  textAnchor={anchor}
                  fontSize={12}
                  fill="var(--color-text-muted)"
                >
                  {row}
                </text>
              ))}
            </ChartHit>
          );
        })}
      </svg>
    );
  }

  return (
    <ChartFigure
      {...common}
      title={title}
      summary={autoSummary}
      height={height}
      isEmpty={isEmpty}
      emptyMessage={
        notEnough && common.emptyMessage === undefined
          ? "Il faut au moins trois critères pour tracer un radar."
          : common.emptyMessage
      }
      legend={legend}
      table={table}
    >
      <div ref={setElement} className="w-full">
        {svg}
      </div>
    </ChartFigure>
  );
}
