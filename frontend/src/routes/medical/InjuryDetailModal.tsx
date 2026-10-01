import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getHealthRecord, getInjury } from "../../api/medical";
import { EmptyState, Modal, StatusBadge } from "../../design-system";
import { InjuryCompleteModal } from "./InjuryCompleteModal";
import { InjuryFollowUpModal } from "./InjuryFollowUpModal";
import { InjuryReturnDialog } from "./InjuryReturnDialog";
import { formatDateFrLong, formatTimeFr } from "./medicalFormat";
import { injuryEventLabel, injuryStatusKey, injuryStatusLabel } from "./medicalLabels";

export type InjuryDetailMode = "doctor" | "readonly";

export interface InjuryDetailModalProps {
  open: boolean;
  injuryId: number;
  mode: InjuryDetailMode;
  /** Nom complet du joueur (déjà connu de l'appelant) — utilisé tel quel
   * partout où la spec écrit « {Prénom} » (même convention que
   * `routes/sport/MatchPage.tsx`/`ConsigneModal.tsx`, l'API ne renvoyant
   * qu'un nom complet). */
  playerName: string;
  onClose: () => void;
  onChanged: () => void;
}

/**
 * « Blessure » (medical.md §4.3) : lecture/écriture pour le Médecin, lecture
 * seule pour le joueur concerné et le Président avec consentement. Réponse
 * N2 jamais mise en cache (§5.4) : `gcTime: 0`, requête invalidée à la
 * fermeture.
 */
export function InjuryDetailModal({ open, injuryId, mode, playerName, onClose, onChanged }: InjuryDetailModalProps) {
  const queryClient = useQueryClient();
  const [menuOpen, setMenuOpen] = useState(false);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [followUpOpen, setFollowUpOpen] = useState(false);
  const [returnOpen, setReturnOpen] = useState(false);

  const injuryQuery = useQuery({
    queryKey: ["medical", "injury", injuryId],
    queryFn: () => getInjury(injuryId),
    enabled: open,
    gcTime: 0,
    staleTime: 0,
  });

  const membershipId = injuryQuery.data?.membership_id;
  const recordQuery = useQuery({
    queryKey: ["medical", "health-record", membershipId],
    queryFn: () => getHealthRecord(membershipId as number),
    enabled: open && mode === "doctor" && membershipId !== undefined,
    gcTime: 0,
    staleTime: 0,
  });

  function handleClose(): void {
    void queryClient.removeQueries({ queryKey: ["medical", "injury", injuryId] });
    onClose();
  }

  function handleChanged(): void {
    void injuryQuery.refetch();
    void recordQuery.refetch();
    onChanged();
  }

  const loading = injuryQuery.isLoading || (mode === "doctor" && membershipId !== undefined && recordQuery.isLoading);
  const injury = injuryQuery.data;
  const consentMissing = mode === "doctor" ? recordQuery.data?.consent_given_at == null : false;
  const hasOtherOpenInjury =
    mode === "doctor"
      ? (recordQuery.data?.open_injuries.filter((i) => i.id !== injuryId).length ?? 0) > 0
      : false;

  return (
    <>
      <Modal
        open={open}
        onClose={handleClose}
        title={injury ? `Blessure du ${formatDateFrLong(injury.reported_at)}` : "Blessure"}
        subtitle={playerName}
        size="lg"
        loading={loading}
        cancelLabel="Fermer"
        footer={
          mode === "readonly" ? undefined : injury ? (
            <InjuryDetailFooter
              injury={injury}
              onClose={handleClose}
              onComplete={() => setCompleteOpen(true)}
              onFollowUp={() => setFollowUpOpen(true)}
              onReturn={() => setReturnOpen(true)}
              menuOpen={menuOpen}
              onToggleMenu={() => setMenuOpen((v) => !v)}
              onEditBilan={() => {
                setMenuOpen(false);
                setCompleteOpen(true);
              }}
            />
          ) : undefined
        }
      >
        {injuryQuery.isError ? (
          <EmptyState variant="error" message="Cet élément n'existe plus." />
        ) : injury ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <StatusBadge
                status={injuryStatusKey({ status: injury.status, doctor_completed: injury.doctor_completed_at !== null })}
              />
              <span className="text-sm text-text-muted">
                {injuryStatusLabel({ status: injury.status, doctor_completed: injury.doctor_completed_at !== null })}
              </span>
            </div>

            <section className="space-y-1">
              <h3 className="text-sm font-semibold text-text">Déclaration</h3>
              <p className="text-sm text-text">
                Déclarée par {injury.reported_by} le {formatDateFrLong(injury.reported_at)} à{" "}
                {formatTimeFr(injury.reported_at)}
              </p>
              <p className="text-sm text-text-muted">
                Survenue : {injuryEventLabel(injury)}
                {injury.occurred_minute != null ? `, ${injury.occurred_minute}ᵉ minute` : ""}
                {injury.occurred_time ? `, à ${injury.occurred_time.slice(0, 5)}` : ""}
              </p>
              {mode === "doctor" || mode === "readonly" ? (
                <p className="text-sm text-text">{injury.circumstances}</p>
              ) : null}
            </section>

            <section className="space-y-1 border-t border-border pt-3">
              <h3 className="text-sm font-semibold text-text">Bilan du Médecin</h3>
              {injury.doctor_completed_at ? (
                <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-text-muted">Localisation</dt>
                    <dd className="text-text">{injury.location_on_body || "Non renseigné"}</dd>
                  </div>
                  <div>
                    <dt className="text-text-muted">Gravité</dt>
                    <dd className="text-text">{SEVERITY_LABELS[injury.severity] ?? "Non renseigné"}</dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="text-text-muted">Soins donnés sur place</dt>
                    <dd className="text-text">{injury.on_site_care || "Non renseigné"}</dd>
                  </div>
                  <div>
                    <dt className="text-text-muted">Orientation</dt>
                    <dd className="text-text">{REFERRAL_LABELS[injury.referral] ?? "Non renseigné"}</dd>
                  </div>
                  <div>
                    <dt className="text-text-muted">Durée d'indisponibilité estimée</dt>
                    <dd className="text-text">
                      {injury.estimated_days_out != null ? `${injury.estimated_days_out} jours` : "Non renseigné"}
                    </dd>
                  </div>
                  <div className="sm:col-span-2">
                    <p className="text-xs text-text-muted">
                      Complété par {injury.doctor_completed_by} le {formatDateFrLong(injury.doctor_completed_at)}
                    </p>
                  </div>
                </dl>
              ) : (
                <p className="text-sm text-text-muted">Le Médecin n'a pas encore complété cette blessure.</p>
              )}
            </section>

            <section className="space-y-2 border-t border-border pt-3">
              <h3 className="text-sm font-semibold text-text">Suivi</h3>
              {injury.followups.length === 0 ? (
                <p className="text-sm text-text-muted">Aucune entrée de suivi pour l'instant.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {injury.followups.map((entry) => (
                    <li key={entry.id} className="py-2">
                      <p className="text-sm text-text-muted">{formatDateFrLong(entry.entry_date)}</p>
                      <p className="text-sm text-text">{entry.note}</p>
                      <p className="text-xs text-text-muted">{entry.created_by}</p>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {injury.status === "resolved" ? (
              <section className="border-t border-border pt-3">
                <p className="text-sm text-text">
                  Retour déclaré le {injury.resolved_at ? formatDateFrLong(injury.resolved_at) : ""} par{" "}
                  {injury.resolved_by}.
                </p>
              </section>
            ) : null}
          </div>
        ) : null}
      </Modal>

      {mode === "doctor" && injury ? (
        <>
          <InjuryCompleteModal
            open={completeOpen}
            injury={injury}
            playerName={playerName}
            consentMissing={consentMissing}
            onClose={() => setCompleteOpen(false)}
            onCompleted={handleChanged}
          />
          <InjuryFollowUpModal
            open={followUpOpen}
            injuryId={injury.id}
            injuryReportedDate={injury.reported_at.slice(0, 10)}
            onClose={() => setFollowUpOpen(false)}
            onAdded={handleChanged}
          />
          <InjuryReturnDialog
            open={returnOpen}
            injuryId={injury.id}
            playerFirstName={playerName}
            hasOtherOpenInjury={hasOtherOpenInjury}
            injuryReportedDate={injury.reported_at.slice(0, 10)}
            onClose={() => setReturnOpen(false)}
            onDeclared={handleChanged}
          />
        </>
      ) : null}
    </>
  );
}

const SEVERITY_LABELS: Record<string, string> = { mild: "Légère", moderate: "Modérée", severe: "Grave" };
const REFERRAL_LABELS: Record<string, string> = { rest: "Repos", consultation: "Consultation", hospital: "Hôpital" };

function InjuryDetailFooter({
  injury,
  onClose,
  onComplete,
  onFollowUp,
  onReturn,
  menuOpen,
  onToggleMenu,
  onEditBilan,
}: {
  injury: { status: "open" | "resolved"; doctor_completed_at: string | null };
  onClose: () => void;
  onComplete: () => void;
  onFollowUp: () => void;
  onReturn: () => void;
  menuOpen: boolean;
  onToggleMenu: () => void;
  onEditBilan: () => void;
}) {
  const toComplete = injury.status === "open" && injury.doctor_completed_at === null;
  const inProgress = injury.status === "open" && injury.doctor_completed_at !== null;

  return (
    <div className="flex w-full flex-wrap items-center justify-end gap-2">
      <button
        type="button"
        onClick={onClose}
        className="h-control-md rounded-sm border border-border-strong bg-surface px-4 text-sm font-medium text-text hover:bg-surface-muted"
      >
        Fermer
      </button>
      {toComplete ? (
        <button
          type="button"
          onClick={onComplete}
          className="h-control-md rounded-sm bg-primary px-4 text-sm font-medium text-on-primary"
        >
          Compléter
        </button>
      ) : null}
      {inProgress ? (
        <>
          <div className="relative">
            <button
              type="button"
              onClick={onToggleMenu}
              className="h-control-md rounded-sm border border-border-strong bg-surface px-3 text-sm font-medium text-text hover:bg-surface-muted"
              aria-label="Autres actions"
            >
              …
            </button>
            {menuOpen ? (
              <div className="absolute bottom-full right-0 mb-1 w-48 rounded-md border border-border bg-surface py-1 shadow-elevated">
                <button
                  type="button"
                  onClick={onEditBilan}
                  className="flex w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                >
                  Modifier le bilan
                </button>
              </div>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onReturn}
            className="h-control-md rounded-sm border border-border-strong bg-surface px-4 text-sm font-medium text-text hover:bg-surface-muted"
          >
            Déclarer le retour
          </button>
          <button
            type="button"
            onClick={onFollowUp}
            className="h-control-md rounded-sm bg-primary px-4 text-sm font-medium text-on-primary"
          >
            Ajouter un suivi
          </button>
        </>
      ) : null}
      {injury.status === "resolved" ? (
        <div className="relative">
          <button
            type="button"
            onClick={onToggleMenu}
            className="h-control-md rounded-sm border border-border-strong bg-surface px-3 text-sm font-medium text-text hover:bg-surface-muted"
            aria-label="Autres actions"
          >
            …
          </button>
          {menuOpen ? (
            <div className="absolute bottom-full right-0 mb-1 w-48 rounded-md border border-border bg-surface py-1 shadow-elevated">
              <button
                type="button"
                onClick={onEditBilan}
                className="flex w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
              >
                Modifier le bilan
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
