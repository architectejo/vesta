import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { listHolders, type Holder, type HolderKind, type StockRow } from "../../api/logistics";
import { Avatar, IconAdd, IconPin } from "../../design-system";
import { HolderFormModal } from "./HolderFormModal";
import { normalizeText, piecesLabel } from "./materielLabels";
import { SearchCombobox } from "./SearchCombobox";

/** Détenteur choisi ; `id: null` = « Non localisé ». */
export interface HolderSelection {
  id: number | null;
  name: string;
}

export const UNLOCATED_LABEL = "Non localisé";

export const HOLDERS_QUERY_KEY = ["logistics", "holders"] as const;

type OptionId = number | "none" | "create";

interface HolderOption {
  id: OptionId;
  name: string;
  kind?: HolderKind;
  pieces?: number;
}

export interface HolderSearchProps {
  value: HolderSelection | null;
  onChange: (value: HolderSelection | null) => void;
  /** Propose « Non localisé » (filtres, retour de match). */
  allowUnlocated?: boolean;
  /**
   * Destination d'un mouvement (défaut) : jamais d'archivés ni de joueurs
   * partis (l'API les refuse). `filter` : les joueurs partis restent
   * proposés, puisqu'ils peuvent encore détenir du matériel.
   */
  purpose?: "destination" | "filter";
  /** Intendant : dernière option « + Ajouter un détenteur » (modale niveau 2). */
  canCreate?: boolean;
  /**
   * Limite le choix à ces lignes de stock (bascule de `HolderPicker` au-delà
   * de 5 sources) ; la liste des détenteurs n'est alors pas chargée.
   */
  sourceRows?: StockRow[];
  ariaLabel?: string;
  placeholder?: string;
  disabled?: boolean;
}

/**
 * Recherche d'un détenteur (spec B4 §0). Aucune route de recherche côté
 * API : `GET holders/` est filtré ici, casse et accents normalisés
 * (écart n° 4). Le nombre de pièces vient toujours de l'API.
 */
export function HolderSearch({
  value,
  onChange,
  allowUnlocated = false,
  purpose = "destination",
  canCreate = false,
  sourceRows,
  ariaLabel = "Rechercher un détenteur",
  placeholder = "Nom du joueur ou du lieu",
  disabled,
}: HolderSearchProps) {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);

  const search = useCallback(
    async (query: string): Promise<HolderOption[]> => {
      const needle = normalizeText(query);
      let options: HolderOption[];
      if (sourceRows) {
        options = sourceRows.map((row) => ({
          id: row.holder_id ?? "none",
          name: row.holder_name,
          kind: row.holder?.kind,
          pieces: row.quantity,
        }));
      } else {
        const data = await queryClient.fetchQuery({
          queryKey: [...HOLDERS_QUERY_KEY, "list", false],
          queryFn: () => listHolders(false),
          staleTime: 30_000,
        });
        options = data.results
          .filter((holder: Holder) => holder.status === "active")
          .filter((holder: Holder) => purpose === "filter" || !holder.has_left_club)
          .map((holder: Holder) => ({
            id: holder.id,
            name: holder.name,
            kind: holder.kind,
            pieces: holder.stock_total,
          }));
        if (allowUnlocated) {
          options.push({ id: "none", name: UNLOCATED_LABEL, pieces: data.unlocated.stock_total });
        }
      }
      const filtered = needle ? options.filter((option) => normalizeText(option.name).includes(needle)) : options;
      if (canCreate && !sourceRows) {
        filtered.push({ id: "create", name: "+ Ajouter un détenteur" });
      }
      return filtered;
    },
    [sourceRows, queryClient, purpose, allowUnlocated, canCreate],
  );

  const selected: HolderOption | null = value ? { id: value.id ?? "none", name: value.name } : null;

  return (
    <>
      <SearchCombobox<HolderOption>
        value={selected}
        onChange={(option) => {
          if (!option) {
            onChange(null);
            return;
          }
          if (option.id === "create") {
            setCreateOpen(true);
            return;
          }
          onChange({ id: option.id === "none" ? null : option.id, name: option.name });
        }}
        search={search}
        searchOnEmpty
        maxResults={50}
        placeholder={placeholder}
        ariaLabel={ariaLabel}
        disabled={disabled}
        renderOption={(option) =>
          option.id === "create" ? (
            <span className="flex items-center gap-2 text-sm font-medium text-primary-text">
              <IconAdd aria-hidden="true" className="h-4 w-4" />
              Ajouter un détenteur
            </span>
          ) : (
            <span className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-2">
                {option.kind === "member" ? (
                  <Avatar name={option.name} size={24} />
                ) : (
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-muted text-text-muted">
                    <IconPin aria-hidden="true" className="h-3.5 w-3.5" />
                  </span>
                )}
                <span
                  className={["truncate text-sm", option.id === "none" ? "text-text-muted" : "text-text"].join(" ")}
                >
                  {option.name}
                </span>
              </span>
              {option.pieces !== undefined ? (
                <span className="shrink-0 tabular-nums text-sm text-text-muted">{piecesLabel(option.pieces)}</span>
              ) : null}
            </span>
          )
        }
        renderSelected={(option) => option.name}
      />
      {canCreate ? (
        <HolderFormModal
          open={createOpen}
          level={2}
          onClose={() => setCreateOpen(false)}
          onCreated={(holder) => {
            setCreateOpen(false);
            void queryClient.invalidateQueries({ queryKey: HOLDERS_QUERY_KEY });
            onChange({ id: holder.id, name: holder.name });
          }}
        />
      ) : null}
    </>
  );
}
