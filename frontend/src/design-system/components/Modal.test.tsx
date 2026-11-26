import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { Modal } from "./Modal";

/**
 * `Modal` garde un état partagé entre instances : chaque retour d'historique
 * demandé par le code (`goBackProgrammatically`) laisse un jeton en attente
 * jusqu'à l'arrivée de son `popstate`, ou 1 s au plus (filet de sécurité).
 * jsdom abandonne parfois ce retour : le jeton survit alors aux tests
 * précédents et avale le `popstate` du test suivant, qui est pris pour le
 * retour du code. Les tests qui simulent un vrai appui sur Retour attendent
 * donc l'expiration du filet pour partir d'un état propre.
 */
const PROGRAMMATIC_BACK_TTL_MS = 1000;
async function waitForProgrammaticBackExpiry(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, PROGRAMMATIC_BACK_TTL_MS + 150));
  });
}

describe("Modal", () => {
  it("n'affiche rien quand open est faux", () => {
    render(
      <Modal open={false} onClose={vi.fn()} title="Titre">
        Contenu
      </Modal>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("affiche le titre, le sous-titre et le contenu quand ouverte", () => {
    render(
      <Modal open onClose={vi.fn()} title="Ajouter un joueur" subtitle="Jean Kabila">
        <p>Corps de la modale</p>
      </Modal>,
    );
    expect(screen.getByRole("dialog", { name: "Ajouter un joueur" })).toBeInTheDocument();
    expect(screen.getByText("Jean Kabila")).toBeInTheDocument();
    expect(screen.getByText("Corps de la modale")).toBeInTheDocument();
  });

  it("ferme via la croix", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <Modal open onClose={onClose} title="Titre">
        Corps
      </Modal>,
    );
    await user.click(screen.getByRole("button", { name: "Fermer" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ferme via Échap", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Titre">
        Corps
      </Modal>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ferme via Échap quand le focus est DANS la modale (série 5 : cas réel, focus initial sur la croix)", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <Modal open onClose={onClose} title="Titre">
        <button type="button">Action</button>
      </Modal>,
    );
    screen.getByRole("button", { name: "Action" }).focus();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Échap dans une modale de niveau 2 ne ferme que celle-ci", async () => {
    const onCloseParent = vi.fn();
    const onCloseChild = vi.fn();
    const user = userEvent.setup();
    render(
      <Modal open onClose={onCloseParent} title="Parent">
        <Modal open onClose={onCloseChild} title="Enfant" level={2}>
          <button type="button">Dans l'enfant</button>
        </Modal>
      </Modal>,
    );
    screen.getByRole("button", { name: "Dans l'enfant" }).focus();
    await user.keyboard("{Escape}");
    expect(onCloseChild).toHaveBeenCalledTimes(1);
    expect(onCloseParent).not.toHaveBeenCalled();
  });

  it("Échap utilise le onClose du rendu courant, pas celui de l'ouverture", async () => {
    const first = vi.fn();
    const second = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <Modal open onClose={first} title="Titre">
        <button type="button">Action</button>
      </Modal>,
    );
    rerender(
      <Modal open onClose={second} title="Titre">
        <button type="button">Action</button>
      </Modal>,
    );
    screen.getByRole("button", { name: "Action" }).focus();
    await user.keyboard("{Escape}");
    expect(second).toHaveBeenCalledTimes(1);
    expect(first).not.toHaveBeenCalled();
  });

  it("ferme au clic sur le voile seulement si l'appui et le relâchement y ont lieu", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Titre">
        Corps
      </Modal>,
    );
    const overlay = screen.getByRole("dialog").previousSibling as HTMLElement;

    // Appui sur le voile puis relâché sur le voile : ferme.
    fireEvent.mouseDown(overlay, { target: overlay });
    fireEvent.mouseUp(overlay, { target: overlay });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("n'ouvre pas de fermeture sur simple clic à l'intérieur du panneau", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <Modal open onClose={onClose} title="Titre">
        <p>Corps</p>
      </Modal>,
    );
    await user.click(screen.getByText("Corps"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("affiche la confirmation d'abandon si isDirty et qu'on tente de fermer", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <Modal open onClose={onClose} title="Titre" isDirty>
        Corps
      </Modal>,
    );
    await user.click(screen.getByRole("button", { name: "Annuler" }));

    expect(screen.getByText("Abandonner les modifications ?")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Continuer la saisie" }));
    expect(screen.queryByText("Abandonner les modifications ?")).not.toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Annuler" }));
    await user.click(screen.getByRole("button", { name: "Abandonner" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("bloque toute fermeture pendant l'enregistrement (isSubmitting)", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Titre" isSubmitting>
        Corps
      </Modal>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Fermer" })).toBeDisabled();
  });

  it("modale bloquante : pas de croix, Échap inactif", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Mot de passe" blocking>
        Corps
      </Modal>,
    );
    expect(screen.queryByRole("button", { name: "Fermer" })).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Se déconnecter" })).toBeInTheDocument();
  });

  it("affiche un squelette pendant le chargement, sans le contenu", () => {
    render(
      <Modal open onClose={vi.fn()} title="Détail" loading>
        <p>Contenu réel</p>
      </Modal>,
    );
    expect(screen.queryByText("Contenu réel")).not.toBeInTheDocument();
  });

  it("affiche le pied par défaut avec Annuler et l'action principale", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <Modal
        open
        onClose={vi.fn()}
        title="Titre"
        onConfirm={onConfirm}
        confirmLabel="Encaisser"
      >
        Corps
      </Modal>,
    );
    expect(screen.getByRole("button", { name: "Annuler" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Encaisser" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("ferme la modale quand l'historique reçoit un popstate (retour Android)", async () => {
    await waitForProgrammaticBackExpiry();
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Titre">
        Corps
      </Modal>,
    );
    fireEvent.popState(window);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("Modal — historique (bouton Retour) et React StrictMode", () => {
  /** Laisse passer les popstate asynchrones de jsdom (history.back()). */
  async function flushHistory(): Promise<void> {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 80));
    });
  }

  // jsdom annule un history.back() en attente dès qu'un pushState suit
  // immédiatement (cas du double effet de StrictMode), alors que les
  // navigateurs le laissent aboutir et émettent bien le popstate. On reproduit
  // le comportement des navigateurs : chaque back() émet un popstate asynchrone.
  beforeAll(async () => {
    vi.spyOn(window.history, "back").mockImplementation(() => {
      setTimeout(() => window.dispatchEvent(new PopStateEvent("popstate")), 0);
    });
    // Jetons laissés en attente par les tests du bloc précédent (voir plus haut).
    await waitForProgrammaticBackExpiry();
  });
  afterAll(() => {
    vi.mocked(window.history.back).mockRestore();
  });

  beforeEach(async () => {
    await flushHistory();
  });

  it("reste ouverte sous StrictMode (le double effet ne la ferme pas)", async () => {
    const onClose = vi.fn();
    render(
      <StrictMode>
        <Modal open onClose={onClose} title="Créer un club">
          Corps
        </Modal>
      </StrictMode>,
    );
    await flushHistory();

    expect(screen.getByRole("dialog", { name: "Créer un club" })).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("sous StrictMode, un vrai retour du navigateur ferme quand même la modale", async () => {
    const onClose = vi.fn();
    render(
      <StrictMode>
        <Modal open onClose={onClose} title="Titre">
          Corps
        </Modal>
      </StrictMode>,
    );
    await flushHistory();
    expect(onClose).not.toHaveBeenCalled();

    act(() => {
      window.history.back();
    });
    await flushHistory();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("un vrai retour (history.back() hors du composant) ferme la modale", async () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Titre">
        Corps
      </Modal>,
    );
    await flushHistory();
    expect(onClose).not.toHaveBeenCalled();

    act(() => {
      window.history.back();
    });
    await flushHistory();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("fermer via le bouton appelle onClose une seule fois, même après le retour d'historique", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <Modal open onClose={onClose} title="Titre">
        Corps
      </Modal>,
    );
    await user.click(screen.getByRole("button", { name: "Annuler" }));
    expect(onClose).toHaveBeenCalledTimes(1);

    rerender(
      <Modal open={false} onClose={onClose} title="Titre">
        Corps
      </Modal>,
    );
    await flushHistory();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("une vraie navigation par-dessus la modale (démontage causé par un changement de route) ne dépile pas cette navigation", async () => {
    // Reproduit le bug : un bouton dans la modale appelle `navigate(...)`
    // (= un vrai `pushState` de react-router) sans fermer la modale
    // d'abord ; le changement de route démonte ensuite la modale, dont le
    // nettoyage ne doit pas confondre cette navigation réelle avec son
    // entrée factice et donc ne doit surtout pas appeler `history.back()`.
    const onClose = vi.fn();
    const { rerender } = render(
      <Modal open onClose={onClose} title="Titre">
        Corps
      </Modal>,
    );
    await flushHistory();
    // À ce stade, l'entrée factice de la modale est au sommet de
    // l'historique.
    expect((window.history.state as { vestaModal?: boolean } | null)?.vestaModal).toBe(true);
    // Le mock global de `back()` est partagé entre les tests de ce bloc
    // (aucun `clearMocks`) : on ne compte que les appels à partir d'ici.
    vi.mocked(window.history.back).mockClear();

    // Une vraie navigation a lieu par-dessus, comme le ferait react-router
    // lors d'un `navigate(...)` déclenché depuis un bouton de la modale.
    act(() => {
      window.history.pushState({ realNav: true }, "", "/plans/1/tableau");
    });
    expect((window.history.state as { realNav?: boolean } | null)?.realNav).toBe(true);

    // La page en dessous change de route : la modale se démonte sans être
    // passée par `onClose` (React ne le sait pas encore, le composant
    // parent a simplement cessé de la rendre).
    rerender(
      <Modal open={false} onClose={onClose} title="Titre">
        Corps
      </Modal>,
    );
    await flushHistory();

    // La navigation réelle ne doit pas avoir été dépilée : sans le
    // correctif, le nettoyage appelait `goBackProgrammatically()` ici et
    // `window.history.state` redevenait le marqueur de la modale.
    expect((window.history.state as { realNav?: boolean } | null)?.realNav).toBe(true);
    expect(window.history.back).not.toHaveBeenCalled();
  });

  it("fermer la modale de niveau 2 par un bouton ne ferme pas celle du dessous", async () => {
    const onCloseBase = vi.fn();
    const onCloseTop = vi.fn();
    function Stack({ topOpen }: { topOpen: boolean }) {
      return (
        <StrictMode>
          <Modal open onClose={onCloseBase} title="Formulaire">
            Corps
          </Modal>
          <Modal open={topOpen} onClose={onCloseTop} title="Confirmation" level={2}>
            Confirmer
          </Modal>
        </StrictMode>
      );
    }
    const { rerender } = render(<Stack topOpen />);
    await flushHistory();
    expect(screen.getAllByRole("dialog")).toHaveLength(2);

    rerender(<Stack topOpen={false} />);
    await flushHistory();

    // La modale de niveau 2 reste montée pendant son animation de fermeture
    // (design-system-icones-animations.md §2.2 : démontage différé).
    await waitFor(() => expect(screen.getAllByRole("dialog")).toHaveLength(1));
    expect(onCloseBase).not.toHaveBeenCalled();
    expect(onCloseTop).not.toHaveBeenCalled();
  });

  it("sous StrictMode, l'ouverture ne déclenche aucun retour d'historique (série 6 : retour à la page précédente)", async () => {
    // Le double effet de StrictMode faisait back() puis pushState() : le
    // navigateur revenait alors sur l'entrée de la page, et la fermeture
    // suivante ramenait à la page précédente.
    vi.mocked(window.history.back).mockClear();
    const pushSpy = vi.spyOn(window.history, "pushState");
    render(
      <StrictMode>
        <Modal open onClose={vi.fn()} title="Frais d'adhésion">
          Corps
        </Modal>
      </StrictMode>,
    );
    await flushHistory();

    expect(window.history.back).not.toHaveBeenCalled();
    expect(pushSpy.mock.calls.filter(([state]) => (state as { vestaModal?: boolean } | null)?.vestaModal)).toHaveLength(1);
    pushSpy.mockRestore();
  });

  it("une redirection juste après la fermeture (« Accéder à mon club ») n'est pas annulée par le retour différé", async () => {
    const { rerender } = render(
      <Modal open onClose={vi.fn()} title="Créer votre club">
        Corps
      </Modal>,
    );
    await flushHistory();
    vi.mocked(window.history.back).mockClear();

    act(() => {
      rerender(
        <Modal open={false} onClose={vi.fn()} title="Créer votre club">
          Corps
        </Modal>,
      );
    });
    // `<Navigate replace />` de la page de connexion, juste après le
    // démontage, avant que le retour différé ne parte.
    window.history.replaceState({ realNav: true }, "", "/");
    await flushHistory();

    expect(window.history.back).not.toHaveBeenCalled();
    expect((window.history.state as { realNav?: boolean } | null)?.realNav).toBe(true);
  });

  it("fermer ensemble deux modales empilées dépile leurs deux entrées en un seul retour", async () => {
    const goSpy = vi.spyOn(window.history, "go").mockImplementation(() => {
      setTimeout(() => window.dispatchEvent(new PopStateEvent("popstate")), 0);
    });
    function Stack({ open }: { open: boolean }) {
      return (
        <StrictMode>
          {open ? (
            <>
              <Modal open onClose={vi.fn()} title="Formulaire">
                Corps
              </Modal>
              <Modal open onClose={vi.fn()} title="Confirmation" level={2}>
                Confirmer
              </Modal>
            </>
          ) : null}
        </StrictMode>
      );
    }
    const { rerender } = render(<Stack open />);
    await flushHistory();
    vi.mocked(window.history.back).mockClear();

    rerender(<Stack open={false} />);
    await flushHistory();

    expect(goSpy).toHaveBeenCalledTimes(1);
    expect(goSpy).toHaveBeenCalledWith(-2);
    expect(window.history.back).not.toHaveBeenCalled();
    goSpy.mockRestore();
  });
});
