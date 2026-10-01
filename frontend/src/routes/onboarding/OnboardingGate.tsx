import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { getPendingTerms } from "../../api/auth";
import { getMyProfile } from "../../api/clubs";
import { useAuth } from "../../auth/AuthContext";
import { Loader } from "../../design-system";
import { ForcedPasswordChangeModal } from "./ForcedPasswordChangeModal";
import { PhotoPromptModal } from "./PhotoPromptModal";
import { TermsGateModal } from "./TermsGateModal";

const PHOTO_PROMPT_SEEN_KEY = "vesta:photo-prompt-seen";

/**
 * Enchaînement bloquant de première connexion (club-accueil.md §3 ;
 * comptes-connexion.md §4.2) : mot de passe, puis CGU, puis (non bloquant)
 * photo. Rendu au-dessus de toute page protégée : tant que le mot de passe
 * ou les CGU sont en attente, **aucune page du club n'est chargée** —
 * `children` n'est monté qu'une fois les deux niveaux résolus, exactement
 * comme l'exige la spec (« aucune donnée du club ni du joueur n'est
 * demandée à l'API »).
 */
export function OnboardingGate({ children }: { children: ReactNode }) {
  const { user, markPasswordChanged } = useAuth();
  const queryClient = useQueryClient();
  const [photoPromptDismissed, setPhotoPromptDismissed] = useState(
    () => window.sessionStorage.getItem(PHOTO_PROMPT_SEEN_KEY) === "1",
  );

  const mustChangePassword = Boolean(user?.must_change_password);

  const termsQuery = useQuery({
    queryKey: ["terms", "pending"],
    queryFn: getPendingTerms,
    enabled: Boolean(user) && !mustChangePassword && !user?.is_superuser,
    staleTime: 0,
  });

  const gatesClear = !mustChangePassword && (user?.is_superuser || !termsQuery.data);

  const profileQuery = useQuery({
    queryKey: ["profile", "me"],
    queryFn: getMyProfile,
    enabled: Boolean(user) && !user?.is_superuser && gatesClear,
    staleTime: 60_000,
  });

  if (!user) return <>{children}</>;

  if (mustChangePassword) {
    return <ForcedPasswordChangeModal onSuccess={markPasswordChanged} />;
  }

  if (!user.is_superuser) {
    if (termsQuery.isLoading) {
      return <Loader loading variant="page" />;
    }
    if (termsQuery.data) {
      return (
        <TermsGateModal
          terms={termsQuery.data}
          onAccepted={() => {
            void queryClient.invalidateQueries({ queryKey: ["terms", "pending"] });
          }}
        />
      );
    }
  }

  const showPhotoPrompt =
    !photoPromptDismissed && Boolean(profileQuery.data) && !profileQuery.data?.identity.photo;

  function dismissPhotoPrompt(): void {
    window.sessionStorage.setItem(PHOTO_PROMPT_SEEN_KEY, "1");
    setPhotoPromptDismissed(true);
  }

  return (
    <>
      {children}
      {showPhotoPrompt && profileQuery.data ? (
        <PhotoPromptModal
          fullName={`${profileQuery.data.identity.first_name} ${profileQuery.data.identity.last_name}`}
          onClose={dismissPhotoPrompt}
          onSaved={() => {
            dismissPhotoPrompt();
            void queryClient.invalidateQueries({ queryKey: ["profile", "me"] });
          }}
        />
      ) : null}
    </>
  );
}
