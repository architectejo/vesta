import { searchLinkableExpenses, type LinkableExpense } from "../../api/logistics";
import { listMatches, type MatchListItem } from "../../api/sport";
import { listClubPlayers, toPlayerSearchResult } from "../../api/clubs";
import type { PlayerSearchResult } from "../../design-system";

/**
 * Recherche de match pour « Enregistrer un mouvement » (fiche `logistique.md`
 * §4.4 : « Adversaire ou date », les plus proches d'aujourd'hui d'abord).
 * Aucun point d'accès de recherche dédié côté `apps.sport` : la liste des
 * matchs (déjà triée par date décroissante côté API) est filtrée et
 * re-triée ici par proximité de la date du jour — limitation documentée au
 * compte rendu plutôt qu'un point d'accès inventé.
 */
export async function searchMatchesForMovement(query: string): Promise<MatchListItem[]> {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  const response = await listMatches({ limit: 100 });
  const today = Date.now();
  return response.results
    .filter(
      (match) => match.opponent.toLowerCase().includes(needle) || match.event_date.includes(needle),
    )
    .sort((a, b) => {
      const da = Math.abs(new Date(a.event_date).getTime() - today);
      const db = Math.abs(new Date(b.event_date).getTime() - today);
      return da - db;
    });
}

/**
 * Recherche de dépense pour « Dépense liée » d'un achat (10.2 n° 167) :
 * `GET logistics/expenses/linkable/?q=`, ouvert à l'Intendant. L'API ne
 * renvoie que les dépenses libérées, avec référence, date, montant, devise,
 * catégorie et statut (jamais le bénéficiaire, le motif ni le justificatif).
 */
export async function searchExpensesForMovement(query: string): Promise<LinkableExpense[]> {
  if (!query.trim()) return [];
  return searchLinkableExpenses(query);
}

/**
 * Joueurs pouvant devenir détenteurs ou donateurs : adhésions actives **et
 * en attente** (l'API accepte les deux, écart n° 3 de la spec B4). Les
 * joueurs partis ne sont jamais proposés : un ancien membre se saisit en
 * texte libre comme donateur hors club.
 */
export async function searchHolderCandidates(query: string): Promise<PlayerSearchResult[]> {
  if (!query.trim()) return [];
  const items = await listClubPlayers({ search: query });
  return items.filter((item) => item.membership_status !== "departed").map(toPlayerSearchResult);
}
