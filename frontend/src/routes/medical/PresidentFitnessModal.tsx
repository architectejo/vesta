import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { getHealthRecord, type FitnessStatus, type HealthRecordFull } from "../../api/medical";
import { Banner, Button, EmptyState, Modal, StatusBadge, Tabs } from "../../design-system";
import { InjuryDetailModal } from "./InjuryDetailModal";
import { formatDateFrLong } from "./medicalFormat";
import { fitnessReturnText, fitnessStatusKey, injuryStatusKey } from "./medicalLabels";

const POLL_INTERVAL_MS = 30_000;

export interface PresidentFitnessModalProps {
  open: boolean;
  membershipId: number;
  playerName: string;
  fitnessStatus: FitnessStatus;
  fitnessReturnDate: string | null;
  fitnessReturnDateLabel?: string | null;
  onClose: () => void;
}

type ConsultState = "idle" | "loading" | "denied" | "granted";

/**
 * « Aptitude de {nom} » (medical.md §4.6), Président. Le corps ne révèle
 * jamais pourquoi le dossier complet n'est pas partagé (jamais accordé,
 * révoqué ou accordé à un Président précédent : même texte). Voir le
 * compte rendu de la tâche : faute d'un point d'accès dédié à l'état du
 * consentement pour un joueur donné (seul `GET .../health-record/`
 * existe, qui journalise déjà chaque succès), cette modale ne peut
 * afficher le texte « état actuel » qu'APRÈS une tentative explicite —
 * `getHealthRecord` n'est jamais appelé avant que le Président clique
 * lui-même sur « Consulter le dossier complet », pour ne jamais
 * journaliser une consultation qui n'a pas eu lieu.
 */
export function PresidentFitnessModal({
  open,
  membershipId,
  playerName,
  fitnessStatus,
  fitnessReturnDate,
  fitnessReturnDateLabel,
  onClose,
}: PresidentFitnessModalProps) {
  const [state, setState] = useState<ConsultState>("idle");
  const [record, setRecord] = useState<HealthRecordFull | null>(null);
  const [dossierOpen, setDossierOpen] = useState(false);
  const [tab, setTab] = useState<"aptitude" | "fiche" | "historique">("aptitude");
  const [injuryId, setInjuryId] = useState<number | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    if (!open) {
      setState("idle");
      setRecord(null);
      setDossierOpen(false);
      setTab("aptitude");
    }
  }, [open]);

  function stopPolling(): void {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function revalidate(): Promise<void> {
    try {
      const fresh = await getHealthRecord(membershipId);
      setRecord(fresh);
    } catch {
      stopPolling();
      setDossierOpen(false);
      setState("denied");
      setRecord(null);
    }
  }

  async function handleConsult(): Promise<void> {
    setState("loading");
    try {
      const fresh = await getHealthRecord(membershipId);
      setRecord(fresh);
      setState("granted");
      setDossierOpen(true);
      stopPolling();
      pollRef.current = window.setInterval(() => void revalidate(), POLL_INTERVAL_MS);
    } catch (error) {
      setState("denied");
      if (!(error instanceof ApiError && error.status === 403)) {
        // Erreur inattendue (réseau, 5xx) : reste sur l'état neutre plutôt
        // que d'affirmer « non partagé » à tort.
        setState("idle");
      }
    }
  }

  useEffect(() => {
    function handleVisibility(): void {
      if (document.visibilityState === "visible" && dossierOpen) void revalidate();
    }
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dossierOpen]);

  function handleClose(): void {
    stopPolling();
    setDossierOpen(false);
    onClose();
  }

  if (dossierOpen) {
    return (
      <>
        <Modal
          open={open}
          onClose={handleClose}
          title={`Dossier médical de ${playerName}`}
          size="lg"
          level={2}
          cancelLabel="Fermer"
        >
          {record ? (
            <div className="space-y-4">
              <Banner variant="info">Consultation enregistrée dans le journal du club.</Banner>
              <Tabs
                items={[
                  { value: "aptitude", label: "Aptitude" },
                  { value: "fiche", label: "Fiche" },
                  { value: "historique", label: "Historique" },
                ]}
                value={tab}
                onChange={setTab}
                label="Dossier médical"
              />
              {tab === "aptitude" ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={fitnessStatusKey(record.fitness_status)} />
                    <span className="text-sm text-text">
                      {fitnessReturnText({
                        fitness_status: record.fitness_status,
                        fitness_return_date: record.fitness_return_date,
                      })}
                    </span>
                  </div>
                  <div>
                    <h3 className="mb-1 text-sm font-semibold text-text">Blessures en cours</h3>
                    {record.open_injuries.length === 0 ? (
                      <p className="text-sm text-text-muted">Aucune blessure en cours.</p>
                    ) : (
                      <ul className="divide-y divide-border">
                        {record.open_injuries.map((item) => (
                          <li key={item.id}>
                            <button
                              type="button"
                              onClick={() => setInjuryId(item.id)}
                              className="flex w-full items-center justify-between gap-2 py-2 text-left"
                            >
                              <span className="text-sm text-text">{formatDateFrLong(item.reported_at)}</span>
                              <StatusBadge status={injuryStatusKey(item)} />
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              ) : null}
              {tab === "fiche" ? (
                <dl className="divide-y divide-border text-sm">
                  <div className="py-2">
                    <dt className="text-text-muted">Groupe sanguin</dt>
                    <dd className="mt-1 text-text">{record.blood_group || "Non renseigné"}</dd>
                  </div>
                  <div className="py-2">
                    <dt className="text-text-muted">Allergies</dt>
                    <dd className="mt-1 text-text">{record.allergies || "Non renseigné"}</dd>
                  </div>
                  <div className="py-2">
                    <dt className="text-text-muted">Antécédents</dt>
                    <dd className="mt-1 text-text">{record.medical_history || "Non renseigné"}</dd>
                  </div>
                  <div className="py-2">
                    <dt className="text-text-muted">Traitements en cours</dt>
                    <dd className="mt-1 text-text">{record.ongoing_treatments || "Non renseigné"}</dd>
                  </div>
                  <div className="py-2">
                    <dt className="text-text-muted">Contact d'urgence</dt>
                    <dd className="mt-1 text-text">
                      {record.emergency_contact_name || "Non renseigné"}
                      {record.emergency_contact_phone ? ` · ${record.emergency_contact_phone}` : ""}
                    </dd>
                  </div>
                  <div className="py-2">
                    <dt className="text-text-muted">Déclaration du joueur</dt>
                    <dd className="mt-1 whitespace-pre-wrap text-text">
                      {record.self_declaration || "Le joueur n'a pas encore rempli sa déclaration."}
                    </dd>
                  </div>
                </dl>
              ) : null}
              {tab === "historique" ? (
                record.resolved_injuries.length === 0 ? (
                  <p className="text-sm text-text-muted">Aucune blessure passée.</p>
                ) : (
                  <ul className="divide-y divide-border">
                    {record.resolved_injuries.map((item) => (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => setInjuryId(item.id)}
                          className="flex w-full items-center justify-between gap-2 py-2 text-left"
                        >
                          <span className="text-sm text-text">
                            {formatDateFrLong(item.reported_at)} ·{" "}
                            {item.location_on_body || "Localisation non renseignée"}
                          </span>
                          <StatusBadge status={injuryStatusKey(item)} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )
              ) : null}
            </div>
          ) : (
            <EmptyState variant="error" message="Ce dossier n'est plus accessible." actionLabel="Fermer" onAction={handleClose} />
          )}
        </Modal>
        {injuryId !== null ? (
          <InjuryDetailModal
            open
            injuryId={injuryId}
            mode="readonly"
            playerName={playerName}
            onClose={() => setInjuryId(null)}
            onChanged={() => void revalidate()}
          />
        ) : null}
      </>
    );
  }

  return (
    <Modal open={open} onClose={handleClose} title={`Aptitude de ${playerName}`} size="sm" cancelLabel="Fermer">
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <StatusBadge status={fitnessStatusKey(fitnessStatus)} />
          <span className="text-sm text-text">
            {fitnessReturnText({
              fitness_status: fitnessStatus,
              fitness_return_date: fitnessReturnDate,
              fitness_return_date_label: fitnessReturnDateLabel,
            })}
          </span>
        </div>

        <div className="rounded-md border border-border p-3">
          <p className="text-sm font-semibold text-text">Dossier médical complet</p>
          {state === "denied" ? (
            <p className="mt-1 text-sm text-text-muted">
              {playerName} n'a pas partagé son dossier médical complet avec le Président. Vous voyez seulement son
              aptitude et sa date de retour prévue.
            </p>
          ) : (
            <>
              <p className="mt-1 text-sm text-text-muted">
                Si {playerName} vous en a donné l'accès, vous pouvez consulter son dossier médical complet.
              </p>
              <Button
                size="sm"
                variant="primary"
                className="mt-2"
                loading={state === "loading"}
                onClick={() => void handleConsult()}
              >
                Consulter le dossier complet
              </Button>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
