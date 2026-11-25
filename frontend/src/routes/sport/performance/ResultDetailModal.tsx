import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../../api/client";
import {
  correctPerformanceResult,
  getPerformanceResult,
  voidPerformanceResult,
  type PerformanceCorrectionInput,
} from "../../../api/performance";
import { Avatar, Banner, Button, ConfirmDialog, EmptyState, Loader, Modal, TextArea, useToast } from "../../../design-system";
import { formatLocalDate, formatLocalDateTime } from "./performanceFormat";
import { draftFromValue, emptyDraft, readDraft, ValueInput, type ValueDraft } from "./ValueInput";

export interface ResultDetailModalProps {
  resultId: number | null;
  onClose: () => void;
  /** Coach / Assistant : peut corriger ou retirer (si la fenêtre est ouverte, selon l'API). */
  canManage: boolean;
}

/** « Résultat de {joueur} » (C6.8) : lecture, historique des corrections, correction et retrait. */
export function ResultDetailModal({ resultId, onClose, canManage }: ResultDetailModalProps) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const open = resultId !== null;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<ValueDraft>(emptyDraft());
  const [reason, setReason] = useState("");
  const [voidOpen, setVoidOpen] = useState(false);
  const [voidReason, setVoidReason] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [voidError, setVoidError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["sport", "performance", "result", resultId],
    queryFn: () => getPerformanceResult(resultId as number),
    enabled: open,
  });
  const detail = query.data;

  useEffect(() => {
    setEditing(false);
    setReason("");
    setVoidReason("");
    setVoidOpen(false);
    setVoidError(null);
    setFieldError(null);
    setReasonError(null);
    setServerError(null);
  }, [resultId]);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["sport", "performance"] });
    void queryClient.invalidateQueries({ queryKey: ["sport", "session-stats"] });
  };

  const correct = useMutation({
    mutationFn: (input: PerformanceCorrectionInput) => correctPerformanceResult(resultId as number, input),
    onSuccess: () => {
      refresh();
      showToast("Correction enregistrée.");
      setEditing(false);
      setReason("");
    },
    onError: (error) => setServerError(error instanceof ApiError ? error.detail : "La correction n'a pas pu être enregistrée. Réessayez."),
  });

  const voidResult = useMutation({
    mutationFn: (text: string) => voidPerformanceResult(resultId as number, text),
    onSuccess: () => {
      refresh();
      showToast("Résultat retiré.");
      setVoidOpen(false);
      setVoidReason("");
    },
    onError: (error) => setVoidError(error instanceof ApiError ? error.detail : "Le résultat n'a pas pu être retiré. Réessayez."),
  });

  function startEditing() {
    if (!detail) return;
    setDraft(draftFromValue(detail.test, detail));
    setReason("");
    setFieldError(null);
    setReasonError(null);
    setServerError(null);
    setEditing(true);
  }

  function saveCorrection() {
    if (!detail) return;
    const read = readDraft(detail.test, draft);
    let valid = true;
    if (read.state === "empty") {
      setFieldError("Saisissez la nouvelle valeur.");
      valid = false;
    } else if (read.state === "error") {
      setFieldError(read.message);
      valid = false;
    }
    if (reason.trim() === "") {
      setReasonError("Indiquez le motif.");
      valid = false;
    }
    if (!valid || read.state !== "ok") return;
    setServerError(null);
    correct.mutate({ reason: reason.trim(), ...read.fields, outcome: read.fields.outcome ?? "done" });
  }

  const editable = canManage && detail && !detail.locked && detail.status === "active";

  return (
    <Modal
      open={open}
      onClose={onClose}
      level={2}
      size="sm"
      title={detail ? `Résultat de ${detail.player.name}` : "Résultat"}
      loading={query.isLoading}
      isDirty={editing && (reason !== "" || draft.text !== "")}
      isSubmitting={correct.isPending}
      footer={
        editing ? (
          <>
            <Button variant="secondary" onClick={() => setEditing(false)} disabled={correct.isPending}>
              Annuler
            </Button>
            <Button variant="primary" onClick={saveCorrection} loading={correct.isPending} loadingLabel="Enregistrement…">
              Enregistrer la correction
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>
              Fermer
            </Button>
            {editable ? (
              <>
                <Button variant="secondary" onClick={() => setVoidOpen(true)}>
                  Retirer ce résultat
                </Button>
                <Button variant="primary" onClick={startEditing}>Corriger</Button>
              </>
            ) : null}
          </>
        )
      }
    >
      {query.isError ? (
        <EmptyState
          variant="error"
          message={query.error instanceof ApiError && query.error.status === 404 ? "Ce résultat n'existe pas." : "Impossible de charger ce résultat."}
          actionLabel="Réessayer"
          onAction={() => void query.refetch()}
        />
      ) : detail ? (
        <div className="space-y-3">
          {serverError ? <Banner variant="danger">{serverError}</Banner> : null}
          {detail.status === "voided" ? <Banner variant="warning">Ce résultat a été retiré : il n'est plus compté.</Banner> : null}
          {detail.locked && detail.status === "active" ? <Banner variant="readonly">Résultat verrouillé (plus de 48 heures).</Banner> : null}

          <div className="flex items-center gap-2">
            <Avatar name={detail.player.name} photoUrl={detail.player.photo} size={32} />
            <div className="min-w-0">
              <p className="break-words text-sm font-medium text-text">{detail.player.name}</p>
              <p className="text-xs text-text-muted">
                {detail.test.name} · séance du {formatLocalDate(detail.date)}
              </p>
            </div>
          </div>

          {editing ? (
            <div className="space-y-3">
              <ValueInput test={detail.test} name={detail.player.name} draft={draft} onChange={setDraft} error={fieldError ?? undefined} />
              <TextArea
                label="Motif de la correction"
                value={reason}
                onChange={(text) => {
                  setReason(text);
                  setReasonError(null);
                }}
                error={reasonError ?? undefined}
                maxLength={500}
              />
            </div>
          ) : (
            <dl className="space-y-1 text-sm">
              <div className="flex justify-between gap-2">
                <dt className="text-text-muted">Résultat</dt>
                <dd className="font-semibold text-text">{detail.display}</dd>
              </div>
              {detail.derived.speed_display ? (
                <div className="flex justify-between gap-2">
                  <dt className="text-text-muted">Vitesse moyenne</dt>
                  <dd className="text-text">
                    {detail.derived.speed_display} · {detail.derived.speed_ms_display}
                  </dd>
                </div>
              ) : null}
              {detail.derived.success_rate_display ? (
                <div className="flex justify-between gap-2">
                  <dt className="text-text-muted">Taux de réussite</dt>
                  <dd className="text-text">{detail.derived.success_rate_display}</dd>
                </div>
              ) : null}
              <div className="flex justify-between gap-2">
                <dt className="text-text-muted">Essai</dt>
                <dd className="text-text">{detail.attempt_no}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-text-muted">Méthode</dt>
                <dd className="text-text">{detail.method_label}</dd>
              </div>
              <p className="pt-1 text-xs text-text-muted">
                Mesuré par {detail.recorded_by.name} le {formatLocalDateTime(detail.recorded_at)}
              </p>
            </dl>
          )}

          {detail.corrections.length > 0 ? (
            <section aria-label="Historique des corrections" className="space-y-1 border-t border-border pt-2">
              <h3 className="text-sm font-semibold text-text">Historique des corrections</h3>
              <ul className="space-y-2">
                {detail.corrections.map((correction) => (
                  <li key={correction.id} className="break-words text-sm text-text">
                    {correction.after.status === "voided"
                      ? `Retiré par ${correction.actor.name} le ${formatLocalDateTime(correction.created_at)}`
                      : `Corrigé par ${correction.actor.name} le ${formatLocalDateTime(correction.created_at)} : ${correction.before.display} → ${correction.after.display}`}
                    {" · motif : "}
                    {correction.reason}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      ) : (
        <Loader loading variant="list" count={3} />
      )}

      <ConfirmDialog
        open={voidOpen}
        title={detail ? `Retirer le résultat de ${detail.player.name} (${detail.display}) ?` : "Retirer ce résultat ?"}
        description={
          <div className="space-y-3">
            <p>Il ne sera plus compté, mais restera dans l'historique des corrections.</p>
            <TextArea
              label="Motif"
              value={voidReason}
              onChange={(text) => {
                setVoidReason(text);
                setVoidError(null);
              }}
              maxLength={500}
            />
          </div>
        }
        confirmLabel="Retirer"
        loading={voidResult.isPending}
        loadingLabel="Retrait…"
        error={voidError ?? undefined}
        onConfirm={() => {
          if (voidReason.trim() === "") {
            setVoidError("Indiquez le motif.");
            return;
          }
          setVoidError(null);
          voidResult.mutate(voidReason.trim());
        }}
        onCancel={() => {
          setVoidOpen(false);
          setVoidError(null);
        }}
      />
    </Modal>
  );
}
