import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/assemblies", async () => {
  const actual = await vi.importActual<typeof import("../../../api/assemblies")>("../../../api/assemblies");
  return { ...actual, uploadArchivedDocument: vi.fn() };
});

import { uploadArchivedDocument } from "../../../api/assemblies";
import { ToastProvider } from "../../../design-system";
import { ArchiveUploadModal, validateArchiveFile } from "./ArchiveUploadModal";

function renderModal() {
  const onDone = vi.fn();
  render(
    <ToastProvider>
      <ArchiveUploadModal onClose={vi.fn()} onDone={onDone} />
    </ToastProvider>,
  );
  return onDone;
}

describe("validateArchiveFile", () => {
  it("accepte PDF et images, refuse les autres formats et les fichiers trop lourds", () => {
    expect(validateArchiveFile(new File(["x"], "a.pdf", { type: "application/pdf" }))).toBeNull();
    expect(validateArchiveFile(new File(["x"], "a.png", { type: "image/png" }))).toBeNull();
    expect(validateArchiveFile(new File(["x"], "a.docx", { type: "application/msword" }))).toBe(
      "Format non accepté : JPEG, PNG, WebP ou PDF.",
    );
    const big = new File(["x"], "big.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 11 * 1024 * 1024 });
    expect(validateArchiveFile(big)).toBe("Fichier trop lourd : 10 Mo maximum.");
  });
});

describe("ArchiveUploadModal", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("signale les champs obligatoires sans rien envoyer, la catégorie n'étant pas présélectionnée", async () => {
    renderModal();
    await userEvent.click(screen.getByRole("button", { name: "Déposer" }));
    expect(await screen.findByText("Ce champ est obligatoire.")).toBeInTheDocument();
    expect(screen.getByText("Choisissez une catégorie.")).toBeInTheDocument();
    expect(screen.getByText("Ajoutez le fichier du document.")).toBeInTheDocument();
    expect(uploadArchivedDocument).not.toHaveBeenCalled();
  });

  it("aligne la longueur maximale du titre sur l'API (160 caractères)", async () => {
    renderModal();
    const title = screen.getByLabelText("Titre") as HTMLInputElement;
    expect(title.maxLength).toBe(160);
    await userEvent.click(title);
    await userEvent.paste("a".repeat(170));
    expect(title.value).toHaveLength(160);
    expect(screen.getByText("160 / 160")).toBeInTheDocument();
  });

  it("refuse une date dans le futur", async () => {
    renderModal();
    await userEvent.type(screen.getByLabelText("Titre"), "Convocation AG");
    await userEvent.click(screen.getByRole("button", { name: "Convocation" }));
    const date = screen.getByLabelText("Date du document");
    await userEvent.clear(date);
    await userEvent.type(date, "2999-01-01");
    await userEvent.click(screen.getByRole("button", { name: "Déposer" }));
    expect(await screen.findByText("La date ne peut pas être dans le futur.")).toBeInTheDocument();
    expect(uploadArchivedDocument).not.toHaveBeenCalled();
  });

  it("envoie le document complet et signale la réussite", async () => {
    const created = { id: 9 } as Awaited<ReturnType<typeof uploadArchivedDocument>>;
    vi.mocked(uploadArchivedDocument).mockResolvedValue(created);
    const onDone = renderModal();
    await userEvent.type(screen.getByLabelText("Titre"), "PV du 4 octobre");
    await userEvent.click(screen.getByRole("button", { name: "PV de réunion" }));
    const file = new File(["pdf"], "pv.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText("Choisir un fichier", { selector: "input" }), file);
    expect(await screen.findByText("pv.pdf")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Déposer" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(created));
    expect(vi.mocked(uploadArchivedDocument).mock.calls[0]?.[0]).toMatchObject({
      category: "pv_reunion",
      title: "PV du 4 octobre",
      file,
    });
  });
});
