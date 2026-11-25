import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../../api/client";
import {
  createPerformanceTest,
  listPerformanceTemplates,
  updatePerformanceTest,
  type PerformanceKind,
  type PerformanceTemplate,
  type PerformanceTest,
  type PerformanceTestInput,
  type PerformanceUnit,
} from "../../../api/performance";
import { Banner, Modal, SegmentedControl, TextArea, TextField, useToast } from "../../../design-system";
import { KIND_OPTIONS, UNIT_OPTIONS, parseCount, parseDecimalString } from "./performanceFormat";

interface FormState {
  name: string;
  kind: PerformanceKind;
  distance: string;
  durationMin: string;
  durationSec: string;
  attempts: string;
  limitMin: string;
  limitSec: string;
  unit: PerformanceUnit;
  decimals: "0" | "1" | "2";
  higher: "high" | "low";
  description: string;
}

const EMPTY: FormState = {
  name: "",
  kind: "timed_distance",
  distance: "",
  durationMin: "",
  durationSec: "",
  attempts: "",
  limitMin: "",
  limitSec: "",
  unit: "points",
  decimals: "0",
  higher: "high",
  description: "",
};

function splitSeconds(total: number | null): { min: string; sec: string } {
  if (total === null) return { min: "", sec: "" };
  return { min: String(Math.floor(total / 60)), sec: String(total % 60) };
}

/** « 30.00 » -> « 30 », « 12.50 » -> « 12,5 » (jamais « 10 » -> « 1 »). */
function trimDecimal(value: string): string {
  const trimmed = value.includes(".") ? value.replace(/0+$/, "").replace(/\.$/, "") : value;
  return trimmed.replace(".", ",");
}

function stateFrom(source: PerformanceTest | PerformanceTemplate): FormState {
  const duration = splitSeconds(source.duration_s);
  const limit = splitSeconds(source.time_limit_s);
  return {
    name: source.name,
    kind: source.kind,
    distance: source.distance_m ? trimDecimal(source.distance_m) : "",
    durationMin: duration.min,
    durationSec: duration.sec,
    attempts: source.attempts === null ? "" : String(source.attempts),
    limitMin: limit.min,
    limitSec: limit.sec,
    unit: (source.unit || "points") as PerformanceUnit,
    decimals: String(Math.min(2, Math.max(0, source.decimals))) as FormState["decimals"],
    higher: source.higher_is_better ? "high" : "low",
    description: source.description,
  };
}

/** Minutes et secondes saisies -> secondes entières ; `undefined` si vide ; `null` si invalide. */
function toSeconds(min: string, sec: string): number | null | undefined {
  if (min.trim() === "" && sec.trim() === "") return undefined;
  const minutes = min.trim() === "" ? 0 : parseCount(min);
  const seconds = sec.trim() === "" ? 0 : parseCount(sec);
  if (minutes === null || seconds === null || seconds > 59) return null;
  return minutes * 60 + seconds;
}

/** Corps de la requête, ou message d'erreur de saisie (les bornes restent jugées par l'API). */
function buildInput(form: FormState, structureLocked: boolean): { input: Partial<PerformanceTestInput> } | { error: string } {
  const name = form.name.trim();
  if (name === "") return { error: "Saisissez un nom pour le test." };
  if (structureLocked) return { input: { name, description: form.description.trim() } };

  const input: PerformanceTestInput = { name, kind: form.kind, description: form.description.trim() };
  if (form.kind === "timed_distance") {
    const distance = parseDecimalString(form.distance);
    if (distance === null) return { error: "Saisissez une distance entre 1 et 5 000 m." };
    input.distance_m = distance;
  } else if (form.kind === "distance_in_time") {
    const duration = toSeconds(form.durationMin, form.durationSec);
    if (typeof duration !== "number") return { error: "Saisissez une durée entre 10 secondes et 60 minutes." };
    input.duration_s = duration;
  } else if (form.kind === "repetitions") {
    if (form.attempts.trim() !== "") {
      const attempts = parseCount(form.attempts);
      if (attempts === null) return { error: "Le nombre de tentatives doit être compris entre 1 et 100." };
      input.attempts = attempts;
    }
    const limit = toSeconds(form.limitMin, form.limitSec);
    if (limit === null) return { error: "La durée limite doit être supérieure à 0." };
    if (limit !== undefined) input.time_limit_s = limit;
  } else {
    input.unit = form.unit;
    input.decimals = Number(form.decimals);
    input.higher_is_better = form.higher === "high";
  }
  return { input };
}

export interface TestFormModalProps {
  open: boolean;
  onClose: () => void;
  /** Test à modifier ; absent = création. */
  test?: PerformanceTest | null;
  onSaved?: (test: PerformanceTest) => void;
  level?: 1 | 2;
}

/** « Nouveau test » / « Modifier le test » (C6.6). Formulaire en modale. */
export function TestFormModal({ open, onClose, test = null, onSaved, level = 1 }: TestFormModalProps) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const editing = test !== null;
  const structureLocked = editing && test.has_results;
  const [form, setForm] = useState<FormState>(EMPTY);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const templatesQuery = useQuery({
    queryKey: ["sport", "performance", "templates"],
    queryFn: listPerformanceTemplates,
    enabled: open,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (!open) return;
    setForm(test ? stateFrom(test) : EMPTY);
    setDirty(false);
    setError(null);
  }, [open, test]);

  const save = useMutation({
    mutationFn: async (input: Partial<PerformanceTestInput>) =>
      test ? updatePerformanceTest(test.id, input) : createPerformanceTest(input as PerformanceTestInput),
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ["sport", "performance"] });
      showToast(editing ? "Test modifié." : "Test créé.");
      setDirty(false);
      onSaved?.(saved);
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Le test n'a pas pu être enregistré. Réessayez."),
  });

  function patch(next: Partial<FormState>) {
    setForm((current) => ({ ...current, ...next }));
    setDirty(true);
    setError(null);
  }

  function submit() {
    const built = buildInput(form, structureLocked);
    if ("error" in built) {
      setError(built.error);
      return;
    }
    save.mutate(built.input);
  }

  const templates = templatesQuery.data?.results ?? [];

  return (
    <Modal
      open={open}
      onClose={onClose}
      level={level}
      title={editing ? "Modifier le test" : "Nouveau test"}
      isDirty={dirty}
      isSubmitting={save.isPending}
      onConfirm={submit}
      confirmLabel="Enregistrer"
    >
      <div className="space-y-4">
        {error ? <Banner variant="danger">{error}</Banner> : null}

        {!editing && templates.length > 0 ? (
          <div>
            <p className="mb-1 text-sm font-medium text-text">Partir d'un modèle</p>
            <div className="flex flex-wrap gap-2">
              {templates.map((template) => (
                <button
                  key={template.code}
                  type="button"
                  onClick={() => {
                    setForm(stateFrom(template));
                    setDirty(true);
                    setError(null);
                  }}
                  className="h-9 rounded-full border border-border-strong px-3 text-sm text-text hover:bg-surface-muted"
                >
                  {template.name}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <TextField
          label="Nom"
          value={form.name}
          onChange={(name) => patch({ name })}
          maxLength={60}
          help={templatesQuery.data?.health_help}
        />

        <SegmentedControl<PerformanceKind>
          label="Type"
          value={form.kind}
          onChange={(kind) => patch({ kind })}
          options={KIND_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
          wrapOnMobile
          disabled={structureLocked}
          help={
            structureLocked
              ? "Le type ne peut plus changer : des résultats existent. Archivez ce test et créez-en un nouveau."
              : undefined
          }
        />

        {form.kind === "timed_distance" ? (
          <TextField
            label="Distance (m)"
            value={form.distance}
            onChange={(distance) => patch({ distance })}
            inputMode="decimal"
            disabled={structureLocked}
          />
        ) : null}

        {form.kind === "distance_in_time" ? (
          <div className="grid grid-cols-2 gap-2">
            <TextField label="Durée (min)" value={form.durationMin} onChange={(durationMin) => patch({ durationMin })} inputMode="numeric" disabled={structureLocked} />
            <TextField label="Durée (s)" value={form.durationSec} onChange={(durationSec) => patch({ durationSec })} inputMode="numeric" disabled={structureLocked} />
          </div>
        ) : null}

        {form.kind === "repetitions" ? (
          <div className="space-y-2">
            <TextField
              label="Nombre de tentatives"
              value={form.attempts}
              onChange={(attempts) => patch({ attempts })}
              inputMode="numeric"
              optional
              disabled={structureLocked}
            />
            <div className="grid grid-cols-2 gap-2">
              <TextField label="Durée limite (min)" value={form.limitMin} onChange={(limitMin) => patch({ limitMin })} inputMode="numeric" optional disabled={structureLocked} />
              <TextField label="Durée limite (s)" value={form.limitSec} onChange={(limitSec) => patch({ limitSec })} inputMode="numeric" optional disabled={structureLocked} />
            </div>
          </div>
        ) : null}

        {form.kind === "free" ? (
          <div className="space-y-3">
            <SegmentedControl<PerformanceUnit>
              label="Unité"
              value={form.unit}
              onChange={(unit) => patch({ unit })}
              options={UNIT_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
              disabled={structureLocked}
            />
            <SegmentedControl<"0" | "1" | "2">
              label="Décimales"
              value={form.decimals}
              onChange={(decimals) => patch({ decimals })}
              options={[
                { value: "0", label: "0" },
                { value: "1", label: "1" },
                { value: "2", label: "2" },
              ]}
              disabled={structureLocked}
            />
            <SegmentedControl<"high" | "low">
              label="Meilleur résultat"
              value={form.higher}
              onChange={(higher) => patch({ higher })}
              options={[
                { value: "high", label: "Le plus élevé" },
                { value: "low", label: "Le plus bas" },
              ]}
              disabled={structureLocked}
            />
          </div>
        ) : null}

        <TextArea
          label="Description"
          value={form.description}
          onChange={(description) => patch({ description })}
          optional
          maxLength={300}
          showCount
        />
      </div>
    </Modal>
  );
}
