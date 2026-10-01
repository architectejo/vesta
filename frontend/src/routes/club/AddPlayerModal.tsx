import { useState } from "react";
import { addPlayerWithSponsor, searchActiveClubPlayers } from "../../api/clubs";
import { ApiError } from "../../api/client";
import {
  Banner,
  Modal,
  PlayerSearch,
  SegmentedControl,
  TextField,
  useToast,
} from "../../design-system";
import type { PlayerSearchResult } from "../../design-system";

type Position = "goalkeeper" | "defender" | "midfielder" | "forward";

const POSITION_OPTIONS: Array<{ value: Position; label: string }> = [
  { value: "goalkeeper", label: "Gardien" },
  { value: "defender", label: "Défenseur" },
  { value: "midfielder", label: "Milieu" },
  { value: "forward", label: "Attaquant" },
];

/**
 * Modale « Ajouter un joueur » (club-comite-bureau.md §4.5, CDC 4.3
 * étape 1). Le champ Parrain est un `PlayerSearch` porté par
 * `searchActiveClubPlayers` (« joueurs inscrits seulement », §4.5 ligne 90).
 *
 * Point ouvert déjà signalé et toujours ouvert (hors périmètre de cette
 * tâche) : le champ « Type de cotisation mensuelle » de la spec (Select des
 * types mensuels actifs, obligatoire) n'est pas représenté ici — aucun point
 * d'accès de liste des types de cotisation actifs du club n'existe côté API
 * à ce jour. `AddPlayerWithSponsorInput.requested_contribution_type_label`
 * reste donc non renseigné (champ optionnel côté API).
 */
export function AddPlayerModal({
  onClose,
  onAdded,
}: {
  onClose: () => void;
  onAdded: () => void;
}) {
  const { showToast } = useToast();
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [position, setPosition] = useState<Position | null>(null);
  const [positionDetail, setPositionDetail] = useState("");
  const [jerseyNumber, setJerseyNumber] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [sponsor, setSponsor] = useState<PlayerSearchResult | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isDirty =
    email !== "" ||
    firstName !== "" ||
    lastName !== "" ||
    phone !== "" ||
    position !== null ||
    positionDetail !== "" ||
    jerseyNumber !== "" ||
    birthDate !== "" ||
    weightKg !== "" ||
    heightCm !== "" ||
    sponsor !== null;

  async function handleSubmit(): Promise<void> {
    setGlobalError(null);
    const nextErrors: Record<string, string> = {};
    if (!firstName.trim()) nextErrors.first_name = "Ce champ est obligatoire.";
    if (!lastName.trim()) nextErrors.last_name = "Ce champ est obligatoire.";
    if (!email.trim()) nextErrors.email = "Ce champ est obligatoire.";
    if (!position) nextErrors.position = "Choisissez un poste.";
    if (!sponsor) nextErrors.sponsor = "Choisissez un parrain.";
    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors);
      return;
    }
    setFieldErrors({});
    setSubmitting(true);
    try {
      await addPlayerWithSponsor({
        email: email.trim(),
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone: phone.trim() || undefined,
        position: position as Position,
        position_detail: positionDetail.trim() || undefined,
        jersey_number: jerseyNumber ? Number(jerseyNumber) : null,
        birth_date: birthDate || null,
        weight_kg: weightKg ? Number(weightKg) : null,
        height_cm: heightCm ? Number(heightCm) : null,
        sponsor_membership_id: Number((sponsor as PlayerSearchResult).id),
      });
      showToast(`${firstName.trim()} ${lastName.trim()} a été ajouté. Statut : En attente.`);
      onAdded();
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length > 0) {
        const flat: Record<string, string> = {};
        for (const [key, value] of Object.entries(err.fields)) {
          flat[key === "sponsor_membership_id" ? "sponsor" : key] = value[0] ?? "";
        }
        setFieldErrors(flat);
      }
      setGlobalError(
        err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Ajouter un joueur"
      size="md"
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Ajouter le joueur"
      confirmLoadingLabel="Ajout…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        {globalError ? <Banner variant="danger">{globalError}</Banner> : null}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextField label="Prénom" value={firstName} onChange={setFirstName} error={fieldErrors.first_name} />
          <TextField label="Nom" value={lastName} onChange={setLastName} error={fieldErrors.last_name} />
        </div>
        <TextField
          label="Email"
          type="email"
          value={email}
          onChange={setEmail}
          error={fieldErrors.email}
        />
        <TextField label="Téléphone (WhatsApp)" optional type="tel" value={phone} onChange={setPhone} />
        <SegmentedControl
          label="Poste"
          value={position}
          onChange={setPosition}
          options={POSITION_OPTIONS}
        />
        {fieldErrors.position ? <p className="text-xs text-status-danger-fg">{fieldErrors.position}</p> : null}
        <TextField label="Poste précis" optional value={positionDetail} onChange={setPositionDetail} placeholder="Arrière gauche" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextField
            label="Numéro de maillot"
            optional
            type="number"
            value={jerseyNumber}
            onChange={setJerseyNumber}
            error={fieldErrors.jersey_number}
          />
          <TextField label="Date de naissance" optional type="date" value={birthDate} onChange={setBirthDate} />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextField label="Poids (kg)" optional type="number" value={weightKg} onChange={setWeightKg} />
          <TextField label="Taille (cm)" optional type="number" value={heightCm} onChange={setHeightCm} />
        </div>
        <div>
          <p className="mb-1 text-sm font-medium text-text">Parrain</p>
          <PlayerSearch
            value={sponsor}
            onChange={setSponsor}
            searchPlayers={searchActiveClubPlayers}
            ariaLabel="Parrain"
            placeholder="Nom ou numéro du joueur"
          />
          {fieldErrors.sponsor ? <p className="mt-1 text-xs text-status-danger-fg">{fieldErrors.sponsor}</p> : null}
        </div>
        <p className="text-xs text-text-muted">
          Le mot de passe initial est l'email. {firstName || "Le joueur"} devra le changer à sa
          première connexion. Il restera « En attente » jusqu'au paiement de l'adhésion et à la
          signature du parrain.
        </p>
      </div>
    </Modal>
  );
}
