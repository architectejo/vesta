import { describe, expect, it } from "vitest";
import { assemblyCardStatus, assemblyTypeLabel, formatDateLong, formatTimeShort } from "./assembliesFormat";
import type { Assembly } from "../../../api/assemblies";

function makeAssembly(overrides: Partial<Assembly> = {}): Assembly {
  return {
    id: 1,
    assembly_type: "ordinary",
    scheduled_date: "2026-10-03",
    scheduled_time: "18:30:00",
    location: "Salle du club",
    status: "scheduled",
    created_at: "2026-09-01T00:00:00Z",
    agenda_items: [],
    decisions: [],
    quorum: { present: 0, total: 0, percentage: "0", threshold: "50", reached: false },
    minutes: null,
    can_manage: false,
    can_convene: false,
    can_sign_president: false,
    can_sign_vice_president: false,
    ...overrides,
  };
}

describe("assembliesFormat", () => {
  it("formatDateLong affiche une date longue en français", () => {
    expect(formatDateLong("2026-10-03")).toMatch(/octobre 2026/);
  });

  it("formatTimeShort tronque les secondes", () => {
    expect(formatTimeShort("18:30:00")).toBe("18:30");
  });

  it("assemblyTypeLabel traduit le type", () => {
    expect(assemblyTypeLabel("ordinary")).toBe("Ordinaire");
    expect(assemblyTypeLabel("extraordinary")).toBe("Extraordinaire");
  });

  it("assemblyCardStatus : « convened » pour une AG programmée", () => {
    expect(assemblyCardStatus(makeAssembly({ status: "scheduled" }))).toBe("convened");
  });

  it("assemblyCardStatus : « cancelled » pour une AG annulée", () => {
    expect(assemblyCardStatus(makeAssembly({ status: "cancelled" }))).toBe("cancelled");
  });

  it("assemblyCardStatus : « pv_to_sign » pour une AG tenue sans PV complet", () => {
    expect(assemblyCardStatus(makeAssembly({ status: "held", minutes: null }))).toBe("pv_to_sign");
  });

  it("assemblyCardStatus : « closed » quand le PV est complet", () => {
    const minutes = {
      content: "Texte",
      president_signed_by_name: "Amos",
      president_signed_at: "2026-10-04T10:00:00Z",
      vp_signed_by_name: "",
      vp_signed_at: null,
      vp_vacant_at_signature: true,
      is_complete: true,
      generated_at: "2026-10-04T10:05:00Z",
      pdf_url: "/assemblies/1/minutes/pdf/",
    };
    expect(assemblyCardStatus(makeAssembly({ status: "held", minutes }))).toBe("closed");
  });
});
