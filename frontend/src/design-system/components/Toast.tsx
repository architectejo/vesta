import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

interface ToastEntry {
  id: number;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  /** Démontage différé pendant l'animation de sortie (§2.2). */
  closing: boolean;
}

interface ToastOptions {
  actionLabel?: string;
  onAction?: () => void;
  durationMs?: number;
}

interface ToastContextValue {
  showToast: (message: string, options?: ToastOptions) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const DEFAULT_DURATION_MS = 4000;
/** Durée de l'animation de sortie du toast (§2.1 `--duration-fast`). */
const EXIT_DURATION_MS = 150;

/**
 * Message bref après une action réussie (docs/lot0/design-system.md §3.1) :
 * 4 secondes, `aria-live="polite"`, jamais utilisé pour une erreur de champ.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const nextId = useRef(0);

  const showToast = useCallback((message: string, options: ToastOptions = {}) => {
    const id = nextId.current++;
    setToasts((current) => [
      ...current,
      { id, message, actionLabel: options.actionLabel, onAction: options.onAction, closing: false },
    ]);
    window.setTimeout(() => {
      // Démarre l'animation de sortie plutôt que de démonter aussitôt (§2.2).
      setToasts((current) => current.map((toast) => (toast.id === id ? { ...toast, closing: true } : toast)));
      window.setTimeout(() => {
        setToasts((current) => current.filter((toast) => toast.id !== id));
      }, EXIT_DURATION_MS);
    }, options.durationMs ?? DEFAULT_DURATION_MS);
  }, []);

  const value = useMemo<ToastContextValue>(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex flex-col items-center gap-2 px-4 sm:inset-x-auto sm:right-4 sm:top-4 sm:bottom-auto sm:items-end"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            data-state={toast.closing ? "closing" : "open"}
            className="vesta-anim-toast pointer-events-auto flex max-w-sm items-center gap-3 rounded-md bg-text px-4 py-2 text-sm text-surface shadow-elevated"
          >
            <span>{toast.message}</span>
            {toast.actionLabel && toast.onAction ? (
              <button
                type="button"
                onClick={toast.onAction}
                className="-my-2 shrink-0 py-2 font-medium underline"
              >
                {toast.actionLabel}
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast doit être utilisé à l'intérieur d'un <ToastProvider>.");
  }
  return ctx;
}
