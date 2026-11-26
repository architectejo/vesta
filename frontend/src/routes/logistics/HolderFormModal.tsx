import { useCallback, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { createHolder, listHolders, type Holder, type HolderKind } from "../../api/logistics";
import {
  Modal,
  PlayerSearch,
  SegmentedControl,
  TextField,
  useToast,
  type PlayerSearchResult,
} from "../../design-system";
import { searchHolderCandidates } from "./movementSearches";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

export interface HolderFormModalProps {
  open: boolean;
  /** 2 quand ouverte depuis `HolderSearch` dans une autre modale. */
  level?: 1 | 2;
  onClose: () => void;
  onCreated: (holder: Holder) => void;
}

/** « Ajouter un détenteur » (spec B4 §1.3), Intendant. */
export function HolderFormModal({ open, level = 1, onClose, onCreated }: HolderFormModalProps) {
  const { showToast } = useToast();
  const [kind, setKind] = useState<HolderKind>("member");
  const [player, setPlayer] = useState<PlayerSearchResult | null>(null);
  const [label, setLabel] = useState("");
  const [playerError, setPlayerError] = useState<string | undefined>(undefined);
  const [labelError, setLabelError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  // Archivés compris : un joueur déjà détenteur (même archivé) est grisé.
  const existingQuery = useQuery({
    queryKey: ["logistics", "holders", "list", true],
    queryFn: () => listHolders(true),
    enabled: open,
  });
  const existingMemberships = new Set(
    (existingQuery.data?.results ?? []).map((holder) => holder.membership_id).filter((id): id is number => id !== null),
  );
  const existingKey = [...existingMemberships].sort().join(",");

  const searchPlayers = useCallback(
    async (query: string): Promise<PlayerSearchResult[]> => {
      const taken = new Set(existingKey ? existingKey.split(",").map(Number) : []);
      const players = await searchHolderCandidates(query);
      return players.map((p) =>
        taken.has(Number(p.id)) ? { ...p, eligible: false, ineligibleReason: "Déjà détenteur" } : p,
      );
    },
    [existingKey],
  );

  useEffect(() => {
    if (!open) return;
    setKind("member");
    setPlayer(null);
    setLabel("");
    setPlayerError(undefined);
    setLabelError(undefined);
    setSubmitError(undefined);
  }, [open]);

  async function handleSubmit(): Promise<void> {
    if (kind === "member" && !player) {
      setPlayerError("Choisissez un joueur.");
      return;
    }
    if (kind === "place" && !label.trim()) {
      setLabelError("Ce champ est obligatoire.");
      return;
    }
    setPlayerError(undefined);
    setLabelError(undefined);
    setSubmitting(true);
    setSubmitError(undefined);
    try {
      const holder = await createHolder(
        kind === "member" ? { kind, membership_id: Number(player!.id) } : { kind, label: label.trim() },
      );
      showToast("Détenteur ajouté.");
      onCreated(holder);
    } catch (error) {
      const message = apiErrorMessage(error);
      if (kind === "place" && /lieu/i.test(message)) setLabelError(message);
      else if (kind === "member" && /joueur/i.test(message)) setPlayerError(message);
      else setSubmitError(message);
    } finally {
      setSubmitting(false);
    }
  }

  const isDirty = Boolean(player || label.trim());

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Ajouter un détenteur"
      size="sm"
      level={level}
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Ajouter"
      confirmLoadingLabel="Ajout…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <SegmentedControl
          label="Type"
          value={kind}
          onChange={(next) => {
            setKind(next);
            setPlayerError(undefined);
            setLabelError(undefined);
          }}
          options={[
            { value: "member", label: "Un joueur" },
            { value: "place", label: "Un lieu" },
          ]}
        />
        {kind === "member" ? (
          // Feuille `sm` (panneau bas à 360 px) : son corps était trop court
          // pour la liste de suggestions, qui passait sous le pied collant.
          // Tant qu'aucun joueur n'est choisi, la hauteur de la liste
          // (max-h-72) est réservée, sans variation pendant la saisie (un
          // agrandissement au focus déplaçait les boutons sous le doigt).
          <div data-testid="holder-player-field" className={player ? undefined : "pb-72"}>
            <p className="mb-1 text-sm font-medium text-text">Joueur</p>
            <PlayerSearch value={player} onChange={setPlayer} searchPlayers={searchPlayers} />
            {playerError ? <p className="mt-1 text-xs text-status-danger-fg">{playerError}</p> : null}
          </div>
        ) : (
          <TextField label="Nom du lieu" value={label} onChange={setLabel} maxLength={60} error={labelError} />
        )}
        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
