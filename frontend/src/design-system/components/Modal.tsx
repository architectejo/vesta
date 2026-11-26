import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useClosingState } from "../../hooks/useClosingState";
import { IconClose } from "../icons";
import { Button, type ButtonVariant } from "./Button";
import { IconButton } from "./IconButton";
import { Skeleton } from "./Skeleton";

export type ModalSize = "sm" | "md" | "lg" | "xl";

export interface ModalProps {
  open: boolean;
  /** Fermeture demandée par un déclencheur (croix, Échap, voile, Annuler, retour). */
  onClose: () => void;
  title: string;
  subtitle?: string;
  size?: ModalSize;
  /** Niveau d'empilement (2 = confirmation au-dessus d'un formulaire). */
  level?: 1 | 2;
  /** Formulaire modifié : toute fermeture ouvre la confirmation d'abandon. */
  isDirty?: boolean;
  /** Enregistrement en cours : fermeture impossible, contenu désactivé. */
  isSubmitting?: boolean;
  /** Corps en cours de chargement (modale de détail) : squelette affiché. */
  loading?: boolean;
  /**
   * Modale bloquante (changement obligatoire du mot de passe initial) :
   * pas de croix, Échap et voile inactifs.
   */
  blocking?: boolean;
  children: ReactNode;
  /** Pied personnalisé ; par défaut, Annuler / action principale. */
  footer?: ReactNode;
  hideFooter?: boolean;
  cancelLabel?: string;
  confirmLabel?: string;
  onConfirm?: () => void;
  confirmVariant?: Extract<ButtonVariant, "primary" | "danger">;
  confirmDisabled?: boolean;
  confirmLoadingLabel?: string;
}

const SIZE_PANEL_WIDTH: Record<Exclude<ModalSize, "sm">, string> = {
  md: "sm:w-[560px]",
  lg: "sm:w-[800px]",
  xl: "sm:w-[960px]",
};

const DRAG_CLOSE_THRESHOLD_PX = 80;

/**
 * Retours d'historique déclenchés par le code lui-même (nettoyage d'une modale)
 * dont le `popstate` n'est pas encore arrivé. Ce `popstate` n'est jamais un
 * appui sur le bouton Retour : il ne doit fermer aucune modale (ni celle qui
 * vient de se démonter, ni celle du dessous, ni la même remontée par
 * React StrictMode en développement).
 */
const pendingProgrammaticBacks = new Set<ReturnType<typeof setTimeout>>();
const programmaticPopEvents = new WeakSet<Event>();
/** Filet de sécurité : un retour sans `popstate` (rien à dépiler) expire. */
const PROGRAMMATIC_BACK_TTL_MS = 1000;

function goBackProgrammatically(): void {
  const token = setTimeout(() => {
    pendingProgrammaticBacks.delete(token);
  }, PROGRAMMATIC_BACK_TTL_MS);
  pendingProgrammaticBacks.add(token);
  window.history.back();
}

if (typeof window !== "undefined") {
  // Enregistré à l'import, donc avant tout écouteur d'instance : il voit chaque
  // popstate en premier et le marque s'il provient d'un retour du code.
  window.addEventListener("popstate", (event) => {
    const [token] = pendingProgrammaticBacks;
    if (token === undefined) return;
    clearTimeout(token);
    pendingProgrammaticBacks.delete(token);
    programmaticPopEvents.add(event);
  });
}

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  const selector =
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';
  return Array.from(container.querySelectorAll<HTMLElement>(selector)).filter(
    (el) => el.offsetParent !== null || el === document.activeElement,
  );
}

/**
 * Boîte modale (docs/lot0/design-system.md §3.2). Contient tout formulaire,
 * toute modale de détail, toute confirmation (CLAUDE.md §2.13).
 */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  size = "md",
  level = 1,
  isDirty = false,
  isSubmitting = false,
  loading = false,
  blocking = false,
  children,
  footer,
  hideFooter = false,
  cancelLabel = "Annuler",
  confirmLabel = "Enregistrer",
  onConfirm,
  confirmVariant = "primary",
  confirmDisabled = false,
  confirmLoadingLabel = "Enregistrement…",
}: ModalProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const { mounted, dataState, onAnimationEnd } = useClosingState(open, 200);
  const [showAbandonConfirm, setShowAbandonConfirm] = useState(false);
  const [mouseDownOnOverlay, setMouseDownOnOverlay] = useState(false);
  const dragStartYRef = useRef<number | null>(null);
  const pushedHistoryRef = useRef(false);
  const closingViaPopStateRef = useRef(false);

  const canCloseNow = !blocking && !isSubmitting;

  function requestClose(): void {
    if (!canCloseNow) return;
    if (isDirty) {
      setShowAbandonConfirm(true);
      return;
    }
    onClose();
  }

  // Échap (au-dessus : ferme d'abord la confirmation d'abandon si ouverte).
  useEffect(() => {
    if (!open) return undefined;
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key !== "Escape") return;
      if (showAbandonConfirm) {
        setShowAbandonConfirm(false);
        return;
      }
      requestClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, showAbandonConfirm, isDirty, blocking, isSubmitting]);

  // Verrouillage du défilement de la page pendant que la modale est ouverte.
  useEffect(() => {
    if (!open) return undefined;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [open]);

  // Bouton retour d'Android : une entrée d'historique par ouverture ; le
  // retour ferme la modale au lieu de quitter la page.
  useEffect(() => {
    if (!open) return undefined;
    window.history.pushState({ vestaModal: true }, "");
    pushedHistoryRef.current = true;

    function handlePopState(event: PopStateEvent): void {
      if (programmaticPopEvents.has(event)) return;
      if (!pushedHistoryRef.current) return;
      pushedHistoryRef.current = false;
      closingViaPopStateRef.current = true;
      requestClose();
    }
    window.addEventListener("popstate", handlePopState);
    return () => {
      window.removeEventListener("popstate", handlePopState);
      if (pushedHistoryRef.current) {
        pushedHistoryRef.current = false;
        // Une vraie navigation (ex. un bouton de la modale qui appelle
        // `navigate(...)` vers une autre route sans fermer la modale
        // d'abord) a pu empiler une entrée réelle par-dessus notre entrée
        // factice avant que ce nettoyage ne s'exécute (démontage causé par
        // le changement de route, pas par une fermeture normale). Dans ce
        // cas, `window.history.state` n'est plus notre marqueur : il ne
        // faut surtout pas dépiler, car `history.back()` annulerait cette
        // navigation réelle (et pas notre entrée factice) — d'où le flash
        // « la page revient en arrière toute seule ». L'entrée factice
        // reste alors dans l'historique ; elle sera simplement consommée
        // par un futur retour de l'utilisateur, ce qui est sans danger.
        const currentStateIsStillOurMarker =
          (window.history.state as { vestaModal?: boolean } | null)?.vestaModal === true;
        if (!closingViaPopStateRef.current && currentStateIsStillOurMarker) {
          goBackProgrammatically();
        }
      }
      closingViaPopStateRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Focus initial + restitution du focus à la fermeture + piège à focus.
  useEffect(() => {
    if (!open) return undefined;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const container = panelRef.current;
    if (container) {
      const focusable = getFocusableElements(container);
      (focusable[0] ?? container).focus();
    }

    function handleTabKey(event: globalThis.KeyboardEvent): void {
      if (event.key !== "Tab" || !container) return;
      const focusable = getFocusableElements(container);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
    container?.addEventListener("keydown", handleTabKey);
    return () => {
      container?.removeEventListener("keydown", handleTabKey);
      previouslyFocused?.focus();
    };
  }, [open]);

  if (!mounted) return null;

  function handleOverlayMouseDown(event: ReactMouseEvent<HTMLDivElement>): void {
    setMouseDownOnOverlay(event.target === event.currentTarget);
  }

  function handleOverlayMouseUp(event: ReactMouseEvent<HTMLDivElement>): void {
    if (mouseDownOnOverlay && event.target === event.currentTarget && canCloseNow) {
      requestClose();
    }
    setMouseDownOnOverlay(false);
  }

  function handleHandlePointerDown(event: ReactPointerEvent<HTMLDivElement>): void {
    dragStartYRef.current = event.clientY;
  }

  function handleHandlePointerMove(event: ReactPointerEvent<HTMLDivElement>): void {
    if (dragStartYRef.current === null || !panelRef.current) return;
    const delta = event.clientY - dragStartYRef.current;
    if (delta > 0) {
      panelRef.current.style.transform = `translateY(${delta}px)`;
    }
  }

  function handleHandlePointerUp(event: ReactPointerEvent<HTMLDivElement>): void {
    if (dragStartYRef.current === null) return;
    const delta = event.clientY - dragStartYRef.current;
    dragStartYRef.current = null;
    if (panelRef.current) panelRef.current.style.transform = "";
    if (delta > DRAG_CLOSE_THRESHOLD_PX && canCloseNow) {
      requestClose();
    }
  }

  function handlePanelKeyDown(event: ReactKeyboardEvent<HTMLDivElement>): void {
    if (event.key !== "Escape") return;
    // Empêche Échap de fuiter vers d'autres modales éventuellement ouvertes
    // en dessous (empilement à deux niveaux au plus, 3.2).
    event.stopPropagation();
    // Correctif série 5 : `stopPropagation` sur l'événement React arrête
    // aussi l'événement natif à la racine de l'application ; l'écouteur posé
    // sur `window` ne le reçoit donc jamais quand le focus est DANS la
    // modale (cas normal, focus initial sur la croix). Échap doit être
    // traité ici, avec l'état et le `onClose` du rendu courant.
    if (showAbandonConfirm) {
      setShowAbandonConfirm(false);
      return;
    }
    requestClose();
  }

  const zIndexClass = level === 2 ? "z-[60]" : "z-[50]";
  const containerAlignClass =
    size === "sm" ? "items-end sm:items-center" : "items-stretch sm:items-center sm:p-4";
  const panelSizeClass =
    size === "sm"
      ? "max-h-[90vh] w-full rounded-t-lg sm:mx-auto sm:w-[400px] sm:rounded-lg"
      : `h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:rounded-lg ${SIZE_PANEL_WIDTH[size]}`;
  // Panneau bas sur mobile pour `sm` (petite confirmation), plein écran pour
  // les autres tailles ; centrée à partir de 640 px dans les deux cas
  // (design-system-icones-animations.md §2.2).
  const panelAnimClass = size === "sm" ? "vesta-anim-panel-sm" : "vesta-anim-panel-full";

  const modalContent = (
    <div
      className={`fixed inset-0 ${zIndexClass} flex justify-center ${containerAlignClass} ${
        dataState === "closing" ? "pointer-events-none" : ""
      }`}
    >
      <div
        className="vesta-anim-overlay absolute inset-0 bg-overlay"
        data-state={dataState}
        onMouseDown={handleOverlayMouseDown}
        onMouseUp={handleOverlayMouseUp}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-busy={isSubmitting || loading || undefined}
        onKeyDown={handlePanelKeyDown}
        data-state={dataState}
        onAnimationEnd={onAnimationEnd}
        className={`relative flex flex-col bg-surface shadow-elevated outline-none ${panelAnimClass} ${panelSizeClass}`}
      >
        {size === "sm" ? (
          <div
            className="flex justify-center pt-2 sm:hidden"
            onPointerDown={handleHandlePointerDown}
            onPointerMove={handleHandlePointerMove}
            onPointerUp={handleHandlePointerUp}
          >
            <span aria-hidden="true" className="h-1 w-8 rounded-full bg-border-strong" />
          </div>
        ) : null}

        <header className="flex items-start justify-between gap-3 border-b border-border p-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-lg font-semibold text-text">
              {title}
            </h2>
            {subtitle ? <p className="text-xs text-text-muted">{subtitle}</p> : null}
          </div>
          {!blocking ? (
            <IconButton
              aria-label="Fermer"
              onClick={requestClose}
              disabled={!canCloseNow}
              icon={<IconClose aria-hidden="true" className="h-5 w-5" />}
            />
          ) : null}
        </header>

        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="space-y-3">
              <Skeleton variant="card" />
              <Skeleton variant="card" />
            </div>
          ) : (
            children
          )}
        </div>

        {!hideFooter ? (
          <footer className="flex items-center justify-end gap-2 border-t border-border p-3 sm:p-4">
            {footer ?? (
              <>
                {blocking ? (
                  <Button variant="secondary" size="md" onClick={onClose}>
                    Se déconnecter
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="md"
                    className="flex-1 sm:flex-none"
                    onClick={requestClose}
                    disabled={isSubmitting}
                  >
                    {cancelLabel}
                  </Button>
                )}
                {onConfirm ? (
                  <Button
                    variant={confirmVariant}
                    size="md"
                    className="flex-1 sm:flex-none"
                    onClick={onConfirm}
                    loading={isSubmitting}
                    loadingLabel={confirmLoadingLabel}
                    disabled={confirmDisabled}
                  >
                    {confirmLabel}
                  </Button>
                ) : null}
              </>
            )}
          </footer>
        ) : null}

        {showAbandonConfirm ? (
          <div className="absolute inset-0 z-[60] flex items-center justify-center bg-overlay p-4">
            <div
              role="alertdialog"
              aria-modal="true"
              aria-label="Abandonner les modifications ?"
              className="w-full max-w-[360px] rounded-lg bg-surface p-4 shadow-elevated"
            >
              <h3 className="text-base font-semibold text-text">
                Abandonner les modifications ?
              </h3>
              <p className="mt-1 text-sm text-text-muted">
                Les informations saisies seront perdues.
              </p>
              <div className="mt-4 flex justify-end gap-2">
                <Button
                  autoFocus
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowAbandonConfirm(false)}
                >
                  Continuer la saisie
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => {
                    setShowAbandonConfirm(false);
                    onClose();
                  }}
                >
                  Abandonner
                </Button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}
