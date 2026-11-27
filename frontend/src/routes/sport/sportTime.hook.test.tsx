import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

import { getMyProfile } from "../../api/clubs";
import { formatTime, useClubTimeZone } from "./sportTime";

function profileWith(timezone: string | null | undefined): MyProfile {
  const club: MyProfile["club"] = {
    id: 1,
    slug: "club-test",
    name: "Club de test",
    logo: null,
    primary_color: "#000000",
    secondary_color: "#ffffff",
  };
  if (timezone !== undefined) club.timezone = timezone;
  return { membership_id: 1, club } as MyProfile;
}

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    client,
    wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  };
}

describe("useClubTimeZone (club.timezone de GET /clubs/profile/me/)", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renvoie le fuseau du club quand l'API le fournit", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(profileWith("Africa/Kinshasa"));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useClubTimeZone(), { wrapper });
    await waitFor(() => expect(result.current).toBe("Africa/Kinshasa"));
  });

  it("timezone null : repli sur le fuseau du téléphone (undefined), sans planter", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(profileWith(null));
    const { wrapper, client } = makeWrapper();
    const { result } = renderHook(() => useClubTimeZone(), { wrapper });
    await waitFor(() => expect(client.getQueryState(["profile", "me"])?.status).toBe("success"));
    expect(result.current).toBeUndefined();
    // Les formateurs acceptent ce repli : heure du téléphone.
    expect(formatTime("2026-11-26T14:05:00Z", result.current)).toMatch(/^\d{2}:\d{2}$/);
  });

  it("timezone absent (ancienne réponse) : même repli", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(profileWith(undefined));
    const { wrapper, client } = makeWrapper();
    const { result } = renderHook(() => useClubTimeZone(), { wrapper });
    await waitFor(() => expect(client.getQueryState(["profile", "me"])?.status).toBe("success"));
    expect(result.current).toBeUndefined();
  });
});
