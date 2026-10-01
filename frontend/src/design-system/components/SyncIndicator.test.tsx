import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SyncIndicator } from "./SyncIndicator";

describe("SyncIndicator", () => {
  it("ne s'affiche pas en ligne sans action en attente", () => {
    const { container } = render(<SyncIndicator isOnline pendingCount={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("signale le hors connexion", () => {
    render(<SyncIndicator isOnline={false} pendingCount={0} />);
    expect(screen.getByRole("status")).toHaveTextContent("Hors connexion");
  });

  it("affiche le nombre d'actions en attente et permet de réessayer", () => {
    const onRetry = vi.fn();
    render(<SyncIndicator isOnline pendingCount={2} onRetry={onRetry} />);
    expect(screen.getByRole("status")).toHaveTextContent("2 actions en attente d'envoi");
    screen.getByRole("button", { name: "Réessayer" }).click();
    expect(onRetry).toHaveBeenCalled();
  });
});
