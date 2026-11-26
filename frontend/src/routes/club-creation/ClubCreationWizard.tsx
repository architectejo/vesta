import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { createClub, getPublicClubCreationSettings } from "../../api/clubs";
import type { ClubCreationInput } from "../../api/clubs";
import type { TermsVersion } from "../../api/auth";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import {
  Banner,
  Button,
  Checkbox,
  EmptyState,
  Loader,
  Modal,
  SegmentedControl,
  TextField,
} from "../../design-system";
import { extractColorsFromImage } from "./colorFromImage";
import { DEFAULT_TIMEZONE_BY_COUNTRY, FRENCH_COUNTRY_NAMES } from "./countries";

type Position = "goalkeeper" | "defender" | "midfielder" | "forward";

const POSITION_OPTIONS: Array<{ value: Position; label: string }> = [
  { value: "goalkeeper", label: "Gardien" },
  { value: "defender", label: "Défenseur" },
  { value: "midfielder", label: "Milieu" },
  { value: "forward", label: "Attaquant" },
];

interface Step1 {
  name: string;
  logo: File | null;
  primaryColor: string;
  secondaryColor: string;
  /**
   * `true` dès que le Président a modifié une couleur à la main. Empêche un
   * changement de logo ultérieur d'écraser silencieusement ce choix : la
   * couleur extraite du logo n'est qu'une proposition (`colorFromImage.ts`),
   * jamais prioritaire sur un choix explicite (remontée utilisateur : les
   * couleurs choisies à l'inscription doivent rester celles du thème Classic).
   */
  colorsTouched: boolean;
  city: string;
  country: string;
  currency: "USD" | "CDF";
  timezone: string;
}

interface Step2 {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  position: Position | null;
  positionDetail: string;
  jerseyNumber: string;
  birthDate: string;
  weightKg: string;
  heightCm: string;
}

const TERMS_UNAVAILABLE_MESSAGE =
  "Les conditions générales d'utilisation ne sont pas encore publiées : la création de club est momentanément impossible. Réessayez plus tard ou contactez le support Vesta.";

const STEP_NAMES =["Votre club", "Votre fiche joueur", "Licence et validation"];

/**
 * Assistant de création de club (docs/ecrans/clubs-creation.md). Modale
 * `xl` ouverte par-dessus la page de connexion. Une clé d'idempotence est
 * générée une seule fois à l'ouverture et réutilisée sur tout nouvel envoi
 * (contrat de `apps.clubs.club_creation.create_club_with_founder`).
 */
export function ClubCreationWizard({ onClose }: { onClose: () => void }) {
  const auth = useAuth();
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [step1, setStep1] = useState<Step1>({
    name: "",
    logo: null,
    primaryColor: "",
    secondaryColor: "",
    colorsTouched: false,
    city: "",
    country: "",
    currency: "USD",
    timezone: "",
  });
  const [step1Errors, setStep1Errors] = useState<Record<string, string>>({});
  const [step2, setStep2] = useState<Step2>({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    position: null,
    positionDetail: "",
    jerseyNumber: "",
    birthDate: "",
    weightKg: "",
    heightCm: "",
  });
  const [step2Errors, setStep2Errors] = useState<Record<string, string>>({});
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [termsError, setTermsError] = useState<string | null>(null);
  const [activeTerms, setActiveTerms] = useState<TermsVersion | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<Awaited<ReturnType<typeof createClub>> | null>(null);
  const [logoPreviewUrl, setLogoPreviewUrl] = useState<string | null>(null);

  const settingsQuery = useQuery({
    queryKey: ["club-creation-settings"],
    queryFn: getPublicClubCreationSettings,
  });

  const termsVersion = activeTerms ?? settingsQuery.data?.terms_version ?? null;

  const isDirty =
    step1.name !== "" ||
    step1.logo !== null ||
    step1.city !== "" ||
    step1.country !== "" ||
    step2.firstName !== "" ||
    step2.lastName !== "" ||
    step2.email !== "";

  async function handleLogoChange(file: File | null): Promise<void> {
    setStep1((s) => ({ ...s, logo: file }));
    setLogoPreviewUrl(file ? URL.createObjectURL(file) : null);
    if (file) {
      const colors = await extractColorsFromImage(file);
      if (colors) {
        // Ne propose les couleurs extraites que si le Président n'a encore
        // rien choisi lui-même : un choix manuel, même antérieur à ce nouveau
        // logo, ne doit jamais être écrasé sans action explicite.
        setStep1((s) =>
          s.colorsTouched ? s : { ...s, primaryColor: colors.primary, secondaryColor: colors.secondary },
        );
      }
    }
  }

  function validateStep1(): boolean {
    const errors: Record<string, string> = {};
    if (!step1.name.trim()) errors.name = "Ce champ est obligatoire.";
    else if (step1.name.length > 120) errors.name = "120 caractères au maximum.";
    if (!step1.city.trim()) errors.city = "Ce champ est obligatoire.";
    if (!step1.country.trim()) errors.country = "Ce champ est obligatoire.";
    else if (!FRENCH_COUNTRY_NAMES.includes(step1.country)) {
      errors.country = "Choisissez un pays dans la liste.";
    }
    if (!step1.timezone) errors.timezone = "Ce champ est obligatoire.";
    const hexRe = /^#[0-9A-Fa-f]{6}$/;
    if (step1.primaryColor && !hexRe.test(step1.primaryColor)) {
      errors.primaryColor = "Saisissez une couleur au format #RRGGBB.";
    }
    if (step1.secondaryColor && !hexRe.test(step1.secondaryColor)) {
      errors.secondaryColor = "Saisissez une couleur au format #RRGGBB.";
    }
    setStep1Errors(errors);
    return Object.keys(errors).length === 0;
  }

  function validateStep2(): boolean {
    const errors: Record<string, string> = {};
    if (!step2.firstName.trim()) errors.firstName = "Ce champ est obligatoire.";
    if (!step2.lastName.trim()) errors.lastName = "Ce champ est obligatoire.";
    if (!/^\S+@\S+\.\S+$/.test(step2.email.trim())) {
      errors.email = "Saisissez une adresse email valide.";
    }
    if (!step2.position) errors.position = "Choisissez un poste.";
    if (step2.jerseyNumber) {
      const n = Number(step2.jerseyNumber);
      if (!Number.isInteger(n) || n < 1 || n > 99) {
        errors.jerseyNumber = "Saisissez un numéro entre 1 et 99.";
      }
    }
    if (step2.birthDate && new Date(step2.birthDate) > new Date()) {
      errors.birthDate = "La date ne peut pas être dans le futur.";
    }
    setStep2Errors(errors);
    return Object.keys(errors).length === 0;
  }

  function goNext(): void {
    if (step === 1 && validateStep1()) setStep(2);
    else if (step === 2 && validateStep2()) setStep(3);
  }

  async function handleSubmit(): Promise<void> {
    if (!termsVersion) {
      // Garde-fou : le bouton est désactivé dans ce cas, mais on ne reste jamais muet.
      setSubmitError(TERMS_UNAVAILABLE_MESSAGE);
      return;
    }
    if (!acceptTerms) {
      setTermsError("Vous devez accepter les conditions générales pour créer votre club.");
      return;
    }
    setSubmitError(null);
    setSubmitting(true);
    try {
      const input: ClubCreationInput = {
        idempotency_key: idempotencyKey,
        name: step1.name.trim(),
        logo: step1.logo,
        primary_color: step1.primaryColor,
        secondary_color: step1.secondaryColor,
        city: step1.city.trim(),
        country: step1.country.trim(),
        currency: step1.currency,
        timezone_name: step1.timezone,
        email: step2.email.trim(),
        first_name: step2.firstName.trim(),
        last_name: step2.lastName.trim(),
        phone: step2.phone.trim(),
        position: step2.position as Position,
        position_detail: step2.positionDetail.trim(),
        jersey_number: step2.jerseyNumber ? Number(step2.jerseyNumber) : null,
        birth_date: step2.birthDate || null,
        weight_kg: step2.weightKg ? Number(step2.weightKg) : null,
        height_cm: step2.heightCm ? Number(step2.heightCm) : null,
        terms_version_id: termsVersion.id,
        accept_terms: acceptTerms,
      };
      const result = await createClub(input);
      setSuccess(result);
    } catch (err) {
      if (err instanceof ApiError && err.code === "terms_version_outdated") {
        const raw = err.raw as { terms_version?: TermsVersion };
        setActiveTerms(raw.terms_version ?? null);
        setAcceptTerms(false);
        setSubmitError(
          "Les conditions générales ont été mises à jour. Lisez la nouvelle version et acceptez-la pour continuer.",
        );
      } else if (err instanceof ApiError && err.code === "email_already_used") {
        setStep(2);
        setStep2Errors((prev) => ({ ...prev, email: "Cette adresse email est déjà utilisée." }));
      } else if (err instanceof ApiError && err.fields.email) {
        setStep(2);
        setStep2Errors((prev) => ({ ...prev, email: err.fieldError("email") ?? "" }));
      } else if (err instanceof ApiError) {
        setSubmitError(
          err.detail || "La création n'a pas abouti. Vérifiez les informations saisies et réessayez.",
        );
      } else {
        setSubmitError(
          "La création n'a pas abouti. Aucune donnée n'a été enregistrée. Vérifiez votre réseau et réessayez.",
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  function handleAccessClub(): void {
    if (!success) return;
    auth.applySession(success);
    onClose();
  }

  const countrySuggestions = useMemo(
    () => FRENCH_COUNTRY_NAMES.filter((c) => c.toLowerCase().includes(step1.country.toLowerCase())),
    [step1.country],
  );

  if (success) {
    return (
      <Modal
        open
        onClose={() => {}}
        blocking
        title="Créer votre club"
        size="xl"
        footer={
          <Button variant="primary" onClick={handleAccessClub}>
            Accéder à mon club
          </Button>
        }
      >
        <div className="space-y-3">
          <Banner variant="info">Votre club {success.club.name} est créé.</Banner>
          <p className="text-sm text-text">
            Adresse de connexion de votre club : vesta.eschoolb.com/c/{success.club.slug}
          </p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              void navigator.clipboard?.writeText(`vesta.eschoolb.com/c/${success.club.slug}`);
            }}
          >
            Copier l'adresse
          </Button>
          <p className="text-sm text-text">
            Licence d'essai jusqu'au {success.licence.end_date}.
          </p>
          <p className="text-sm text-text">
            Votre mot de passe provisoire est votre email. Vous allez devoir le changer tout de
            suite.
          </p>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Créer votre club"
      subtitle={`Étape ${step} sur 3 — ${STEP_NAMES[step - 1]}`}
      size="xl"
      isDirty={isDirty}
      isSubmitting={submitting}
      hideFooter
    >
      <div className="mb-4 h-[3px] w-full rounded-full bg-surface-muted">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${(step / 3) * 100}%` }}
        />
      </div>

      {step === 1 ? (
        <div className="space-y-4">
          <p className="text-sm text-text-muted">
            Ces informations s'affichent sur l'espace de votre club. Vous pourrez les modifier
            plus tard.
          </p>
          <TextField
            label="Nom du club"
            value={step1.name}
            onChange={(v) => setStep1((s) => ({ ...s, name: v }))}
            error={step1Errors.name}
          />
          <div>
            <p className="mb-1 text-sm font-medium text-text">Logo (facultatif)</p>
            <div className="flex items-center gap-3">
              {logoPreviewUrl ? (
                <img src={logoPreviewUrl} alt="" className="h-[72px] w-[72px] rounded-md object-cover" />
              ) : null}
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(e) => void handleLogoChange(e.target.files?.[0] ?? null)}
                className="text-sm"
              />
              {step1.logo ? (
                <Button variant="ghost" size="sm" onClick={() => void handleLogoChange(null)}>
                  Retirer
                </Button>
              ) : null}
            </div>
            <p className="mt-1 text-xs text-text-muted">
              Le logo apparaît en haut du menu et sur la page de connexion de votre club.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <TextField
              label="Couleur principale (facultatif)"
              value={step1.primaryColor}
              onChange={(v) => setStep1((s) => ({ ...s, primaryColor: v, colorsTouched: true }))}
              placeholder="#1D4ED8"
              error={step1Errors.primaryColor}
            />
            <TextField
              label="Couleur secondaire (facultatif)"
              value={step1.secondaryColor}
              onChange={(v) => setStep1((s) => ({ ...s, secondaryColor: v, colorsTouched: true }))}
              placeholder="#0F172A"
              error={step1Errors.secondaryColor}
            />
          </div>
          {!step1.primaryColor && !step1.secondaryColor ? (
            <p className="text-xs text-text-muted">
              Sans couleurs, votre club utilisera un thème neutre. Vous pourrez les ajouter plus
              tard.
            </p>
          ) : (
            <>
              {!step1.colorsTouched && step1.logo ? (
                <p className="text-xs text-text-muted">
                  Couleurs proposées à partir du logo. Modifiez-les si besoin : le thème Classic de
                  votre club utilisera exactement les couleurs ci-dessus.
                </p>
              ) : null}
              <div className="flex h-[88px] items-center gap-3 rounded-md border border-border p-3">
                <span
                  className="h-10 w-10 shrink-0 rounded-md"
                  style={{ backgroundColor: step1.primaryColor || "#e1e5eb" }}
                />
                <div>
                  <p className="text-sm font-semibold text-text">{step1.name || "Votre club"}</p>
                  <span
                    className="mt-1 inline-block rounded-sm px-3 py-1 text-xs font-medium text-white"
                    style={{ backgroundColor: step1.primaryColor || "#1D4ED8" }}
                  >
                    Bouton principal
                  </span>
                </div>
              </div>
            </>
          )}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <TextField
              label="Ville"
              value={step1.city}
              onChange={(v) => setStep1((s) => ({ ...s, city: v }))}
              error={step1Errors.city}
            />
            <div>
              <TextField
                label="Pays"
                value={step1.country}
                onChange={(v) => {
                  setStep1((s) => ({ ...s, country: v }));
                  const tz = DEFAULT_TIMEZONE_BY_COUNTRY[v];
                  if (tz) setStep1((s) => ({ ...s, timezone: tz }));
                }}
                error={step1Errors.country}
                list="club-creation-countries"
              />
              <datalist id="club-creation-countries">
                {countrySuggestions.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <SegmentedControl
              label="Devise"
              value={step1.currency}
              onChange={(v) => setStep1((s) => ({ ...s, currency: v }))}
              options={[
                { value: "USD", label: "USD" },
                { value: "CDF", label: "CDF" },
              ]}
              help="Devise de toutes les cotisations et dépenses du club."
            />
            <div>
              <label htmlFor="wizard-timezone" className="mb-1 block text-sm font-medium text-text">
                Fuseau horaire
              </label>
              {settingsQuery.isLoading ? (
                <Loader loading variant="list" count={1} />
              ) : (
                <select
                  id="wizard-timezone"
                  value={step1.timezone}
                  onChange={(e) => setStep1((s) => ({ ...s, timezone: e.target.value }))}
                  className="h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text"
                >
                  <option value="">Choisissez un fuseau</option>
                  {(settingsQuery.data?.timezones ?? []).map((tz) => (
                    <option key={tz} value={tz}>
                      {tz}
                    </option>
                  ))}
                </select>
              )}
              {step1Errors.timezone ? (
                <p className="mt-1 text-xs text-status-danger-fg">{step1Errors.timezone}</p>
              ) : (
                <p className="mt-1 text-xs text-text-muted">
                  Sert à dater les séances, les paiements et les échéances.
                </p>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {step === 2 ? (
        <div className="space-y-4">
          <Banner variant="info">
            Sur Vesta, tout membre du club est un joueur, le Président aussi. Vous deviendrez
            Président de ce club et figurerez dans son effectif.
          </Banner>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <TextField
              label="Prénom"
              autoComplete="given-name"
              value={step2.firstName}
              onChange={(v) => setStep2((s) => ({ ...s, firstName: v }))}
              error={step2Errors.firstName}
            />
            <TextField
              label="Nom"
              autoComplete="family-name"
              value={step2.lastName}
              onChange={(v) => setStep2((s) => ({ ...s, lastName: v }))}
              error={step2Errors.lastName}
            />
          </div>
          <TextField
            label="Email"
            type="email"
            value={step2.email}
            onChange={(v) => setStep2((s) => ({ ...s, email: v }))}
            error={step2Errors.email}
            help="Ce sera votre identifiant de connexion."
          />
          <TextField
            label="Téléphone (WhatsApp)"
            type="tel"
            optional
            value={step2.phone}
            onChange={(v) => setStep2((s) => ({ ...s, phone: v }))}
            help="Pour recevoir les reçus et les communiqués."
          />
          <SegmentedControl
            label="Poste"
            value={step2.position}
            onChange={(v) => setStep2((s) => ({ ...s, position: v }))}
            options={POSITION_OPTIONS}
            error={step2Errors.position}
            wrapOnMobile
          />
          <TextField
            label="Poste précis"
            optional
            value={step2.positionDetail}
            onChange={(v) => setStep2((s) => ({ ...s, positionDetail: v }))}
            placeholder="Arrière gauche"
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <TextField
              label="Numéro de maillot"
              optional
              type="number"
              value={step2.jerseyNumber}
              onChange={(v) => setStep2((s) => ({ ...s, jerseyNumber: v }))}
              error={step2Errors.jerseyNumber}
            />
            <TextField
              label="Date de naissance"
              optional
              type="date"
              value={step2.birthDate}
              onChange={(v) => setStep2((s) => ({ ...s, birthDate: v }))}
              error={step2Errors.birthDate}
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <TextField
              label="Poids (kg)"
              optional
              type="number"
              value={step2.weightKg}
              onChange={(v) => setStep2((s) => ({ ...s, weightKg: v }))}
            />
            <TextField
              label="Taille (cm)"
              optional
              type="number"
              value={step2.heightCm}
              onChange={(v) => setStep2((s) => ({ ...s, heightCm: v }))}
            />
          </div>
          <p className="text-xs text-text-muted">
            Vous n'avez pas besoin de parrain. Votre cotisation sera définie plus tard, quand le
            club aura créé ses types de cotisation.
          </p>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="space-y-4">
          {settingsQuery.isError ? (
            <EmptyState
              variant="error"
              message="Impossible de charger les conditions de la licence et les CGU."
              actionLabel="Réessayer"
              onAction={() => void settingsQuery.refetch()}
            />
          ) : settingsQuery.isLoading || !settingsQuery.data ? (
            <Loader loading variant="list" count={3} />
          ) : (
            <>
              <div className="rounded-md bg-surface-muted p-3">
                <p className="text-base font-semibold text-text">
                  Licence d'essai gratuite de {settingsQuery.data.trial_duration_days} jours
                </p>
                <p className="mt-1 text-sm text-text">
                  Elle démarre dès la création du club. À son terme, le club garde un accès
                  complet pendant {settingsQuery.data.grace_period_days} jours. Ensuite, il passe
                  en lecture seule : vos données restent consultables et exportables. Vous serez
                  prévenu avant l'échéance.
                </p>
                <p className="mt-1 text-xs text-text-muted">
                  Pour continuer au-delà de l'essai, ou si le support Vesta vous a déjà accordé une
                  licence, le support l'activera sur votre club après sa création.
                </p>
              </div>

              <div className="rounded-md border border-border p-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-text">Votre club</p>
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="inline-flex min-h-control-sm items-center text-xs font-medium text-primary-text hover:underline"
                  >
                    Modifier
                  </button>
                </div>
                <p className="mt-1 text-sm text-text">{step1.name || "—"}</p>
                <p className="text-xs text-text-muted">
                  {step1.city}, {step1.country}
                </p>
                <p className="text-xs text-text-muted">Devise : {step1.currency}</p>
                <p className="text-xs text-text-muted">Fuseau : {step1.timezone || "—"}</p>
              </div>

              <div className="rounded-md border border-border p-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-text">Votre fiche joueur</p>
                  <button
                    type="button"
                    onClick={() => setStep(2)}
                    className="inline-flex min-h-control-sm items-center text-xs font-medium text-primary-text hover:underline"
                  >
                    Modifier
                  </button>
                </div>
                <p className="mt-1 text-sm text-text">
                  {step2.firstName} {step2.lastName}
                </p>
                <p className="text-xs text-text-muted">{step2.email}</p>
                <p className="text-xs text-text-muted">
                  {POSITION_OPTIONS.find((p) => p.value === step2.position)?.label ?? "—"} · n°{" "}
                  {step2.jerseyNumber || "Sans numéro"}
                </p>
                <p className="text-xs text-text-muted">Rôle : Président</p>
              </div>

              {termsVersion ? (
                <>
                  {submitError ? <Banner variant="danger">{submitError}</Banner> : null}
                  <Checkbox
                    checked={acceptTerms}
                    onChange={(v) => {
                      setAcceptTerms(v);
                      setTermsError(null);
                    }}
                    error={termsError ?? undefined}
                    label={`J'accepte les conditions générales d'utilisation et la politique de confidentialité de Vesta (version ${termsVersion.version_number}).`}
                  />
                </>
              ) : (
                <Banner
                  variant="danger"
                  action={
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={settingsQuery.isFetching}
                      onClick={() => void settingsQuery.refetch()}
                    >
                      Réessayer
                    </Button>
                  }
                >
                  {TERMS_UNAVAILABLE_MESSAGE}
                </Banner>
              )}
            </>
          )}
        </div>
      ) : null}

      <div className="sticky -bottom-4 z-20 -mx-4 -mb-4 mt-6 flex items-center justify-between gap-2 border-t border-border bg-surface px-4 py-3">
        <Button variant="secondary" onClick={onClose} disabled={submitting}>
          Annuler
        </Button>
        <div className="flex gap-2">
          {step > 1 ? (
            <Button variant="secondary" onClick={() => setStep((s) => ((s - 1) as 1 | 2))} disabled={submitting}>
              Précédent
            </Button>
          ) : null}
          {step < 3 ? (
            <Button variant="primary" onClick={goNext}>
              Suivant
            </Button>
          ) : (
            <Button
              variant="primary"
              loading={submitting}
              loadingLabel="Création du club…"
              disabled={!settingsQuery.data || settingsQuery.isError || !termsVersion}
              onClick={() => void handleSubmit()}
            >
              Créer mon club
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
