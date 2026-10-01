import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import {
  closeInventory,
  justifyInventoryLine,
  listArticles,
  getInventory,
  type DiscrepancyReason,
  type InventoryLine,
} from "../../api/logistics";
import { Button, ConfirmDialog, DataTable, Modal, StatusBadge, type DataTableColumn } from "../../design-system";
import { formatDateFr } from "./format";
import { JustifyDiscrepancyModal } from "./JustifyDiscrepancyModal";
import type { StatusKey } from "../../design-system";

function rowStatusKey(status: RowStatus): StatusKey {
  if (status === "to_count") return "inventory_line_to_count";
  if (status === "no_gap") return "inventory_line_no_gap";
  if (status === "justified") return "inventory_line_justified";
  return "to_justify";
}

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

type RowStatus = "to_count" | "to_justify" | "justified" | "no_gap";

interface DisplayRow {
  article_id: number;
  article_name: string;
  theoretical: number | null;
  physical: number | null;
  discrepancy: number | null;
  discrepancy_reason: string;
  status: RowStatus;
  line: InventoryLine | null;
}

const CHIP_OPTIONS: Array<{ value: "all" | RowStatus; label: string }> = [
  { value: "all", label: "Tous" },
  { value: "to_count", label: "À compter" },
  { value: "to_justify", label: "Écarts à justifier" },
  { value: "justified", label: "Justifiés" },
];

export interface InventoryDetailModalProps {
  inventoryId: number | null;
  canManage: boolean;
  onClose: () => void;
  onOpenCount: () => void;
  onClosed: (message: string) => void;
}

/** « Inventaire du {trimestre} » (détail) — fiche `logistique.md` §4.9. */
export function InventoryDetailModal({ inventoryId, canManage, onClose, onOpenCount, onClosed }: InventoryDetailModalProps) {
  const open = inventoryId !== null;
  const [chip, setChip] = useState<"all" | RowStatus>("all");
  const [justifyLine, setJustifyLine] = useState<InventoryLine | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [closeError, setCloseError] = useState<string | undefined>(undefined);
  const [closing, setClosing] = useState(false);

  const inventoryQuery = useQuery({
    queryKey: ["logistics", "inventory", inventoryId],
    queryFn: () => getInventory(inventoryId as number),
    enabled: open,
  });
  const articlesQuery = useQuery({
    queryKey: ["logistics", "articles", "active-for-inventory"],
    queryFn: () => listArticles(),
    enabled: open,
  });

  const inventory = inventoryQuery.data;
  const rows = useMemo<DisplayRow[]>(() => {
    if (!inventory) return [];
    const linesByArticle = new Map((inventory.lines ?? []).map((line) => [line.article_id, line]));
    const articles = articlesQuery.data?.results ?? [];
    const seen = new Set<number>();
    const result: DisplayRow[] = [];
    for (const article of articles) {
      seen.add(article.id);
      const line = linesByArticle.get(article.id) ?? null;
      result.push({
        article_id: article.id,
        article_name: article.name,
        theoretical: line ? line.theoretical_quantity : null,
        physical: line ? line.physical_quantity : null,
        discrepancy: line ? line.discrepancy : null,
        discrepancy_reason: line?.discrepancy_reason ?? "",
        status: line ? (line.status as RowStatus) : "to_count",
        line,
      });
    }
    // Article compté puis archivé entre-temps : la ligne reste visible.
    for (const line of inventory.lines ?? []) {
      if (!seen.has(line.article_id)) {
        result.push({
          article_id: line.article_id,
          article_name: line.article_name,
          theoretical: line.theoretical_quantity,
          physical: line.physical_quantity,
          discrepancy: line.discrepancy,
          discrepancy_reason: line.discrepancy_reason,
          status: line.status as RowStatus,
          line,
        });
      }
    }
    return result;
  }, [inventory, articlesQuery.data]);

  const filteredRows =
    chip === "all"
      ? rows
      : chip === "justified"
        ? rows.filter((r) => r.status === "justified" || r.status === "no_gap")
        : rows.filter((r) => r.status === chip);

  const countedCount = rows.filter((r) => r.status !== "to_count").length;
  const toJustifyCount = rows.filter((r) => r.status === "to_justify").length;

  async function handleJustify(reason: DiscrepancyReason): Promise<void> {
    if (!justifyLine) return;
    await justifyInventoryLine(justifyLine.id, reason);
    setJustifyLine(null);
    void inventoryQuery.refetch();
  }

  async function handleClose(): Promise<void> {
    if (!inventory) return;
    setClosing(true);
    setCloseError(undefined);
    try {
      await closeInventory(inventory.id);
      setConfirmClose(false);
      onClosed(`Inventaire du ${inventory.quarter_label_display} clôturé.`);
    } catch (error) {
      setCloseError(apiErrorMessage(error));
    } finally {
      setClosing(false);
    }
  }

  const columns: Array<DataTableColumn<DisplayRow>> = [
    { key: "article", header: "Article", widthPx: 180, render: (row) => row.article_name },
    {
      key: "theoretical",
      header: "Théorique",
      align: "right",
      render: (row) => (row.theoretical ?? row.theoretical === 0 ? row.theoretical : "—"),
    },
    {
      key: "physical",
      header: "Compté",
      align: "right",
      render: (row) => (row.physical ?? row.physical === 0 ? row.physical : "—"),
    },
    {
      key: "discrepancy",
      header: "Écart",
      align: "right",
      render: (row) =>
        row.discrepancy === null
          ? "—"
          : `${row.discrepancy > 0 ? "+" : ""}${row.discrepancy}`,
    },
    {
      key: "cause",
      header: "Cause",
      render: (row) => {
        const map: Record<string, string> = { theft: "Vol", wear: "Usure", oversight: "Oubli", loss: "Perte" };
        return row.discrepancy_reason ? map[row.discrepancy_reason] ?? row.discrepancy_reason : "—";
      },
    },
    {
      key: "status",
      header: "Statut",
      render: (row) => <StatusBadge status={rowStatusKey(row.status)} />,
    },
  ];

  const canJustifyRows = canManage && inventory?.status === "open";

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={inventory ? `Inventaire du ${inventory.quarter_label_display}` : "Inventaire"}
        subtitle={
          inventory
            ? `Ouvert le ${formatDateFr(inventory.opened_at.slice(0, 10))} par ${inventory.opened_by.name}${
                inventory.closed_at
                  ? ` · clôturé le ${formatDateFr(inventory.closed_at.slice(0, 10))} par ${inventory.closed_by?.name ?? ""}`
                  : ""
              }`
            : undefined
        }
        size="lg"
        loading={inventoryQuery.isLoading}
        footer={
          <div className="flex w-full flex-wrap items-center justify-end gap-2">
            <Button variant="secondary" size="md" onClick={onClose}>
              Fermer
            </Button>
            {canManage && inventory?.status === "open" ? (
              <>
                <Button variant="secondary" size="md" onClick={() => setConfirmClose(true)}>
                  Clôturer l'inventaire
                </Button>
                <Button variant="primary" size="md" onClick={onOpenCount}>
                  Saisir le comptage
                </Button>
              </>
            ) : null}
          </div>
        }
      >
        {inventoryQuery.isError ? (
          <p role="alert" className="text-sm text-status-danger-fg">
            Impossible de charger l'inventaire. Réessayez.
          </p>
        ) : inventory ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <StatusBadge status={inventory.status === "closed" ? "inventory_closed" : "inventory_open"} />
            </div>
            <p className="text-sm text-text-muted">
              {countedCount} articles comptés sur {rows.length} · {toJustifyCount} écarts à justifier
            </p>
            <DataTable
              columns={columns}
              rows={filteredRows}
              getRowId={(row) => row.article_id}
              loading={articlesQuery.isLoading}
              stickyFirstColumn
              getSearchableText={(row) => row.article_name}
              searchPlaceholder="Rechercher un article"
              resultLabel="articles"
              filtersSlot={
                <div className="flex flex-wrap gap-1">
                  {CHIP_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setChip(option.value)}
                      className={[
                        "h-control-sm rounded-full border px-3 text-xs font-medium",
                        chip === option.value
                          ? "border-primary bg-primary text-on-primary"
                          : "border-border-strong bg-surface text-text",
                      ].join(" ")}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              }
              onRowClick={
                canJustifyRows
                  ? (row) => {
                      if (row.line && (row.status === "to_justify" || row.status === "justified")) {
                        setJustifyLine(row.line);
                      }
                    }
                  : undefined
              }
            />
          </div>
        ) : null}
      </Modal>

      <JustifyDiscrepancyModal line={justifyLine} onClose={() => setJustifyLine(null)} onSubmit={handleJustify} />

      <ConfirmDialog
        open={confirmClose}
        title={inventory ? `Clôturer l'inventaire du ${inventory.quarter_label_display} ?` : "Clôturer l'inventaire ?"}
        description={
          <>
            <span>
              Les comptages et les justifications ne pourront plus être modifiés. L'inventaire du trimestre suivant
              pourra ensuite être ouvert.
            </span>
            {closeError ? <span className="mt-2 block text-status-danger-fg">{closeError}</span> : null}
          </>
        }
        confirmLabel="Clôturer"
        danger={false}
        loading={closing}
        onConfirm={() => void handleClose()}
        onCancel={() => setConfirmClose(false)}
      />
    </>
  );
}
