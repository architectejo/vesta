import { useQuery } from "@tanstack/react-query";
import { getMyProfile } from "../../../api/clubs";
import { canManagePerformanceTests } from "../sportAccess";
import { canViewTrainingStaffStats } from "../sportAccess";

/**
 * Droits d'affichage des tests de performance. Simple indication : l'API reste
 * seule juge (403 / 404) et l'interface affiche alors la raison qu'elle donne.
 */
export function usePerformanceAccess() {
  const query = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const roles = query.data?.roles;
  return {
    loading: query.isLoading,
    canManage: canManagePerformanceTests(roles),
    canViewAll: canViewTrainingStaffStats(roles),
  };
}
