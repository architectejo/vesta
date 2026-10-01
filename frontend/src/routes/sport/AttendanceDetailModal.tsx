import { useState } from "react";
import { ApiError } from "../../api/client";
import { correctAttendanceTime, excuseSessionAttendance, type Attendance } from "../../api/sport";
import { Button, Modal, SegmentedControl, StatusBadge, TextField } from "../../design-system";
import type { StatusKey } from "../../design-system";
import { combineDateTimeToIso, formatTime } from "./sportTime";

const EXCUSE_MOTIVES = [
  { value: "Blessé", label: "Blessé" },
  { value: "Voyage", label: "Voyage" },
  { value: "Autre", label: "Autre" },
] as const;

function statusKey(status: Attendance["status"]): StatusKey {
  if (status === "present") return "present";
  if (status === "late_absent") return "late";
  if (status === "excused_absent") return "excused";
  return "absent";
}

export interface AttendanceDetailModalProps {
  open: boolean;
  sessionId: number;
  attendance: Attendance;
  eventDate: string;
  arrivalRank: number | null;
  canCorrectTime: boolean;
  isLocked: boolean;
  onClose: () => void;
  onUpdated: () => void;
}

/** « Pointage de {nom} » (docs/ecrans/sport-seance.md §4.1). */
export function AttendanceDetailModal({
  open,
  sessionId,
  attendance,
  eventDate,
  arrivalRank,
  canCorrectTime,
  isLocked,
  onClose,
  onUpdated,
}: AttendanceDetailModalProps) {
  const [mode, setMode] = useState<"view" | "excuse">("view");
  const [time, setTime] = useState(formatTime(attendance.arrived_at) || "00:00");
  const [motive, setMotive] = useState<(typeof EXCUSE_MOTIVES)[number]["value"]>("Blessé");
  const [detail, setDetail] = useState("");
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  const canEdit = canCorrectTime && !isLocked;

  async function handleSaveTime(): Promise<void> {
    setError(undefined);
    setSubmitting(true);
    try {
      await correctAttendanceTime(attendance.id, combineDateTimeToIso(eventDate, time));
      onUpdated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleExcuse(): Promise<void> {
    setError(undefined);
    setSubmitting(true);
    try {
      await excuseSessionAttendance(sessionId, {
        membership_id: attendance.membership_id,
        reason: detail ? `${motive} : ${detail}` : motive,
      });
      onUpdated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Pointage de ${attendance.player.name}`}
      size="sm"
      isSubmitting={submitting}
      footer={
        canEdit ? (
          <>
            <Button variant="secondary" className="flex-1 sm:flex-none" onClick={onClose}>
              Annuler
            </Button>
            <Button
              variant="primary"
              className="flex-1 sm:flex-none"
              loading={submitting}
              onClick={() => void (mode === "excuse" ? handleExcuse() : handleSaveTime())}
            >
              Enregistrer
            </Button>
          </>
        ) : (
          <Button variant="secondary" className="flex-1 sm:flex-none" onClick={onClose}>
            Fermer
          </Button>
        )
      }
    >
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-text">
              Heure d'arrivée : {formatTime(attendance.arrived_at) || "—"}
              {arrivalRank ? ` · rang #${arrivalRank}` : ""}
            </p>
            {attendance.excused_reason ? (
              <p className="text-sm text-text-muted">Motif : {attendance.excused_reason}</p>
            ) : null}
          </div>
          <StatusBadge status={statusKey(attendance.status)} />
        </div>

        {canEdit ? (
          mode === "view" ? (
            <>
              <label className="block text-sm font-medium text-text">
                Heure d'arrivée
                <input
                  type="time"
                  className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
                  value={time}
                  onChange={(e) => setTime(e.target.value)}
                />
              </label>
              <p className="text-xs text-text-muted">L'heure doit être comprise dans la journée de la séance.</p>
              <Button variant="secondary" size="sm" onClick={() => setMode("excuse")}>
                Marquer absent excusé
              </Button>
            </>
          ) : (
            <div className="space-y-3 rounded-md border border-border p-3">
              <SegmentedControl label="Motif" value={motive} onChange={setMotive} options={[...EXCUSE_MOTIVES]} />
              <TextField label="Précision" optional value={detail} onChange={setDetail} />
              <Button variant="ghost" size="sm" onClick={() => setMode("view")}>
                Annuler l'absence excusée
              </Button>
            </div>
          )
        ) : null}

        {error ? <p className="text-sm text-status-danger-fg">{error}</p> : null}
      </div>
    </Modal>
  );
}
