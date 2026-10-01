import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ContributionType } from "../../api/treasury";
import { ContributionTypeModal, contributionTypeError } from "./ContributionTypeModal";
import { ApiError } from "../../api/client";

const EXISTING: ContributionType = {
  id: 1,
  name: "Mensuelle",
  nature: "mandatory",
  amount: "20.00",
  periodicity: "monthly",
  due_day: 10,
  due_month: null,
  deadline: null,
  is_membership_fee: false,
  scope: "selected",
  status: "active",
  archived_at: null,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

function renderModal(props: Partial<React.ComponentProps<typeof ContributionTypeModal>> = {}) {
  const onSubmit = vi.fn();
  const onClose = vi.fn();
  render(
    <ContributionTypeModal
      open
      canEdit
      isSubmitting={false}
      onClose={onClose}
      onSubmit={onSubmit}
      {...props}
    />,
  );
  return { onSubmit, onClose };
}

describe("ContributionTypeModal", () => {
  it("exige un nom", async () => {
    const { onSubmit } = renderModal();
    await userEvent.setup().click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(screen.getByText("Ce champ est obligatoire.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("exige un montant supérieur à 0 pour une cotisation obligatoire, affiché sous le champ", async () => {
    const { onSubmit } = renderModal();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Nom"), "Mensuelle");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(screen.getByText("Saisissez un montant supérieur à 0.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("exige un jour d'échéance entre 1 et 28 pour une périodicité mensuelle", async () => {
    const { onSubmit } = renderModal();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Nom"), "Mensuelle");
    await user.type(screen.getByLabelText("Montant"), "20");
    await user.clear(screen.getByLabelText("Jour d'échéance"));
    await user.type(screen.getByLabelText("Jour d'échéance"), "31");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(screen.getByText("Saisissez un jour entre 1 et 28.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("n'exige pas de montant pour une cotisation libre et n'affiche pas d'échéance pour une ponctuelle", async () => {
    const { onSubmit } = renderModal();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Nom"), "Vestiaire");
    await user.click(screen.getByRole("button", { name: "Libre" }));
    await user.selectOptions(screen.getByLabelText("Périodicité"), "one_off");

    expect(screen.queryByLabelText("Jour d'échéance")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Montant suggéré/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "Vestiaire",
      nature: "free",
      amount: null,
      periodicity: "one_off",
      due_day: null,
      scope: "all",
    });
  });

  it("préremplit le formulaire depuis le type consulté et bloque le montant", () => {
    renderModal({ type: EXISTING });

    expect(screen.getByLabelText("Nom")).toHaveValue("Mensuelle");
    expect(screen.getByLabelText("Montant")).toBeDisabled();
    expect(screen.getByText("Le montant est conservé pour les échéances déjà générées.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Obligatoire" })).toHaveAttribute("aria-pressed", "true");
  });

  it("conserve le périmètre du type modifié à l'envoi", async () => {
    const { onSubmit } = renderModal({ type: EXISTING });
    await userEvent.setup().click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ scope: "selected", due_day: 10 }));
  });

  it("désactive les champs et masque « Enregistrer » sans droit d'écriture", () => {
    renderModal({ type: EXISTING, canEdit: false });

    expect(screen.getByLabelText("Nom")).toBeDisabled();
    expect(screen.getByLabelText("Périodicité")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Enregistrer" })).not.toBeInTheDocument();
  });

  it("affiche l'erreur d'enregistrement fournie par l'appelant", () => {
    renderModal({ submitError: "Un type portant ce nom existe déjà." });

    expect(screen.getByRole("alert")).toHaveTextContent("Un type portant ce nom existe déjà.");
  });

  it("appelle onClose avec « Annuler »", async () => {
    const { onClose } = renderModal();
    await userEvent.setup().click(screen.getByRole("button", { name: "Annuler" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("contributionTypeError", () => {
  it("renvoie le message de l'API", () => {
    expect(contributionTypeError(new ApiError(400, { detail: "Montant invalide." }))).toBe("Montant invalide.");
  });

  it("renvoie un message générique en français pour toute autre erreur", () => {
    expect(contributionTypeError(new Error("boom"))).toBe(
      "Une erreur est survenue de notre côté. Réessayez dans un instant.",
    );
  });
});
