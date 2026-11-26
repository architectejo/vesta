import { useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getHealthRecord } from "../../api/medical";
import { Banner, EmptyState, Modal, StatusBadge, Tabs } from "../../design-system";
import { FitnessUpdateModal } from "./FitnessUpdateModal";
import { HealthRecordEditModal } from "./HealthRecordEditModal";
import { InjuryDetailModal } from "./InjuryDetailModal";
import { formatDateFrLong } from "./medicalFormat";
import { fitnessReturnText, fitnessStatusKey, injuryStatusKey } from "./medicalLabels";

export interface HealthRecordModalProps {
  open: boolean;
  membershipId: number;
  onClose: () => void;
  onChanged: () => void;
}

type TabKey = "aptitude" | "fiche" | "historique";

const TAB_ITEMS: Array<{ value: TabKey; label: string }> = [
  { value: "aptitude", label: "Aptitude" },
  { value: "fiche", label: "Fiche" },
  { value: "historique", label: "Historique" },
];

/**
 * « Fiche de santé » (medical.md §4.2), Médecin. Chaque ouverture est
 * journalisée côté API (`view_health_record_as_doctor`). Jamais mise en
 * cache (§5.4) : `gcTime: 0`, requête retirée à la fermeture.
 */
export function HealthRecordModal({ open, membershipId, onClose, onChanged }: HealthRecordModalProps) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<TabKey>("aptitude");
  const [fitnessOpen, setFitnessOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [injuryId, setInjuryId] = useState<number | null>(null);

  const queryKey = ["medical", "health-record", membershipId] as const;
  const recordQuery = useQuery({
    queryKey,
    queryFn: () => getHealthRecord(membershipId),
    enabled: open,
    gcTime: 0,
    staleTime: 0,
  });

  function handleClose(): void {
    void queryClient.removeQueries({ queryKey });
    setTab("aptitude");
    onClose();
  }

  function handleChanged(): void {
    void recordQuery.refetch();
    onChanged();
  }

  const record = recordQuery.data;
  const consentMissing = record ? record.consent_given_at == null : false;

  return (
    <>
      <Modal
        open={open}
        onClose={handleClose}
        title="Fiche de santé"
        subtitle={record ? `${record.name} · n° ${record.jersey_number ?? "—"}` : undefined}
        size="lg"
        loading={recordQuery.isLoading}
        cancelLabel="Fermer"
        confirmLabel={
          tab === "aptitude" ? "Modifier l'aptitude" : tab === "fiche" && !consentMissing ? "Modifier la fiche" : undefined
        }
        onConfirm={
          tab === "aptitude"
            ? () => setFitnessOpen(true)
            : tab === "fiche" && !consentMissing
              ? () => setEditOpen(true)
              : undefined
        }
      >
        {recordQuery.isError ? (
          <EmptyState variant="error" message="Impossible de charger la fiche." actionLabel="Réessayer" onAction={() => void recordQuery.refetch()} />
        ) : record ? (
          <div className="space-y-4">
            {consentMissing ? (
              <Banner variant="warning">
                {record.name.split(" ")[0]} n'a pas encore donné son consentement au traitement de ses données de
                santé. Vous pouvez fixer son aptitude et suivre ses blessures déclarées, mais pas compléter sa
                fiche. Il peut le donner depuis son profil.
              </Banner>
            ) : null}

            <Tabs items={TAB_ITEMS} value={tab} onChange={setTab} label="Fiche de santé" />

            {tab === "aptitude" ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <StatusBadge status={fitnessStatusKey(record.fitness_status)} />
                  <span className="text-sm text-text">
                    {fitnessReturnText({
                      fitness_status: record.fitness_status,
                      fitness_return_date: record.fitness_return_date,
                      showOverdue: true,
                    })}
                  </span>
                </div>
                {record.fitness_set_by && record.fitness_set_at ? (
                  <p className="text-xs text-text-muted">
                    Fixée par {record.fitness_set_by} le {formatDateFrLong(record.fitness_set_at)}
                  </p>
                ) : null}

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
                <FicheRow label="Groupe sanguin" value={record.blood_group || "Non renseigné"} />
                <FicheRow label="Allergies" value={record.allergies || "Non renseigné"} />
                <FicheRow label="Antécédents" value={record.medical_history || "Non renseigné"} />
                <FicheRow label="Traitements en cours" value={record.ongoing_treatments || "Non renseigné"} />
                <FicheRow
                  label="Contact d'urgence"
                  value={
                    record.emergency_contact_name || record.emergency_contact_phone ? (
                      <span>
                        {record.emergency_contact_name || "Non renseigné"}
                        {record.emergency_contact_phone ? (
                          <>
                            {" · "}
                            <a href={`tel:${record.emergency_contact_phone}`} className="-my-2 py-2 text-primary-text hover:underline">
                              {record.emergency_contact_phone}
                            </a>
                          </>
                        ) : null}
                      </span>
                    ) : (
                      "Non renseigné"
                    )
                  }
                />
                <div className="py-2">
                  <dt className="text-text-muted">Déclaration du joueur</dt>
                  <dd className="mt-1 whitespace-pre-wrap text-text">
                    {record.self_declaration || "Le joueur n'a pas encore rempli sa déclaration."}
                  </dd>
                  {record.self_declaration_updated_at ? (
                    <p className="mt-1 text-xs text-text-muted">
                      Mise à jour par le joueur le {formatDateFrLong(record.self_declaration_updated_at)}
                    </p>
                  ) : null}
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
                          {formatDateFrLong(item.reported_at)} · {item.location_on_body || "Localisation non renseignée"}
                        </span>
                        <StatusBadge status={injuryStatusKey(item)} />
                      </button>
                    </li>
                  ))}
                </ul>
              )
            ) : null}
          </div>
        ) : null}
      </Modal>

      {record ? (
        <>
          <FitnessUpdateModal
            open={fitnessOpen}
            membershipId={membershipId}
            playerFirstName={record.name}
            currentStatus={record.fitness_status}
            currentReturnDate={record.fitness_return_date}
            hasOpenInjury={record.open_injuries.length > 0}
            onClose={() => setFitnessOpen(false)}
            onUpdated={handleChanged}
          />
          <HealthRecordEditModal
            open={editOpen}
            record={record}
            onClose={() => setEditOpen(false)}
            onUpdated={handleChanged}
          />
        </>
      ) : null}

      {injuryId !== null ? (
        <InjuryDetailModal
          open
          injuryId={injuryId}
          mode="doctor"
          playerName={record?.name ?? ""}
          onClose={() => setInjuryId(null)}
          onChanged={handleChanged}
        />
      ) : null}
    </>
  );
}

function FicheRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="py-2">
      <dt className="text-text-muted">{label}</dt>
      <dd className="mt-1 text-text">{value}</dd>
    </div>
  );
}
