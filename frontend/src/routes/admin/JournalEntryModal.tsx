import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { getAuditLog } from "../../api/audit";
import type { AuditLogDetail } from "../../api/audit";
import { EmptyState, Modal } from "../../design-system";
import { actionLabel } from "./actionLabels";
import { formatInZone, formatUtc, formatValue } from "./journalFormat";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-text-muted">{label}</dt>
      <dd className="break-words text-sm text-text">{children}</dd>
    </div>
  );
}

function Snapshot({
  title,
  data,
  other,
}: {
  title: string;
  data: Record<string, unknown> | null;
  other: Record<string, unknown> | null;
}) {
  const keys = Object.keys(data ?? {});
  return (
    <section aria-label={title} className="rounded-md border border-border p-2">
      <h3 className="mb-1 text-sm font-semibold text-text">{title}</h3>
      {keys.length === 0 ? (
        <p className="text-sm text-text-muted">Aucune valeur.</p>
      ) : (
        <dl className="space-y-1">
          {keys.map((key) => {
            const changed = JSON.stringify((data ?? {})[key]) !== JSON.stringify((other ?? {})[key]);
            return (
              <div
                key={key}
                data-changed={changed || undefined}
                className={["rounded-sm px-1 text-sm", changed ? "bg-status-warning-bg" : ""].join(" ")}
              >
                <dt className="text-xs text-text-muted">{key}</dt>
                <dd className="break-words text-text">{formatValue((data ?? {})[key])}</dd>
              </div>
            );
          })}
        </dl>
      )}
    </section>
  );
}

/** Modale « Entrée du journal » (superuser-espace.md §4.6) : lecture seule. */
export function JournalEntryModal({ logId, onClose }: { logId: number; onClose: () => void }) {
  const query = useQuery({ queryKey: ["audit-log", logId], queryFn: () => getAuditLog(logId) });
  const entry: AuditLogDetail | undefined = query.data;

  return (
    <Modal open onClose={onClose} title="Entrée du journal" size="lg" loading={query.isLoading} cancelLabel="Fermer">
      {query.isError ? (
        <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void query.refetch()} />
      ) : entry ? (
        <div className="space-y-4">
          <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Field label="Horodatage">
              {formatInZone(entry.created_at, entry.club_timezone)}
              {entry.club_timezone ? ` (${entry.club_timezone})` : ""}
              <span className="block text-xs text-text-muted">{formatUtc(entry.created_at)}</span>
            </Field>
            <Field label="Club">{entry.club_name ?? "—"}</Field>
            <Field label="Acteur">
              {entry.actor_display}
              {entry.acted_as_ghost ? " (support)" : ""}
            </Field>
            {entry.support_session ? (
              <Field label="Session de support">Motif : {entry.support_session.reason}</Field>
            ) : null}
            <Field label="Type d'action">
              {actionLabel(entry.action_type)}
              {actionLabel(entry.action_type) !== entry.action_type ? (
                <span className="block text-xs text-text-muted">{entry.action_type}</span>
              ) : null}
            </Field>
            <Field label="Objet">
              {entry.object_type} #{entry.object_id}
            </Field>
            <Field label="Adresse IP">{entry.ip_address ?? "—"}</Field>
            <Field label="Navigateur">{entry.user_agent || "—"}</Field>
            <Field label="Appareil">{entry.device || "—"}</Field>
          </dl>
          {entry.medical_content_withheld ? (
            <p className="rounded-md bg-surface-muted p-2 text-sm text-text">
              Contenu médical non copié dans le journal.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Snapshot title="Avant" data={entry.before} other={entry.after} />
              <Snapshot title="Après" data={entry.after} other={entry.before} />
            </div>
          )}
        </div>
      ) : null}
    </Modal>
  );
}
