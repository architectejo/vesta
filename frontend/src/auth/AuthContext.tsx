import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { logout as apiLogout } from "../api/auth";
import type { ClubSummary, LoginSuccess, UserSummary } from "../api/auth";
import type { ClubCreationSuccess } from "../api/clubs";
import {
  clearSessionTokens,
  getAccessToken,
  getRefreshToken,
  getStoredIdentity,
  setSessionTokens,
  setStoredIdentity,
  subscribeToSession,
} from "./session";
import { setActiveSupportSession } from "./supportSession";

export interface AuthState {
  status: "anonymous" | "authenticated";
  user: UserSummary | null;
  club: ClubSummary | null;
}

interface AuthContextValue extends AuthState {
  /** Après connexion ou création de club : ouvre la session de cet onglet. */
  applySession: (result: LoginSuccess | ClubCreationSuccess) => void;
  /** Mise à jour locale après un changement de mot de passe forcé réussi. */
  markPasswordChanged: () => void;
  /** Mise à jour locale après un changement d'email (onglet « Identifiant »). */
  updateEmail: (email: string) => void;
  /** Déconnexion de cet onglet (révoque aussi le jeton côté API si possible). */
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readState(): AuthState {
  const identity = getStoredIdentity();
  if (!getAccessToken() || !identity) {
    return { status: "anonymous", user: null, club: null };
  }
  return { status: "authenticated", user: identity.user, club: identity.club };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => readState());

  useEffect(() => subscribeToSession(() => setState(readState())), []);

  const applySession = useCallback((result: LoginSuccess | ClubCreationSuccess) => {
    setSessionTokens({ access: result.access, refresh: result.refresh });
    setStoredIdentity({ user: result.user, club: result.club as ClubSummary | null });
  }, []);

  const markPasswordChanged = useCallback(() => {
    const identity = getStoredIdentity();
    if (!identity) return;
    setStoredIdentity({ ...identity, user: { ...identity.user, must_change_password: false } });
  }, []);

  const updateEmail = useCallback((email: string) => {
    const identity = getStoredIdentity();
    if (!identity) return;
    setStoredIdentity({ ...identity, user: { ...identity.user, email } });
  }, []);

  const logout = useCallback(async () => {
    const refresh = getRefreshToken();
    setActiveSupportSession(null);
    try {
      if (refresh) await apiLogout(refresh);
    } catch {
      // La déconnexion locale doit réussir même si l'appel réseau échoue
      // (CDC 7.1 : « Se déconnecter » reste toujours une issue disponible).
    } finally {
      clearSessionTokens();
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, applySession, markPasswordChanged, updateEmail, logout }),
    [state, applySession, markPasswordChanged, updateEmail, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth doit être utilisé à l'intérieur d'un <AuthProvider>.");
  }
  return ctx;
}
