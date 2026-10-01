import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { OnboardingGate } from "../routes/onboarding/OnboardingGate";
import { useAuth } from "./AuthContext";

/**
 * Garde d'accès aux pages protégées. Redirige vers `/connexion` avec le
 * chemin demandé conservé dans `?suite=` (comptes-connexion.md §2 : « le
 * lien demandé est conservé [...] et rouvert après connexion »).
 */
export function ProtectedRoute({
  children,
  requireSuperuser = false,
}: {
  children: ReactNode;
  requireSuperuser?: boolean;
}) {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "anonymous") {
    const suite = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/connexion?suite=${suite}`} replace />;
  }

  if (requireSuperuser && !user?.is_superuser) {
    return <Navigate to="/" replace />;
  }

  if (!requireSuperuser && user?.is_superuser) {
    return <Navigate to="/admin" replace />;
  }

  return <OnboardingGate>{children}</OnboardingGate>;
}
