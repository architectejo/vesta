import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { IconLock } from "../icons";
import { hexToRgb, pickReadableOnColor, rgbToHex } from "../tokens/color-contrast";
import {
  pitchDragBus,
  usePitchDragState,
  usePitchDraggable,
  usePitchDropZone,
  type PitchDragItem,
} from "../tactics/pitchDragBus";

export interface PitchPinData {
  /** Identifiant unique dans ce contexte (id d'affectation/emplacement, ou
   * `membership_id` pour un pion du banc/de la liste « Non répartis »). */
  id: string;
  membershipId: number;
  label: string;
  number?: number | null;
  x: number;
  y: number;
  /** Couleur du maillot (pastille), jamais une couleur de club sur le
   * terrain lui-même (design-system §2.7, sport-plan-tactique.md §5.4). */
  jerseyColor?: string;
  /** Pion non déplaçable — bloqué (dette, suspension, inaptitude, attente
   * d'adhésion) : ne se soulève jamais (§3.2 bis, §5.3). */
  locked?: boolean;
  /** Mis en avant (« Vous », joueur connecté). */
  highlighted?: boolean;
  /** URL absolue de la photo (servie par l'API) ; absente = initiales. */
  photoUrl?: string | null;
  /** Nom complet, pour les initiales (repli : `label`). */
  fullName?: string;
}

export interface PitchSlotData {
  id: string;
  x: number;
  y: number;
  abbrev: string;
  occupied?: boolean;
}

export interface PitchAnnotationData {
  id: string;
  type: "arrow" | "zone" | "note";
  points: Array<{ x: number; y: number }>;
  text?: string;
}

export type PitchBoardMode = "readonly" | "teams" | "tactic";

export interface PitchBoardProps {
  mode: PitchBoardMode;
  ariaLabel: string;
  pins: PitchPinData[];
  slots?: PitchSlotData[];
  annotations?: PitchAnnotationData[];
  /** Oriente le terrain (portrait par défaut, paysage sinon, §7.1/§7.2). */
  vertical?: boolean;
  /** Clé d'enregistrement comme zone de dépose ; absent = non receveur. */
  dropZoneKey?: string;
  onDropPlayer?: (item: PitchDragItem<{ membershipId: number }>, x: number, y: number) => void;
  onTapPin?: (pin: PitchPinData) => void;
  onTapSlot?: (slot: PitchSlotData) => void;
  /** Un pion peut-il être saisi depuis ce terrain (glisser un pion déjà
   * placé vers un autre emplacement) ? Toujours faux en lecture seule. */
  pinsDraggable?: boolean;
  /** Coupe toute interaction pointeur des pions (outil de dessin actif,
   * §5.4). Par défaut `true` : un pion reste toujours touchable. */
  pinsInteractive?: boolean;
  dragKind?: string;
  className?: string;
}

const PITCH_LINE = "var(--pitch-line, rgba(255,255,255,0.85))";

/** Convertit un point en coordonnées « métier » (0-100, repère fixe,
 * indépendant de l'orientation d'affichage — §7.1/§7.2) en coordonnées
 * d'affichage 0-100 selon l'orientation du terrain. Même rotation de
 * repère que `pointStyle`/`coordFromDropPoint` ci-dessous : utilisée à la
 * fois pour les pions et pour les tracés (`AnnotationsLayer`), afin que
 * marquages, pions et annotations tournent ensemble. */
function rotateCoord(x: number, y: number, vertical: boolean): { sx: number; sy: number } {
  return vertical ? { sx: x, sy: 100 - y } : { sx: y, sy: x };
}

/** Marquages du terrain. Le repère SVG (0-100 x 0-100) suit la même
 * rotation que `pointStyle`/`coordFromDropPoint` : en mode `vertical`, la
 * ligne médiane est horizontale et les surfaces de réparation sont en
 * haut/bas ; en mode paysage (`vertical=false`), x et y sont échangés
 * (ligne médiane verticale, surfaces de réparation à gauche/droite). */
function PitchMarkings({ vertical }: { vertical: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      className="pointer-events-none absolute inset-0 h-full w-full"
    >
      <rect x="1.5" y="1.5" width="97" height="97" fill="none" stroke={PITCH_LINE} strokeWidth="0.6" />
      {vertical ? (
        <line x1="1.5" y1="50" x2="98.5" y2="50" stroke={PITCH_LINE} strokeWidth="0.5" />
      ) : (
        <line x1="50" y1="1.5" x2="50" y2="98.5" stroke={PITCH_LINE} strokeWidth="0.5" />
      )}
      <circle cx="50" cy="50" r="9" fill="none" stroke={PITCH_LINE} strokeWidth="0.5" />
      {vertical ? (
        <>
          <rect x="20" y="1.5" width="60" height="16" fill="none" stroke={PITCH_LINE} strokeWidth="0.5" />
          <rect x="20" y="82.5" width="60" height="16" fill="none" stroke={PITCH_LINE} strokeWidth="0.5" />
        </>
      ) : (
        <>
          <rect x="1.5" y="20" width="16" height="60" fill="none" stroke={PITCH_LINE} strokeWidth="0.5" />
          <rect x="82.5" y="20" width="16" height="60" fill="none" stroke={PITCH_LINE} strokeWidth="0.5" />
        </>
      )}
    </svg>
  );
}

function AnnotationsLayer({ annotations, vertical }: { annotations: PitchAnnotationData[]; vertical: boolean }) {
  if (annotations.length === 0) return null;
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      className="pointer-events-none absolute inset-0 h-full w-full"
    >
      <defs>
        <marker id="pitch-arrow-head" markerWidth="6" markerHeight="6" refX="4" refY="3" orient="auto">
          <path d="M0,0 L5,3 L0,6 Z" fill="#fff" />
        </marker>
      </defs>
      {annotations.map((annotation) => {
        if (annotation.type === "arrow" && annotation.points.length >= 2) {
          const [a, b] = annotation.points;
          if (!a || !b) return null;
          const pa = rotateCoord(a.x, a.y, vertical);
          const pb = rotateCoord(b.x, b.y, vertical);
          return (
            <line
              key={annotation.id}
              x1={pa.sx}
              y1={pa.sy}
              x2={pb.sx}
              y2={pb.sy}
              stroke="#fff"
              strokeWidth="0.8"
              markerEnd="url(#pitch-arrow-head)"
            />
          );
        }
        if (annotation.type === "zone" && annotation.points.length >= 2) {
          const [a, b] = annotation.points;
          if (!a || !b) return null;
          const pa = rotateCoord(a.x, a.y, vertical);
          const pb = rotateCoord(b.x, b.y, vertical);
          const x = Math.min(pa.sx, pb.sx);
          const y = Math.min(pa.sy, pb.sy);
          const w = Math.abs(pb.sx - pa.sx);
          const h = Math.abs(pb.sy - pa.sy);
          return (
            <rect
              key={annotation.id}
              x={x}
              y={y}
              width={w}
              height={h}
              rx="2"
              fill="rgba(255,255,255,0.2)"
              stroke="#fff"
              strokeWidth="0.5"
              strokeDasharray="2,1.5"
            />
          );
        }
        return null;
      })}
    </svg>
  );
}

function pointStyle(x: number, y: number, vertical: boolean): { left: string; top: string } {
  const { sx, sy } = rotateCoord(x, y, vertical);
  return { left: `${sx}%`, top: `${sy}%` };
}

/** Inverse de `pointStyle` : reconvertit un point de dépose (en % de la
 * zone) vers les coordonnées `(x, y)` 0-100 du plan (§7.1/§7.2 : le
 * repère ne change jamais, seule l'orientation d'affichage tourne). */
function coordFromDropPoint(leftPct: number, topPct: number, vertical: boolean): { x: number; y: number } {
  return vertical ? { x: leftPct, y: 100 - topPct } : { x: topPct, y: leftPct };
}

interface PitchPinProps {
  pin: PitchPinData;
  vertical: boolean;
  draggable: boolean;
  dragKind: string;
  /** Interaction pointeur totalement coupée (ex. outil de dessin actif,
   * §5.4 : « en mode dessin, les pions ne se déplacent pas »). Par
   * défaut `true` : un pion reste toujours touchable, y compris
   * verrouillé (le toucher ouvre un panneau en lecture seule, §3.2 bis) ou
   * en mode `readonly` (petite fenêtre d'information, §4.1). */
  interactive?: boolean;
  /** `true` pour un pion réutilisé hors terrain, dans une simple liste à
   * puces (banc, « À placer à la main », « Ne peuvent pas jouer »). Le
   * positionnement par `pin.x`/`pin.y` n'a alors aucun sens (coordonnées
   * factices) : sans ce mode, le pion restait quand même en `position:
   * absolute` au pourcentage `pin.x`/`pin.y` (50/50 par convention), et se
   * positionnait donc par rapport au premier ancêtre positionné trouvé —
   * presque jamais la petite liste elle-même, qui n'a pas de position
   * relative (elle n'a pas besoin d'être une pelouse) — faisant disparaître
   * chaque pion de son emplacement réel et superposer tous les pions d'une
   * même liste au même endroit ailleurs sur la page (constat du client :
   * bancs visuellement vides, un seul pion flottant « dans le vide »).
   * Par défaut `false` : comportement inchangé pour un pion réellement posé
   * sur un `PitchBoard`. */
  standalone?: boolean;
  onTap?: (pin: PitchPinData) => void;
}

/** Initiales (2 lettres max) tirées du nom complet ; « ? » si vide. */
export function pinInitials(name: string): string {
  const parts = name
    .replace(/\./g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase() || "?";
}

function readableOn(bgHex: string | undefined): string {
  const rgb = bgHex ? hexToRgb(bgHex) : null;
  if (!rgb) return "#ffffff";
  return rgbToHex(pickReadableOnColor(rgb));
}

/** Cercle de 40 x 40 px du pion : photo (ou initiales en repli), bordure à
 * la couleur du maillot, numéro dans une pastille (sport-vestiaire.md §9.2).
 * La taille est fixe : le chargement de l'image ne déplace rien. */
function PinDisc({ pin }: { pin: PitchPinData }) {
  const photoUrl = pin.photoUrl || null;
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);
  const showPhoto = photoUrl !== null && failedUrl !== photoUrl;
  const loaded = showPhoto && loadedUrl === photoUrl;

  useEffect(() => {
    setSlow(false);
    if (!showPhoto || loaded) return undefined;
    const timer = window.setTimeout(() => setSlow(true), 1500);
    return () => window.clearTimeout(timer);
  }, [photoUrl, showPhoto, loaded]);

  const jersey = pin.jerseyColor;
  const accent = pin.highlighted ? "var(--color-primary)" : jersey;
  const fill = pin.locked ? undefined : (jersey ?? undefined);
  const textColor = pin.locked ? undefined : readableOn(jersey);
  const showInitials = !showPhoto || slow;
  const hasNumber = pin.number != null && pin.number !== undefined;

  return (
    <span className="relative block h-10 w-10 shrink-0">
      <span
        className={[
          "relative block h-10 w-10 overflow-hidden rounded-full border-[3px] shadow-elevated",
          pin.locked ? "border-dashed border-white/60 bg-black/30" : "",
          !pin.locked && !accent ? "border-white/80" : "",
        ].join(" ")}
        style={{
          ...(pin.locked ? {} : { borderColor: accent, backgroundColor: fill, boxShadow: "0 0 0 1px #fff" }),
          WebkitTouchCallout: "none",
        }}
      >
        {showInitials ? (
          <span
            data-testid="pin-initials"
            className="flex h-full w-full items-center justify-center text-[13px] font-semibold leading-none"
            style={{ color: pin.locked ? "rgba(255,255,255,0.8)" : textColor }}
          >
            {pinInitials(pin.fullName ?? pin.label)}
          </span>
        ) : null}
        {showPhoto ? (
          <img
            src={photoUrl ?? undefined}
            alt=""
            draggable={false}
            loading="lazy"
            decoding="async"
            onLoad={() => setLoadedUrl(photoUrl)}
            onError={() => setFailedUrl(photoUrl)}
            className={[
              "pointer-events-none absolute inset-0 h-full w-full select-none object-cover [-webkit-user-drag:none]",
              pin.locked ? "opacity-60 grayscale" : "",
              loaded ? "" : "opacity-0",
            ].join(" ")}
            style={{ objectPosition: "50% 25%" }}
          />
        ) : null}
      </span>
      {pin.locked ? (
        <span
          className="absolute -bottom-0.5 -right-3 flex h-[18px] w-[18px] items-center justify-center rounded-full text-white"
          style={{ backgroundColor: "var(--color-status-neutral-dot, #6b7280)" }}
        >
          <IconLock aria-hidden="true" className="h-3 w-3" />
        </span>
      ) : hasNumber ? (
        <span
          className="absolute -bottom-0.5 -right-3 flex h-[18px] min-w-[18px] items-center justify-center rounded-full px-1 text-[11px] font-bold leading-none tabular-nums"
          style={{ backgroundColor: fill ?? "var(--color-primary)", color: fill ? textColor : "#fff" }}
        >
          {pin.number}
        </span>
      ) : null}
    </span>
  );
}

/** Pion exporté séparément : réutilisé hors terrain (banc, « Non
 * répartis ») avec la même mécanique de glisser/toucher. */
export function PitchPin({ pin, vertical, draggable, dragKind, interactive = true, standalone = false, onTap }: PitchPinProps) {
  const dragItem: PitchDragItem<{ membershipId: number }> | null =
    draggable && !pin.locked ? { kind: dragKind, data: { membershipId: pin.membershipId }, label: pin.label } : null;
  const handlers = usePitchDraggable({ item: dragItem, disabled: !interactive, onTap: () => onTap?.(pin) });
  const style = standalone ? undefined : pointStyle(pin.x, pin.y, vertical);

  return (
    <button
      type="button"
      {...handlers}
      aria-label={pin.locked ? `${pin.label} : indisponible` : pin.label}
      className={[
        standalone ? "relative" : "absolute z-10 -translate-x-1/2 -translate-y-1/2",
        "flex select-none flex-col items-center gap-0.5",
        draggable && !pin.locked ? "cursor-grab touch-none" : "cursor-pointer",
      ].join(" ")}
      style={style}
      title={pin.fullName ?? pin.label}
    >
      <PinDisc pin={pin} />
      {/* 2 lignes au plus : au-delà de 18 caractères, 11 px (≈ 12 caractères
          par ligne) ; le nom complet reste dans l'infobulle (`title`). */}
      <span
        data-testid="pin-label"
        className={[
          "line-clamp-2 max-w-[72px] break-words rounded bg-black/50 px-1 text-center leading-tight text-white [overflow-wrap:anywhere]",
          pin.label.length > 18 ? "text-[11px]" : "text-[12px]",
        ].join(" ")}
      >
        {pin.label}
      </span>
    </button>
  );
}

/**
 * Terrain réutilisable (docs/ecrans/sport-seance.md, sport-feuille-de-
 * match.md, sport-plan-tactique.md, sport-vestiaire.md). Modes :
 * `readonly` (consultation), `teams` (deux terrains A/B, séance/vestiaire),
 * `tactic` (édition, tableau noir). Le glisser-déposer utilise des pointer
 * events natifs (`pitchDragBus`) ; chaque interaction de glissement a une
 * alternative de toucher fournie par l'écran appelant (menu, modale),
 * jamais recréée ici.
 */
export function PitchBoard({
  mode,
  ariaLabel,
  pins,
  slots = [],
  annotations = [],
  vertical = true,
  dropZoneKey,
  onDropPlayer,
  onTapPin,
  onTapSlot,
  pinsDraggable,
  pinsInteractive = true,
  dragKind = "pin",
  className = "",
}: PitchBoardProps) {
  const setDropRef = usePitchDropZone(dropZoneKey ?? null, (item, point) => {
    const { x, y } = coordFromDropPoint(point.xPct, point.yPct, vertical);
    onDropPlayer?.(item as PitchDragItem<{ membershipId: number }>, x, y);
  });
  const draggable = pinsDraggable ?? mode !== "readonly";

  return (
    <div
      ref={setDropRef}
      role="group"
      aria-label={ariaLabel}
      data-pitch-dropzone={dropZoneKey}
      className={[
        "relative w-full overflow-hidden rounded-md bg-[color:var(--pitch-fill,#2f7d3f)]",
        vertical ? "aspect-[68/105]" : "aspect-[105/68]",
        className,
      ].join(" ")}
    >
      <PitchMarkings vertical={vertical} />
      {mode === "tactic"
        ? slots.map((slot) => {
            const style = pointStyle(slot.x, slot.y, vertical);
            return (
              <button
                key={slot.id}
                type="button"
                onClick={() => onTapSlot?.(slot)}
                aria-label={`Emplacement ${slot.abbrev} : ${slot.occupied ? "occupé" : "vide, toucher pour choisir un joueur"}`}
                className={[
                  "absolute z-0 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center",
                  "rounded-full border-2 border-dashed border-white/50 text-[11px] font-medium text-white/70",
                  slot.occupied ? "opacity-0" : "opacity-100 hover:border-white",
                ].join(" ")}
                style={style}
                disabled={slot.occupied}
              >
                {slot.abbrev}
              </button>
            );
          })
        : null}
      <AnnotationsLayer annotations={annotations} vertical={vertical} />
      {pins.map((pin) => (
        <PitchPin
          key={pin.id}
          pin={pin}
          vertical={vertical}
          draggable={draggable}
          interactive={pinsInteractive}
          dragKind={dragKind}
          onTap={onTapPin}
        />
      ))}
    </div>
  );
}

/**
 * Fantôme flottant pendant un glissement (à monter une fois par écran qui
 * utilise `PitchBoard`/`PitchPin` en mode glissable). Purement visuel :
 * aucune logique métier, ne fait que suivre le pointeur.
 */
export function PitchDragGhost() {
  const { dragging, pointer } = usePitchDragState();
  if (!dragging || typeof document === "undefined") return null;
  return createPortal(
    <div
      aria-hidden="true"
      className="pointer-events-none fixed z-[70] -translate-x-1/2 -translate-y-1/2 rounded-full bg-text px-2 py-1 text-xs font-medium text-surface shadow-elevated"
      style={{ left: pointer.x, top: pointer.y }}
    >
      {dragging.label}
    </div>,
    document.body,
  );
}

export { pitchDragBus };
