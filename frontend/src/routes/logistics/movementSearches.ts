import { getExpenses, type Expense } from "../../api/treasury";
import { listMatches, type MatchListItem } from "../../api/sport";

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

/** Vue réduite d'une dépense pour la recherche du matériel : seulement date,
 * catégorie, montant et statut (fiche §4.8, jamais le bénéficiaire, le motif
 * ni le justificatif). */
export interface ExpenseSearchRow {
  id: number;
  expense_date: string;
  category_name: string;
  amount: string;
  currency: string;
  status_label: string;
}

function toExpenseSearchRow(expense: Expense): ExpenseSearchRow {
  return {
    id: expense.id,
    expense_date: expense.expense_date,
    category_name: expense.category.name,
    amount: expense.amount,
    currency: expense.currency,
    status_label: expense.status_label,
  };
}

/**
 * Recherche de dépense pour « Enregistrer un mouvement » (fiche §4.4, §4.8,
 * point ouvert n° 1) : dépenses libérées, justifiées ou non justifiées
 * (proposition de la fiche), jamais en attente ni refusées. Le point
 * d'accès `/treasury/expenses/` reste réservé au Président, Vice-président,
 * Trésorier et Trésorier adjoint (matrice 2.4) — **pas à l'Intendant**, seul
 * rôle pouvant ouvrir cette modale (`CanManageMaterial`). Cette fonction
 * n'est donc utilisable qu'une fois ce point ouvert tranché côté API ; en
 * attendant, l'appelant doit détecter un refus 403 et masquer le champ
 * (voir `RecordMovementModal`, compte rendu de la tâche).
 */
export async function searchExpensesForMovement(query: string): Promise<ExpenseSearchRow[]> {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  const response = await getExpenses({ status: ["released", "justified", "unjustified"], limit: 200 });
  return response.results
    .filter(
      (expense) =>
        expense.category.name.toLowerCase().includes(needle) ||
        expense.expense_date.includes(needle) ||
        expense.amount.includes(needle),
    )
    .map(toExpenseSearchRow);
}
