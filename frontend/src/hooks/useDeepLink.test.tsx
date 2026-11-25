import { render, screen } from "@testing-library/react";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { useDeepLink } from "./useDeepLink";

function Probe({ onId }: { onId: (id: number) => void }) {
  useDeepLink("paiement", onId);
  const [params] = useSearchParams();
  return <p>param:{params.get("paiement") ?? "aucun"}</p>;
}

describe("useDeepLink", () => {
  it("transmet l'identifiant puis retire le paramètre", async () => {
    const onId = vi.fn();
    render(
      <MemoryRouter initialEntries={["/?paiement=12"]}>
        <Probe onId={onId} />
      </MemoryRouter>,
    );
    expect(onId).toHaveBeenCalledWith(12);
    expect(await screen.findByText("param:aucun")).toBeInTheDocument();
  });

  it("ignore un identifiant invalide", () => {
    const onId = vi.fn();
    render(
      <MemoryRouter initialEntries={["/?paiement=abc"]}>
        <Probe onId={onId} />
      </MemoryRouter>,
    );
    expect(onId).not.toHaveBeenCalled();
  });
});
