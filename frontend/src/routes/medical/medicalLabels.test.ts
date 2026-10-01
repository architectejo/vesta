import { describe, expect, it } from "vitest";
import {
  fitnessReturnText,
  fitnessStatusKey,
  injuryEventLabel,
  injuryStatusKey,
  injuryStatusLabel,
} from "./medicalLabels";

describe("fitnessStatusKey", () => {
  it("mappe chaque statut d'aptitude sur la bonne clé de badge", () => {
    expect(fitnessStatusKey("fit")).toBe("fit");
    expect(fitnessStatusKey("fit_with_restriction")).toBe("fit_restricted");
    expect(fitnessStatusKey("unfit")).toBe("unfit");
  });
});

describe("injuryStatusKey / injuryStatusLabel", () => {
  it("« À compléter » pour une blessure ouverte non complétée par le Médecin", () => {
    const item = { status: "open" as const, doctor_completed: false };
    expect(injuryStatusKey(item)).toBe("medical_injury_to_complete");
    expect(injuryStatusLabel(item)).toBe("À compléter");
  });

  it("« En cours » pour une blessure ouverte déjà complétée", () => {
    const item = { status: "open" as const, doctor_completed: true };
    expect(injuryStatusKey(item)).toBe("medical_injury_open");
    expect(injuryStatusLabel(item)).toBe("En cours");
  });

  it("« Retour déclaré » pour une blessure résolue", () => {
    const item = { status: "resolved" as const, doctor_completed: true };
    expect(injuryStatusKey(item)).toBe("medical_injury_resolved");
    expect(injuryStatusLabel(item)).toBe("Retour déclaré");
  });
});

describe("fitnessReturnText (medical.md §2.4, §3.2, §4.2, §4.4)", () => {
  it("ne renvoie rien pour un joueur apte", () => {
    expect(fitnessReturnText({ fitness_status: "fit", fitness_return_date: null })).toBe("");
  });

  it("« Date de retour non fixée » si inapte sans date", () => {
    expect(fitnessReturnText({ fitness_status: "unfit", fitness_return_date: null })).toBe(
      "Date de retour non fixée",
    );
  });

  it("« Retour prévu le {date} » à partir du libellé déjà fourni par l'API", () => {
    expect(
      fitnessReturnText({
        fitness_status: "unfit",
        fitness_return_date: "2099-01-01",
        fitness_return_date_label: "jeu. 1 janv. 2099",
      }),
    ).toBe("Retour prévu le jeu. 1 janv. 2099");
  });

  it("ajoute « · dépassé » seulement si demandé et la date est passée", () => {
    const params = {
      fitness_status: "unfit" as const,
      fitness_return_date: "2020-01-01",
      fitness_return_date_label: "mer. 1 janv. 2020",
    };
    expect(fitnessReturnText(params)).toBe("Retour prévu le mer. 1 janv. 2020");
    expect(fitnessReturnText({ ...params, showOverdue: true })).toBe(
      "Retour prévu le mer. 1 janv. 2020 · dépassé",
    );
  });
});

describe("injuryEventLabel (gap signalé au compte rendu : event_label absent de l'API)", () => {
  it("« Hors séance ou match » sans évènement", () => {
    expect(injuryEventLabel({ event_id: null })).toBe("Hors séance ou match");
  });

  it("libellé générique tant que l'API ne renvoie pas event_label", () => {
    expect(injuryEventLabel({ event_id: 42 })).toBe("Séance ou match du club");
  });

  it("utilise event_label dès qu'il est fourni par l'API", () => {
    expect(injuryEventLabel({ event_id: 42, event_label: "Séance du 12 oct. 2026" })).toBe(
      "Séance du 12 oct. 2026",
    );
  });
});
