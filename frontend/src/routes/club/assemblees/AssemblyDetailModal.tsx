import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { downloadMinutesPdf, getAssembly, signMinutes, type Assembly } from "../../../api/assemblies";
import { Banner, Button, EmptyState, Modal, PinPrompt, StatusBadge, Tabs } from "../../../design-system";
import { AttachmentLink } from "../../treasury/AttachmentLink";
import { formatPinError } from "../../treasury/pinErrors";
import { assemblyCardStatus, assemblyTypeLabel, formatDateLong, formatTimeShort } from "./assembliesFormat";
import { AttendanceTab } from "./AttendanceTab";
import { DecisionModal } from "./DecisionModal";
import { MinutesEditModal } from "./MinutesEditModal";

type TabKey = "agenda" | "attendance" | "decisions" | "minutes";

const CARD_STATUS_KEY = {
  convened: "ag_convened",
  cancelled: "cancelled",
  pv_to_sign: "ag_pv_to_sign",
  closed: "ag_closed",
} as const;

function AgendaTab({ assembly }: { assembly: Assembly }) {
  if (assembly.agenda_items.length === 0) {
    return <EmptyState message="Aucun point à l'ordre du jour." />;
  }
  return (
    <ol className="list-decimal space-y-3 pl-5">
      {assembly.agenda_items.map((item) => (
        <li key={item.id}>
          <p className="text-sm font-semibold text-text">{item.title}</p>
          {item.description ? <p className="mt-0.5 text-sm text-text-muted">{item.description}</p> : null}
        </li>
      ))}
    </ol>
  );
}

function DecisionsTab({
  assembly,
  onEditItem,
}: {
  assembly: Assembly;
  onEditItem: (agendaItemId: number) => void;
}) {
  if (assembly.agenda_items.length === 0) {
    return <EmptyState message="Aucune décision saisie." />;
  }
  return (
    <div className="space-y-3">
      {!assembly.quorum.reached ? (
        <Banner variant="warning">
          Quorum non atteint : {assembly.quorum.present} présents sur {assembly.quorum.total} (
          {assembly.quorum.percentage} %), seuil {assembly.quorum.threshold} %.
        </Banner>
      ) : null}
      {assembly.agenda_items.map((item) => {
        const decision = assembly.decisions.find((d) => d.agenda_item_id === item.id);
        return (
          <div key={item.id} className="rounded-md border border-border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold text-text">{item.title}</p>
              {assembly.can_manage ? (
                <Button size="sm" variant="secondary" onClick={() => onEditItem(item.id)}>
                  Saisir le vote
                </Button>
              ) : null}
            </div>
            {decision ? (
              <>
                <p className="mt-1 text-sm text-text">
                  Pour {decision.votes_for} · Contre {decision.votes_against} · Abstention {decision.votes_abstain}
                </p>
                <p className="mt-1 text-sm text-text-muted">{decision.outcome}</p>
              </>
            ) : (
              <p className="mt-1 text-sm text-text-muted">Aucune décision saisie.</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function MinutesTab({
  assembly,
  onEditMinutes,
  onOpenSign,
}: {
  assembly: Assembly;
  onEditMinutes: () => void;
  onOpenSign: () => void;
}) {
  const minutes = assembly.minutes;
  if (!minutes) {
    return (
      <div className="space-y-3">
        <EmptyState message="Le procès-verbal n'est pas encore rédigé." />
        {assembly.can_manage ? (
          <Button variant="primary" size="sm" onClick={onEditMinutes}>
            Rédiger le PV
          </Button>
        ) : null}
      </div>
    );
  }

  const canSign = assembly.can_sign_president || assembly.can_sign_vice_president;
  const canEdit = assembly.can_manage && !minutes.president_signed_at && !minutes.vp_signed_at;

  return (
    <div className="space-y-3">
      <p className="whitespace-pre-wrap text-base text-text">{minutes.content}</p>

      <div className="rounded-md border border-border p-3 text-sm">
        <p className="text-text">
          Président : {minutes.president_signed_by_name || "—"}
          {minutes.president_signed_at ? ` — signé le ${formatDateLong(minutes.president_signed_at.slice(0, 10))}` : " — en attente"}
        </p>
        {minutes.vp_vacant_at_signature ? (
          <p className="mt-1 flex items-center gap-2 text-text">
            Vice-président : <StatusBadge status="vacant" />
          </p>
        ) : (
          <p className="mt-1 text-text">
            Vice-président : {minutes.vp_signed_by_name || "—"}
            {minutes.vp_signed_at ? ` — signé le ${formatDateLong(minutes.vp_signed_at.slice(0, 10))}` : " — en attente"}
          </p>
        )}
      </div>

      {minutes.vp_vacant_at_signature ? (
        <p className="text-xs text-text-muted">
          Le poste de Vice-président étant vacant à la date de la signature, le procès-verbal est signé par le
          Président seul.
        </p>
      ) : null}

      {minutes.president_signed_at || minutes.vp_signed_at ? (
        <p className="text-xs text-text-muted">Le PV ne peut plus être modifié après une signature.</p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {canEdit ? (
          <Button variant="secondary" size="sm" onClick={onEditMinutes}>
            Modifier le PV
          </Button>
        ) : null}
        {canSign ? (
          <Button variant="primary" size="sm" onClick={onOpenSign}>
            Signer le PV
          </Button>
        ) : null}
        {minutes.is_complete ? (
          minutes.generated_at ? (
            <AttachmentLink label="Télécharger le PV (PDF)" download={() => downloadMinutesPdf(assembly.id)} />
          ) : (
            <Button variant="secondary" size="sm" loading loadingLabel="Génération…">
              Télécharger le PV (PDF)
            </Button>
          )
        ) : null}
      </div>
    </div>
  );
}

/** Modale « Assemblée générale » (détail, à onglets) — assemblees-page-ag.md §4.2. */
export function AssemblyDetailModal({
  assemblyId,
  onClose,
}: {
  assemblyId: number;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<TabKey>("agenda");
  const [decisionAgendaItemId, setDecisionAgendaItemId] = useState<number | null>(null);
  const [minutesEditOpen, setMinutesEditOpen] = useState(false);
  const [signOpen, setSignOpen] = useState(false);
  const [signError, setSignError] = useState<string | undefined>(undefined);
  const [signing, setSigning] = useState(false);

  const query = useQuery({ queryKey: ["assembly", assemblyId], queryFn: () => getAssembly(assemblyId) });
  const assembly = query.data;

  function invalidate(): void {
    void queryClient.invalidateQueries({ queryKey: ["assembly", assemblyId] });
    void queryClient.invalidateQueries({ queryKey: ["assemblies"] });
  }

  async function handleSign(pin: string): Promise<void> {
    setSignError(undefined);
    setSigning(true);
    try {
      const minutes = await signMinutes(assemblyId, pin);
      invalidate();
      setSignOpen(false);
      // Toast succès géré au niveau page pour rester simple ici.
      void minutes;
    } catch (err) {
      setSignError(formatPinError(err));
    } finally {
      setSigning(false);
    }
  }

  const status = assembly ? assemblyCardStatus(assembly) : null;

  return (
    <Modal
      open
      onClose={onClose}
      title={assembly ? `AG ${assemblyTypeLabel(assembly.assembly_type).toLowerCase()} du ${formatDateLong(assembly.scheduled_date)}` : "Assemblée générale"}
      subtitle={assembly ? `${formatTimeShort(assembly.scheduled_time)} · ${assembly.location}` : undefined}
      size="lg"
      loading={query.isLoading}
      cancelLabel="Fermer"
      hideFooter
    >
      {query.isError ? (
        <EmptyState variant="error" message="Impossible de charger l'assemblée." actionLabel="Réessayer" onAction={() => void query.refetch()} />
      ) : assembly ? (
        <div className="space-y-4">
          <div>{status ? <StatusBadge status={CARD_STATUS_KEY[status]} /> : null}</div>
          <Tabs
            label="Assemblée générale"
            value={tab}
            onChange={setTab}
            items={[
              { value: "agenda", label: "Ordre du jour" },
              { value: "attendance", label: "Présences" },
              { value: "decisions", label: "Décisions" },
              { value: "minutes", label: "Procès-verbal" },
            ]}
          />
          {tab === "agenda" ? <AgendaTab assembly={assembly} /> : null}
          {tab === "attendance" ? <AttendanceTab assembly={assembly} /> : null}
          {tab === "decisions" ? <DecisionsTab assembly={assembly} onEditItem={setDecisionAgendaItemId} /> : null}
          {tab === "minutes" ? (
            <MinutesTab assembly={assembly} onEditMinutes={() => setMinutesEditOpen(true)} onOpenSign={() => setSignOpen(true)} />
          ) : null}
        </div>
      ) : null}

      {assembly && decisionAgendaItemId !== null ? (
        <DecisionModal
          assembly={assembly}
          agendaItemId={decisionAgendaItemId}
          existing={assembly.decisions.find((d) => d.agenda_item_id === decisionAgendaItemId)}
          presentCount={assembly.quorum.present}
          onClose={() => setDecisionAgendaItemId(null)}
          onSaved={() => {
            setDecisionAgendaItemId(null);
            invalidate();
          }}
        />
      ) : null}

      {assembly && minutesEditOpen ? (
        <MinutesEditModal
          assembly={assembly}
          onClose={() => setMinutesEditOpen(false)}
          onSaved={() => {
            setMinutesEditOpen(false);
            invalidate();
          }}
        />
      ) : null}

      {assembly ? (
        <PinPrompt
          open={signOpen}
          title="Confirmer avec votre code PIN"
          description={`Signer le procès-verbal de l'AG du ${formatDateLong(assembly.scheduled_date)}`}
          isSubmitting={signing}
          error={signError}
          onSubmit={(pin) => void handleSign(pin)}
          onClose={() => setSignOpen(false)}
        />
      ) : null}
    </Modal>
  );
}
