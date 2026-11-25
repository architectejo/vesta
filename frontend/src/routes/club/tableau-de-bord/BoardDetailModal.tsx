import type { ComponentType } from "react";
import { Modal, PeriodPicker, type PeriodPickerProps } from "../../../design-system";
import type { BoardPeriodQuery } from "../../../api/clubBoardDashboard";
import type { CardOpenKey } from "./BoardCards";
import {
  AttendanceDetail,
  AttendanceRankingDetail,
  CashDetail,
  CoachNotesDetail,
  ContributionsDetail,
  DisciplineDetail,
  EquipmentDetail,
  ExpensesDetail,
  FeedDetail,
  FitnessDetail,
  NewcomersDetail,
  ResultsDetail,
  SquadStatusDetail,
  SquadTrendDetail,
  ToProcessDetail,
  UpcomingDetail,
  type DetailProps,
} from "./BoardDetails";

interface DetailEntry {
  title: string;
  Component: ComponentType<DetailProps>;
  /** Carte « instantanée » : ignore le filtre de période (fiche §3). */
  instant?: boolean;
}

export const DETAIL_ENTRIES: Record<CardOpenKey, DetailEntry> = {
  attendance: { title: "Présences", Component: AttendanceDetail },
  contributions: { title: "Cotisations", Component: ContributionsDetail },
  squad_status: { title: "Situation de l'effectif", Component: SquadStatusDetail, instant: true },
  cash: { title: "Caisse : encaissements et dépenses", Component: CashDetail },
  results: { title: "Résultats", Component: ResultsDetail },
  discipline: { title: "Discipline", Component: DisciplineDetail },
  newcomers: { title: "Nouveaux venus", Component: NewcomersDetail },
  fitness: { title: "Aptitude de l'effectif", Component: FitnessDetail, instant: true },
  upcoming: { title: "Prochaines échéances", Component: UpcomingDetail, instant: true },
  expenses_by_category: { title: "Dépenses par catégorie", Component: ExpensesDetail },
  squad_trend: { title: "Évolution de l'effectif", Component: SquadTrendDetail },
  attendance_ranking: { title: "Assiduité par joueur", Component: AttendanceRankingDetail },
  to_process: { title: "À traiter", Component: ToProcessDetail, instant: true },
  equipment_out: { title: "Matériel à retourner", Component: EquipmentDetail, instant: true },
  coach_notes: { title: "Notes du Coach", Component: CoachNotesDetail },
  feed_activity: { title: "Activité du fil", Component: FeedDetail },
};

interface BoardDetailModalProps {
  cardKey: CardOpenKey;
  currency: string;
  periodLabel: string;
  period: BoardPeriodQuery | null;
  picker: Pick<PeriodPickerProps, "value" | "onChange" | "seasons">;
  onClose: () => void;
}

/**
 * Modale de détail d'une carte (fiche §5, règle 14) : lecture seule, graphique
 * agrandi puis listes paginées. Le filtre de période est repris ici et se
 * modifie sans fermer la modale.
 */
export function BoardDetailModal({ cardKey, currency, periodLabel, period, picker, onClose }: BoardDetailModalProps) {
  const entry = DETAIL_ENTRIES[cardKey];
  const { Component } = entry;
  return (
    <Modal
      open
      onClose={onClose}
      title={entry.title}
      subtitle={entry.instant ? "Aujourd'hui" : periodLabel}
      size="lg"
      cancelLabel="Fermer"
    >
      <div className="space-y-4">
        {entry.instant ? null : <PeriodPicker {...picker} />}
        <Component period={period} currency={currency} />
      </div>
    </Modal>
  );
}
