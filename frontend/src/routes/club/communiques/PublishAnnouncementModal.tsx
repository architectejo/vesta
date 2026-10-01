import { useState } from "react";
import { createAnnouncement } from "../../../api/social";
import { ApiError } from "../../../api/client";
import { Banner, Checkbox, Modal, TextArea, TextField } from "../../../design-system";
import { ImagePickerField } from "../../fil/ImagePickerField";

/** Modale « Publier un communiqué » (club-accueil.md §5.2 ; Président, VP). */
export function PublishAnnouncementModal({ onClose, onPublished }: { onClose: () => void; onPublished: () => void }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [pinned, setPinned] = useState(true);
  const [titleError, setTitleError] = useState<string | undefined>(undefined);
  const [bodyError, setBodyError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isDirty = title.trim() !== "" || body.trim() !== "" || images.length > 0;

  async function handleSubmit(): Promise<void> {
    setTitleError(undefined);
    setBodyError(undefined);
    setSubmitError(null);
    let hasError = false;
    if (!title.trim()) {
      setTitleError("Ce champ est obligatoire.");
      hasError = true;
    }
    if (!body.trim()) {
      setBodyError("Ce champ est obligatoire.");
      hasError = true;
    }
    if (hasError) return;
    setSubmitting(true);
    try {
      await createAnnouncement({ title: title.trim(), body: body.trim(), images, pinned });
      onPublished();
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : "Connexion impossible. Vérifiez votre réseau et réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Publier un communiqué"
      size="md"
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Publier"
      confirmLoadingLabel="Publication…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        {submitError ? <Banner variant="danger">{submitError}</Banner> : null}
        <TextField label="Titre" value={title} onChange={(v) => setTitle(v.slice(0, 120))} error={titleError} />
        <TextArea label="Message" value={body} onChange={setBody} rows={5} maxLength={2000} showCount error={bodyError} />
        <div>
          <p className="mb-1 text-sm font-medium text-text">Images (facultatif)</p>
          <ImagePickerField images={images} onChange={setImages} max={4} maxLabel="4 images au maximum." />
        </div>
        <Checkbox checked={pinned} onChange={setPinned} label="Épingler en tête de l'accueil" />
      </div>
    </Modal>
  );
}
