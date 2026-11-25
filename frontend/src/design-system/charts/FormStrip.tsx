import { EmptyState } from "../components/EmptyState";
import { Loader } from "../components/Loader";
import type { ChartState } from "./ChartParts";

export type MatchOutcome = "win" | "draw" | "loss";

export interface FormStripResult {
  outcome: MatchOutcome;
  opponent?: string;
  /** Score tel qu'écrit (ex. « 3-1 »). */
  score?: string;
  /** Date lisible (ex. « 8 nov. »), complète le libellé accessible. */
  date?: string;
}

export interface FormStripProps {
  title?: string;
  /** Résultats déjà ordonnés par l'appelant (les 5 premiers sont affichés). */
  results: FormStripResult[];
  state?: ChartState;
  emptyMessage?: string;
  errorMessage?: string;
  onRetry?: () => void;
  onSelect?: (index: number, result: FormStripResult) => void;
  className?: string;
}

const MAX_RESULTS = 5;

const LETTER: Record<MatchOutcome, string> = { win: "V", draw: "N", loss: "D" };
const WORD: Record<MatchOutcome, string> = { win: "Victoire", draw: "Match nul", loss: "Défaite" };
const TONE: Record<MatchOutcome, string> = {
  win: "border-status-success-dot bg-status-success-bg text-status-success-fg",
  draw: "border-status-neutral-dot bg-status-neutral-bg text-status-neutral-fg",
  loss: "border-status-danger-dot bg-status-danger-bg text-status-danger-fg",
};

function describe(result: FormStripResult): string {
  const versus = result.opponent ? ` contre ${result.opponent}` : "";
  const score = result.score ? `, ${result.score}` : "";
  const date = result.date ? `, ${result.date}` : "";
  return `${WORD[result.outcome]}${versus}${score}${date}`;
}

/**
 * Bande de forme : pastilles « V », « N », « D » (la lettre est écrite, la
 * couleur ne porte jamais seule l'information).
 */
export function FormStrip({
  title = "Forme récente",
  results,
  state = "ready",
  emptyMessage,
  errorMessage,
  onRetry,
  onSelect,
  className = "",
}: FormStripProps) {
  const shown = results.slice(0, MAX_RESULTS);
  const summary = `${title} : ${shown.map(describe).join(" ; ")}.`;

  let body;
  if (state === "loading") {
    body = <Loader loading variant="list" listSkeleton="row" count={1} onRetry={onRetry} />;
  } else if (state === "error") {
    body = (
      <EmptyState
        variant="error"
        message={errorMessage ?? "Impossible de charger les résultats."}
        actionLabel="Réessayer"
        onAction={onRetry}
      />
    );
  } else if (shown.length === 0) {
    body = <EmptyState message={emptyMessage ?? "Aucun match joué sur la période."} />;
  } else {
    body = (
      <ol className="vesta-chart-enter m-0 flex list-none flex-wrap gap-2 p-0">
        {shown.map((result, index) => {
          const classes = [
            "inline-flex h-9 w-9 items-center justify-center rounded-full border-2 text-sm font-semibold",
            TONE[result.outcome],
          ].join(" ");
          return (
            <li key={index}>
              {onSelect ? (
                <button
                  type="button"
                  aria-label={describe(result)}
                  onClick={() => onSelect(index, result)}
                  className={[
                    classes,
                    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
                  ].join(" ")}
                >
                  {LETTER[result.outcome]}
                </button>
              ) : (
                <span role="img" aria-label={describe(result)} className={classes}>
                  {LETTER[result.outcome]}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    );
  }

  return (
    <figure aria-label={title} className={["m-0 w-full", className].join(" ")}>
      {body}
      <figcaption className="sr-only">{summary}</figcaption>
    </figure>
  );
}
