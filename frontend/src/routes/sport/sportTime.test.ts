import { describe, expect, it } from "vitest";
import { formatTime } from "./sportTime";

describe("formatTime", () => {
  it("renvoie une chaîne vide sans heure", () => {
    expect(formatTime(null)).toBe("");
  });

  it("formate une heure ISO en HH:mm", () => {
    const iso = new Date(2026, 8, 27, 7, 42).toISOString();
    expect(formatTime(iso)).toMatch(/^\d{2}:\d{2}$/);
  });
});
