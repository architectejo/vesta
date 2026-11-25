import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { KpiTile } from "./KpiTile";

describe("KpiTile", () => {
  it("affiche libellé, valeur et indice", () => {
    render(<KpiTile label="Taux de recouvrement" value="82 %" hint="Types obligatoires" />);
    expect(screen.getByText("Taux de recouvrement")).toBeInTheDocument();
    expect(screen.getByText("82 %")).toBeInTheDocument();
    expect(screen.getByText("Types obligatoires")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("écrit le statut en toutes lettres à côté de la pastille", () => {
    render(<KpiTile label="Suspendus" value={2} family="suspended" statusLabel="À surveiller" />);
    expect(screen.getByText("À surveiller")).toBeInTheDocument();
  });

  it("devient un bouton cliquable au clavier avec onClick", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<KpiTile label="Caisse" value="860 $" onClick={onClick} />);
    const button = screen.getByRole("button", { name: /Caisse/ });
    await user.click(button);
    button.focus();
    await user.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it("accepte une valeur nulle", () => {
    render(<KpiTile label="Dépenses" value={0} />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});
