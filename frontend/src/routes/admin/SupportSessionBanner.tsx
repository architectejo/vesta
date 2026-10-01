import { useEffect, useState } from "react";
import { endSupportSession } from "../../api/licences";
import {
  getActiveSupportSession,
  setActiveSupportSession,
  subscribeToSupportSession,
} from "../../auth/supportSession";
import { Banner, Button, useToast } from "../../design-system";

function minutesRemaining(expiresAt: string): number {
  return Math.max(0, Math.round((new Date(expiresAt).getTime() - Date.now()) / 60_000));
}

/**
 * Bandeau de session de support en Ghost Mode (superuser-espace.md §4.4).
 *
 * Point ouvert signalé au compte rendu : `X-Support-Session` positionne
 * correctement le club actif côté API (`TenantJWTAuthentication`), mais
 * les permissions des pages de club (`IsActiveClubMember`,
 * `IsClubPresident`…) résolvent l'adhésion de `request.user` — un
 * Superuser n'en a structurellement aucune (CLAUDE.md règle n°1). Ce
 * bandeau reste donc utile pour le mécanisme de session (démarrage, fin,
 * décompte, journalisation) mais aucune page de club réelle n'est
 * actuellement navigable pendant la session : ce serait la construire
 * contre des permissions qui la refuseraient de toute façon.
 */
export function SupportSessionBanner() {
  const { showToast } = useToast();
  const [session, setSession] = useState(() => getActiveSupportSession());
  const [ending, setEnding] = useState(false);

  useEffect(() => subscribeToSupportSession(() => setSession(getActiveSupportSession())), []);

  useEffect(() => {
    if (!session) return;
    const timer = window.setInterval(() => {
      if (minutesRemaining(session.expiresAt) <= 0) {
        setActiveSupportSession(null);
        showToast("Session de support terminée.");
      } else {
        setSession({ ...session });
      }
    }, 30_000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.id]);

  if (!session) return null;

  async function handleEnd(): Promise<void> {
    if (!session) return;
    setEnding(true);
    try {
      await endSupportSession(Number(session.id));
    } finally {
      setActiveSupportSession(null);
      showToast("Session de support terminée.");
      setEnding(false);
    }
  }

  const remaining = minutesRemaining(session.expiresAt);

  return (
    <Banner
      variant="support"
      action={
        <Button variant="secondary" size="sm" loading={ending} onClick={() => void handleEnd()}>
          Terminer la session
        </Button>
      }
    >
      Session de support — {session.clubName} — Motif : {session.reason} — reste {remaining} min
      {remaining <= 5 ? " · La session se termine dans 5 minutes." : ""}
    </Banner>
  );
}
