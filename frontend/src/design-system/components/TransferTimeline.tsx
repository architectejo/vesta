/**
 * `TransferTimeline` (fiche `docs/ecrans/mercato.md` §4.3) : liste verticale
 * d'étapes d'un transfert. Simple composant d'affichage — l'état de chaque
 * étape (faite / en cours / bloquée / à venir) et son explication viennent
 * toujours de l'API, jamais évalués ici (10.2 n° 30, §5).
 */
export type TransferTimelineStepState = "done" | "current" | "blocked" | "upcoming";

export interface TransferTimelineStep {
  key: string;
  label: string;
  state: TransferTimelineStepState;
  /** Date affichée après le libellé (ex. « Acceptée le 12/03/2026 »). */
  date?: string;
  /** Ligne d'explication de l'étape en cours ou bloquée (§4.3, 10.2 n° 31). */
  detail?: string;
}

export interface TransferTimelineProps {
  steps: TransferTimelineStep[];
}

const DOT_CLASS: Record<TransferTimelineStepState, string> = {
  done: "bg-status-success-dot",
  current: "bg-status-warning-dot",
  blocked: "bg-status-danger-dot",
  upcoming: "border border-border-strong bg-surface",
};

function LockIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-3 w-3 text-status-danger-fg" fill="currentColor">
      <path d="M12 2a4 4 0 0 0-4 4v3H7a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2h-1V6a4 4 0 0 0-4-4Zm0 2a2 2 0 0 1 2 2v3h-4V6a2 2 0 0 1 2-2Z" />
    </svg>
  );
}

/** Chronologie d'un transfert (§4.3, §4.4). Jamais la couleur seule : le
 * libellé et la date accompagnent toujours la pastille (10.2 n° 31). */
export function TransferTimeline({ steps }: TransferTimelineProps) {
  return (
    <ol className="space-y-3">
      {steps.map((step) => (
        <li key={step.key} className="flex gap-3">
          <span className="flex flex-col items-center pt-0.5">
            <span
              aria-hidden="true"
              className={["flex h-3 w-3 shrink-0 items-center justify-center rounded-full", DOT_CLASS[step.state]].join(" ")}
            >
              {step.state === "blocked" ? <LockIcon /> : null}
            </span>
          </span>
          <div className="min-w-0 flex-1 pb-1">
            <p
              className={[
                "text-sm",
                step.state === "blocked" ? "font-medium text-status-danger-fg" : "text-text",
              ].join(" ")}
            >
              {step.label}
              {step.date ? <span className="text-text-muted"> · {step.date}</span> : null}
            </p>
            {step.detail ? (
              <p
                className={[
                  "text-xs",
                  step.state === "blocked" ? "text-status-danger-fg" : "text-text-muted",
                ].join(" ")}
              >
                {step.detail}
              </p>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
