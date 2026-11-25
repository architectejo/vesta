import { useEffect, useRef, useState } from "react";
import "./PlayerTradingCard.css";

export type PlayerTradingCardMotion = "interactive" | "static";
export type PlayerTradingCardSize = "md" | "sm";

/**
 * Six indicateurs de la partie B (club-carte-joueur.md B1/B2.3). `null` sur
 * un champ isolé n'existe pas : c'est l'objet entier qui est `null` ou
 * `undefined` tant que l'API ne sert pas encore de statistiques (B2.1).
 * `averageRating` est sur 10 ; les autres sont des entiers réels (« 0 » est
 * une vraie valeur, jamais un texte vide).
 */
export interface PlayerTradingCardStats {
  matchesPlayed: number;
  goals: number;
  assists: number;
  yellowCards: number;
  redCards: number;
  /** Pourcentage, ou `null` : « — » (aucune séance ni match pointé). */
  attendanceRate: number | null;
  /** Sur 10, ou `null` : « — » (aucune évaluation). */
  averageRating: number | null;
}

/** Tokens de couleur d'un *autre* club (comparaison, B2.1 `palette`),
 * posés en variables CSS sur la carte seule — jamais globalement. */
export interface PlayerTradingCardPalette {
  from: string;
  to: string;
  fg: string;
  fgMuted: string;
  bandBg: string;
  bandFg: string;
  frame: string;
  frameHighlight: string;
}

export interface PlayerTradingCardProps {
  firstName: string;
  lastName: string;
  /** `null` : silhouette (A4.4). */
  photoUrl?: string | null;
  /** Vide : « Poste non renseigné » (A4.1). */
  positionLabel?: string;
  /** Poste précis, facultatif. */
  positionDetail?: string;
  /** `null` : pas de numéro affiché sur la carte (A4.3). */
  jerseyNumber?: number | null;
  /** Partie A : `useClubBranding().logoUrl`. */
  clubLogoUrl?: string | null;
  /** Sert seulement au texte alternatif du logo. Partie A : `useClubBranding().name`. */
  clubName?: string;
  /**
   * `"interactive"` (défaut) : inclinaison au survol sur ordinateur, relief
   * fixe + animation d'ouverture sur mobile (A5). `"static"` : aucune
   * animation ni interaction (ex. capture, comparaison au Lot 4).
   */
  motion?: PlayerTradingCardMotion;
  /**
   * Partie B (B2.2). Absent (`undefined`) : comportement de la partie A
   * inchangé (numéro de maillot en colonne gauche). Fourni (y compris
   * `null`, « pas encore de donnée ») : la colonne gauche affiche la note
   * globale et le numéro passe dans le bandeau du nom (« n° {n} · {Nom} »).
   */
  overallRating?: number | null;
  /**
   * Partie B (B2.3). `undefined`/`null` : pied de la partie A
   * (« Statistiques à venir »). Objet : grille des six indicateurs. Le
   * composant ne calcule jamais ces valeurs, ne fait aucun appel réseau.
   */
  stats?: PlayerTradingCardStats | null;
  /** « Saison {saison} » sous la carte, hors cadre (B2.3). */
  seasonLabel?: string;
  /** `"md"` (280 px, défaut) ou `"sm"` (168 px, comparaison : note, photo, nom, poste seulement, B2.1). */
  size?: PlayerTradingCardSize;
  /** Fourni : la carte devient un bouton « Voir la fiche détaillée de {prénom} {nom} » (B2.5). */
  onOpen?: () => void;
  /** Couleurs d'un autre club, posées sur cette carte seule (comparaison, B2.1). */
  palette?: PlayerTradingCardPalette;
  className?: string;
}

function paletteStyleVars(palette: PlayerTradingCardPalette | undefined): Record<string, string> {
  if (!palette) return {};
  return {
    "--color-player-card-from": palette.from,
    "--color-player-card-to": palette.to,
    "--color-player-card-fg": palette.fg,
    "--color-player-card-fg-muted": palette.fgMuted,
    "--color-player-card-band-bg": palette.bandBg,
    "--color-player-card-band-fg": palette.bandFg,
    "--color-player-card-frame": palette.frame,
    "--color-player-card-frame-highlight": palette.frameHighlight,
  };
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function supportsHoverTilt(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(hover: hover) and (pointer: fine)").matches;
}

/** Silhouette de joueur générique (A4.4), affichée sans photo ou si elle échoue au chargement. */
function PlayerSilhouette() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 100 100"
      className="h-1/2 w-1/2"
      fill="none"
      stroke="var(--color-player-card-fg-muted)"
      strokeWidth={4}
    >
      <circle cx="50" cy="30" r="16" />
      <path d="M20 88c2-22 14-34 30-34s28 12 30 34" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * Carte de joueur style FC/FIFA (docs/ecrans/club-carte-joueur.md, partie A).
 * Ne fait aucun appel réseau ; ne présente que des données réelles reçues en
 * propriétés (aucune statistique ni note inventée, CLAUDE.md §3).
 *
 * Structure en trois niveaux (A5.3) : conteneur `perspective` > élément
 * incliné (transform + ombre) > carte découpée (`clip-path`, cadre, fond,
 * contenu). Les mises à jour d'inclinaison au survol écrivent directement
 * des variables CSS sur le DOM via `requestAnimationFrame`, jamais par un
 * état React (A5.1).
 */
export function PlayerTradingCard({
  firstName,
  lastName,
  photoUrl = null,
  positionLabel = "",
  positionDetail = "",
  jerseyNumber = null,
  clubLogoUrl = null,
  clubName = "",
  motion = "interactive",
  overallRating,
  stats = null,
  seasonLabel,
  size = "md",
  onOpen,
  palette,
  className = "",
}: PlayerTradingCardProps) {
  const fullName = `${firstName} ${lastName}`.trim();
  const [photoFailed, setPhotoFailed] = useState(false);
  const showPhoto = Boolean(photoUrl) && !photoFailed;
  const isPartieB = overallRating !== undefined;
  const isSmall = size === "sm";
  const photoSizePx = isSmall ? 88 : 152;

  const tiltRef = useRef<HTMLDivElement | null>(null);
  const photoRef = useRef<HTMLDivElement | null>(null);
  const leftColRef = useRef<HTMLDivElement | null>(null);
  const rafRef = useRef<number | null>(null);
  // Animation d'ouverture unique, sur tous les appareils (A5.2), décidée une
  // fois pour toutes au montage (jamais réévaluée : `motion` ne change pas en
  // pratique). Coupée par `prefers-reduced-motion` (déjà réduite à ~0
  // globalement par tokens.css ; on évite en plus de déclencher un nouveau
  // cycle inutilement).
  const [enterAnimation] = useState(() => motion === "interactive" && !prefersReducedMotion());

  // Inclinaison au survol de la souris (A5.1), ordinateur seulement.
  useEffect(() => {
    if (motion !== "interactive" || prefersReducedMotion() || !supportsHoverTilt()) return undefined;
    const node = tiltRef.current;
    if (!node) return undefined;

    function scheduleUpdate(clientX: number, clientY: number): void {
      if (rafRef.current !== null) return;
      rafRef.current = window.requestAnimationFrame(() => {
        rafRef.current = null;
        const rect = node!.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        const x = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
        const y = Math.min(1, Math.max(0, (clientY - rect.top) / rect.height));
        const rotateY = (x - 0.5) * 16;
        const rotateX = (0.5 - y) * 16;
        node!.style.transition = "none";
        node!.style.setProperty("--rx", `${rotateX.toFixed(2)}deg`);
        node!.style.setProperty("--ry", `${rotateY.toFixed(2)}deg`);
        node!.style.setProperty("--mx", `${(x * 100).toFixed(1)}%`);
        node!.style.setProperty("--my", `${(y * 100).toFixed(1)}%`);
        const relX = x - 0.5;
        const relY = y - 0.5;
        if (photoRef.current) {
          photoRef.current.style.setProperty("--photo-tx", `${(relX * 12).toFixed(1)}px`);
          photoRef.current.style.setProperty("--photo-ty", `${(relY * 12).toFixed(1)}px`);
        }
        if (leftColRef.current) {
          leftColRef.current.style.setProperty("--left-tx", `${(relX * 6).toFixed(1)}px`);
          leftColRef.current.style.setProperty("--left-ty", `${(relY * 6).toFixed(1)}px`);
        }
      });
    }

    function handlePointerMove(event: PointerEvent): void {
      if (event.pointerType !== "mouse") return;
      scheduleUpdate(event.clientX, event.clientY);
    }

    function handlePointerLeave(): void {
      if (rafRef.current !== null) {
        window.cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      node!.style.transition = "transform var(--duration-slow) var(--ease-out)";
      node!.style.setProperty("--rx", "0deg");
      node!.style.setProperty("--ry", "0deg");
      node!.style.setProperty("--mx", "50%");
      node!.style.setProperty("--my", "50%");
      photoRef.current?.style.setProperty("--photo-tx", "0px");
      photoRef.current?.style.setProperty("--photo-ty", "0px");
      leftColRef.current?.style.setProperty("--left-tx", "0px");
      leftColRef.current?.style.setProperty("--left-ty", "0px");
    }

    node.addEventListener("pointermove", handlePointerMove);
    node.addEventListener("pointerleave", handlePointerLeave);
    return () => {
      node.removeEventListener("pointermove", handlePointerMove);
      node.removeEventListener("pointerleave", handlePointerLeave);
      if (rafRef.current !== null) window.cancelAnimationFrame(rafRef.current);
    };
  }, [motion]);

  const tiltClassName = [
    "player-trading-card__tilt",
    enterAnimation ? "player-trading-card__tilt--enter" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const nameBandPrefix = isPartieB && jerseyNumber !== null && jerseyNumber !== undefined ? `n° ${jerseyNumber} · ` : "";

  const cardInner = (
    <div ref={tiltRef} className={tiltClassName}>
      <div className="player-trading-card__shape player-trading-card__frame" aria-hidden="true" />
      <div className="player-trading-card__shape player-trading-card__body">
        <div className="player-trading-card__glare" aria-hidden="true" />
        {enterAnimation ? (
          <div className="player-trading-card__sweep player-trading-card__sweep--enter" aria-hidden="true" />
        ) : null}
        <div className="player-trading-card__reflect" aria-hidden="true" />

        <div className="player-trading-card__content flex flex-col p-3.5">
          <div className="flex gap-3">
            <div
              ref={leftColRef}
              className="player-trading-card__left-parallax flex w-[72px] shrink-0 flex-col"
            >
              {isPartieB ? (
                <p className="text-2xl font-bold tabular-nums" style={{ color: "var(--color-player-card-fg)" }}>
                  {overallRating !== null ? (
                    <>
                      <span aria-hidden="true">{overallRating}</span>
                      <span className="sr-only">Note globale : {overallRating}</span>
                    </>
                  ) : (
                    <>
                      <span aria-hidden="true">—</span>
                      <span className="sr-only">Note globale : pas encore de donnée</span>
                    </>
                  )}
                </p>
              ) : jerseyNumber !== null && jerseyNumber !== undefined ? (
                <p
                  className="text-2xl font-bold tabular-nums"
                  style={{ color: "var(--color-player-card-fg)" }}
                >
                  <span aria-hidden="true">{jerseyNumber}</span>
                  <span className="sr-only">Numéro {jerseyNumber}</span>
                </p>
              ) : null}
              <p
                className="mt-1 break-words text-[13px] font-semibold"
                style={{ color: "var(--color-player-card-fg-muted)" }}
              >
                {positionLabel || "Poste non renseigné"}
              </p>
              {!isSmall ? (
                <>
                  <span
                    aria-hidden="true"
                    className="mt-2 h-px w-6"
                    style={{ backgroundColor: "var(--color-player-card-fg-muted)" }}
                  />
                  {clubLogoUrl ? (
                    <span
                      className="mt-2 inline-flex h-8 w-8 items-center justify-center rounded-full"
                      style={{ backgroundColor: "var(--color-surface)" }}
                    >
                      <img
                        src={clubLogoUrl}
                        alt={`Logo de ${clubName}`}
                        className="h-7 w-7 rounded-full object-contain"
                      />
                    </span>
                  ) : null}
                </>
              ) : null}
            </div>

            <div
              ref={photoRef}
              className="player-trading-card__photo-parallax relative shrink-0 overflow-hidden rounded-[10px]"
              style={{
                border: "2px solid var(--color-player-card-frame)",
                height: photoSizePx,
                width: photoSizePx,
              }}
            >
              {showPhoto ? (
                <img
                  src={photoUrl ?? undefined}
                  alt={`Photo de ${fullName}`}
                  loading="lazy"
                  decoding="async"
                  onError={() => setPhotoFailed(true)}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div
                  role="img"
                  aria-label={`Photo de ${fullName}`}
                  className="flex h-full w-full items-center justify-center"
                  style={{ backgroundColor: "var(--color-player-card-band-bg)" }}
                >
                  <PlayerSilhouette />
                </div>
              )}
            </div>
          </div>

          <div
            className="mt-3 rounded-[4px] px-3 py-2 text-center"
            style={{ backgroundColor: "var(--color-player-card-band-bg)" }}
          >
            <p
              className="text-lg font-bold"
              style={{
                color: "var(--color-player-card-band-fg)",
                textWrap: "balance",
                overflowWrap: "anywhere",
              }}
            >
              {nameBandPrefix}
              {fullName}
            </p>
            {positionDetail && !isSmall ? (
              <p
                className="mt-0.5 break-words text-[13px] opacity-80"
                style={{ color: "var(--color-player-card-band-fg)" }}
              >
                {positionDetail}
              </p>
            ) : null}
          </div>

          {!isSmall ? (
            stats ? (
              <dl className="mt-3 mb-[18px] grid grid-cols-2 gap-x-2 gap-y-2">
                {(
                  [
                    ["Matchs", String(stats.matchesPlayed)],
                    ["Buts", String(stats.goals)],
                    ["Passes décisives", String(stats.assists)],
                    [
                      "Cartons",
                      `${stats.yellowCards + stats.redCards}`,
                      `${stats.yellowCards} jaune${stats.yellowCards > 1 ? "s" : ""}, ${stats.redCards} rouge${stats.redCards > 1 ? "s" : ""}`,
                    ],
                    ["Taux de présence", stats.attendanceRate !== null ? `${stats.attendanceRate} %` : "—"],
                    ["Note moyenne", stats.averageRating !== null ? `${String(stats.averageRating).replace(".", ",")} sur 10` : "—"],
                  ] as Array<[string, string, string?]>
                ).map(([label, value, sub]) => (
                  <div key={label} className="border-t pt-1" style={{ borderColor: "color-mix(in srgb, var(--color-player-card-fg-muted) 40%, transparent)" }}>
                    <dd className="text-lg font-bold tabular-nums" style={{ color: "var(--color-player-card-fg)" }}>
                      {value}
                    </dd>
                    <dt className="text-[13px]" style={{ color: "var(--color-player-card-fg-muted)" }}>
                      {label}
                    </dt>
                    {sub ? (
                      <p className="text-[13px]" style={{ color: "var(--color-player-card-fg-muted)" }}>
                        {sub}
                      </p>
                    ) : null}
                  </div>
                ))}
              </dl>
            ) : (
              <div className="mt-3 mb-[18px] flex justify-center">
                <span
                  className="inline-flex h-6 items-center rounded-full border px-2 text-[13px]"
                  style={{
                    borderColor: "var(--color-player-card-fg-muted)",
                    color: "var(--color-player-card-fg)",
                  }}
                >
                  Statistiques à venir
                </span>
              </div>
            )
          ) : null}
        </div>
      </div>
    </div>
  );

  const paletteStyle = paletteStyleVars(palette);

  return (
    <>
      {onOpen ? (
        <button
          type="button"
          onClick={onOpen}
          aria-label={`Voir la fiche détaillée de ${fullName}`}
          className={["player-trading-card mx-auto block text-left", className].join(" ")}
          style={paletteStyle}
        >
          {cardInner}
        </button>
      ) : (
        <figure
          aria-label={`Carte de joueur de ${fullName}`}
          className={["player-trading-card mx-auto", className].join(" ")}
          style={paletteStyle}
        >
          {cardInner}
        </figure>
      )}
      {seasonLabel ? <p className="mt-2 text-center text-[13px] text-text-muted">Saison {seasonLabel}</p> : null}
    </>
  );
}
