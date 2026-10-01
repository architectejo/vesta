import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getTacticalPlan, type Annotation, type Placement } from "../../api/sport";
import {
  Button,
  EmptyState,
  FORMATION_LABELS,
  Loader,
  Modal,
  PitchBoard,
  slotsForFormation,
  StatusBadge,
  type PitchPinData,
} from "../../design-system";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { shortLabel } from "./pinLayout";

export interface PlanDetailModalProps {
  open: boolean;
  planId: number | null;
  isCoach: boolean;
  ownMembershipId: number | undefined;
  onClose: () => void;
  onDuplicate: (plan: { id: number; name: string }) => void;
  onDelete: (plan: { id: number; name: string }) => void;
}

function annotationsForBoard(annotations: Annotation[]) {
  return annotations
    .filter((a) => a.annotation_type !== "note")
    .map((a) => {
      let points: Array<{ x: number; y: number }> = [];
      try {
        const parsed = JSON.parse(a.path_data || "[]");
        if (Array.isArray(parsed)) points = parsed;
      } catch {
        points = [];
      }
      return { id: String(a.id), type: a.annotation_type, points, text: a.text };
    });
}

/** « Plan » (docs/ecrans/sport-plan-tactique.md §4.1), consultation. */
export function PlanDetailModal({ open, planId, isCoach, ownMembershipId, onClose, onDuplicate, onDelete }: PlanDetailModalProps) {
  const navigate = useNavigate();
  const [selectedPlacement, setSelectedPlacement] = useState<Placement | null>(null);

  // Disposition à deux colonnes (terrain à gauche, consignes à droite),
  // docs/ecrans/sport-plan-tactique.md §7.3 (paysage mobile) et §7.4
  // (tablette/ordinateur, taille `lg`). Le point de rupture « ordinateur »
  // est celui de la modale elle-même (design-system Modal.tsx : `sm:` =
  // 640 px, au-delà duquel elle quitte le plein écran pour son panneau
  // fixe) : en dessous, la modale reste en plein écran (§7.3) et ne bascule
  // en deux colonnes qu'en paysage, faute de largeur utilisable en portrait.
  const isDesktopPanel = useMediaQuery("(min-width: 640px)");
  const isLandscape = useMediaQuery("(orientation: landscape)");
  const isHorizontalLayout = isDesktopPanel || isLandscape;

  // Contrainte de hauteur (remarques.md) : le terrain ne doit jamais forcer
  // le défilement du corps de la modale pour voir les consignes. Le panneau
  // est plafonné à 90 vh à partir de 640 px et à 100dvh en plein écran
  // (Modal.tsx) ; on retranche une estimation généreuse de l'en-tête, du
  // pied et des marges du corps pour obtenir la hauteur réellement offerte
  // au terrain, puis on en déduit la largeur maximale compatible avec son
  // ratio horizontal (105/68). La largeur retenue est la plus petite entre
  // 60 % de la colonne (§7.4) et cette largeur dérivée de la hauteur : le
  // terrain ne peut donc jamais dépasser l'espace vertical disponible.
  const pitchHeightBudget = isDesktopPanel ? "calc(90vh - 260px)" : "calc(100dvh - 200px)";
  const pitchColumnStyle = isHorizontalLayout
    ? { width: `min(60%, calc(${pitchHeightBudget} * 105 / 68))` }
    : undefined;

  const query = useQuery({
    queryKey: ["sport", "tactical-plan", planId],
    queryFn: () => getTacticalPlan(planId as number),
    enabled: open && planId != null,
  });

  const plan = query.data;
  const slots = plan ? slotsForFormation(plan.formation, plan.squad_size) : [];

  const pins: PitchPinData[] = (plan?.placements ?? [])
    .filter((p) => p.membership_id != null)
    .map((p) => ({
      id: String(p.id),
      membershipId: p.membership_id as number,
      label: shortLabel(p.player?.name ?? ""),
      number: p.jersey_number_override ?? p.player?.jersey_number ?? null,
      x: Number(p.x_coord),
      y: Number(p.y_coord),
      locked: Boolean(p.no_longer_eligible),
      highlighted: p.membership_id === ownMembershipId,
    }));
  void slots;

  const lineNotes = (plan?.annotations ?? []).filter((a) => a.annotation_type === "note" && a.target_line);
  const playerNotes = (plan?.annotations ?? []).filter((a) => a.annotation_type === "note" && a.target_membership_id);
  const ownNote = playerNotes.find((n) => n.target_membership_id === ownMembershipId);

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={plan?.name ?? "Plan"}
        subtitle={plan ? [FORMATION_LABELS[plan.formation], plan.match_id ? `Match n° ${plan.match_id}` : null].filter(Boolean).join(" · ") : undefined}
        size="lg"
        loading={query.isLoading}
        footer={
          <div className="flex w-full items-center justify-between gap-2">
            <div className="flex gap-2">
              {isCoach && plan ? (
                <>
                  <Button variant="ghost" size="sm" onClick={() => onDuplicate({ id: plan.id, name: plan.name })}>
                    Dupliquer
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => onDelete({ id: plan.id, name: plan.name })}>
                    Supprimer le plan
                  </Button>
                </>
              ) : null}
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={onClose}>
                Fermer
              </Button>
              {isCoach && plan ? (
                <Button
                  variant="primary"
                  onClick={() => {
                    // Ferme proprement la modale avant de changer de route :
                    // sans cela, l'état React du parent (ex. `detailPlanId`)
                    // reste « modale ouverte » alors que la page a changé.
                    onClose();
                    navigate(`/plans/${plan.id}/tableau`);
                  }}
                >
                  Modifier sur le tableau noir
                </Button>
              ) : null}
            </div>
          </div>
        }
      >
        {query.isError ? (
          <EmptyState variant="error" />
        ) : !plan ? (
          <Loader loading variant="list" count={3} />
        ) : (
          <div className={isHorizontalLayout ? "flex items-start gap-4" : "space-y-4"}>
            <div
              className={isHorizontalLayout ? "flex-shrink-0 space-y-2" : "space-y-2"}
              style={pitchColumnStyle}
            >
              <StatusBadge status={plan.is_published ? "lineup_published" : "lineup_draft"} />
              <PitchBoard
                mode="readonly"
                ariaLabel={plan.name}
                pins={pins}
                annotations={annotationsForBoard(plan.annotations)}
                vertical={!isHorizontalLayout}
                pinsDraggable={false}
                onTapPin={(pin) => {
                  const placement = plan.placements.find((p) => String(p.id) === pin.id) ?? null;
                  setSelectedPlacement(placement);
                }}
              />
            </div>

            <div className={isHorizontalLayout ? "min-w-0 flex-1" : undefined}>
              <h3 className="mb-2 text-sm font-semibold text-text">Consignes</h3>
              {ownNote ? (
                <div className="mb-2 rounded-md bg-surface-muted p-2">
                  <p className="text-xs font-medium text-text-muted">Pour vous</p>
                  <p className="text-sm text-text">{ownNote.text}</p>
                </div>
              ) : null}
              {lineNotes.length === 0 && playerNotes.length === 0 ? (
                <EmptyState message="Aucune consigne." />
              ) : (
                <ul className="space-y-2">
                  {lineNotes.map((note) => (
                    <li key={note.id} className="text-sm text-text">
                      <span className="font-medium">
                        {note.target_line === "defense" ? "Défense" : note.target_line === "midfield" ? "Milieu" : "Attaque"} :
                      </span>{" "}
                      {note.text}
                    </li>
                  ))}
                  {playerNotes.map((note) => {
                    const placement = plan.placements.find((p) => p.membership_id === note.target_membership_id);
                    return (
                      <li key={note.id} className="text-sm text-text">
                        <span className="font-medium">{placement?.player?.name ?? "Joueur"} :</span> {note.text}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        )}
      </Modal>

      <Modal
        open={selectedPlacement !== null}
        onClose={() => setSelectedPlacement(null)}
        title={selectedPlacement?.player?.name ?? ""}
        size="sm"
        level={2}
        hideFooter
      >
        {selectedPlacement ? (
          <div className="space-y-1 text-sm text-text">
            <p>
              n° {selectedPlacement.jersey_number_override ?? selectedPlacement.player?.jersey_number ?? "—"} ·{" "}
              {selectedPlacement.position_override || selectedPlacement.player?.position_label}
            </p>
            {selectedPlacement.no_longer_eligible ? (
              <p className="text-status-danger-fg">{selectedPlacement.no_longer_eligible.reason}</p>
            ) : null}
            {(() => {
              const note = playerNotes.find((n) => n.target_membership_id === selectedPlacement.membership_id);
              return note ? <p className="text-text-muted">Consigne : {note.text}</p> : null;
            })()}
          </div>
        ) : null}
      </Modal>
    </>
  );
}
