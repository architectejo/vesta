import { useState } from "react";
import { conveneAssembly, type Assembly, type AssemblyType } from "../../../api/assemblies";
import { ApiError } from "../../../api/client";
import {
  Banner,
  Button,
  IconButton,
  IconMoveDown,
  IconMoveUp,
  IconRemove,
  Modal,
  SegmentedControl,
  TextArea,
  TextField,
} from "../../../design-system";
import { assemblyTypeLabel, formatDateLong, formatTimeShort } from "./assembliesFormat";

interface AgendaDraftItem {
  key: string;
  title: string;
  description: string;
}

const STEP_NAMES = ["Informations", "Ordre du jour", "Récapitulatif"];

function todayIso(): string {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}

/** Assistant « Convoquer une assemblée générale » (assemblees-page-ag.md §4.1). */
export function ConveneAssemblyWizard({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (assembly: Assembly) => void;
}) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [assemblyType, setAssemblyType] = useState<AssemblyType>("ordinary");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [location, setLocation] = useState("");
  const [step1Errors, setStep1Errors] = useState<Record<string, string>>({});

  const [items, setItems] = useState<AgendaDraftItem[]>([
    { key: crypto.randomUUID(), title: "", description: "" },
  ]);
  const [agendaError, setAgendaError] = useState<string | null>(null);

  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isDirty = date !== "" || time !== "" || location !== "" || items.some((i) => i.title.trim() !== "");

  function validateStep1(): boolean {
    const errors: Record<string, string> = {};
    if (!date) errors.date = "Ce champ est obligatoire.";
    else if (date < todayIso()) errors.date = "La date doit être dans le futur.";
    if (!time) errors.time = "Ce champ est obligatoire.";
    if (!location.trim()) errors.location = "Ce champ est obligatoire.";
    setStep1Errors(errors);
    return Object.keys(errors).length === 0;
  }

  function validateAgenda(): boolean {
    const hasAtLeastOne = items.some((i) => i.title.trim() !== "");
    if (!hasAtLeastOne) {
      setAgendaError("Ajoutez au moins un point à l'ordre du jour.");
      return false;
    }
    setAgendaError(null);
    return true;
  }

  function goNext(): void {
    if (step === 1 && validateStep1()) setStep(2);
    else if (step === 2 && validateAgenda()) setStep(3);
  }

  function updateItem(key: string, patch: Partial<AgendaDraftItem>): void {
    setItems((current) => current.map((i) => (i.key === key ? { ...i, ...patch } : i)));
  }

  function moveItem(index: number, direction: -1 | 1): void {
    setItems((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      const [moved] = next.splice(index, 1);
      if (moved) next.splice(target, 0, moved);
      return next;
    });
  }

  async function handleSubmit(): Promise<void> {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const assembly = await conveneAssembly({
        assembly_type: assemblyType,
        scheduled_date: date,
        scheduled_time: time,
        location: location.trim(),
        agenda_items: items
          .filter((i) => i.title.trim() !== "")
          .map((i) => ({ title: i.title.trim(), description: i.description.trim() })),
      });
      onCreated(assembly);
    } catch (err) {
      setSubmitError(
        err instanceof ApiError
          ? err.detail
          : "La convocation n'a pas abouti. Vérifiez votre réseau et réessayez.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Convoquer une assemblée générale"
      subtitle={`Étape ${step} sur 3 — ${STEP_NAMES[step - 1]}`}
      size="xl"
      isDirty={isDirty}
      isSubmitting={submitting}
      hideFooter
    >
      <div className="mb-4 h-[3px] w-full rounded-full bg-surface-muted">
        <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${(step / 3) * 100}%` }} />
      </div>

      {step === 1 ? (
        <div className="space-y-4">
          <SegmentedControl
            label="Type"
            value={assemblyType}
            onChange={setAssemblyType}
            options={[
              { value: "ordinary", label: "Ordinaire" },
              { value: "extraordinary", label: "Extraordinaire" },
            ]}
          />
          <TextField
            label="Date"
            type="date"
            value={date}
            onChange={setDate}
            error={step1Errors.date}
            min={todayIso()}
          />
          <TextField label="Heure" type="time" value={time} onChange={setTime} error={step1Errors.time} />
          <TextField label="Lieu" value={location} onChange={setLocation} error={step1Errors.location} />
        </div>
      ) : null}

      {step === 2 ? (
        <div className="space-y-4">
          {agendaError ? <Banner variant="danger">{agendaError}</Banner> : null}
          <div className="space-y-3">
            {items.map((item, index) => (
              <div key={item.key} className="rounded-md border border-border p-3">
                <div className="flex items-start gap-2">
                  <div className="flex-1 space-y-2">
                    <TextField
                      label="Intitulé"
                      value={item.title}
                      onChange={(v) => updateItem(item.key, { title: v })}
                    />
                    <TextArea
                      label="Description"
                      optional
                      value={item.description}
                      onChange={(v) => updateItem(item.key, { description: v })}
                      rows={2}
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <IconButton
                      aria-label="Monter"
                      variant="secondary"
                      icon={<IconMoveUp aria-hidden="true" className="h-4 w-4" />}
                      disabled={index === 0}
                      onClick={() => moveItem(index, -1)}
                    />
                    <IconButton
                      aria-label="Descendre"
                      variant="secondary"
                      icon={<IconMoveDown aria-hidden="true" className="h-4 w-4" />}
                      disabled={index === items.length - 1}
                      onClick={() => moveItem(index, 1)}
                    />
                    <IconButton
                      aria-label="Retirer"
                      variant="secondary"
                      icon={<IconRemove aria-hidden="true" className="h-4 w-4" />}
                      disabled={items.length === 1}
                      onClick={() => setItems((current) => current.filter((i) => i.key !== item.key))}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setItems((current) => [...current, { key: crypto.randomUUID(), title: "", description: "" }])}
          >
            Ajouter un point
          </Button>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="space-y-4">
          {submitError ? <Banner variant="danger">{submitError}</Banner> : null}
          <div className="rounded-md border border-border p-3">
            <p className="text-sm font-semibold text-text">
              AG {assemblyTypeLabel(assemblyType).toLowerCase()} du {date ? formatDateLong(date) : ""}
            </p>
            <p className="text-xs text-text-muted">
              {time ? formatTimeShort(`${time}:00`) : ""} · {location}
            </p>
          </div>
          <div className="rounded-md border border-border p-3">
            <p className="mb-1 text-sm font-semibold text-text">Ordre du jour</p>
            <ol className="list-decimal space-y-1 pl-5 text-sm text-text">
              {items
                .filter((i) => i.title.trim() !== "")
                .map((item) => (
                  <li key={item.key}>{item.title}</li>
                ))}
            </ol>
          </div>
          <p className="text-sm text-text-muted">
            Tous les joueurs recevront la convocation par notification et par email. Un rappel sera envoyé la
            veille.
          </p>
        </div>
      ) : null}

      <div className="sticky -bottom-4 z-20 -mx-4 -mb-4 mt-6 flex items-center justify-between gap-2 border-t border-border bg-surface px-4 py-3">
        <Button variant="secondary" onClick={onClose} disabled={submitting}>
          Annuler
        </Button>
        <div className="flex gap-2">
          {step > 1 ? (
            <Button variant="secondary" onClick={() => setStep((s) => (s - 1) as 1 | 2)} disabled={submitting}>
              Précédent
            </Button>
          ) : null}
          {step < 3 ? (
            <Button variant="primary" onClick={goNext}>
              Suivant
            </Button>
          ) : (
            <Button variant="primary" loading={submitting} loadingLabel="Convocation…" onClick={() => void handleSubmit()}>
              Convoquer
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
