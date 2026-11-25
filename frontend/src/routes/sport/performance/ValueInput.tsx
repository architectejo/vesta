import { useId } from "react";
import type { PerformanceTest } from "../../../api/performance";
import { Checkbox, TextField } from "../../../design-system";
import type { ItemFields } from "./measureTypes";
import { fromHundredths, parseCount, parseDecimalString, parseTimeToMs, toHundredths } from "./performanceFormat";

/** Saisie d'un joueur, avant lecture (texte brut des champs). */
export interface ValueDraft {
  text: string;
  /** Aides « tours × longueur du tour + mètres en plus » (distance en temps donné). */
  laps: string;
  extra: string;
  dnf: boolean;
}

export const emptyDraft = (): ValueDraft => ({ text: "", laps: "", extra: "", dnf: false });

export type ReadValue =
  | { state: "empty" }
  | { state: "error"; message: string }
  | { state: "ok"; fields: ItemFields };

const ERRORS = {
  time: "Saisissez un temps supérieur à 0.",
  distance: "La distance doit être comprise entre 0 et 10 000 m.",
  count: "Saisissez le nombre réussi.",
  value: "Saisissez une valeur positive.",
  lap: "Saisissez des tours et des mètres valides.",
};

/** Distance en mètres (chaîne décimale) déduite des tours, sans flottant. */
function distanceFromLaps(draft: ValueDraft, lapLength: string): string | null {
  const length = parseDecimalString(lapLength);
  const laps = parseCount(draft.laps);
  const extra = draft.extra.trim() === "" ? "0" : parseDecimalString(draft.extra);
  if (length === null || laps === null || extra === null) return null;
  return fromHundredths(laps * toHundredths(length) + toHundredths(extra));
}

/** Lit la saisie selon le type du test. Les bornes (min, max) restent jugées par l'API. */
export function readDraft(test: PerformanceTest, draft: ValueDraft, lapLength = ""): ReadValue {
  if (draft.dnf) return { state: "ok", fields: { outcome: "dnf" } };
  const text = draft.text.trim();
  if (test.kind === "distance_in_time" && draft.laps.trim() !== "") {
    const distance = distanceFromLaps(draft, lapLength);
    return distance === null ? { state: "error", message: ERRORS.lap } : { state: "ok", fields: { distance_m: distance } };
  }
  if (text === "") return { state: "empty" };
  if (test.kind === "timed_distance") {
    const ms = parseTimeToMs(text);
    return ms === null ? { state: "error", message: ERRORS.time } : { state: "ok", fields: { time_ms: ms } };
  }
  if (test.kind === "distance_in_time") {
    const distance = parseDecimalString(text);
    return distance === null ? { state: "error", message: ERRORS.distance } : { state: "ok", fields: { distance_m: distance } };
  }
  if (test.kind === "repetitions") {
    const count = parseCount(text);
    return count === null ? { state: "error", message: ERRORS.count } : { state: "ok", fields: { count } };
  }
  const value = parseDecimalString(text, 4);
  return value === null ? { state: "error", message: ERRORS.value } : { state: "ok", fields: { value } };
}

/** Millisecondes -> « 4,52 » (champ de correction). */
export function msToText(ms: number): string {
  const whole = Math.floor(ms / 1000);
  const frac = String(ms % 1000)
    .padStart(3, "0")
    .replace(/0+$/, "");
  return frac ? `${whole},${frac}` : String(whole);
}

export function draftFromValue(
  test: PerformanceTest,
  value: { outcome: string; time_ms: number | null; distance_m: string | null; count: number | null; value: string | null },
): ValueDraft {
  const draft = emptyDraft();
  if (value.outcome === "dnf") return { ...draft, dnf: true };
  if (test.kind === "timed_distance" && value.time_ms !== null) draft.text = msToText(value.time_ms);
  else if (test.kind === "distance_in_time" && value.distance_m !== null) {
    draft.text = value.distance_m.includes(".") ? value.distance_m.replace(/0+$/, "").replace(/\.$/, "").replace(".", ",") : value.distance_m;
  } else if (test.kind === "repetitions" && value.count !== null) draft.text = String(value.count);
  else if (value.value !== null) draft.text = value.value.replace(".", ",");
  return draft;
}

export interface ValueInputProps {
  test: PerformanceTest;
  name: string;
  draft: ValueDraft;
  onChange: (draft: ValueDraft) => void;
  error?: string;
  /** Longueur du tour saisie une fois pour tous (distance en temps donné). */
  lapLength?: string;
  allowDnf?: boolean;
  disabled?: boolean;
}

/** Champ de saisie d'une valeur : temps, distance, compteur ou valeur libre. */
export function ValueInput({ test, name, draft, onChange, error, lapLength = "", allowDnf = true, disabled }: ValueInputProps) {
  const id = useId();
  const locked = disabled || draft.dnf;
  const set = (patch: Partial<ValueDraft>) => onChange({ ...draft, ...patch });

  let field;
  if (test.kind === "repetitions") {
    const current = parseCount(draft.text);
    const step = (delta: number) => {
      if (current === null && delta < 0) return;
      set({ text: String(Math.max(0, (current ?? 0) + delta)) });
    };
    field = (
      <div>
        <label htmlFor={id} className="mb-1 block text-sm font-medium text-text">
          Nombre réussi{test.attempts ? ` (sur ${test.attempts})` : ""}
        </label>
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-label={`Retirer une répétition pour ${name}`}
            disabled={locked}
            onClick={() => step(-1)}
            className="h-10 w-10 shrink-0 rounded-md border border-border-strong text-lg text-text disabled:opacity-60"
          >
            −
          </button>
          <input
            id={id}
            inputMode="numeric"
            value={draft.text}
            disabled={locked}
            onChange={(event) => set({ text: event.target.value })}
            className="h-10 w-20 rounded-md border border-border-strong bg-surface px-2 text-center text-base tabular-nums text-text"
          />
          <button
            type="button"
            aria-label={`Ajouter une répétition pour ${name}`}
            disabled={locked}
            onClick={() => step(1)}
            className="h-10 w-10 shrink-0 rounded-md border border-border-strong text-lg text-text disabled:opacity-60"
          >
            +
          </button>
        </div>
      </div>
    );
  } else {
    const label =
      test.kind === "timed_distance" ? "Temps (s)" : test.kind === "distance_in_time" ? "Distance (m)" : "Valeur";
    const hasLaps = test.kind === "distance_in_time" && draft.laps.trim() !== "";
    field = (
      <div className="space-y-2">
        <TextField
          label={label}
          value={draft.text}
          onChange={(text) => set({ text })}
          inputMode="decimal"
          disabled={locked || hasLaps}
          help={test.kind === "timed_distance" ? "Ex. 4,52 ou 1:05,30" : undefined}
          rightSlot={
            test.kind === "free" && test.unit_label ? <span className="text-xs text-text-muted">{test.unit_label}</span> : undefined
          }
        />
        {test.kind === "distance_in_time" ? (
          <div className="grid grid-cols-2 gap-2">
            <TextField label="Tours" value={draft.laps} onChange={(laps) => set({ laps })} inputMode="numeric" optional disabled={locked} />
            <TextField
              label="Mètres en plus"
              value={draft.extra}
              onChange={(extra) => set({ extra })}
              inputMode="decimal"
              optional
              disabled={locked}
            />
            {hasLaps && lapLength.trim() === "" ? (
              <p className="col-span-2 text-xs text-text-muted">Saisissez la longueur du tour ci-dessus.</p>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {field}
      {allowDnf ? (
        <Checkbox checked={draft.dnf} onChange={(dnf) => set({ dnf })} label={`Abandon de ${name}`} disabled={disabled} />
      ) : null}
      {error ? (
        <p role="alert" className="text-xs text-status-danger-fg">
          {error}
        </p>
      ) : null}
    </div>
  );
}
