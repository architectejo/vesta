import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import {
  recordMovement,
  searchArticles,
  toArticleSearchResult,
  type Article,
  type MovementInput,
  type MovementType,
} from "../../api/logistics";
import { getExpenses } from "../../api/treasury";
import { searchActiveClubPlayers } from "../../api/clubs";
import type { MatchListItem } from "../../api/sport";
import {
  ArticleSearch,
  Modal,
  NumberField,
  PlayerSearch,
  SegmentedControl,
  TextArea,
  type ArticleSearchResult,
  type PlayerSearchResult,
} from "../../design-system";
import { formatDateFr, todayIsoDate } from "./format";
import { IN_MOVEMENT_TYPE_OPTIONS, MOVEMENT_TYPES_WITH_MATCH, MOVEMENT_TYPES_WITH_MEMBERSHIP, OUT_MOVEMENT_TYPE_OPTIONS } from "./materielLabels";
import { SearchCombobox } from "./SearchCombobox";
import { searchExpensesForMovement, searchMatchesForMovement, type ExpenseSearchRow } from "./movementSearches";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

export interface RecordMovementModalProps {
  open: boolean;
  /** Article préchoisi et verrouillé (ouverte depuis la fiche d'un article). */
  lockedArticle?: Article | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}

/** « Enregistrer un mouvement » (fiche `logistique.md` §4.4, Intendant). */
export function RecordMovementModal({ open, lockedArticle, onClose, onSaved }: RecordMovementModalProps) {
  const [sense, setSense] = useState<"in" | "out">("in");
  const [movementType, setMovementType] = useState<MovementType | null>(null);
  const [article, setArticle] = useState<ArticleSearchResult | null>(null);
  const [quantity, setQuantity] = useState<number | null>(null);
  const [date, setDate] = useState(todayIsoDate());
  const [player, setPlayer] = useState<PlayerSearchResult | null>(null);
  const [match, setMatch] = useState<MatchListItem | null>(null);
  const [expense, setExpense] = useState<ExpenseSearchRow | null>(null);
  const [reason, setReason] = useState("");

  const [typeError, setTypeError] = useState<string | undefined>(undefined);
  const [articleError, setArticleError] = useState<string | undefined>(undefined);
  const [quantityError, setQuantityError] = useState<string | undefined>(undefined);
  const [dateError, setDateError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  // Sonde d'accès aux dépenses (point ouvert n° 1 de la fiche d'écran) : la
  // seule personne pouvant ouvrir cette modale est l'Intendant, qui n'a
  // aucun accès à `/treasury/expenses/` dans la matrice 2.4. Un refus 403
  // masque le champ « Dépense liée » avec une explication plutôt que de
  // laisser une recherche qui échouera systématiquement.
  const expenseAccessQuery = useQuery({
    queryKey: ["logistics", "expense-access-probe"],
    queryFn: () => getExpenses({ limit: 1 }),
    enabled: open,
    retry: false,
  });
  const expenseAccessDenied = expenseAccessQuery.isError && (expenseAccessQuery.error as ApiError)?.status === 403;

  useEffect(() => {
    if (!open) return;
    setSense("in");
    setMovementType(null);
    setArticle(lockedArticle ? toArticleSearchResult(lockedArticle) : null);
    setQuantity(null);
    setDate(todayIsoDate());
    setPlayer(null);
    setMatch(null);
    setExpense(null);
    setReason("");
    setTypeError(undefined);
    setArticleError(undefined);
    setQuantityError(undefined);
    setDateError(undefined);
    setSubmitError(undefined);
  }, [open, lockedArticle]);

  const typeOptions = sense === "in" ? IN_MOVEMENT_TYPE_OPTIONS : OUT_MOVEMENT_TYPE_OPTIONS;
  const showMembership = movementType ? MOVEMENT_TYPES_WITH_MEMBERSHIP.includes(movementType) : false;
  const showMatch = movementType ? MOVEMENT_TYPES_WITH_MATCH.includes(movementType) : false;
  const showExpense = movementType === "in_purchase";

  async function handleSubmit(): Promise<void> {
    let hasError = false;
    if (!movementType) {
      setTypeError("Choisissez le type de mouvement.");
      hasError = true;
    } else {
      setTypeError(undefined);
    }
    if (!article) {
      setArticleError("Choisissez un article.");
      hasError = true;
    } else {
      setArticleError(undefined);
    }
    if (!quantity || quantity < 1) {
      setQuantityError("Saisissez une quantité supérieure à 0.");
      hasError = true;
    } else {
      setQuantityError(undefined);
    }
    if (!date) {
      setDateError("La date est obligatoire.");
      hasError = true;
    } else {
      setDateError(undefined);
    }
    if (hasError || !movementType || !article || !quantity || !date) return;

    const input: MovementInput = {
      movement_type: movementType,
      article_id: Number(article.id),
      quantity,
      movement_date: date,
      reason: reason.trim() || undefined,
      membership_id: showMembership && player ? Number(player.id) : undefined,
      match_id: showMatch && match ? match.id : undefined,
      expense_id: showExpense && expense ? expense.id : undefined,
    };

    setSubmitting(true);
    setSubmitError(undefined);
    try {
      const result = await recordMovement(input);
      onSaved(`Mouvement enregistré. Stock de ${article.name} : ${result.in_stock} ${article.unit}.`);
    } catch (error) {
      if (error instanceof ApiError && /quantité|stock/i.test(error.detail)) {
        setQuantityError(error.detail);
      } else if (error instanceof ApiError && /date/i.test(error.detail)) {
        setDateError(error.detail);
      } else {
        setSubmitError(apiErrorMessage(error));
      }
    } finally {
      setSubmitting(false);
    }
  }

  const isDirty = Boolean(movementType || article || quantity || player || match || expense || reason.trim());

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Enregistrer un mouvement"
      size="md"
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Enregistrer le mouvement"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <SegmentedControl
          label="Sens"
          value={sense}
          onChange={(value) => {
            setSense(value);
            setMovementType(null);
          }}
          options={[
            { value: "in", label: "Entrée" },
            { value: "out", label: "Sortie" },
          ]}
        />
        <SegmentedControl
          label="Type"
          value={movementType}
          onChange={setMovementType}
          options={typeOptions}
          error={typeError}
          wrapOnMobile
        />
        <div>
          <p className="mb-1 text-sm font-medium text-text">Article</p>
          {lockedArticle ? (
            <div className="flex h-control-md items-center gap-2 rounded-sm border border-border-strong bg-surface-muted px-3 text-sm text-text">
              {lockedArticle.name}
            </div>
          ) : (
            <ArticleSearch
              value={article}
              onChange={setArticle}
              searchArticles={searchArticles}
              mode={sense === "out" ? "out" : "in"}
            />
          )}
          {articleError ? <p className="mt-1 text-xs text-status-danger-fg">{articleError}</p> : null}
        </div>
        <NumberField
          label="Quantité"
          value={quantity}
          onChange={setQuantity}
          min={1}
          error={quantityError}
        />
        <label className="block text-sm font-medium text-text">
          Date
          <input
            type="date"
            value={date}
            max={todayIsoDate()}
            onChange={(e) => setDate(e.target.value)}
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
          />
          {dateError ? <p className="mt-1 text-xs text-status-danger-fg">{dateError}</p> : null}
        </label>
        {showMembership ? (
          <div>
            <p className="mb-1 text-sm font-medium text-text">Joueur concerné (facultatif)</p>
            <PlayerSearch value={player} onChange={setPlayer} searchPlayers={searchActiveClubPlayers} />
          </div>
        ) : null}
        {showMatch ? (
          <div>
            <p className="mb-1 text-sm font-medium text-text">Match (facultatif)</p>
            <SearchCombobox
              value={match}
              onChange={setMatch}
              search={searchMatchesForMovement}
              placeholder="Adversaire ou date"
              ariaLabel="Rechercher un match"
              emptyHint="Tapez l'adversaire ou une date."
              renderOption={(m) => (
                <span className="text-sm text-text">
                  {m.opponent} · {formatDateFr(m.event_date)}
                </span>
              )}
              renderSelected={(m) => `${m.opponent} · ${formatDateFr(m.event_date)}`}
            />
          </div>
        ) : null}
        {showExpense ? (
          <div>
            <p className="mb-1 text-sm font-medium text-text">Dépense liée (facultatif)</p>
            <SearchCombobox
              value={expense}
              onChange={setExpense}
              search={searchExpensesForMovement}
              placeholder="Catégorie, date ou montant"
              ariaLabel="Rechercher une dépense"
              emptyHint="Tapez une catégorie, une date ou un montant."
              unavailableMessage={
                expenseAccessDenied
                  ? "Ce champ nécessite un accès aux dépenses, réservé au Président, au Vice-président et au Trésorier (CDC 2.4). Point ouvert n° 1 de la fiche d'écran, non tranché."
                  : undefined
              }
              renderOption={(row) => (
                <span className="text-sm text-text">
                  {formatDateFr(row.expense_date)} · {row.category_name} · {row.amount} {row.currency}
                </span>
              )}
              renderSelected={(row) => `${formatDateFr(row.expense_date)} · ${row.category_name} · ${row.amount} ${row.currency}`}
            />
            <p className="mt-1 text-xs text-text-muted">
              Rattachez l'achat à la dépense saisie par la trésorerie.
            </p>
          </div>
        ) : null}
        <TextArea label="Motif" optional value={reason} onChange={setReason} maxLength={500} />
        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
