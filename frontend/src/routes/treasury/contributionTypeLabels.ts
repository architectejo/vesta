import type { ContributionNature, ContributionPeriodicity, ContributionType } from "../../api/treasury";

export const NATURE_LABELS: Record<ContributionNature, string> = {
  mandatory: "Obligatoire",
  free: "Libre",
};

export const PERIODICITY_LABELS: Record<ContributionPeriodicity, string> = {
  monthly: "Mensuelle",
  annual: "Annuelle",
  one_off: "Ponctuelle",
};

export const PERIODICITY_OPTIONS: ReadonlyArray<readonly [ContributionPeriodicity, string]> = [
  ["monthly", PERIODICITY_LABELS.monthly],
  ["annual", PERIODICITY_LABELS.annual],
  ["one_off", PERIODICITY_LABELS.one_off],
];

/** Ligne de résumé d'un type : « Obligatoire · Mensuelle · 20.00 ». */
export function describeContributionType(type: ContributionType): string {
  const parts = [NATURE_LABELS[type.nature], PERIODICITY_LABELS[type.periodicity]];
  if (type.amount) parts.push(type.amount);
  return parts.join(" · ");
}
