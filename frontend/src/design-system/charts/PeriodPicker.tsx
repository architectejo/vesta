import { IconButton } from "../components/IconButton";
import { SegmentedControl } from "../components/SegmentedControl";
import { IconChevronLeft, IconChevronRight } from "../icons";

export interface PeriodSeason {
  id: string;
  /** Libellé fourni par l'API (ex. « 2026-2027 », saison des paramètres du club). */
  label: string;
}

export type PeriodValue =
  | { mode: "month"; /** « AAAA-MM » */ month: string }
  | { mode: "season"; seasonId: string };

export interface PeriodPickerProps {
  value: PeriodValue;
  onChange: (value: PeriodValue) => void;
  /** Saisons de la plus récente à la plus ancienne. Vide : seul « Mois » est proposé. */
  seasons?: PeriodSeason[];
  /** Plus ancien mois sélectionnable (« AAAA-MM »), ex. mois de création du club. */
  minMonth?: string;
  /** Dernier mois sélectionnable (« AAAA-MM »). Par défaut : le mois en cours. */
  maxMonth?: string;
  /** Date de référence (tests). */
  now?: Date;
  className?: string;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function currentMonth(now: Date = new Date()): string {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}`;
}

/** Ajoute `delta` mois à un mois « AAAA-MM ». */
export function shiftMonth(month: string, delta: number): string {
  const [yearText, monthText] = month.split("-");
  const total = Number(yearText) * 12 + (Number(monthText) - 1) + delta;
  return `${Math.floor(total / 12)}-${pad((total % 12) + 1)}`;
}

/** « 2026-11 » -> « novembre 2026 ». */
export function formatMonthLabel(month: string): string {
  const [yearText, monthText] = month.split("-");
  const date = new Date(Date.UTC(Number(yearText), Number(monthText) - 1, 1));
  return date.toLocaleDateString("fr-FR", { month: "long", year: "numeric", timeZone: "UTC" });
}

/**
 * Filtre de période : « Mois » / « Saison » + flèches de 40 px. Les bornes
 * (`minMonth`, `maxMonth`) et la liste des saisons viennent de l'appelant
 * (donnees de l'API) : aucune règle de calendrier n'est décidée ici.
 */
export function PeriodPicker({
  value,
  onChange,
  seasons = [],
  minMonth,
  maxMonth,
  now,
  className = "",
}: PeriodPickerProps) {
  const upperMonth = maxMonth ?? currentMonth(now);
  const options: Array<{ value: "month" | "season"; label: string }> = [{ value: "month", label: "Mois" }];
  if (seasons.length > 0) options.push({ value: "season", label: "Saison" });

  const changeMode = (mode: "month" | "season") => {
    if (mode === value.mode) return;
    if (mode === "month") {
      onChange({ mode: "month", month: upperMonth });
    } else if (seasons[0]) {
      onChange({ mode: "season", seasonId: seasons[0].id });
    }
  };

  let label: string;
  let canGoOlder: boolean;
  let canGoNewer: boolean;
  let goOlder: () => void;
  let goNewer: () => void;
  let olderLabel: string;
  let newerLabel: string;

  if (value.mode === "month") {
    const month = value.month;
    label = formatMonthLabel(month);
    canGoOlder = !minMonth || month > minMonth;
    canGoNewer = month < upperMonth;
    goOlder = () => onChange({ mode: "month", month: shiftMonth(month, -1) });
    goNewer = () => onChange({ mode: "month", month: shiftMonth(month, 1) });
    olderLabel = "Mois précédent";
    newerLabel = "Mois suivant";
  } else {
    const seasonId = value.seasonId;
    const index = seasons.findIndex((s) => s.id === seasonId);
    label = `Saison ${seasons[index]?.label ?? ""}`.trim();
    canGoOlder = index >= 0 && index < seasons.length - 1;
    canGoNewer = index > 0;
    goOlder = () => {
      const next = seasons[index + 1];
      if (next) onChange({ mode: "season", seasonId: next.id });
    };
    goNewer = () => {
      const next = seasons[index - 1];
      if (next) onChange({ mode: "season", seasonId: next.id });
    };
    olderLabel = "Saison précédente";
    newerLabel = "Saison suivante";
  }

  return (
    <div className={["flex flex-wrap items-center gap-x-3 gap-y-1", className].join(" ")}>
      <div className="w-40">
        <SegmentedControl
          label="Type de période"
          hideLabel
          value={value.mode}
          onChange={changeMode}
          options={options}
        />
      </div>
      <div className="flex items-center">
        <IconButton
          aria-label={olderLabel}
          disabled={!canGoOlder}
          onClick={goOlder}
          icon={<IconChevronLeft aria-hidden="true" className="h-5 w-5" />}
        />
        <span
          aria-live="polite"
          className="min-w-[8.5rem] px-1 text-center text-sm font-semibold text-text"
        >
          {label}
        </span>
        <IconButton
          aria-label={newerLabel}
          disabled={!canGoNewer}
          onClick={goNewer}
          icon={<IconChevronRight aria-hidden="true" className="h-5 w-5" />}
        />
      </div>
    </div>
  );
}
