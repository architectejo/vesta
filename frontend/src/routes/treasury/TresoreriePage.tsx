import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getMyProfile } from "../../api/clubs";
import {
  archiveContributionType,
  createContributionType,
  getContributionTypes,
  getTreasuryCapabilities,
  updateContributionType,
  type ContributionType,
  type ContributionTypeInput,
} from "../../api/treasury";
import { Button, EmptyState, Loader, Modal, useToast } from "../../design-system";
import { useAuth } from "../../auth/AuthContext";
import { CashRegisterFlow } from "./CashRegisterModal";
import { ContributionTypeModal, contributionTypeError } from "./ContributionTypeModal";
import { describeContributionType } from "./contributionTypeLabels";
import { RecordPaymentModal } from "./RecordPaymentModal";
import { getTreasuryAccess } from "./treasuryAccess";

const TYPES_QUERY_KEY = ["treasury", "contribution-types"] as const;
const CAPABILITIES_QUERY_KEY = ["treasury", "capabilities"] as const;

interface ContributionTypeRowProps {
  type: ContributionType;
  canWrite: boolean;
  onOpen: (type: ContributionType) => void;
  onArchive: (type: ContributionType) => void;
}

function ContributionTypeRow({ type, canWrite, onOpen, onArchive }: ContributionTypeRowProps) {
  return (
    <article className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
      <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpen(type)}>
        <p className="font-medium text-text">{type.name}</p>
        <p className="text-sm text-text-muted">{describeContributionType(type)}</p>
      </button>
      {canWrite ? (
        <Button size="sm" variant="ghost" onClick={() => onArchive(type)}>
          Archiver
        </Button>
      ) : null}
    </article>
  );
}

interface ContributionTypesCardProps {
  types: ContributionType[];
  canWrite: boolean;
  onCreate: () => void;
  onOpen: (type: ContributionType) => void;
  onArchive: (type: ContributionType) => void;
}

function ContributionTypesCard({ types, canWrite, onCreate, onOpen, onArchive }: ContributionTypesCardProps) {
  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-text">Types de cotisation</h2>
        <span className="text-sm text-text-muted">
          {types.length} actif{types.length > 1 ? "s" : ""}
        </span>
      </div>
      {types.length === 0 ? (
        <EmptyState
          message="Aucun type de cotisation."
          description="Créez-en un pour commencer."
          actionLabel={canWrite ? "Nouveau type" : undefined}
          onAction={canWrite ? onCreate : undefined}
        />
      ) : (
        <div className="divide-y divide-border">
          {types.map((type) => (
            <ContributionTypeRow
              key={type.id}
              type={type}
              canWrite={canWrite}
              onOpen={onOpen}
              onArchive={onArchive}
            />
          ))}
        </div>
      )}
    </section>
  );
}

/**
 * Écran « Trésorerie » : types de cotisation (cahier des charges 4.4.1).
 * L'accès (lecture, écriture) est déterminé par `treasuryAccess.ts`
 * (temporaire, en attendant des capacités renvoyées par l'API).
 */
export function TresoreriePage() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [selected, setSelected] = useState<ContributionType>();
  const [showForm, setShowForm] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState<ContributionType>();
  const [showRecordPayment, setShowRecordPayment] = useState(false);
  const [showCashRegister, setShowCashRegister] = useState(false);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const { canRead, canWrite } = getTreasuryAccess(profileQuery.data?.roles);
  const typesQuery = useQuery({
    queryKey: TYPES_QUERY_KEY,
    queryFn: () => getContributionTypes(),
    enabled: canRead,
  });
  // Capacités calculées côté API (backend/apps/treasury/views.py
  // `TreasuryCapabilitiesView`) : gouvernent « Enregistrer un paiement » et
  // « Caisse Terrain Express », réservées au Trésorier et à l'adjoint
  // (matrice 2.4), sans dupliquer cette règle côté interface.
  const capabilitiesQuery = useQuery({
    queryKey: CAPABILITIES_QUERY_KEY,
    queryFn: () => getTreasuryCapabilities(),
    enabled: canRead,
  });
  const currency = capabilitiesQuery.data?.currency ?? "";
  const canRecordPayments = capabilitiesQuery.data?.capabilities.can_record_payments ?? false;

  const saveMutation = useMutation({
    mutationFn: (input: ContributionTypeInput) =>
      selected ? updateContributionType(selected.id, input) : createContributionType(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: TYPES_QUERY_KEY });
      setShowForm(false);
      setSelected(undefined);
      showToast("Type de cotisation enregistré.");
    },
  });
  const archiveMutation = useMutation({
    mutationFn: (type: ContributionType) => archiveContributionType(type.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: TYPES_QUERY_KEY });
      setConfirmArchive(undefined);
      showToast("Type de cotisation archivé.");
    },
  });

  function openForm(type?: ContributionType): void {
    saveMutation.reset();
    setSelected(type);
    setShowForm(true);
  }

  function closeForm(): void {
    setShowForm(false);
    setSelected(undefined);
  }

  function askArchive(type: ContributionType): void {
    archiveMutation.reset();
    setConfirmArchive(type);
  }

  // L'accès n'est décidé qu'une fois le profil connu : jamais de message
  // « accès refusé » pendant le chargement (règle 17).
  if (profileQuery.isLoading) return <Loader loading variant="page" />;
  if (profileQuery.isError) {
    return <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void profileQuery.refetch()} />;
  }
  if (!canRead) return <EmptyState message="Vous n'avez pas accès à la trésorerie." />;
  if (typesQuery.isLoading) return <Loader loading variant="page" />;
  if (typesQuery.isError) {
    return <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void typesQuery.refetch()} />;
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">Trésorerie</h1>
          <p className="text-sm text-text-muted">{auth.club?.name ?? ""}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canRecordPayments ? (
            <>
              <Button variant="primary" size="sm" onClick={() => setShowRecordPayment(true)}>
                Enregistrer un paiement
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setShowCashRegister(true)}>
                Caisse Terrain Express
              </Button>
            </>
          ) : null}
          {canWrite ? (
            // Une seule action « primary » par zone (docs/lot0/design-system.md
            // §3.1) : secondaire dès que « Enregistrer un paiement » l'est déjà.
            <Button variant={canRecordPayments ? "secondary" : "primary"} size="sm" onClick={() => openForm()}>
              Nouveau type
            </Button>
          ) : null}
        </div>
      </header>

      <ContributionTypesCard
        types={typesQuery.data ?? []}
        canWrite={canWrite}
        onCreate={() => openForm()}
        onOpen={openForm}
        onArchive={askArchive}
      />

      {showForm ? (
        <ContributionTypeModal
          key={selected?.id ?? "new"}
          open
          type={selected}
          canEdit={canWrite}
          isSubmitting={saveMutation.isPending}
          submitError={saveMutation.isError ? contributionTypeError(saveMutation.error) : undefined}
          onClose={closeForm}
          onSubmit={(input) => saveMutation.mutate(input)}
        />
      ) : null}

      <Modal
        open={Boolean(confirmArchive)}
        onClose={() => setConfirmArchive(undefined)}
        title="Archiver ce type ?"
        size="sm"
        confirmLabel="Archiver"
        confirmVariant="danger"
        isSubmitting={archiveMutation.isPending}
        onConfirm={() => confirmArchive && archiveMutation.mutate(confirmArchive)}
      >
        <p className="text-sm text-text">Il ne sera plus proposé pour de nouveaux paiements.</p>
        {archiveMutation.isError ? (
          <p role="alert" className="mt-3 text-sm text-status-danger-fg">
            {contributionTypeError(archiveMutation.error)}
          </p>
        ) : null}
      </Modal>

      {showRecordPayment ? (
        <RecordPaymentModal
          open
          currency={currency}
          onClose={() => setShowRecordPayment(false)}
          onRecorded={() => void queryClient.invalidateQueries({ queryKey: TYPES_QUERY_KEY })}
        />
      ) : null}

      <CashRegisterFlow
        open={showCashRegister}
        currency={currency}
        onClose={() => setShowCashRegister(false)}
      />
    </div>
  );
}
