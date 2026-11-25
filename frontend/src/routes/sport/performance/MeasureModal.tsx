import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../../api/client";
import {
  listPerformanceTests,
  type BulkPerformanceItem,
  type BulkPerformanceResponse,
  type PerformanceMethod,
  type PerformanceStartMode,
  type PerformanceTest,
  type PlayerBrief,
} from "../../../api/performance";
import { getSession } from "../../../api/sport";
import {
  Avatar,
  Banner,
  Button,
  Checkbox,
  ConfirmDialog,
  EmptyState,
  Loader,
  Modal,
  SegmentedControl,
  TextField,
  useToast,
} from "../../../design-system";
import { CountdownStep } from "./CountdownStep";
import { ManualStep } from "./ManualStep";
import type { DraftItem, PendingMeasureBatch } from "./measureTypes";
import { StepFooter } from "./StepFooter";
import { StopwatchStep } from "./StopwatchStep";
import { TestFormModal } from "./TestFormModal";
import type { Clock } from "./useTicker";
import type { MeasureOutbox } from "./useMeasureOutbox";

/** Au-delà, il devient impossible d'arrêter chaque chrono au bon moment (C6.1). */
const ADVISED_GROUP_SIZE = 6;
const MAX_GROUP_SIZE = 12;

type Step = "choose" | "countdown" | "stopwatch" | "manual" | "summary";

export interface MeasureModalProps {
  open: boolean;
  eventId: number;
  outbox: MeasureOutbox;
  onClose: () => void;
  /** Test présélectionné (« Ajouter des mesures » depuis les résultats). */
  initialTestId?: number | null;
  /** Horloge monotone injectable (tests) ; `performance.now()` par défaut. */
  clock?: Clock;
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count > 1 ? many : one}`;
}

/**
 * Écran de mesure (C6.1 à C6.3) : choix du test, des joueurs pointés, puis
 * chrono ou saisie manuelle, récapitulatif et envoi. Rien n'est calculé ici
 * hors aperçu de vitesse : le serveur décide des refus et des valeurs.
 */
export function MeasureModal({ open, ...rest }: MeasureModalProps) {
  return open ? <MeasureModalBody {...rest} /> : null;
}

function MeasureModalBody({ eventId, outbox, onClose, initialTestId = null, clock }: Omit<MeasureModalProps, "open">) {
  const { showToast } = useToast();
  const [step, setStep] = useState<Step>("choose");
  const [testId, setTestId] = useState<number | null>(initialTestId);
  const [method, setMethod] = useState<PerformanceMethod>("stopwatch");
  const [startMode, setStartMode] = useState<PerformanceStartMode>("group");
  const [selected, setSelected] = useState<number[]>([]);
  const [search, setSearch] = useState("");
  const [dirty, setDirty] = useState(false);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [review, setReview] = useState<DraftItem[] | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [summary, setSummary] = useState<{ response: BulkPerformanceResponse; names: Record<number, string> } | null>(null);
  const [usedMethod, setUsedMethod] = useState<PerformanceMethod>("manual");
  const [formError, setFormError] = useState<string | null>(null);
  const [newTestOpen, setNewTestOpen] = useState(false);

  // Clés d'idempotence : conservées tant que l'envoi n'a pas reçu de réponse (nouvel essai réseau).
  const lotUuid = useRef<string | null>(null);
  const itemUuids = useRef(new Map<string, string>());

  const sessionQuery = useQuery({ queryKey: ["sport", "session", eventId], queryFn: () => getSession(eventId) });
  const testsQuery = useQuery({ queryKey: ["sport", "performance", "tests", "active"], queryFn: () => listPerformanceTests() });

  const tests = testsQuery.data?.results ?? [];
  const test: PerformanceTest | null = tests.find((candidate) => candidate.id === testId) ?? null;
  // Le chronomètre n'existe que pour certains types : sinon, saisie manuelle.
  const effectiveMethod: PerformanceMethod = test && !test.stopwatch_available ? "manual" : method;

  // Seuls les joueurs pointés (présents ou en retard) sont mesurables ; l'API reste juge.
  const roster: PlayerBrief[] = useMemo(
    () =>
      (sessionQuery.data?.attendances ?? [])
        .filter((attendance) => attendance.status === "present" || attendance.status === "late_absent")
        .map((attendance) => attendance.player),
    [sessionQuery.data],
  );
  const filtered = roster.filter((player) => {
    const needle = search.trim().toLowerCase();
    return needle === "" || player.name.toLowerCase().includes(needle) || String(player.jersey_number ?? "") === needle;
  });
  const players = roster.filter((player) => selected.includes(player.membership_id));

  useEffect(() => {
    if (!dirty || step === "summary") return undefined;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty, step]);

  const onDirtyChange = useCallback((value: boolean) => setDirty(value), []);

  function requestClose() {
    if (step !== "summary" && dirty) setConfirmAbandon(true);
    else onClose();
  }

  function chooseTest(next: PerformanceTest) {
    setTestId(next.id);
    setMethod(next.stopwatch_available ? "stopwatch" : "manual");
    setFormError(null);
  }

  function toggle(id: number) {
    setSelected((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id]));
  }

  function begin() {
    if (!test) {
      setFormError("Choisissez un test.");
      return;
    }
    if (selected.length === 0) {
      setFormError("Cochez au moins un joueur.");
      return;
    }
    const stopwatch = effectiveMethod === "stopwatch";
    if (stopwatch && test.kind === "timed_distance" && startMode === "group" && selected.length > MAX_GROUP_SIZE) {
      setFormError(`${MAX_GROUP_SIZE} joueurs au plus par départ groupé. Choisissez « Un par un » ou réduisez la sélection.`);
      return;
    }
    setUsedMethod(stopwatch ? "stopwatch" : "manual");
    setStep(stopwatch ? (test.kind === "distance_in_time" ? "countdown" : "stopwatch") : "manual");
  }

  function buildBatch(items: DraftItem[], activeTest: PerformanceTest): PendingMeasureBatch {
    if (lotUuid.current === null) lotUuid.current = crypto.randomUUID();
    const meta: PendingMeasureBatch["meta"] = {};
    const bodyItems: BulkPerformanceItem[] = items.map((draft) => {
      const signature = `${draft.membershipId}:${draft.attemptNo}:${JSON.stringify(draft.fields)}`;
      let uuid = itemUuids.current.get(signature);
      if (!uuid) {
        uuid = crypto.randomUUID();
        itemUuids.current.set(signature, uuid);
      }
      meta[uuid] = { name: draft.name, label: draft.label };
      return { membership_id: draft.membershipId, attempt_no: draft.attemptNo, ...draft.fields, client_uuid: uuid };
    });
    return {
      eventId,
      testName: activeTest.name,
      body: {
        test_id: activeTest.id,
        method: usedMethod,
        start_mode: usedMethod === "stopwatch" && activeTest.kind === "timed_distance" ? startMode : "",
        client_uuid: lotUuid.current,
        items: bodyItems,
      },
      meta,
    };
  }

  async function send() {
    if (!review || !test) return;
    setSubmitting(true);
    setSendError(null);
    const names = Object.fromEntries(review.map((item) => [item.membershipId, item.name]));
    try {
      const outcome = await outbox.submit(buildBatch(review, test));
      lotUuid.current = null;
      itemUuids.current = new Map();
      setReview(null);
      if (outcome.kind === "queued") {
        showToast(
          `${plural(review.length, "résultat enregistré", "résultats enregistrés")} sur ce téléphone. Ils seront envoyés au retour du réseau.`,
        );
        setDirty(false);
        onClose();
        return;
      }
      setDirty(false);
      setSummary({ response: outcome.response, names });
      setStep("summary");
    } catch (error) {
      setSendError(error instanceof ApiError ? error.detail : "Les mesures n'ont pas pu être envoyées. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  const title =
    step === "choose" || step === "summary" || !test
      ? "Mesurer"
      : step === "manual"
        ? `Saisie manuelle : ${test.name}`
        : `Chronomètre : ${test.name}`;

  return (
    <>
      <Modal open onClose={requestClose} size="xl" title={title} hideFooter isSubmitting={submitting}>
        {step === "choose" ? (
          <div className="space-y-4">
            {formError ? <Banner variant="danger">{formError}</Banner> : null}

            <section aria-label="Test">
              <div className="mb-1 flex items-center justify-between">
                <h3 className="text-sm font-medium text-text">Test</h3>
                <Button size="sm" variant="ghost" onClick={() => setNewTestOpen(true)}>
                  Nouveau test
                </Button>
              </div>
              {testsQuery.isLoading ? (
                <Loader loading variant="list" count={3} />
              ) : testsQuery.isError ? (
                <EmptyState variant="error" message="Impossible de charger les tests." actionLabel="Réessayer" onAction={() => void testsQuery.refetch()} />
              ) : tests.length === 0 ? (
                <EmptyState message="Aucun test de performance pour l'instant." actionLabel="Nouveau test" onAction={() => setNewTestOpen(true)} />
              ) : (
                <div role="radiogroup" aria-label="Test" className="space-y-1">
                  {tests.map((candidate) => (
                    <button
                      key={candidate.id}
                      type="button"
                      role="radio"
                      aria-checked={candidate.id === testId}
                      onClick={() => chooseTest(candidate)}
                      className={[
                        "flex min-h-11 w-full flex-col items-start rounded-md border px-3 py-1 text-left",
                        candidate.id === testId ? "border-primary bg-surface-muted" : "border-border",
                      ].join(" ")}
                    >
                      <span className="text-sm font-medium text-text">{candidate.name}</span>
                      <span className="text-xs text-text-muted">{candidate.kind_text}</span>
                    </button>
                  ))}
                </div>
              )}
            </section>

            {test ? (
              <SegmentedControl<PerformanceMethod>
                label="Méthode"
                value={effectiveMethod}
                onChange={setMethod}
                options={[
                  ...(test.stopwatch_available ? [{ value: "stopwatch" as const, label: "Chronomètre" }] : []),
                  { value: "manual" as const, label: "Saisie manuelle" },
                ]}
              />
            ) : null}

            {test && effectiveMethod === "stopwatch" && test.kind === "timed_distance" ? (
              <SegmentedControl<PerformanceStartMode>
                label="Départ"
                value={startMode}
                onChange={setStartMode}
                options={[
                  { value: "group", label: "Départ groupé" },
                  { value: "individual", label: "Un par un" },
                ]}
              />
            ) : null}

            <section aria-label="Joueurs pointés">
              <h3 className="mb-1 text-sm font-medium text-text">Joueurs</h3>
              {sessionQuery.isLoading ? (
                <Loader loading variant="list" count={4} />
              ) : sessionQuery.isError ? (
                <EmptyState variant="error" message="Impossible de charger les joueurs pointés." actionLabel="Réessayer" onAction={() => void sessionQuery.refetch()} />
              ) : roster.length === 0 ? (
                <EmptyState message="Aucun joueur n'est encore pointé : seuls les joueurs pointés peuvent être mesurés." />
              ) : (
                <div className="space-y-2">
                  <TextField label="Nom ou numéro" value={search} onChange={setSearch} />
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" onClick={() => setSelected((c) => [...c, ...filtered.map((p) => p.membership_id).filter((id) => !c.includes(id))])}>
                      Tout cocher
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setSelected([])}>
                      Tout décocher
                    </Button>
                  </div>
                  {effectiveMethod === "stopwatch" && test?.kind === "timed_distance" && startMode === "group" && selected.length > ADVISED_GROUP_SIZE ? (
                    <p className="text-xs text-text-muted">
                      {ADVISED_GROUP_SIZE} joueurs au plus conseillés par départ : au-delà, il devient difficile d'arrêter chaque chrono au bon moment.
                    </p>
                  ) : null}
                  {filtered.length === 0 ? (
                    <EmptyState variant="no-results" message="Aucun joueur ne correspond à cette recherche." />
                  ) : (
                    <ul className="divide-y divide-border">
                      {filtered.map((player) => (
                        <li key={player.membership_id} className="flex min-h-11 items-center gap-2 py-1">
                          <Checkbox
                            checked={selected.includes(player.membership_id)}
                            onChange={() => toggle(player.membership_id)}
                            label={
                              <span className="flex items-center gap-2">
                                <Avatar name={player.name} photoUrl={player.photo} size={32} />
                                <span className="break-words">
                                  {player.name}
                                  {player.jersey_number !== null ? ` · n°${player.jersey_number}` : ""}
                                </span>
                              </span>
                            }
                          />
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </section>

            <StepFooter>
              <Button variant="secondary" className="flex-1" onClick={requestClose}>
                Annuler
              </Button>
              <Button variant="primary" className="flex-1" onClick={begin} disabled={roster.length === 0}>
                Commencer
              </Button>
            </StepFooter>
          </div>
        ) : null}

        {step === "countdown" && test ? (
          <CountdownStep
            test={test}
            clock={clock}
            onDirtyChange={onDirtyChange}
            onElapsed={() => {
              setDirty(false);
              setStep("manual");
            }}
          />
        ) : null}

        {step === "stopwatch" && test ? (
          <StopwatchStep
            test={test}
            players={players}
            startMode={startMode}
            clock={clock}
            onDirtyChange={onDirtyChange}
            onReview={setReview}
          />
        ) : null}

        {step === "manual" && test ? (
          <ManualStep
            test={test}
            players={players}
            intro={usedMethod === "stopwatch" ? "Temps écoulé. Saisissez la distance de chaque joueur." : undefined}
            onDirtyChange={onDirtyChange}
            onReview={setReview}
          />
        ) : null}

        {step === "summary" && summary ? (
          <div className="space-y-3">
            <p className="text-sm text-text">
              {plural(summary.response.counts.created, "mesure enregistrée", "mesures enregistrées")}.
              {summary.response.counts.skipped > 0
                ? ` ${plural(summary.response.counts.skipped, "mesure déjà enregistrée", "mesures déjà enregistrées")}.`
                : ""}
            </p>
            {summary.response.results.some((r) => r.warning) ? (
              <Banner variant="warning">
                <ul>
                  {summary.response.results
                    .filter((r) => r.warning)
                    .map((r, index) => (
                      <li key={index}>
                        {summary.names[r.membership_id] ?? "Joueur"} : {r.warning}
                      </li>
                    ))}
                </ul>
              </Banner>
            ) : null}
            {summary.response.counts.refused > 0 ? (
              <section aria-label="Mesures refusées" className="space-y-1">
                <Banner variant="danger">
                  {plural(summary.response.counts.refused, "mesure refusée", "mesures refusées")}. Elles restent sur ce
                  téléphone : vous pourrez les réessayer depuis le bilan de la séance.
                </Banner>
                <ul className="divide-y divide-border">
                  {summary.response.results
                    .filter((r) => r.outcome === "refused")
                    .map((r, index) => (
                      <li key={index} className="py-2 text-sm text-text">
                        <span className="font-medium">{summary.names[r.membership_id] ?? "Joueur"}</span> : {r.message}
                      </li>
                    ))}
                </ul>
              </section>
            ) : null}
            <StepFooter>
              <Button variant="primary" className="w-full" onClick={onClose}>
                Fermer
              </Button>
            </StepFooter>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        open={review !== null}
        danger={false}
        title={review ? `Envoyer ${plural(review.length, "mesure", "mesures")} ?` : "Envoyer les mesures ?"}
        description={
          review ? (
            <ul className="max-h-60 divide-y divide-border overflow-y-auto">
              {review.map((item) => (
                <li key={`${item.membershipId}-${item.attemptNo}`} className="flex justify-between gap-2 py-1">
                  <span className="break-words text-text">
                    {item.name}
                    {item.attemptNo > 1 || review.some((o) => o.membershipId === item.membershipId && o !== item) ? ` · essai ${item.attemptNo}` : ""}
                  </span>
                  <span className="shrink-0 font-medium text-text">{item.label}</span>
                </li>
              ))}
            </ul>
          ) : null
        }
        confirmLabel="Envoyer les mesures"
        loading={submitting}
        loadingLabel="Envoi…"
        error={sendError ?? undefined}
        onConfirm={() => void send()}
        onCancel={() => {
          setReview(null);
          setSendError(null);
        }}
      />

      <ConfirmDialog
        open={confirmAbandon}
        title="Abandonner ces mesures ?"
        description="Les temps non enregistrés seront perdus."
        confirmLabel="Abandonner"
        cancelLabel="Continuer"
        onConfirm={() => {
          setConfirmAbandon(false);
          onClose();
        }}
        onCancel={() => setConfirmAbandon(false)}
      />

      <TestFormModal
        open={newTestOpen}
        level={2}
        onClose={() => setNewTestOpen(false)}
        onSaved={(saved) => chooseTest(saved)}
      />
    </>
  );
}
