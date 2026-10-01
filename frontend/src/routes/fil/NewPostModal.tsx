import { useState } from "react";
import { createPost, type PostVisibility } from "../../api/social";
import { ApiError } from "../../api/client";
import { Banner, Modal, SegmentedControl, TextArea } from "../../design-system";
import { ImagePickerField } from "./ImagePickerField";

const MAX_BODY = 2000;

/** Modale « Nouvelle publication » (A5.1). */
export function NewPostModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [body, setBody] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [visibility, setVisibility] = useState<PostVisibility>("club_only");
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isDirty = body.trim() !== "" || images.length > 0;

  async function handleSubmit(): Promise<void> {
    setError(undefined);
    setSubmitError(null);
    if (!body.trim() && images.length === 0) {
      setError("Écrivez un texte ou ajoutez au moins une image.");
      return;
    }
    if (body.length > MAX_BODY) {
      setError("2 000 caractères au maximum.");
      return;
    }
    setSubmitting(true);
    try {
      await createPost({ body: body.trim(), visibility, images });
      onCreated();
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.detail : "Connexion impossible. Vérifiez votre réseau et réessayez.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Nouvelle publication"
      size="md"
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Publier"
      confirmLoadingLabel="Publication…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        {submitError ? <Banner variant="danger">{submitError}</Banner> : null}
        <TextArea
          label="Texte"
          value={body}
          onChange={setBody}
          rows={4}
          maxLength={MAX_BODY}
          showCount
          placeholder="Quoi de neuf au club ?"
          error={error}
        />
        <div>
          <p className="mb-1 text-sm font-medium text-text">Images (facultatif)</p>
          <ImagePickerField images={images} onChange={setImages} max={4} maxLabel="4 images au maximum." />
        </div>
        <SegmentedControl
          label="Visibilité"
          value={visibility}
          onChange={setVisibility}
          options={[
            { value: "club_only", label: "Club" },
            { value: "public", label: "Publique" },
          ]}
        />
        {visibility === "club_only" ? (
          <p className="text-xs text-text-muted">Visible uniquement par les membres de votre club.</p>
        ) : (
          <Banner variant="warning">
            Visible par les membres de tous les clubs sur Vesta. N'y mettez ni numéro de téléphone, ni
            information de santé, ni montant.
          </Banner>
        )}
      </div>
    </Modal>
  );
}
