import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import { RecordMovementModal } from "./RecordMovementModal";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn(), searchActiveClubPlayers: vi.fn().mockResolvedValue([]) };
});
vi.mock("../../api/treasury", async () => {
  const actual = await vi.importActual<typeof import("../../api/treasury")>("../../api/treasury");
  return { ...actual, getExpenses: vi.fn() };
});

import { getMyProfile } from "../../api/clubs";
import { getExpenses } from "../../api/treasury";

describe("RecordMovementModal - accès aux dépenses", () => {
  it("ne sonde pas treasury/expenses/ pour l'Intendant (accès déduit du rôle)", async () => {
    vi.mocked(getMyProfile).mockResolvedValue({ roles: [{ role: "steward", label: "Intendant" }] } as unknown as MyProfile);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <RecordMovementModal open onClose={() => {}} onSaved={() => {}} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(getMyProfile).toHaveBeenCalled());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(getExpenses).not.toHaveBeenCalled();
  });
});
