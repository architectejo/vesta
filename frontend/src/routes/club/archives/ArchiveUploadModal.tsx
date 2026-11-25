import { useRef, useState } from "react";
import {
  replaceArchivedDocument,
  uploadArchivedDocument,
  type ArchiveCategory,
  type ArchivedDocument,
} from "../../../api/assemblies";
import { ApiError } from "../../../api/client";
import {
  Banner,
  Button,
  IconCamera,
  IconDocumentImage,
  IconDocumentPdf,
  IconUpload,
  Modal,
  SegmentedControl,
  TextField,
  useToast,
} from "../../../design-system";
import { prepareImageForUpload } from "../../fil/imagePrep";
import { formatFileSize, todayIso } from "./archivesFormat";

const MAX_FILE_BYTES = 10 * 1024 * 1024;
/** Plafond de côté des photos de documents (club-archives.md §4.1, point ouvert 9). */
const MAX_DOCUMENT_IMAGE_SIDE_PX = 2400;
const ACCEPTED_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/webp"];
const TITLE_MAX = 160;

const CATEGORY_OPTIONS: Array<{ value: ArchiveCategory; label: string }> = [
  { value: "pv_reunion", label: "PV de réunion" },
  { value: "convocation", label: "Convocation" },
  { value: "autre", label: "Autre" },
];

export function validateArchiveFile(file: File): string | null {
  if (!ACCEPTED_TYPES.includes(file.type)) return "Format non accepté : JPEG, PNG, WebP ou PDF.";
  if (file.size > MAX_FILE_BYTES) return "Fichier trop lourd : 10 Mo maximum.";
  return null;
}

/**
 * Modale « Déposer un document » (club-archives.md §4.1). Avec `replacing`,
 * même formulaire mais le fichier remplace un document existant : l'ancien est
 * retiré et conservé par l'API (`POST documents/<id>/replace/`).
 */
export function ArchiveUploadModal({
  replacing,
  onClose,
  onDone,
}: {
  replacing?: ArchivedDocument;
  onClose: () => void;
  onDone: (document: ArchivedDocument) => void;
}) {
  const { showToast } = useToast();
  const [title, setTitle] = useState(replacing?.title ?? "");
  const [category, setCategory] = useState<ArchiveCategory | null>(replacing?.category ?? null);
  const [documentDate, setDocumentDate] = useState(replacing?.document_date ?? todayIso());
  const [file, setFile] = useState<File | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [errors, setErrors] = useState<{ title?: string; category?: string; date?: string; file?: string }>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const cameraInputRef = useRef<HTMLInputElement | null>(null);

  const online = typeof navigator === "undefined" ? true : navigator.onLine;
  const isDirty = file !== null || (replacing ? title !== replacing.title : title.trim() !== "");

  async function handleFile(list: FileList | null): Promise<void> {
    const picked = list?.[0];
    if (!picked) return;
    const problem = validateArchiveFile(picked);
    if (problem) {
      setFile(null);
      setErrors((e) => ({ ...e, file: problem }));
      return;
    }
    setErrors((e) => ({ ...e, file: undefined }));
    setPreparing(true);
    try {
      const ready = picked.type.startsWith("image/")
        ? await prepareImageForUpload(picked, MAX_DOCUMENT_IMAGE_SIDE_PX)
        : picked;
      setFile(ready);
    } finally {
      setPreparing(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (cameraInputRef.current) cameraInputRef.current.value = "";
    }
  }

  async function handleSubmit(): Promise<void> {
    setSubmitError(null);
    const next: typeof errors = {};
    if (!title.trim()) next.title = "Ce champ est obligatoire.";
    else if (title.trim().length > TITLE_MAX) next.title = "160 caractères au maximum.";
    if (!category) next.category = "Choisissez une catégorie.";
    if (!documentDate) next.date = "Ce champ est obligatoire.";
    else if (documentDate > todayIso()) next.date = "La date ne peut pas être dans le futur.";
    if (!file) next.file = "Ajoutez le fichier du document.";
    setErrors(next);
    if (Object.keys(next).length > 0 || !file || !category) return;

    setSubmitting(true);
    try {
      const input = { category, title: title.trim(), document_date: documentDate, file };
      const created = replacing
        ? await replaceArchivedDocument(replacing.id, input)
        : await uploadArchivedDocument(input);
      showToast(
        replacing ? "Document remplacé. L'ancien est retiré mais conservé." : "Document déposé dans les archives.",
      );
      onDone(created);
    } catch (err) {
      // Le fichier choisi est conservé pour pouvoir réessayer (§4.1).
      if (err instanceof ApiError && Object.keys(err.fields).length > 0) {
        setErrors({
          title: err.fieldError("title"),
          category: err.fieldError("category"),
          date: err.fieldError("document_date"),
          file: err.fieldError("file"),
        });
      } else {
        setSubmitError(
          err instanceof ApiError ? err.detail : "Connexion impossible. Vérifiez votre réseau et réessayez.",
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  const isImage = file?.type.startsWith("image/") ?? false;

  return (
    <Modal
      open
      onClose={onClose}
      title={replacing ? "Remplacer le document" : "Déposer un document"}
      size="md"
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel={replacing ? "Remplacer" : "Déposer"}
      confirmLoadingLabel="Envoi…"
      confirmDisabled={!online || preparing}
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        {!online ? <Banner variant="info">Cette action nécessite une connexion.</Banner> : null}
        {submitError ? <Banner variant="danger">{submitError}</Banner> : null}
        <div>
          <TextField
            label="Titre"
            value={title}
            maxLength={TITLE_MAX}
            onChange={setTitle}
            error={errors.title}
            help="Exemple : PV de la réunion du bureau du 4 octobre 2026."
          />
          {title.length >= 120 ? (
            <p className="mt-1 text-right text-xs text-text-muted">
              {title.length} / {TITLE_MAX}
            </p>
          ) : null}
        </div>
        <SegmentedControl<ArchiveCategory>
          label="Catégorie"
          value={category}
          onChange={setCategory}
          options={CATEGORY_OPTIONS}
          error={errors.category}
        />
        <TextField
          label="Date du document"
          type="date"
          value={documentDate}
          max={todayIso()}
          onChange={setDocumentDate}
          error={errors.date}
          help="Date de la réunion ou date inscrite sur le document."
        />
        <div>
          <p className="mb-1 text-sm font-medium text-text">Fichier</p>
          <input
            ref={fileInputRef}
            type="file"
            aria-label="Choisir un fichier"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            className="sr-only"
            onChange={(e) => void handleFile(e.target.files)}
          />
          <input
            ref={cameraInputRef}
            type="file"
            aria-label="Prendre une photo"
            accept="image/*"
            capture="environment"
            className="sr-only"
            onChange={(e) => void handleFile(e.target.files)}
          />
          {file ? (
            <div className="flex items-center gap-3 rounded-md border border-border p-2">
              {isImage ? (
                <IconDocumentImage aria-hidden="true" className="h-6 w-6 shrink-0 text-text-muted" />
              ) : (
                <IconDocumentPdf aria-hidden="true" className="h-6 w-6 shrink-0 text-text-muted" />
              )}
              <div className="min-w-0 flex-1">
                <p className="break-words text-sm text-text">{file.name}</p>
                <p className="text-[13px] text-text-muted">{formatFileSize(file.size)}</p>
              </div>
              <Button variant="ghost" size="sm" disabled={submitting} onClick={() => fileInputRef.current?.click()}>
                Changer de fichier
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                size="sm"
                loading={preparing}
                loadingLabel="Préparation…"
                icon={<IconUpload aria-hidden="true" className="h-4 w-4" />}
                onClick={() => fileInputRef.current?.click()}
              >
                Choisir un fichier
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={preparing}
                icon={<IconCamera aria-hidden="true" className="h-4 w-4" />}
                onClick={() => cameraInputRef.current?.click()}
              >
                Prendre une photo
              </Button>
            </div>
          )}
          {errors.file ? (
            <p role="alert" className="mt-1 text-xs text-status-danger-fg">
              {errors.file}
            </p>
          ) : (
            <p className="mt-1 text-xs text-text-muted">
              Un document de plusieurs pages : préférez un PDF. Une photo doit rester lisible : cadrez la page entière,
              sans reflet. PDF, JPEG, PNG ou WebP, 10 Mo maximum.
            </p>
          )}
        </div>
      </div>
    </Modal>
  );
}
