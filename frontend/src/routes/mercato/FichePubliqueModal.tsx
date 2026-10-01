import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getPublicPlayer } from "../../api/mercato";
import { Avatar, Button, EmptyState, Modal, StatusBadge, Tabs } from "../../design-system";

export interface FichePubliqueModalProps {
  membershipId: number | null;
  /** Le joueur appartient à un autre club et le viewer peut agir (Pdt/DS). */
  canOffer: boolean;
  onClose: () => void;
  onMakeOffer: (membershipId: number) => void;
  onWriteToClub: (clubId: number) => void;
}

type TabKey = "apercu" | "stats" | "evaluations" | "presences" | "discipline" | "carriere";

const TABS: Array<{ value: TabKey; label: string }> = [
  { value: "apercu", label: "Aperçu" },
  { value: "stats", label: "Statistiques" },
  { value: "evaluations", label: "Évaluations" },
  { value: "presences", label: "Présences" },
  { value: "discipline", label: "Discipline" },
  { value: "carriere", label: "Carrière" },
];

/**
 * « Fiche publique » (fiche `mercato.md` §4.1). Seul l'onglet « Aperçu » est
 * câblé : `apps.mercato.serializers.serialize_public_player` ne renvoie
 * aujourd'hui que l'identité publique et la note moyenne (statistiques,
 * présences, discipline et carrière dépendent d'agrégations exposées
 * ailleurs par `apps.sport`, non branchées ici — point ouvert signalé au
 * compte rendu). **Pas d'onglet « Aptitude »** pour un joueur d'un autre
 * club (10.2 n° 16, point ouvert n° 1 de la fiche).
 */
export function FichePubliqueModal({ membershipId, canOffer, onClose, onMakeOffer, onWriteToClub }: FichePubliqueModalProps) {
  const open = membershipId !== null;
  const [tab, setTab] = useState<TabKey>("apercu");
  const [menuOpen, setMenuOpen] = useState(false);

  const query = useQuery({
    queryKey: ["mercato", "public-player", membershipId],
    queryFn: () => getPublicPlayer(membershipId as number),
    enabled: open,
  });
  const player = query.data;

  return (
    <Modal
      open={open}
      onClose={() => {
        setTab("apercu");
        onClose();
      }}
      title={player ? `${player.first_name} ${player.last_name}` : "Fiche publique"}
      subtitle={player ? `${player.position_label} · ${player.club.name}` : undefined}
      size="lg"
      loading={query.isLoading}
      footer={
        <div className="flex w-full items-center justify-between gap-2">
          {canOffer && player ? (
            <div className="relative">
              <Button size="sm" variant="ghost" onClick={() => setMenuOpen((v) => !v)}>
                …
              </Button>
              {menuOpen ? (
                <div className="absolute bottom-full left-0 z-10 mb-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated">
                  <button
                    type="button"
                    className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                    onClick={() => {
                      setMenuOpen(false);
                      onWriteToClub(player.club.id);
                    }}
                  >
                    Écrire à son club
                  </button>
                </div>
              ) : null}
            </div>
          ) : (
            <span />
          )}
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="md" onClick={onClose}>
              Fermer
            </Button>
            {canOffer && player ? (
              <Button variant="primary" size="md" onClick={() => onMakeOffer(player.membership_id)}>
                Faire une offre
              </Button>
            ) : null}
          </div>
        </div>
      }
    >
      {query.isError ? (
        <p role="alert" className="text-sm text-status-danger-fg">
          Impossible de charger ce détail. Réessayez.
        </p>
      ) : player ? (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <Avatar name={`${player.first_name} ${player.last_name}`} photoUrl={player.photo} size={72} />
            <div className="min-w-0">
              <p className="truncate text-base font-semibold text-text">
                {player.first_name} {player.last_name}
              </p>
              <p className="truncate text-sm text-text-muted">{player.position_label}</p>
              <div className="mt-1 flex items-center gap-2">
                <Avatar name={player.club.name} photoUrl={player.club.logo} size={24} />
                <span className="text-sm text-text-muted">{player.club.name}</span>
              </div>
              {player.is_on_transfer_market ? <StatusBadge status="mercato_open" /> : null}
            </div>
          </div>

          <Tabs items={TABS} value={tab} onChange={setTab} label="Fiche publique" />

          {tab === "apercu" ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <div className="rounded-md border border-border p-2 text-center">
                <p className="text-xs text-text-muted">Âge</p>
                <p className="text-base font-semibold text-text">{player.age ?? "—"}</p>
              </div>
              <div className="rounded-md border border-border p-2 text-center">
                <p className="text-xs text-text-muted">Numéro</p>
                <p className="text-base font-semibold text-text">
                  {player.jersey_number != null ? player.jersey_number : "—"}
                </p>
              </div>
              <div className="rounded-md border border-border p-2 text-center">
                <p className="text-xs text-text-muted">Note moyenne</p>
                <p className="tabular-nums text-base font-semibold text-text">{player.average_rating ?? "—"}</p>
              </div>
            </div>
          ) : (
            <EmptyState message="Ces données ne sont pas encore disponibles depuis le marché." />
          )}
        </div>
      ) : null}
    </Modal>
  );
}
