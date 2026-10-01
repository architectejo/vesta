import { useState } from "react";
import type { Formation, SessionDetail } from "../../api/sport";
import { Banner, Button, Modal, PitchDragGhost } from "../../design-system";
import { TeamFieldPanel, type ArmedPlayer } from "./TeamFieldPanel";

interface PinMenuState {
  kind: "field" | "bench";
  membershipId: number;
  name: string;
  team: "A" | "B";
}

function otherTeam(team: "A" | "B"): "A" | "B" {
  return team === "A" ? "B" : "A";
}

export interface TeamsBoardProps {
  session: SessionDetail;
  canAssign: boolean;
  /** Vestiaire du jour (extension client du 30/09/2026, point suivant) :
   * un dépôt sur le banc de l'autre équipe bascule l'équipe du joueur.
   * Comportement historique de la page Séance si `false` (par défaut). */
  allowCrossTeamBenchDrop?: boolean;
  onAssign: (membershipId: number, team: "A" | "B") => void;
  onSetFormation: (team: "A" | "B", formation: Formation) => void;
  onPlacePlayer: (team: "A" | "B", membershipId: number, x: number | null, y: number | null) => void;
  onShowCard: (membershipId: number) => void;
}

/**
 * Deux terrains A/B éditables côte à côte, avec leur banc et le menu
 * d'action d'un pion (terrain/banc). Partagé entre la vue « Équipes A/B »
 * de la page Séance (§3.2) et le mode éditable du Vestiaire du jour
 * (extension client du 30/09/2026, hors CDC écrit à ce jour pour le
 * Vestiaire — voir le compte rendu de cette tâche). Les listes « À placer
 * à la main » et « Ne peuvent pas jouer », propres à la page Séance, ne
 * sont pas de son ressort : elles restent dans `SeancePage.tsx`.
 */
export function TeamsBoard({
  session,
  canAssign,
  allowCrossTeamBenchDrop = false,
  onAssign,
  onSetFormation,
  onPlacePlayer,
  onShowCard,
}: TeamsBoardProps) {
  const [menu, setMenu] = useState<PinMenuState | null>(null);
  const [armed, setArmed] = useState<ArmedPlayer | null>(null);

  return (
    <div className="space-y-3">
      {armed ? (
        <Banner variant="info" action={<Button size="sm" variant="ghost" onClick={() => setArmed(null)}>Annuler</Button>}>
          Touchez un emplacement libre ou un joueur du terrain pour y placer {armed.name}.
        </Banner>
      ) : null}

      <div className="grid grid-cols-1 gap-4 [@media(orientation:landscape)]:grid-cols-2 md:grid-cols-2">
        <TeamFieldPanel
          team="A"
          color={session.team_a_color}
          formation={session.team_a_formation}
          assignments={session.team_a}
          canAssign={canAssign}
          allowCrossTeamBenchDrop={allowCrossTeamBenchDrop}
          armed={armed}
          onArm={setArmed}
          onSetFormation={onSetFormation}
          onPlacePlayer={onPlacePlayer}
          onAssignTeam={onAssign}
          onOpenFieldMenu={(team, membershipId, name) => setMenu({ kind: "field", membershipId, name, team })}
          onOpenBenchMenu={(team, membershipId, name) => setMenu({ kind: "bench", membershipId, name, team })}
        />
        <TeamFieldPanel
          team="B"
          color={session.team_b_color}
          formation={session.team_b_formation}
          assignments={session.team_b}
          canAssign={canAssign}
          allowCrossTeamBenchDrop={allowCrossTeamBenchDrop}
          armed={armed}
          onArm={setArmed}
          onSetFormation={onSetFormation}
          onPlacePlayer={onPlacePlayer}
          onAssignTeam={onAssign}
          onOpenFieldMenu={(team, membershipId, name) => setMenu({ kind: "field", membershipId, name, team })}
          onOpenBenchMenu={(team, membershipId, name) => setMenu({ kind: "bench", membershipId, name, team })}
        />
      </div>

      <PitchDragGhost />

      <Modal open={menu !== null} onClose={() => setMenu(null)} title={menu?.name ?? ""} size="sm" hideFooter>
        {menu?.kind === "field" ? (
          <div className="space-y-2">
            {canAssign ? (
              <>
                <Button
                  variant="secondary"
                  className="w-full"
                  onClick={() => {
                    onPlacePlayer(menu.team, menu.membershipId, null, null);
                    setMenu(null);
                  }}
                >
                  Renvoyer sur le banc
                </Button>
                <Button
                  variant="ghost"
                  className="w-full"
                  onClick={() => {
                    onAssign(menu.membershipId, otherTeam(menu.team));
                    setMenu(null);
                  }}
                >
                  Passer en {otherTeam(menu.team)}
                </Button>
              </>
            ) : null}
            <Button variant="ghost" className="w-full" onClick={() => { onShowCard(menu.membershipId); setMenu(null); }}>
              Voir la fiche du joueur
            </Button>
          </div>
        ) : menu?.kind === "bench" ? (
          <div className="space-y-2">
            {canAssign ? (
              <>
                <Button
                  variant="secondary"
                  className="w-full"
                  onClick={() => {
                    setArmed({ team: menu.team, membershipId: menu.membershipId, name: menu.name });
                    setMenu(null);
                  }}
                >
                  Placer sur le terrain
                </Button>
                <Button
                  variant="ghost"
                  className="w-full"
                  onClick={() => {
                    onAssign(menu.membershipId, otherTeam(menu.team));
                    setMenu(null);
                  }}
                >
                  Passer en {otherTeam(menu.team)}
                </Button>
              </>
            ) : null}
            <Button variant="ghost" className="w-full" onClick={() => { onShowCard(menu.membershipId); setMenu(null); }}>
              Voir la fiche du joueur
            </Button>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
