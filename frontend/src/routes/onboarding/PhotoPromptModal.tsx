import { useState } from "react";
import { updateProfilePhoto } from "../../api/auth";
import { ApiError } from "../../api/client";
import { Avatar, Banner, Button, Modal, useToast } from "../../design-system";

/**
 * Modale non bloquante « Ajoutez votre photo » (club-accueil.md §3 étape 3).
 * « Plus tard » autorisé (proposition retenue par la spec, §8).
 */
export function PhotoPromptModal({
  fullName,
  onClose,
  onSaved,
}: {
  fullName: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { showToast } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function handleFileChange(selected: File | null): void {
    setFile(selected);
    setPreviewUrl(selected ? URL.createObjectURL(selected) : null);
  }

  async function handleSave(): Promise<void> {
    if (!file) {
      onClose();
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await updateProfilePhoto(file);
      showToast("Photo mise à jour.");
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
      title="Ajoutez votre photo"
      size="sm"
      isSubmitting={submitting}
      cancelLabel="Plus tard"
      confirmLabel="Enregistrer la photo"
      confirmLoadingLabel="Enregistrement…"
      confirmDisabled={!file}
      onConfirm={() => void handleSave()}
    >
      <div className="flex flex-col items-center gap-3">
        {error ? <Banner variant="danger" className="w-full">{error}</Banner> : null}
        <Avatar name={fullName} photoUrl={previewUrl} size={72} />
        <label className="inline-block">
          <span className="sr-only">Choisir une photo</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
            className="hidden"
            id="photo-prompt-input"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => document.getElementById("photo-prompt-input")?.click()}
          >
            Choisir une photo
          </Button>
        </label>
      </div>
    </Modal>
  );
}
