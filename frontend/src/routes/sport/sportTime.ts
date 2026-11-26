/**
 * Petits utilitaires de date/heure partagés par les écrans du sport.
 *
 * Dates stockées en UTC, affichées dans le fuseau du CLUB (CLAUDE.md §7) :
 * chaque fonction accepte le fuseau IANA du club (`useClubTimeZone()`). Sans
 * fuseau connu (`undefined`), on retombe sur celui du téléphone, comme avant.
 */

import { useQuery } from "@tanstack/react-query";
import { getMyProfile } from "../../api/clubs";
import type { NextEvent } from "../../api/sport";

/** Fuseau valide pour `Intl`, sinon `undefined` (fuseau du téléphone). */
function safeZone(timeZone: string | null | undefined): string | undefined {
  if (!timeZone) return undefined;
  try {
    new Intl.DateTimeFormat("fr-FR", { timeZone });
    return timeZone;
  } catch {
    return undefined;
  }
}

interface WallClock {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
}

/** Heure murale d'un instant dans un fuseau donné. */
function wallClockIn(date: Date, timeZone: string | undefined): WallClock {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(date);
  const get = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  return { year: get("year"), month: get("month"), day: get("day"), hour: get("hour"), minute: get("minute"), second: get("second") };
}

const pad2 = (n: number) => String(n).padStart(2, "0");

/**
 * Une date et une heure saisies (« heure du club ») → instant ISO UTC.
 * Deux passes pour tomber juste autour d'un changement d'heure.
 */
export function combineDateTimeToIso(dateStr: string, timeStr: string, timeZone?: string | null): string {
  const normalizedTime = timeStr.length === 5 ? `${timeStr}:00` : timeStr;
  const zone = safeZone(timeZone);
  if (!zone) return new Date(`${dateStr}T${normalizedTime}`).toISOString();
  const target = Date.parse(`${dateStr}T${normalizedTime}Z`);
  if (Number.isNaN(target)) return new Date(Number.NaN).toISOString();
  let guess = target;
  for (let i = 0; i < 2; i += 1) {
    const w = wallClockIn(new Date(guess), zone);
    const shown = Date.UTC(w.year, w.month - 1, w.day, w.hour, w.minute, w.second);
    guess += target - shown;
  }
  return new Date(guess).toISOString();
}

export function formatTime(iso: string | null, timeZone?: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", timeZone: safeZone(timeZone) });
  } catch {
    return "";
  }
}

/** « HH:MM » de l'instant présent, à l'heure du club. */
export function nowTimeHHMM(timeZone?: string | null, now: Date = new Date()): string {
  const w = wallClockIn(now, safeZone(timeZone));
  return `${pad2(w.hour)}:${pad2(w.minute)}`;
}

/** Date du jour « YYYY-MM-DD », à l'heure du club. */
export function todayIsoDate(timeZone?: string | null, now: Date = new Date()): string {
  const w = wallClockIn(now, safeZone(timeZone));
  return `${w.year}-${pad2(w.month)}-${pad2(w.day)}`;
}

/**
 * Fuseau du club connecté, lu dans le profil (`profile/me`, même cache que
 * les écrans). `undefined` tant qu'il n'est pas connu : fuseau du téléphone.
 */
export function useClubTimeZone(): string | undefined {
  const query = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  return safeZone(query.data?.club.timezone);
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
