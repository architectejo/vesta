/**
 * Liste de pays en français, pour le champ « Pays » à suggestions
 * (clubs-creation.md §4.1 : « choix dans la liste »). Donnée statique, pas
 * une règle métier : aucune information de club n'y figure.
 */
export const FRENCH_COUNTRY_NAMES: string[] = [
  "République démocratique du Congo",
  "République du Congo",
  "Rwanda",
  "Burundi",
  "Ouganda",
  "Kenya",
  "Tanzanie",
  "Zambie",
  "Angola",
  "Cameroun",
  "Côte d'Ivoire",
  "Sénégal",
  "Mali",
  "Bénin",
  "Togo",
  "Gabon",
  "Belgique",
  "France",
  "Canada",
  "États-Unis",
].sort((a, b) => a.localeCompare(b, "fr"));

/** Fuseau par défaut proposé pour un pays, en tête de liste (clubs-creation.md §4.1). */
export const DEFAULT_TIMEZONE_BY_COUNTRY: Record<string, string> = {
  "République démocratique du Congo": "Africa/Kinshasa",
  "République du Congo": "Africa/Brazzaville",
  Rwanda: "Africa/Kigali",
  Burundi: "Africa/Bujumbura",
  Ouganda: "Africa/Kampala",
  Kenya: "Africa/Nairobi",
  Tanzanie: "Africa/Dar_es_Salaam",
  Zambie: "Africa/Lusaka",
  Angola: "Africa/Luanda",
  Cameroun: "Africa/Douala",
  "Côte d'Ivoire": "Africa/Abidjan",
  Sénégal: "Africa/Dakar",
  Mali: "Africa/Bamako",
  Bénin: "Africa/Porto-Novo",
  Togo: "Africa/Lome",
  Gabon: "Africa/Libreville",
  Belgique: "Europe/Brussels",
  France: "Europe/Paris",
  Canada: "America/Toronto",
  "États-Unis": "America/New_York",
};
