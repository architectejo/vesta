import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import {
  PROVENANCE_MOVEMENT_TYPES,
  recordMovement,
  searchArticles,
  toArticleSearchResult,
  type Article,
  type ArticleCondition,
  type LinkableExpense,
  type ManualMovementType,
  type MovementInput,
  type OriginKind,
  type ProvenanceInput,
} from "../../api/logistics";
import { searchActiveClubPlayers } from "../../api/clubs";
import type { MatchListItem } from "../../api/sport";
import {
  ArticleSearch,
  Avatar,
  Checkbox,
  Modal,
  NumberField,
  PlayerSearch,
  SegmentedControl,
  TextArea,
  TextField,
  type ArticleSearchResult,
  type PlayerSearchResult,
} from "../../design-system";
import { formatDateFr, todayIsoDate } from "./format";
import { HolderPicker } from "./HolderPicker";
import { HolderSearch, type HolderSelection } from "./HolderSearch";
import {
  ARTICLE_CONDITION_OPTIONS,
  IN_MOVEMENT_TYPE_OPTIONS,
  MOVEMENT_TYPES_WITH_MATCH,
  MOVEMENT_TYPES_WITH_MEMBERSHIP,
  ORIGIN_KIND_OPTIONS,
  OUT_MOVEMENT_TYPE_OPTIONS,
  formatQuantity,
} from "./materielLabels";
import { SearchCombobox } from "./SearchCombobox";
import { searchExpensesForMovement, searchHolderCandidates, searchMatchesForMovement } from "./movementSearches";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

const DONOR_NAME_MAX = 120;

/** Donateur : joueur du club, ou nom libre « hors club ». */
interface DonorOption {
  id: string;
  name: string;
  membershipId: number | null;
  photoUrl?: string | null;
}

async function searchDonors(query: string): Promise<DonorOption[]> {
  const text = query.trim();
  if (!text) return [];
  const players = await searchHolderCandidates(text);
  const options: DonorOption[] = players.map((p) => ({
    id: `m${p.id}`,
    name: `${p.firstName} ${p.lastName}`.trim(),
    membershipId: Number(p.id),
    photoUrl: p.photoUrl,
  }));
  options.push({ id: `free:${text}`, name: text, membershipId: null });
  return options;
}

type FieldKey =
  | "type"
  | "article"
  | "quantity"
  | "holder"
  | "date"
  | "donor"
  | "acquisitionDate"
  | "acquisitionNote"
  | "submit";

export interface RecordMovementModalProps {
  open: boolean;
  /** Article préchoisi et verrouillé (ouverte depuis la fiche d'un article). */
  lockedArticle?: Article | null;
  /** 2 quand ouverte depuis une autre modale (fiche d'un article). */
  level?: 1 | 2;
  onClose: () => void;
  onSaved: (message: string) => void;
}

/** « Enregistrer un mouvement » (fiche `logistique.md` §4.4 ; spec B4 §1.5 et §2.1), Intendant. */
export function RecordMovementModal({ open, lockedArticle, level = 1, onClose, onSaved }: RecordMovementModalProps) {
  const [sense, setSense] = useState<"in" | "out">("in");
  const [movementType, setMovementType] = useState<ManualMovementType | null>(null);
  const [article, setArticle] = useState<ArticleSearchResult | null>(null);
  const [quantity, setQuantity] = useState<number | null>(null);
  const [holderIn, setHolderIn] = useState<HolderSelection | null>(null);
  const [holderOut, setHolderOut] = useState<number | null | undefined>(undefined);
  const [date, setDate] = useState(todayIsoDate());
  const [player, setPlayer] = useState<PlayerSearchResult | null>(null);
  const [match, setMatch] = useState<MatchListItem | null>(null);
  const [expense, setExpense] = useState<LinkableExpense | null>(null);
  const [reason, setReason] = useState("");

  // Provenance (lot 3) : valeurs par défaut = aucune provenance envoyée.
  const [provenanceExpanded, setProvenanceExpanded] = useState(false);
  const [originKind, setOriginKind] = useState<OriginKind>("unknown");
  const [donor, setDonor] = useState<DonorOption | null>(null);
  const [acquisitionDate, setAcquisitionDate] = useState("");
  const [acquisitionUnknown, setAcquisitionUnknown] = useState(false);
  const [acquisitionNote, setAcquisitionNote] = useState("");
  const [conditionAtEntry, setConditionAtEntry] = useState<ArticleCondition>("unknown");

  const [errors, setErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const [submitting, setSubmitting] = useState(false);

  const resetProvenance = useCallback((type: ManualMovementType | null) => {
    setOriginKind(type === "in_donation" ? "donation" : "unknown");
    setProvenanceExpanded(type === "in_donation" || type === "in_opening");
    setDonor(null);
    setAcquisitionDate("");
    setAcquisitionUnknown(false);
    setAcquisitionNote("");
    setConditionAtEntry("unknown");
  }, []);

  useEffect(() => {
    if (!open) return;
    setSense("in");
    setMovementType(null);
    const initialArticle = lockedArticle ? toArticleSearchResult(lockedArticle) : null;
    setArticle(initialArticle);
    setQuantity(null);
    setHolderIn(null);
    setHolderOut(undefined);
    setDate(todayIsoDate());
    setPlayer(null);
    setMatch(null);
    setExpense(null);
    setReason("");
    resetProvenance(null);
    setErrors({});
  }, [open, lockedArticle, resetProvenance]);

  const typeOptions = sense === "in" ? IN_MOVEMENT_TYPE_OPTIONS : OUT_MOVEMENT_TYPE_OPTIONS;
  const showMembership = movementType ? MOVEMENT_TYPES_WITH_MEMBERSHIP.includes(movementType) : false;
  const showMatch = movementType ? MOVEMENT_TYPES_WITH_MATCH.includes(movementType) : false;
  const showExpense = movementType === "in_purchase";
  const showProvenance = movementType ? PROVENANCE_MOVEMENT_TYPES.includes(movementType) : false;

  const stockRows = article?.stockByHolder ?? [];
  // Sortie : « Chez » affiché seulement si l'article a au moins un détenteur.
  const showOutHolder = sense === "out" && stockRows.some((row) => row.holder_id !== null);

  function selectArticle(next: ArticleSearchResult | null): void {
    setArticle(next);
    setHolderOut(next?.suggestedHolder ? next.suggestedHolder.id : undefined);
  }

  function selectSense(next: "in" | "out"): void {
    setSense(next);
    setMovementType(null);
    setHolderIn(null);
    setHolderOut(article?.suggestedHolder ? article.suggestedHolder.id : undefined);
    resetProvenance(null);
  }

  function selectType(next: ManualMovementType): void {
    setMovementType(next);
    resetProvenance(next);
  }

  const provenanceTouched =
    originKind !== "unknown" ||
    donor !== null ||
    acquisitionDate !== "" ||
    acquisitionUnknown ||
    conditionAtEntry !== "unknown";

  /** `null` si le bloc est laissé à ses valeurs par défaut (spec §2.1). */
  function buildProvenance(): ProvenanceInput | null {
    if (!showProvenance || !provenanceTouched) return null;
    const provenance: ProvenanceInput = { origin_kind: originKind, condition_at_entry: conditionAtEntry };
    if (originKind === "donation" && donor) {
      if (donor.membershipId !== null) provenance.donor_membership_id = donor.membershipId;
      else provenance.donor_name = donor.name;
    }
    if (acquisitionUnknown) {
      provenance.acquisition_date_unknown = true;
      if (acquisitionNote.trim()) provenance.acquisition_date_note = acquisitionNote.trim();
    } else if (acquisitionDate) {
      provenance.acquisition_date = acquisitionDate;
    }
    return provenance;
  }

  async function handleSubmit(): Promise<void> {
    const next: Partial<Record<FieldKey, string>> = {};
    const today = todayIsoDate();
    if (!movementType) next.type = "Choisissez le type de mouvement.";
    if (!article) next.article = "Choisissez un article.";
    if (!quantity || quantity < 1) next.quantity = "Saisissez une quantité supérieure à 0.";
    if (showOutHolder && holderOut === undefined) next.holder = "Choisissez d'où sort le matériel.";
    if (!date) next.date = "La date est obligatoire.";
    else if (date > today) next.date = "La date ne peut pas être dans le futur.";
    if (showProvenance && originKind === "donation") {
      if (!donor) next.donor = "Indiquez le donateur.";
      else if (donor.membershipId === null && donor.name.length > DONOR_NAME_MAX)
        next.donor = "Le nom du donateur ne peut pas dépasser 120 caractères.";
    }
    if (showProvenance && !acquisitionUnknown && acquisitionDate) {
      if (acquisitionDate > today) next.acquisitionDate = "La date ne peut pas être dans le futur.";
      else if (date && acquisitionDate > date)
        next.acquisitionDate = "La date d'acquisition ne peut pas être postérieure à la date d'enregistrement.";
    }
    setErrors(next);
    if (Object.keys(next).length > 0 || !movementType || !article || !quantity) {
      if (next.donor || next.acquisitionDate) setProvenanceExpanded(true);
      return;
    }

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
    if (sense === "in" && holderIn) input.holder_id = holderIn.id;
    if (showOutHolder && holderOut !== undefined) input.holder_id = holderOut;
    if (showProvenance) input.provenance = buildProvenance();

    setSubmitting(true);
    try {
      const result = await recordMovement(input);
      onSaved(`Mouvement enregistré. Stock de ${article.name} : ${formatQuantity(result.in_stock, article.unit)}.`);
    } catch (error) {
      const message = apiErrorMessage(error);
      if (/donateur/i.test(message)) {
        setProvenanceExpanded(true);
        setErrors({ donor: message });
      } else if (/acquisition|précision/i.test(message)) {
        setProvenanceExpanded(true);
        setErrors({ [/précision/i.test(message) ? "acquisitionNote" : "acquisitionDate"]: message });
      } else if (/quantité|stock/i.test(message)) {
        setErrors({ quantity: message });
      } else if (/détenteur|ne fait plus partie/i.test(message)) {
        setErrors({ holder: message });
      } else if (/date/i.test(message)) {
        setErrors({ date: message });
      } else {
        setErrors({ submit: message });
      }
    } finally {
      setSubmitting(false);
    }
  }

  const isDirty = Boolean(
    movementType || (!lockedArticle && article) || quantity || holderIn || player || match || expense || reason.trim(),
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Enregistrer un mouvement"
      size="md"
      level={level}
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
          onChange={selectSense}
          options={[
            { value: "in", label: "Entrée" },
            { value: "out", label: "Sortie" },
          ]}
        />
        <SegmentedControl
          label="Type"
          value={movementType}
          onChange={selectType}
          options={typeOptions}
          error={errors.type}
          help={
            movementType === "in_opening" ? "Pour le matériel que le club possédait avant d'utiliser Vesta." : undefined
          }
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
              onChange={selectArticle}
              searchArticles={searchArticles}
              mode={sense === "out" ? "out" : "in"}
            />
          )}
          {errors.article ? <p className="mt-1 text-xs text-status-danger-fg">{errors.article}</p> : null}
        </div>
        <NumberField label="Quantité" value={quantity} onChange={setQuantity} min={1} error={errors.quantity} />

        {sense === "in" ? (
          <div>
            <p className="mb-1 text-sm font-medium text-text">
              Qui reçoit le matériel ? <span className="font-normal text-text-muted">(facultatif)</span>
            </p>
            <HolderSearch value={holderIn} onChange={setHolderIn} canCreate ariaLabel="Qui reçoit le matériel ?" />
            {errors.holder ? <p className="mt-1 text-xs text-status-danger-fg">{errors.holder}</p> : null}
          </div>
        ) : showOutHolder ? (
          <HolderPicker
            label="D'où sort le matériel ?"
            rows={stockRows}
            value={holderOut}
            onChange={setHolderOut}
            error={errors.holder}
          />
        ) : null}

        {showProvenance ? (
          provenanceExpanded ? (
            <fieldset className="min-w-0 space-y-4 rounded-md border border-border p-3">
              <legend className="px-1 text-sm font-semibold text-text">Provenance</legend>
              <SegmentedControl
                label="Origine"
                value={originKind}
                onChange={(value) => {
                  setOriginKind(value);
                  if (value !== "donation") setDonor(null);
                }}
                options={ORIGIN_KIND_OPTIONS}
              />
              {originKind === "donation" ? (
                <div>
                  <p className="mb-1 text-sm font-medium text-text">Donateur</p>
                  <SearchCombobox<DonorOption>
                    value={donor}
                    onChange={setDonor}
                    search={searchDonors}
                    placeholder="Nom du joueur ou du donateur"
                    ariaLabel="Donateur"
                    emptyHint="Tapez le nom du donateur."
                    renderOption={(option) =>
                      option.membershipId === null ? (
                        <span className="text-sm text-primary-text">Utiliser « {option.name} » (hors club)</span>
                      ) : (
                        <span className="flex items-center gap-2 text-sm text-text">
                          <Avatar name={option.name} photoUrl={option.photoUrl} size={24} />
                          {option.name}
                        </span>
                      )
                    }
                    renderSelected={(option) =>
                      option.membershipId === null ? `${option.name} (hors club)` : option.name
                    }
                  />
                  {errors.donor ? <p className="mt-1 text-xs text-status-danger-fg">{errors.donor}</p> : null}
                </div>
              ) : null}
              <div>
                <label className="block text-sm font-medium text-text">
                  Date d'acquisition <span className="font-normal text-text-muted">(facultatif)</span>
                  <input
                    type="date"
                    value={acquisitionDate}
                    max={date || todayIsoDate()}
                    disabled={acquisitionUnknown}
                    onChange={(e) => setAcquisitionDate(e.target.value)}
                    className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base disabled:opacity-60"
                  />
                </label>
                {errors.acquisitionDate ? (
                  <p className="mt-1 text-xs text-status-danger-fg">{errors.acquisitionDate}</p>
                ) : (
                  <p className="mt-1 text-xs text-text-muted">Vide : la date d'enregistrement est retenue.</p>
                )}
                <div className="mt-2">
                  <Checkbox
                    checked={acquisitionUnknown}
                    onChange={(checked) => {
                      setAcquisitionUnknown(checked);
                      if (checked) setAcquisitionDate("");
                      else setAcquisitionNote("");
                    }}
                    label="Date inconnue"
                  />
                </div>
              </div>
              {acquisitionUnknown ? (
                <TextField
                  label="Précision sur la date"
                  optional
                  value={acquisitionNote}
                  onChange={setAcquisitionNote}
                  maxLength={60}
                  placeholder="Ex. : voir le comité précédent"
                  error={errors.acquisitionNote}
                />
              ) : null}
              <SegmentedControl
                label="État à l'entrée"
                value={conditionAtEntry}
                onChange={setConditionAtEntry}
                options={ARTICLE_CONDITION_OPTIONS}
                wrapOnMobile
              />
            </fieldset>
          ) : (
            <p className="text-sm text-text">
              Provenance : <span className="text-text-muted">non renseignée</span> ·{" "}
              <button
                type="button"
                onClick={() => setProvenanceExpanded(true)}
                className="-my-2 py-2 font-medium text-primary-text hover:underline"
              >
                Modifier
              </button>
            </p>
          )
        ) : null}

        <label className="block text-sm font-medium text-text">
          Date
          <input
            type="date"
            value={date}
            max={todayIsoDate()}
            onChange={(e) => setDate(e.target.value)}
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
          />
          {errors.date ? <p className="mt-1 text-xs text-status-danger-fg">{errors.date}</p> : null}
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
            <SearchCombobox<LinkableExpense>
              value={expense}
              onChange={setExpense}
              search={searchExpensesForMovement}
              placeholder="Catégorie, date ou montant"
              ariaLabel="Rechercher une dépense"
              emptyHint="Tapez une catégorie, une date ou un montant."
              renderOption={(row) => (
                <span className="text-sm text-text">
                  {row.reference} · {formatDateFr(row.expense_date)} · {row.category} · {row.amount} {row.currency}
                </span>
              )}
              renderSelected={(row) =>
                `${row.reference} · ${formatDateFr(row.expense_date)} · ${row.category} · ${row.amount} ${row.currency}`
              }
            />
            <p className="mt-1 text-xs text-text-muted">Rattachez l'achat à la dépense saisie par la trésorerie.</p>
          </div>
        ) : null}
        <TextArea label="Motif" optional value={reason} onChange={setReason} maxLength={500} />
        {errors.submit ? <p className="text-sm text-status-danger-fg">{errors.submit}</p> : null}
      </div>
    </Modal>
  );
}
