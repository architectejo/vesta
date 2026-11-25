import { Navigate, useLocation } from "react-router-dom";

/**
 * Ancienne page « Plans tactiques » (`/plans`) : renvoie vers l'onglet « Plans »
 * du Vestiaire en conservant la query (ex. `?plan=3` d'une notification).
 */
export function PlansRedirect() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  params.set("onglet", "plans");
  return <Navigate to={`/vestiaire?${params.toString()}`} replace />;
}
