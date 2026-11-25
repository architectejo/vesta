import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { listLicenceEvents } from "../../api/licences";
import type { Licence } from "../../api/licences";
import { Button, EmptyState, IconButton, IconMore, Loader, Modal, StatusBadge, Tabs } from "../../design-system";
import type { StatusKey } from "../../design-system";
import { useClosingState } from "../../hooks/useClosingState";
import { LicenceFormModal } from "./LicenceFormModal";
import { StartSupportSessionModal } from "./StartSupportSessionModal";
import { SuspendTerminateModal } from "./SuspendTerminateModal";

const LICENCE_STATUS_KEY: Record<Licence["status"], StatusKey> = {
  trial: "licence_trial",
  active: "licence_active",
  expired: "licence_expired_grace",
  suspended: "licence_suspended",
  terminated: "licence_terminated",
};

type Tab = "informations" | "licence" | "historique";

/**
 * Modale « Club » (superuser-espace.md §4.1).
 *
 * Point ouvert signalé au compte rendu : l'onglet « Informations » ne
 * porte que le nom du club (`LicenceSerializer.club_name`) — ville, pays,
 * devise, Président, nombre de joueurs et dernière activité ne sont
 * fournis par aucun endpoint accessible au Superuser (`ClubIdentityView`
 * exige une adhésion active, qu'un Superuser n'a structurellement jamais,
 * CLAUDE.md règle n°1). Idem pour les colonnes « Joueurs » et « Dernière
 * activité » du tableau (`superuser-espace.md` §3.2), absentes de
 * `LicenceSerializer` : non affichées plutôt qu'inventées.
 */
export function ClubDetailModal({ licence, onClose, onChanged }: { licence: Licence; onClose: () => void; onChanged: () => void }) {
  const [tab, setTab] = useState<Tab>("informations");
  const [menuOpen, setMenuOpen] = useState(false);
  const { mounted: menuMounted, dataState: menuDataState, onAnimationEnd: onMenuAnimationEnd } =
    useClosingState(menuOpen, 200);
  const [formModal, setFormModal] = useState<"activate" | "extend" | null>(null);
  const [suspendTerminate, setSuspendTerminate] = useState<"suspend" | "terminate" | null>(null);
  const [supportOpen, setSupportOpen] = useState(false);

  const eventsQuery = useQuery({
    queryKey: ["licence-events", licence.id],
    queryFn: () => listLicenceEvents(licence.id),
    enabled: tab === "historique",
  });

  const primaryAction: { label: string; mode: "activate" | "extend" } | null =
    licence.status === "active" || licence.status === "expired"
      ? { label: "Prolonger", mode: "extend" }
      : licence.status === "trial" || licence.status === "suspended"
        ? { label: "Activer", mode: "activate" }
        : null;

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title="Club"
        subtitle={licence.club_name}
        size="lg"
        footer={
          <div className="flex w-full items-center justify-between gap-2">
            <div className="relative">
              <IconButton
                aria-label="Ouvrir le menu"
                onClick={() => setMenuOpen((v) => !v)}
                icon={<IconMore aria-hidden="true" className="h-5 w-5" />}
              />
              {menuMounted ? (
                <div
                  data-state={menuDataState}
                  onAnimationEnd={onMenuAnimationEnd}
                  className="vesta-anim-menu vesta-anim-menu--bottom-left absolute bottom-full left-0 mb-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated"
                >
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      setSuspendTerminate("suspend");
                    }}
                    className="flex w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                  >
                    Suspendre
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      setSuspendTerminate("terminate");
                    }}
                    className="flex w-full px-3 py-2 text-left text-sm text-status-danger-fg hover:bg-surface-muted"
                  >
                    Résilier
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      setSupportOpen(true);
                    }}
                    className="flex w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                  >
                    Intervenir sur ce club
                  </button>
                </div>
              ) : null}
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={onClose}>
                Fermer
              </Button>
              {primaryAction ? (
                <Button variant="primary" onClick={() => setFormModal(primaryAction.mode)}>
                  {primaryAction.label}
                </Button>
              ) : null}
            </div>
          </div>
        }
      >
        <div className="space-y-4">
          <Tabs
            label="Club"
            value={tab}
            onChange={setTab}
            items={[
              { value: "informations", label: "Informations" },
              { value: "licence", label: "Licence" },
              { value: "historique", label: "Historique de licence" },
            ]}
          />

          {tab === "informations" ? (
            <p className="text-sm text-text">{licence.club_name}</p>
          ) : null}

          {tab === "licence" ? (
            <div className="space-y-2 text-sm text-text">
              <p>Début : {licence.start_date}</p>
              <p>Fin : {licence.end_date}</p>
              <p>
                Statut :{" "}
                <StatusBadge status={LICENCE_STATUS_KEY[licence.status]} detail={licence.status_label} />
              </p>
            </div>
          ) : null}

          {tab === "historique" ? (
            eventsQuery.isLoading ? (
              <Loader loading variant="list" count={3} />
            ) : eventsQuery.isError ? (
              <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void eventsQuery.refetch()} />
            ) : !eventsQuery.data || eventsQuery.data.length === 0 ? (
              <EmptyState message="Aucun historique pour cette licence." />
            ) : (
              <ul className="space-y-2">
                {eventsQuery.data.map((event) => (
                  <li key={event.id} className="border-b border-border pb-2 text-sm">
                    <p className="text-text">{event.event_type_label}</p>
                    <p className="text-xs text-text-muted">
                      {new Date(event.event_date).toLocaleString("fr-FR")}
                      {event.note ? ` · ${event.note}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            )
          ) : null}
        </div>
      </Modal>

      {formModal ? (
        <LicenceFormModal
          licence={licence}
          mode={formModal}
          onClose={() => setFormModal(null)}
          onSaved={() => {
            setFormModal(null);
            onChanged();
          }}
        />
      ) : null}
      {suspendTerminate ? (
        <SuspendTerminateModal
          licence={licence}
          mode={suspendTerminate}
          onClose={() => setSuspendTerminate(null)}
          onSaved={() => {
            setSuspendTerminate(null);
            onChanged();
          }}
        />
      ) : null}
      {supportOpen ? (
        <StartSupportSessionModal
          clubId={licence.club_id}
          clubName={licence.club_name}
          onClose={() => setSupportOpen(false)}
        />
      ) : null}
    </>
  );
}
