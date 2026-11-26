import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { login } from "../../api/auth";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { Banner, Button, Footer, PasswordField, TextField } from "../../design-system";
import { ClubCreationWizard } from "../club-creation/ClubCreationWizard";
import { ForgotPasswordModal } from "./ForgotPasswordModal";

function sanitizeSuite(raw: string | null): string {
  if (!raw) return "";
  try {
    const decoded = decodeURIComponent(raw);
    // Chemins internes uniquement (comptes-connexion.md §2) : toute autre
    // valeur est ignorée et remplacée par « / ».
    return decoded.startsWith("/") && !decoded.startsWith("//") ? decoded : "";
  } catch {
    return "";
  }
}

/**
 * Écran de connexion (docs/ecrans/comptes-connexion.md). Couvre `/connexion`
 * (présentation neutre) et `/c/:slug` (identité du club).
 *
 * Point ouvert signalé au compte rendu : aucun point d'accès public ne
 * renvoie l'identité (logo/nom/couleurs) d'un club à partir de son
 * `slug` avant connexion (`backend/apps/clubs/urls.py` n'expose que
 * `public/creation-settings/`, jamais « club par slug »). La zone
 * d'identité de `/c/:slug` retombe donc systématiquement sur la
 * présentation neutre prévue par la spec pour ce cas précis (§5.1,
 * « Identité du club indisponible »), sans jamais inventer un appel.
 */
export function ConnexionPage() {
  const { slug } = useParams<{ slug?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const auth = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lockedUntil, setLockedUntil] = useState<string | null>(null);
  const [candidateClubs, setCandidateClubs] = useState<Array<{ slug: string; name: string }>>([]);
  const [submitting, setSubmitting] = useState(false);
  const [forgotOpen, setForgotOpen] = useState(false);
  const [creatingClub, setCreatingClub] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  // Destination décidée à la connexion : lue par la redirection « déjà connecté »
  // qui se déclenche dès que la session est ouverte (sinon elle enverrait « / »).
  const destinationRef = useRef<string | null>(null);

  useEffect(() => {
    function handleOnline() {
      setOnline(true);
    }
    function handleOffline() {
      setOnline(false);
    }
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  if (auth.status === "authenticated") {
    return <Navigate to={destinationRef.current ?? (auth.user?.is_superuser ? "/admin" : "/")} replace />;
  }

  async function attemptLogin(clubSlug?: string): Promise<void> {
    setError(null);
    setCandidateClubs([]);
    if (!email.trim()) {
      setError("Ce champ est obligatoire.");
      return;
    }
    if (!password) {
      setError("Ce champ est obligatoire.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await login({ email: email.trim(), password, club_slug: clubSlug ?? slug });
      const suite = sanitizeSuite(searchParams.get("suite"));
      // Une adresse de suite l'emporte toujours ; sinon la destination d'arrivée
      // est décidée par l'API (`default_landing`), jamais déduite d'un rôle ici.
      const landing = result.default_landing === "board_dashboard" ? "/tableau-de-bord" : "/";
      const destination = suite || (result.user.is_superuser ? "/admin" : landing);
      destinationRef.current = destination;
      auth.applySession(result);
      navigate(destination, { replace: true });
    } catch (err) {
      setPassword("");
      if (err instanceof ApiError) {
        const raw = err.raw as Record<string, unknown> | null;
        if (err.code === "account_locked") {
          setLockedUntil((raw?.locked_until as string) ?? null);
          setError(
            "Trop de tentatives. Pour protéger votre compte, la connexion est bloquée pendant 15 minutes.",
          );
        } else if (err.code === "invalid_credentials") {
          const remaining = raw?.attempts_remaining as number | undefined;
          setError(
            remaining != null && remaining <= 2
              ? `Email ou mot de passe incorrect. Encore ${remaining} essai(s) avant un blocage de 15 minutes.`
              : "Email ou mot de passe incorrect.",
          );
        } else if (err.code === "club_disambiguation_required") {
          const clubs = (raw?.clubs as Array<{ slug: string; name: string }>) ?? [];
          setCandidateClubs(clubs);
          setError(err.detail);
        } else if (err.status === 429) {
          setError("Trop de tentatives depuis cet appareil. Réessayez dans quelques minutes.");
        } else {
          setError(err.detail);
        }
      } else {
        setError("Une erreur est survenue de notre côté. Réessayez dans un instant.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  function openCreateClub(): void {
    setCreatingClub(true);
  }

  function closeCreateClub(): void {
    setCreatingClub(false);
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-[400px] flex-col px-3 pt-8 sm:pt-[10vh]">
      <div className="mb-4 text-center">
        <p className="text-lg font-semibold text-text">Vesta</p>
      </div>

      <div className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <h1 className="text-xl font-semibold text-text">Connexion</h1>
        <p className="mt-1 text-sm text-text-muted">Accédez à l'espace de votre club.</p>

        <form
          className="mt-4 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void attemptLogin();
          }}
        >
          {!online ? (
            <Banner variant="info">Vous êtes hors connexion. La connexion nécessite un réseau.</Banner>
          ) : null}
          {error ? <Banner variant="danger">{error}</Banner> : null}
          {candidateClubs.length > 0 ? (
            <div className="flex flex-col gap-2">
              {candidateClubs.map((club) => (
                <Button
                  key={club.slug}
                  type="button"
                  variant="secondary"
                  onClick={() => void attemptLogin(club.slug)}
                >
                  {club.name}
                </Button>
              ))}
            </div>
          ) : null}

          <TextField
            label="Email"
            type="email"
            autoComplete="username"
            inputMode="email"
            autoCapitalize="none"
            value={email}
            onChange={setEmail}
          />
          <PasswordField
            label="Mot de passe"
            autoComplete="current-password"
            value={password}
            onChange={setPassword}
          />

          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => setForgotOpen(true)}
              className="inline-flex min-h-control-sm items-center text-sm font-medium text-primary-text hover:underline"
            >
              Mot de passe oublié ?
            </button>
            <Button
              type="submit"
              variant="primary"
              loading={submitting}
              loadingLabel="Connexion…"
              disabled={!online || Boolean(lockedUntil)}
            >
              Se connecter
            </Button>
          </div>
          <p className="text-[13px] text-text-muted">
            Par sécurité, chaque onglet demande sa propre connexion.
          </p>
        </form>
      </div>

      {!slug ? (
        <div className="mt-4 text-center">
          <p className="text-sm text-text">Vous voulez inscrire votre équipe sur Vesta ?</p>
          <Button variant="secondary" size="sm" className="mt-2" onClick={openCreateClub}>
            Créer un club
          </Button>
        </div>
      ) : null}

      <Footer />

      {forgotOpen ? (
        <ForgotPasswordModal initialEmail={email} onClose={() => setForgotOpen(false)} />
      ) : null}
      {creatingClub ? <ClubCreationWizard onClose={closeCreateClub} /> : null}
    </div>
  );
}
