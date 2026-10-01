import { useQueryClient, type QueryKey } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { assignTeam, placeTeamPlayer, setTeamFormation, type Formation, type SessionDetail } from "../../api/sport";
import { useToast } from "../../design-system";

/**
 * Actions de répartition d'équipe (§3.2), partagées entre la page Séance
 * et le mode éditable du Vestiaire du jour (extension client du
 * 30/09/2026, hors CDC écrit à ce jour pour le Vestiaire — voir le compte
 * rendu de cette tâche). Mêmes appels API, même gestion d'erreur ; seules
 * les clés de requête à invalider après succès changent d'un écran à
 * l'autre (`["sport","session",id]` pour la page Séance, `["sport",
 * "locker-room"]` pour le Vestiaire du jour).
 */
export function useTeamFieldActions(sessionId: number, invalidateKeys: QueryKey[]) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  function invalidateAll(): void {
    for (const key of invalidateKeys) {
      void queryClient.invalidateQueries({ queryKey: key });
    }
  }

  async function handleAssign(
    session: SessionDetail | null | undefined,
    membershipId: number,
    team: "A" | "B",
  ): Promise<void> {
    try {
      const previous = session
        ? [...session.team_a, ...session.team_b].find((a) => a.membership_id === membershipId)
        : undefined;
      await assignTeam(sessionId, { membership_id: membershipId, team });
      if (previous?.is_on_field) {
        // Sécurité : une bascule d'équipe ne réinitialise pas is_on_field/
        // x/y côté service (`assign_team` ne touche pas ces champs) ; on
        // renvoie explicitement le joueur au banc de sa nouvelle équipe
        // pour ne jamais laisser une position du terrain héritée d'une
        // autre équipe.
        await placeTeamPlayer(sessionId, { team, membership_id: membershipId, x_coord: null, y_coord: null });
      }
      invalidateAll();
      showToast(`Joueur passé en équipe ${team}.`);
    } catch (error) {
      showToast(error instanceof ApiError ? error.detail : "Déplacement non enregistré. Réessayez.");
    }
  }

  async function handleSetFormation(team: "A" | "B", formation: Formation): Promise<void> {
    try {
      await setTeamFormation(sessionId, { team, formation });
      invalidateAll();
    } catch (error) {
      showToast(error instanceof ApiError ? error.detail : "Formation non enregistrée. Réessayez.");
    }
  }

  async function handlePlaceTeamPlayer(
    team: "A" | "B",
    membershipId: number,
    x: number | null,
    y: number | null,
  ): Promise<void> {
    try {
      await placeTeamPlayer(sessionId, { team, membership_id: membershipId, x_coord: x, y_coord: y });
      invalidateAll();
    } catch (error) {
      showToast(error instanceof ApiError ? error.detail : "Déplacement non enregistré. Réessayez.");
    }
  }

  return { handleAssign, handleSetFormation, handlePlaceTeamPlayer };
}
