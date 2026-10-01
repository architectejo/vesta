import { useState } from "react";
import {
  removeProfilePhoto,
  updateCredentials,
  updatePersonalInfo,
  updatePin,
  updateProfilePhoto,
} from "../../api/auth";
import type { MyProfile } from "../../api/clubs";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import {
  Avatar,
  Banner,
  Button,
  ConfirmDialog,
  Modal,
  PasswordField,
  Tabs,
  TextField,
  useToast,
} from "../../design-system";

type TabKey = "informations" | "identifiants" | "pin" | "photo";

const TAB_ITEMS: Array<{ value: TabKey; label: string }> = [
  { value: "informations", label: "Informations" },
  { value: "identifiants", label: "Identifiant et mot de passe" },
  { value: "pin", label: "Code PIN" },
  { value: "photo", label: "Photo" },
];

/**
 * Modale « Modifier mon profil » (comptes-mon-profil.md §4.1), 4 onglets,
 * un « Enregistrer » par onglet. Si l'API renvoie un 403 (par exemple
 * pendant l'état de changement de mot de passe forcé), le message renvoyé
 * par l'API est affiché tel quel, sans être masqué ni réécrit
 * (CLAUDE.md consigne explicite de la tâche).
 */
export function EditProfileModal({
  profile,
  onClose,
  onUpdated,
}: {
  profile: MyProfile;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const auth = useAuth();
  const { showToast } = useToast();
  const [tab, setTab] = useState<TabKey>("informations");

  // Onglet « Informations »
  const [firstName, setFirstName] = useState(profile.identity.first_name);
  const [lastName, setLastName] = useState(profile.identity.last_name);
  const [phone, setPhone] = useState(profile.identity.phone);
  const [birthDate, setBirthDate] = useState(profile.identity.birth_date ?? "");
  const [weightKg, setWeightKg] = useState(profile.identity.weight_kg ?? "");
  const [heightCm, setHeightCm] = useState(profile.identity.height_cm ?? "");
  const [infoErrors, setInfoErrors] = useState<Record<string, string>>({});
  const [infoGlobalError, setInfoGlobalError] = useState<string | null>(null);
  const [infoSubmitting, setInfoSubmitting] = useState(false);

  // Onglet « Identifiant et mot de passe »
  const [email, setEmail] = useState(profile.identity.email);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [credErrors, setCredErrors] = useState<Record<string, string>>({});
  const [credGlobalError, setCredGlobalError] = useState<string | null>(null);
  const [credSubmitting, setCredSubmitting] = useState(false);

  // Onglet « Code PIN »
  const [pinPassword, setPinPassword] = useState("");
  const [newPin, setNewPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [pinError, setPinError] = useState<string | null>(null);
  const [pinSubmitting, setPinSubmitting] = useState(false);

  // Onglet « Photo »
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(profile.identity.photo);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [photoSubmitting, setPhotoSubmitting] = useState(false);
  const [confirmRemoveOpen, setConfirmRemoveOpen] = useState(false);

  const isDirty =
    firstName !== profile.identity.first_name ||
    lastName !== profile.identity.last_name ||
    phone !== profile.identity.phone ||
    email !== profile.identity.email ||
    currentPassword !== "" ||
    newPassword !== "" ||
    pinPassword !== "" ||
    newPin !== "" ||
    photoFile !== null;

  function applyApiError(err: unknown, setGlobal: (m: string) => void, setFields?: (f: Record<string, string>) => void): void {
    if (err instanceof ApiError) {
      if (setFields && Object.keys(err.fields).length > 0) {
        const flat: Record<string, string> = {};
        for (const [k, v] of Object.entries(err.fields)) flat[k] = v[0] ?? "";
        setFields(flat);
      }
      setGlobal(err.detail);
    } else {
      setGlobal("Une erreur est survenue de notre côté. Réessayez dans un instant.");
    }
  }

  async function saveInformations(): Promise<void> {
    setInfoErrors({});
    setInfoGlobalError(null);
    if (!firstName.trim() || !lastName.trim()) {
      setInfoErrors({
        ...(firstName.trim() ? {} : { first_name: "Ce champ est obligatoire." }),
        ...(lastName.trim() ? {} : { last_name: "Ce champ est obligatoire." }),
      });
      return;
    }
    setInfoSubmitting(true);
    try {
      await updatePersonalInfo({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone: phone.trim(),
        birth_date: birthDate || null,
        weight_kg: weightKg === "" ? null : Number(weightKg),
        height_cm: heightCm === "" ? null : Number(heightCm),
      });
      showToast("Profil mis à jour.");
      onUpdated();
    } catch (err) {
      applyApiError(err, setInfoGlobalError, setInfoErrors);
    } finally {
      setInfoSubmitting(false);
    }
  }

  async function saveCredentials(): Promise<void> {
    setCredErrors({});
    setCredGlobalError(null);
    if (newPassword && newPassword !== confirmNewPassword) {
      setCredErrors({ confirm_new_password: "Les deux mots de passe ne correspondent pas." });
      return;
    }
    setCredSubmitting(true);
    try {
      await updateCredentials({
        email: email.trim(),
        current_password: currentPassword,
        new_password: newPassword,
        confirm_new_password: confirmNewPassword,
      });
      auth.updateEmail(email.trim());
      setCurrentPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
      showToast("Identifiants mis à jour.");
      onUpdated();
    } catch (err) {
      applyApiError(err, setCredGlobalError, setCredErrors);
    } finally {
      setCredSubmitting(false);
    }
  }

  async function savePin(): Promise<void> {
    setPinError(null);
    if (!/^\d{4,6}$/.test(newPin)) {
      setPinError("Le code PIN doit contenir 4 à 6 chiffres.");
      return;
    }
    if (newPin !== confirmPin) {
      setPinError("Les deux codes ne correspondent pas.");
      return;
    }
    setPinSubmitting(true);
    try {
      await updatePin({ current_password: pinPassword, new_pin: newPin, confirm_new_pin: confirmPin });
      setPinPassword("");
      setNewPin("");
      setConfirmPin("");
      showToast("Code PIN enregistré.");
    } catch (err) {
      setPinError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setPinSubmitting(false);
    }
  }

  async function savePhoto(): Promise<void> {
    if (!photoFile) return;
    setPhotoError(null);
    setPhotoSubmitting(true);
    try {
      await updateProfilePhoto(photoFile);
      showToast("Photo mise à jour.");
      setPhotoFile(null);
      onUpdated();
    } catch (err) {
      setPhotoError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setPhotoSubmitting(false);
    }
  }

  async function confirmRemovePhoto(): Promise<void> {
    setPhotoSubmitting(true);
    try {
      await removeProfilePhoto();
      setPhotoPreview(null);
      setConfirmRemoveOpen(false);
      showToast("Photo mise à jour.");
      onUpdated();
    } catch (err) {
      setPhotoError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setPhotoSubmitting(false);
    }
  }

  const footerByTab: Record<TabKey, { label: string; onSave: () => void; submitting: boolean }> = {
    informations: { label: "Enregistrer", onSave: () => void saveInformations(), submitting: infoSubmitting },
    identifiants: { label: "Enregistrer", onSave: () => void saveCredentials(), submitting: credSubmitting },
    pin: { label: "Enregistrer", onSave: () => void savePin(), submitting: pinSubmitting },
    photo: { label: "Enregistrer la photo", onSave: () => void savePhoto(), submitting: photoSubmitting },
  };
  const activeFooter = footerByTab[tab];

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title="Modifier mon profil"
        size="md"
        isDirty={isDirty}
        isSubmitting={activeFooter.submitting}
        confirmLabel={activeFooter.label}
        confirmLoadingLabel="Enregistrement…"
        confirmDisabled={tab === "photo" && !photoFile}
        onConfirm={activeFooter.onSave}
      >
        <div className="space-y-4">
          <Tabs items={TAB_ITEMS} value={tab} onChange={setTab} label="Modifier mon profil" />

          {tab === "informations" ? (
            <div className="space-y-4">
              {infoGlobalError ? <Banner variant="danger">{infoGlobalError}</Banner> : null}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <TextField
                  label="Prénom"
                  value={firstName}
                  onChange={setFirstName}
                  error={infoErrors.first_name}
                />
                <TextField
                  label="Nom"
                  value={lastName}
                  onChange={setLastName}
                  error={infoErrors.last_name}
                />
              </div>
              <TextField
                label="Téléphone (WhatsApp)"
                type="tel"
                optional
                value={phone}
                onChange={setPhone}
                error={infoErrors.phone}
              />
              <TextField
                label="Date de naissance"
                type="date"
                optional
                value={birthDate}
                onChange={setBirthDate}
                error={infoErrors.birth_date}
              />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <TextField
                  label="Poids (kg)"
                  type="number"
                  optional
                  value={String(weightKg)}
                  onChange={setWeightKg}
                  error={infoErrors.weight_kg}
                />
                <TextField
                  label="Taille (cm)"
                  type="number"
                  optional
                  value={String(heightCm)}
                  onChange={setHeightCm}
                  error={infoErrors.height_cm}
                />
              </div>
              <div>
                <p className="text-sm font-medium text-text">Poste, numéro</p>
                <p className="text-sm text-text-muted">
                  {profile.position_label || "Poste non renseigné"} · n°{" "}
                  {profile.jersey_number ?? "Sans numéro"}
                </p>
                <p className="text-xs text-text-muted">Modifiables par le Coach uniquement.</p>
              </div>
            </div>
          ) : null}

          {tab === "identifiants" ? (
            <div className="space-y-4">
              {credGlobalError ? <Banner variant="danger">{credGlobalError}</Banner> : null}
              <TextField
                label="Email (identifiant de connexion)"
                type="email"
                value={email}
                onChange={setEmail}
                error={credErrors.email}
              />
              <PasswordField
                label="Nouveau mot de passe"
                optional
                value={newPassword}
                onChange={setNewPassword}
                error={credErrors.new_password}
              />
              <PasswordField
                label="Confirmez le mot de passe"
                optional
                value={confirmNewPassword}
                onChange={setConfirmNewPassword}
                error={credErrors.confirm_new_password}
              />
              <PasswordField
                label="Mot de passe actuel"
                value={currentPassword}
                onChange={setCurrentPassword}
                error={credErrors.current_password}
              />
            </div>
          ) : null}

          {tab === "pin" ? (
            <div className="space-y-4">
              <p className="text-sm text-text-muted">
                Le code PIN confirme les actions sensibles : validation de paiement ou de dépense,
                signature, annulation.
              </p>
              {pinError ? <Banner variant="danger">{pinError}</Banner> : null}
              <PasswordField
                label="Mot de passe actuel"
                value={pinPassword}
                onChange={setPinPassword}
              />
              <TextField
                label="Nouveau code PIN"
                inputMode="numeric"
                type="password"
                value={newPin}
                onChange={(v) => setNewPin(v.replace(/\D/g, "").slice(0, 6))}
              />
              <TextField
                label="Confirmez le code"
                inputMode="numeric"
                type="password"
                value={confirmPin}
                onChange={(v) => setConfirmPin(v.replace(/\D/g, "").slice(0, 6))}
              />
            </div>
          ) : null}

          {tab === "photo" ? (
            <div className="flex flex-col items-center gap-3">
              {photoError ? <Banner variant="danger" className="w-full">{photoError}</Banner> : null}
              <Avatar
                name={`${profile.identity.first_name} ${profile.identity.last_name}`}
                photoUrl={photoFile ? URL.createObjectURL(photoFile) : photoPreview}
                size={72}
              />
              <div className="flex gap-2">
                <label>
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    id="edit-profile-photo-input"
                    onChange={(e) => setPhotoFile(e.target.files?.[0] ?? null)}
                  />
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => document.getElementById("edit-profile-photo-input")?.click()}
                  >
                    Choisir une photo
                  </Button>
                </label>
                {photoPreview ? (
                  <Button variant="ghost" size="sm" onClick={() => setConfirmRemoveOpen(true)}>
                    Retirer la photo
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmRemoveOpen}
        title="Retirer votre photo ?"
        description="Vos initiales seront affichées à la place."
        confirmLabel="Retirer"
        onConfirm={() => void confirmRemovePhoto()}
        onCancel={() => setConfirmRemoveOpen(false)}
        loading={photoSubmitting}
      />
    </>
  );
}
