import { useEffect, useState } from "react";

export const OFFLINE_ACTION_MESSAGE = "Cette action nécessite une connexion.";

/**
 * État de connexion du navigateur (`navigator.onLine` + événements
 * `online`/`offline`). Sert aux actions de l'intendance qui ne passent pas
 * par la file hors connexion (fiche `logistique-intendance-registre.md` §14) :
 * bouton désactivé et « Cette action nécessite une connexion. ».
 */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  return online;
}
