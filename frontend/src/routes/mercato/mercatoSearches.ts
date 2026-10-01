import { listMarket, type MarketRow } from "../../api/mercato";
import type { ClubSearchResult } from "../../design-system/components/ClubSearch";
import type { PlayerSearchResult } from "../../design-system/components/PlayerSearch";

/** Adapte une ligne du marché au format attendu par `PlayerSearch` (§4.2 :
 * « joueur visé », portée `public`, limitée aux joueurs « Sur le marché »
 * des autres clubs). */
function toPlayerSearchResult(row: MarketRow): PlayerSearchResult {
  return {
    id: row.membership_id,
    firstName: row.first_name,
    lastName: row.last_name,
    number: row.jersey_number,
    position: [row.position_label, row.age != null ? `${row.age} ans` : null, row.club.name]
      .filter(Boolean)
      .join(" · "),
    photoUrl: row.photo,
  };
}

/** Joueurs « Sur le marché » d'un autre club, pour « Faire une offre » (§4.2).
 * Aucun badge financier ni médical (§2.1) : le marché ne les expose jamais. */
export function searchMarketPlayers(query: string): Promise<PlayerSearchResult[]> {
  return listMarket({ search: query }).then((response) =>
    response.results.filter((row) => !row.is_own_club).map(toPlayerSearchResult),
  );
}

/**
 * `ClubSearch` (« Écrire à un club », §4.5 ; filtre « Club » du marché,
 * §3.1) : **aucun point d'accès de recherche de tous les clubs Vesta**
 * n'est exposé par l'API à ce jour (seul `/mercato/market/` existe, limité
 * aux clubs ayant au moins un joueur « Sur le marché »). En attendant un
 * point d'accès dédié (ex. `GET /clubs/public/`), les suggestions sont
 * dérivées des clubs déjà visibles dans le marché — limitation documentée
 * au compte rendu plutôt qu'un point d'accès inventé ou une liste figée.
 */
export function searchClubsFromMarket(query: string): Promise<ClubSearchResult[]> {
  return listMarket({ search: query }).then((response) => {
    const seen = new Map<number, ClubSearchResult>();
    for (const row of response.results) {
      if (row.is_own_club) continue;
      if (!seen.has(row.club.id)) {
        seen.set(row.club.id, { id: row.club.id, name: row.club.name, logo: row.club.logo });
      }
    }
    const needle = query.trim().toLowerCase();
    return [...seen.values()].filter((club) => club.name.toLowerCase().includes(needle));
  });
}
