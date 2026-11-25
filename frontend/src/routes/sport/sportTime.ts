/**
 * Petits utilitaires de date/heure partagés par les écrans du Lot 3.
 * Simplification documentée au compte rendu : combine une date et une
 * heure saisies comme si elles étaient dans le fuseau du navigateur (en
 * pratique celui du club, l'équipe opérant sur place) — aucun fuseau de
 * club n'est chargé par ces écrans, à la différence de
 * `routes/treasury/money.ts` qui en a besoin pour la Caisse Terrain
 * Express.
 */

import type { NextEvent } from "../../api/sport";

export function combineDateTimeToIso(dateStr: string, timeStr: string): string {
  const normalizedTime = timeStr.length === 5 ? `${timeStr}:00` : timeStr;
  return new Date(`${dateStr}T${normalizedTime}`).toISOString();
}

export function formatTime(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export function nowTimeHHMM(): string {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

/** Date du jour au format « YYYY-MM-DD » (fuseau local du navigateur), même
 * calcul que `routes/logistics/format.ts#todayIsoDate`. */
export function todayIsoDate(): string {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}

/** « dimanche 4 octobre » à partir d'une date « YYYY-MM-DD » — format
 * partagé par `ProchainRendezVousCard` (accueil) et `VestiairePage`
 * (vestiaire, état vide « Prochain rendez-vous »), pour ne pas inventer
 * deux formats de date différents pour la même information. */
export function formatDateLong(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" }).format(date);
}

/** « Séance · dimanche 4 octobre · 07:30 » (exemple donné par
 * `sport-vestiaire.md` §6) ou « Match contre {adversaire} · {date} ·
 * {heure} » — texte de précision « Prochain rendez-vous : … » partagé par
 * `VestiairePage` (état vide) et `ProchainRendezVousCard` (accueil), même
 * source API (`getLockerRoom`, champ `next_event`). */
export function formatNextEventLabel(nextEvent: NextEvent): string {
  const date = formatDateLong(nextEvent.event_date);
  if (nextEvent.type === "session") {
    return `Séance · ${date} · ${nextEvent.gathering_time.slice(0, 5)}`;
  }
  return `Match contre ${nextEvent.opponent} · ${date} · ${nextEvent.kickoff_time.slice(0, 5)}`;
}
