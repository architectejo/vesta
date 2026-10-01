import { useState } from "react";
import { activateLicence, extendLicence } from "../../api/licences";
import type { Licence } from "../../api/licences";
import { ApiError } from "../../api/client";
import { Banner, Modal, TextField, useToast } from "../../design-system";

function dayAfter(dateStr: string): string {
  const date = new Date(dateStr);
  date.setDate(date.getDate() + 1);
  return date.toISOString().slice(0, 10);
}

/**
 * Modale « Attribuer une licence » / « Prolonger la licence » / « Activer
 * la licence » (superuser-espace.md §4.2). Le champ « Club » est toujours
 * prérempli et en lecture seule ici : ouverte depuis le détail d'un club
 * uniquement (chaque club dispose déjà d'une licence créée avec lui, voir
 * `apps.clubs.club_creation`), jamais depuis un choix libre de club.
 */
export function LicenceFormModal({
  licence,
  mode,
  onClose,
  onSaved,
}: {
  licence: Licence;
  mode: "activate" | "extend";
  onClose: () => void;
  onSaved: () => void;
}) {
  const { showToast } = useToast();
  const [startDate, setStartDate] = useState(
    mode === "extend" ? dayAfter(licence.end_date) : new Date().toISOString().slice(0, 10),
  );
  const [endDate, setEndDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSave(): Promise<void> {
    if (!endDate) {
      setError("Indiquez la date de fin.");
      return;
    }
    if (startDate && endDate <= startDate) {
      setError("La date de fin doit être postérieure à la date de début.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      if (mode === "activate") {
        await activateLicence(licence.id, { start_date: startDate, end_date: endDate });
      } else {
        await extendLicence(licence.id, { end_date: endDate, start_date: startDate });
      }
      showToast(`Licence enregistrée pour ${licence.club_name} jusqu'au ${endDate}.`);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={mode === "activate" ? "Activer la licence" : "Prolonger la licence"}
      size="sm"
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={() => void handleSave()}
    >
      <div className="space-y-4">
        {error ? <Banner variant="danger">{error}</Banner> : null}
        <TextField label="Club" value={licence.club_name} onChange={() => {}} disabled />
        <TextField label="Date de début" type="date" value={startDate} onChange={setStartDate} />
        <TextField label="Date de fin" type="date" value={endDate} onChange={setEndDate} />
        <p className="text-xs text-text-muted">
          La licence est active entre ces deux dates. Après la date de fin, le club dispose de{" "}
          {licence.grace_period_days} jours de grâce avant de passer en lecture seule.
        </p>
      </div>
    </Modal>
  );
}
