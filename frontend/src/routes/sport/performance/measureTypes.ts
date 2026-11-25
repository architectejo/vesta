import type { BulkPerformanceInput, BulkPerformanceItem } from "../../../api/performance";

/** Valeur brute d'une mesure (une seule des quatre, ou un abandon). */
export type ItemFields = Pick<BulkPerformanceItem, "time_ms" | "distance_m" | "count" | "value" | "outcome">;

/** Mesure saisie à l'écran, pas encore envoyée. */
export interface DraftItem {
  membershipId: number;
  name: string;
  attemptNo: number;
  fields: ItemFields;
  /** Texte lisible pour le récapitulatif (« 4,52 s », « Abandon »). */
  label: string;
}

/** Lot mis en file hors connexion (6.6) : le corps exact qui sera envoyé à l'API. */
export interface PendingMeasureBatch {
  eventId: number;
  testName: string;
  body: BulkPerformanceInput;
  /** Nom et valeur lisible de chaque mesure, par `client_uuid` d'item (affichage local seulement). */
  meta: Record<string, { name: string; label: string }>;
}

/** Mesure refusée par l'API pour un joueur, gardée sur le téléphone. */
export interface RefusedMeasure {
  id: string;
  eventId: number;
  testId: number;
  testName: string;
  name: string;
  label: string;
  message: string;
  item: BulkPerformanceItem;
  method: BulkPerformanceInput["method"];
  startMode: BulkPerformanceInput["start_mode"];
  lotUuid: string;
}
