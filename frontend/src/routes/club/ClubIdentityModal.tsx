import { useEffect, useRef, useState } from "react";
import { updateClubIdentity } from "../../api/clubs";
import type { ClubIdentity } from "../../api/clubs";
import { ApiError } from "../../api/client";
import {
  Banner,
  Button,
  Modal,
  NumberField,
  SegmentedControl,
  TextField,
  useToast,
} from "../../design-system";
import { extractColorsFromImage } from "../club-creation/colorFromImage";
import { ClubIdentityPreview } from "./ClubIdentityPreview";
import { ImageValidationError, prepareImageForUpload, validateImageFile } from "../fil/imagePrep";

/**
 * Modale « Identité du club » (club-comite-bureau.md §4.1), Président
 * uniquement.
 */
export function ClubIdentityModal({
  identity,
  onClose,
  onUpdated,
  canEditDebtTolerance = true,
}: {
  identity: ClubIdentity;
  onClose: () => void;
  onUpdated: () => void;
  /** Seul le Président modifie la tolérance de dette (l'API refuse les autres rôles). */
  canEditDebtTolerance?: boolean;
}) {
  const { showToast } = useToast();
  const [name, setName] = useState(identity.name);
  const [primaryColor, setPrimaryColor] = useState(identity.primary_color);
  const [secondaryColor, setSecondaryColor] = useState(identity.secondary_color);
  const [city, setCity] = useState(identity.city);
  const [country, setCountry] = useState(identity.country);
  const [currency, setCurrency] = useState<"USD" | "CDF">(identity.currency);
  const [timezone, setTimezone] = useState(identity.timezone);
  const [paymentLinkUrl, setPaymentLinkUrl] = useState(identity.payment_link_url ?? "");
  const [debtToleranceDays, setDebtToleranceDays] = useState<number | null>(
    identity.debt_tolerance_days ?? 0,
  );
  const [logo, setLogo] = useState<File | null>(null);
  const [logoPreviewUrl, setLogoPreviewUrl] = useState<string | null>(null);
  const [preparingLogo, setPreparingLogo] = useState(false);
  const [logoError, setLogoError] = useState<string | undefined>(undefined);
  const logoInputRef = useRef<HTMLInputElement | null>(null);
  const [analysingLogo, setAnalysingLogo] = useState(false);
  const [colorsProposed, setColorsProposed] = useState(false);
  // Identifie la dernière analyse : une réponse tardive d'un ancien logo est ignorée.
  const analysisId = useRef(0);
  // `true` dès que le Président modifie une couleur à la main : un choix
  // explicite ne doit jamais être écrasé sans consentement par la proposition
  // faite au prochain changement de logo (colorFromImage.ts : « n'est qu'une
  // proposition »). Remontée utilisateur : le thème Classic doit refléter les
  // couleurs choisies par le club, pas une extraction automatique qui les ignore.
  const colorsTouchedRef = useRef(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isDirty =
    name !== identity.name ||
    primaryColor !== identity.primary_color ||
    secondaryColor !== identity.secondary_color ||
    city !== identity.city ||
    country !== identity.country ||
    currency !== identity.currency ||
    timezone !== identity.timezone ||
    paymentLinkUrl !== (identity.payment_link_url ?? "") ||
    (canEditDebtTolerance && debtToleranceDays !== (identity.debt_tolerance_days ?? 0)) ||
    logo !== null;

  // Aperçu du fichier nouvellement choisi (FileField + aperçu, §4.1). Révoqué
  // à chaque changement pour ne pas fuiter d'URL objet.
  useEffect(() => {
    if (!logo) {
      setLogoPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(logo);
    setLogoPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [logo]);

  /**
   * Au changement de logo, propose les couleurs extraites (docs/lot0/design-system.md
   * §7.2) : elles pré-remplissent les champs, sans jamais être enregistrées
   * sans l'action du Président.
   */
  async function handleLogoChange(file: File | null): Promise<void> {
    setLogo(file);
    setColorsProposed(false);
    analysisId.current += 1;
    const currentId = analysisId.current;
    if (!file) {
      setAnalysingLogo(false);
      return;
    }
    setAnalysingLogo(true);
    const colors = await extractColorsFromImage(file);
    if (currentId !== analysisId.current) return;
    setAnalysingLogo(false);
    if (colors && !colorsTouchedRef.current) {
      setPrimaryColor(colors.primary);
      setSecondaryColor(colors.secondary);
      setColorsProposed(true);
    }
  }

  /**
   * Sélection d'un fichier via le bouton stylé (remarques.md : plus de
   * `<input type="file">` brut). Valide le format/poids, compresse l'image
   * dans le navigateur (remarques.md : « tout fichier doit être compressé »,
   * même utilitaire que le fil : `imagePrep.ts`), puis déclenche la même
   * proposition de couleurs qu'auparavant.
   */
  async function handlePickLogo(fileList: FileList | null): Promise<void> {
    const file = fileList?.[0] ?? null;
    if (!file) return;
    setLogoError(undefined);
    setPreparingLogo(true);
    try {
      validateImageFile(file);
      const prepared = await prepareImageForUpload(file);
      await handleLogoChange(prepared);
    } catch (err) {
      setLogoError(
        err instanceof ImageValidationError ? err.message : "Cette image n'a pas pu être ajoutée.",
      );
    } finally {
      setPreparingLogo(false);
      if (logoInputRef.current) logoInputRef.current.value = "";
    }
  }

  async function handleSave(): Promise<void> {
    setErrors({});
    setGlobalError(null);
    if (!name.trim()) {
      setErrors({ name: "Ce champ est obligatoire." });
      return;
    }
    if (canEditDebtTolerance && debtToleranceDays === null) {
      setErrors({ debt_tolerance_days: "Saisissez un nombre de jours entre 0 et 90." });
      return;
    }
    setSubmitting(true);
    try {
      await updateClubIdentity({
        name: name.trim(),
        logo,
        primary_color: primaryColor,
        secondary_color: secondaryColor,
        city: city.trim(),
        country: country.trim(),
        currency: identity.currency_locked ? undefined : currency,
        timezone,
        payment_link_url: paymentLinkUrl,
        debt_tolerance_days: canEditDebtTolerance ? (debtToleranceDays ?? undefined) : undefined,
      });
      showToast("Identité du club mise à jour.");
      onUpdated();
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length > 0) {
        const flat: Record<string, string> = {};
        for (const [k, v] of Object.entries(err.fields)) flat[k] = v[0] ?? "";
        setErrors(flat);
      }
      setGlobalError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Identité du club"
      size="md"
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={() => void handleSave()}
    >
      <div className="space-y-4">
        {globalError ? <Banner variant="danger">{globalError}</Banner> : null}
        <TextField label="Nom du club" value={name} onChange={setName} error={errors.name} />
        <div>
          <p className="mb-1 text-sm font-medium text-text">Logo (facultatif)</p>
          <div className="flex items-center gap-3">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border bg-surface-muted">
              {logoPreviewUrl ? (
                <img src={logoPreviewUrl} alt="Aperçu du logo choisi" className="h-full w-full object-cover" />
              ) : identity.logo ? (
                <img src={identity.logo} alt="Logo actuel du club" className="h-full w-full object-cover" />
              ) : (
                <span className="px-1 text-center text-[10px] leading-tight text-text-muted">
                  Aucun logo
                </span>
              )}
            </div>
            <div>
              <input
                ref={logoInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="sr-only"
                onChange={(e) => void handlePickLogo(e.target.files)}
              />
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={preparingLogo}
                loading={preparingLogo}
                loadingLabel="Préparation de l'image…"
                onClick={() => logoInputRef.current?.click()}
              >
                {identity.logo || logo ? "Remplacer le logo" : "Choisir un logo"}
              </Button>
              {logoError ? <p className="mt-1 text-xs text-status-danger-fg">{logoError}</p> : null}
              {analysingLogo ? (
                <p role="status" className="mt-1 text-xs text-text-muted">
                  Analyse du logo en cours…
                </p>
              ) : null}
            </div>
          </div>
        </div>
        {colorsProposed ? (
          <Banner variant="info">
            Couleurs proposées à partir du logo. Modifiez-les si besoin, elles ne seront
            enregistrées qu&apos;avec le bouton « Enregistrer ».
          </Banner>
        ) : null}
        <div className="grid grid-cols-2 gap-3">
          <TextField
            label="Couleur principale"
            value={primaryColor}
            onChange={(v) => {
              colorsTouchedRef.current = true;
              setPrimaryColor(v);
            }}
            error={errors.primary_color}
          />
          <TextField
            label="Couleur secondaire"
            value={secondaryColor}
            onChange={(v) => {
              colorsTouchedRef.current = true;
              setSecondaryColor(v);
            }}
            error={errors.secondary_color}
          />
        </div>
        <ClubIdentityPreview
          logoUrl={logoPreviewUrl ?? identity.logo}
          name={name}
          primaryColor={primaryColor}
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextField label="Ville" value={city} onChange={setCity} error={errors.city} />
          <TextField label="Pays" value={country} onChange={setCountry} error={errors.country} />
        </div>
        {identity.currency_locked ? (
          <div>
            <p className="mb-1 text-sm font-medium text-text">Devise</p>
            <p className="text-sm text-text-muted">{identity.currency}</p>
            <p className="mt-1 text-xs text-text-muted">
              La devise ne peut plus être changée : des paiements existent déjà.
            </p>
          </div>
        ) : (
          <SegmentedControl
            label="Devise"
            value={currency}
            onChange={setCurrency}
            options={[
              { value: "USD", label: "USD" },
              { value: "CDF", label: "CDF" },
            ]}
          />
        )}
        <TextField label="Fuseau horaire" value={timezone} onChange={setTimezone} error={errors.timezone} />
        <TextField
          label="Lien de paiement"
          optional
          type="url"
          value={paymentLinkUrl}
          onChange={setPaymentLinkUrl}
          error={errors.payment_link_url}
          help="Saisissez une adresse commençant par https://"
        />
        {canEditDebtTolerance ? (
          <NumberField
            label="Jours de tolérance avant qu'un retard devienne une dette"
            value={debtToleranceDays}
            onChange={setDebtToleranceDays}
            min={0}
            max={90}
            help="0 = la dette naît le lendemain de l'échéance"
            error={errors.debt_tolerance_days}
          />
        ) : (
          <div>
            <p className="mb-1 text-sm font-medium text-text">Tolérance de dette</p>
            <p className="text-sm text-text-muted">{identity.debt_tolerance_days ?? 0} jour(s)</p>
          </div>
        )}
      </div>
    </Modal>
  );
}
