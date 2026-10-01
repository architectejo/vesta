import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getHealthRecord } from "../../api/medical";
import { EmptyState, Modal, StatusBadge, Tabs } from "../../design-system";
import { InjuryDetailModal } from "./InjuryDetailModal";
import { SelfDeclarationModal } from "./SelfDeclarationModal";
import { formatDateFrLong } from "./medicalFormat";
import { fitnessReturnText, fitnessStatusKey, injuryStatusKey } from "./medicalLabels";

export interface MyHealthRecordModalProps {
  open: boolean;
  membershipId: number;
  playerName: string;
  onClose: () => void;
}

type TabKey = "aptitude" | "fiche" | "historique";

const TAB_ITEMS: Array<{ value: TabKey; label: string }> = [
  { value: "aptitude", label: "Aptitude" },
  { value: "fiche", label: "Ma fiche" },
  { value: "historique", label: "Mes blessures" },
];

/**
 * « Ma fiche de santé » (medical.md §4.10), depuis « Mon profil ». Lecture
 * seule, sauf la déclaration du joueur. Chaque ouverture est journalisée
 * côté API (`view_health_record_as_player`). Jamais mise en cache (§5.4).
 */
export function MyHealthRecordModal({ open, membershipId, playerName, onClose }: MyHealthRecordModalProps) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<TabKey>("aptitude");
  const [declarationOpen, setDeclarationOpen] = useState(false);
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

  const record = recordQuery.data;
  const consentMissing = record ? record.consent_given_at == null : false;

  return (
    <>
      <Modal
        open={open}
        onClose={handleClose}
        title="Ma fiche de santé"
        size="lg"
        loading={recordQuery.isLoading}
        cancelLabel="Fermer"
        confirmLabel={tab === "fiche" ? "Mettre à jour ma déclaration" : undefined}
        onConfirm={tab === "fiche" ? () => setDeclarationOpen(true) : undefined}
      >
        {recordQuery.isError ? (
          <EmptyState variant="error" message="Impossible de charger votre fiche." actionLabel="Réessayer" onAction={() => void recordQuery.refetch()} />
        ) : record ? (
          <div className="space-y-4">
            <Tabs items={TAB_ITEMS} value={tab} onChange={setTab} label="Ma fiche de santé" />
            <p className="text-xs text-text-muted">
              Seuls le Médecin et vous voyez ces informations. Le Coach voit uniquement votre aptitude et votre date
              de retour prévue.
            </p>

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
                  <dt className="text-text-muted">Déclaration sur mon état de santé</dt>
                  <dd className="mt-1 whitespace-pre-wrap text-text">
                    {record.self_declaration || "Vous n'avez pas encore rempli votre déclaration."}
                  </dd>
                  {record.self_declaration_updated_at ? (
                    <p className="mt-1 text-xs text-text-muted">
                      Mise à jour le {formatDateFrLong(record.self_declaration_updated_at)}
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
        ) : null}
      </Modal>

      {record ? (
        <SelfDeclarationModal
          open={declarationOpen}
          currentDeclaration={record.self_declaration}
          consentMissing={consentMissing}
          onClose={() => setDeclarationOpen(false)}
          onUpdated={() => void recordQuery.refetch()}
        />
      ) : null}

      {injuryId !== null ? (
        <InjuryDetailModal
          open
          injuryId={injuryId}
          mode="readonly"
          playerName={playerName}
          onClose={() => setInjuryId(null)}
          onChanged={() => void recordQuery.refetch()}
        />
      ) : null}
    </>
  );
}
